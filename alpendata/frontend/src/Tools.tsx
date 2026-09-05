import { useEffect, useState } from 'react';
import { CalendarDays, ExternalLink, FileSearch, Mail, PlugZap } from 'lucide-react';
import { api, ApiError } from './api';
import { Notice, useAction } from './feedback';
import { copy, errorText } from './locale';
import type { Language } from './locale';

type Capability = 'mail' | 'calendar' | 'files';
type Connection = { available: boolean; status: 'disconnected' | 'connected' | 'reconnect_required'; capabilities: Capability[] };
type MailItem = { id: string; subject: string; sender: string; preview: string; url: string | null };
type FileItem = { id: string; drive_id: string; name: string; url: string | null };
type EventItem = { id: string; subject: string; start: { dateTime: string; timeZone: string } | null; url: string | null };
const text = {
  fr: {
    title: 'Connectez vos outils Microsoft 365', choose: 'Que souhaitez-vous rendre accessible à votre assistant ?',
    mail: 'Mes mails', mailDetail: 'Lire vos échanges pour retrouver le contexte d’un client.',
    calendar: 'Mon calendrier', calendarDetail: 'Consulter vos rendez-vous à venir.',
    files: 'Mes documents et SharePoint', filesDetail: 'Rechercher dans les fichiers auxquels votre compte a accès, y compris les fichiers partagés.',
    reading: 'Ces accès permettent uniquement la lecture. Aucun mail ne sera envoyé et aucun document ne sera modifié.',
    permission: 'Utilisez le même compte que pour AlpenData. Selon les règles Microsoft de votre entreprise, une validation de votre administrateur Microsoft peut être nécessaire.',
    connect: 'Connecter mes outils', change: 'Modifier mes accès', disconnect: 'Déconnecter mes outils', connected: 'Vos outils sont connectés.',
    unavailable: 'La connexion aux outils n’est pas encore configurée dans cet environnement.', working: 'Chargement…',
    try: 'Vérifiez avec votre travail', tryText: 'Affichez vos données pour vérifier que les bons outils sont connectés.',
    showMail: 'Voir mes derniers mails', showCalendar: 'Voir mes prochains rendez-vous', search: 'Rechercher mes documents',
    query: 'Quel document recherchez-vous ?', placeholder: 'Ex. atelier leadership', noResults: 'Aucun résultat dans cette sélection.',
    open: 'Ouvrir dans Microsoft 365', untitled: 'Sans titre', upcoming: 'Les 7 prochains jours', recent: 'Vos 10 derniers mails',
  },
  en: {
    title: 'Connect your Microsoft 365 tools', choose: 'What would you like your assistant to access?',
    mail: 'My email', mailDetail: 'Read your conversations to find client context.',
    calendar: 'My calendar', calendarDetail: 'View your upcoming appointments.',
    files: 'My documents and SharePoint', filesDetail: 'Search files your account can access, including shared files.',
    reading: 'These permissions allow reading only. No email will be sent and no document will be changed.',
    permission: 'Use the same account as for AlpenData. Your company’s Microsoft policies may require approval from your Microsoft administrator.',
    connect: 'Connect my tools', change: 'Change my access', disconnect: 'Disconnect my tools', connected: 'Your tools are connected.',
    unavailable: 'Tool connections have not been configured in this environment yet.', working: 'Loading…',
    try: 'Check with your own work', tryText: 'View your data to check that the right tools are connected.',
    showMail: 'View my latest emails', showCalendar: 'View my upcoming appointments', search: 'Search my documents',
    query: 'Which document are you looking for?', placeholder: 'E.g. leadership workshop', noResults: 'No results in this selection.',
    open: 'Open in Microsoft 365', untitled: 'Untitled', upcoming: 'The next 7 days', recent: 'Your 10 latest emails',
  },
};

function SourceLink({ url, label }: { url: string | null; label: string }) {
  if (!url || !url.startsWith('https://')) return null;
  return <a href={url} target="_blank" rel="noopener noreferrer">{label}<ExternalLink size={14} aria-hidden="true" /></a>;
}

export function Tools({ companyId, language }: { companyId: string; language: Language }) {
  const t = copy[language], c = text[language], action = useAction(t);
  const base = `/api/organizations/${companyId}/microsoft`;
  const [connection, setConnection] = useState<Connection | null>(null), [loadError, setLoadError] = useState('');
  const [selected, setSelected] = useState<Capability[]>(['mail']), [query, setQuery] = useState('');
  const [messages, setMessages] = useState<MailItem[] | null>(null), [files, setFiles] = useState<FileItem[] | null>(null), [events, setEvents] = useState<EventItem[] | null>(null);
  useEffect(() => {
    let active = true;
    api<Connection>(base).then(value => { if (active) { setConnection(value); if (value.capabilities.length) setSelected(value.capabilities); } }).catch(error => { if (active) setLoadError(errorText(error, t)); });
    return () => { active = false; };
  }, [base]);
  const connected = connection?.status === 'connected';
  function clearResults() { setMessages(null); setFiles(null); setEvents(null); }
  async function read(operation: () => Promise<void>) {
    await action.run(async () => {
      try { await operation(); }
      catch (error) {
        if (error instanceof ApiError && error.code === 'microsoft_reconnect_required') {
          clearResults(); setConnection(current => current ? { ...current, status: 'reconnect_required', capabilities: [] } : current);
        }
        throw error;
      }
    });
  }
  const choices = [
    { id: 'mail' as const, title: c.mail, description: c.mailDetail, Icon: Mail },
    { id: 'calendar' as const, title: c.calendar, description: c.calendarDetail, Icon: CalendarDays },
    { id: 'files' as const, title: c.files, description: c.filesDetail, Icon: FileSearch },
  ];
  if (loadError) return <Notice>{loadError}</Notice>;
  if (!connection) return <p role="status">{t.loading}</p>;
  return <section className="tools-panel" aria-label={c.title}>
    <h2><PlugZap size={21} />{c.title}</h2>
    {connected && <Notice success>{c.connected}</Notice>}
    {connection.status === 'reconnect_required' && <Notice>{t.reconnect}</Notice>}
    <fieldset disabled={action.busy || !connection.available} className="tool-choices"><legend>{c.choose}</legend>
      {choices.map(({ id, title, description, Icon }) => <label className="tool-choice" key={id}>
        <input type="checkbox" checked={selected.includes(id)} onChange={event => setSelected(values => event.target.checked ? [...values, id] : values.filter(value => value !== id))} />
        <Icon size={20} aria-hidden="true" /><span><strong>{title}</strong><small>{description}</small></span>
      </label>)}
    </fieldset>
    <p className="subtle">{c.reading}</p><p className="subtle">{c.permission}</p>
    <div className="tool-actions"><button className="primary" disabled={action.busy || !connection.available || !selected.length} onClick={() => action.run(async () => {
      const result = await api<{ authorization_url: string }>(base + '/connect', { capabilities: selected });
      const url = new URL(result.authorization_url);
      if (url.origin !== 'https://login.microsoftonline.com') throw new Error('Unexpected identity provider');
      sessionStorage.setItem('alpendata.return-company', companyId); location.assign(url.href);
    })}>{action.busy ? c.working : connected ? c.change : c.connect}</button>
    {connection.status !== 'disconnected' && <button className="secondary" disabled={action.busy} onClick={() => action.run(async () => {
      await api(base, undefined, 'DELETE'); clearResults(); setConnection({ ...connection, status: 'disconnected', capabilities: [] });
    })}>{c.disconnect}</button>}</div>
    {!connection.available && <p className="configuration-note">{c.unavailable}</p>}
    <Notice>{action.error}</Notice>
    {connected && <div className="tool-preview"><h2>{c.try}</h2><p>{c.tryText}</p>
      <div className="tool-actions">
        {connection.capabilities.includes('mail') && <button className="secondary" disabled={action.busy} onClick={() => read(async () => setMessages((await api<{ messages: MailItem[] }>(base + '/mail')).messages))}><Mail size={17} />{c.showMail}</button>}
        {connection.capabilities.includes('calendar') && <button className="secondary" disabled={action.busy} onClick={() => read(async () => setEvents((await api<{ events: EventItem[] }>(base + '/calendar')).events))}><CalendarDays size={17} />{c.showCalendar}</button>}
      </div>
      {connection.capabilities.includes('files') && <form onSubmit={event => { event.preventDefault(); void read(async () => setFiles((await api<{ files: FileItem[] }>(base + '/files/search', { query })).files)); }}>
        <label htmlFor="document-query">{c.query}</label><input id="document-query" value={query} onChange={event => setQuery(event.target.value)} required maxLength={256} placeholder={c.placeholder} />
        <button className="secondary" disabled={action.busy || !query.trim()}><FileSearch size={17} />{c.search}</button>
      </form>}
      {messages && <section aria-label={c.recent} className="tool-results"><h3>{c.recent}</h3>{!messages.length && <p>{c.noResults}</p>}{messages.map(item => <article key={item.id}><h4>{item.subject || c.untitled}</h4><small>{item.sender}</small><p>{item.preview}</p><SourceLink url={item.url} label={c.open} /></article>)}</section>}
      {events && <section aria-label={c.upcoming} className="tool-results"><h3>{c.upcoming}</h3>{!events.length && <p>{c.noResults}</p>}{events.map(item => <article key={item.id}><h4>{item.subject || c.untitled}</h4>{item.start && <p>{item.start.dateTime.replace('T', ' ')} ({item.start.timeZone})</p>}<SourceLink url={item.url} label={c.open} /></article>)}</section>}
      {files && <section aria-label={c.files} className="tool-results"><h3>{c.files}</h3>{!files.length && <p>{c.noResults}</p>}{files.map(item => <article key={`${item.drive_id}:${item.id}`}><h4>{item.name || c.untitled}</h4><SourceLink url={item.url} label={c.open} /></article>)}</section>}
    </div>}
  </section>;
}
