import { useId, useRef, useState } from 'react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';

type Target = 'memory' | 'user';
interface Memory { version: string; entries: string[]; limit: number }
interface Memories { available: boolean; memory: Memory; user: Memory }

const words = {
  fr: {
    title: 'Ma mémoire', intro: 'Consultez et corrigez ce que votre assistant retient pour vous. Ces éléments restent privés, y compris vis-à-vis de votre administrateur.',
    effect: 'Les modifications sont prises en compte dans les nouvelles conversations. Elles ne suppriment pas les messages de vos échanges passés.',
    memory: 'Mes notes de travail', user: 'Mes préférences et mon profil',
    entry: 'Élément', add: 'Ajouter un élément', remove: 'Retirer', clear: 'Tout retirer', save: 'Enregistrer', reload: 'Recharger',
    empty: 'Aucun élément mémorisé ici.', loading: 'Chargement…', saving: 'Enregistrement…', saved: 'La mémoire active est enregistrée.',
    count: 'caractères', unavailable: 'AlpenData doit terminer la configuration de la mémoire de votre assistant.',
    busy: 'Votre assistant est en cours d’exécution. Attendez sa fin ou arrêtez-le dans le chat, puis rechargez la mémoire.',
    changed: 'La mémoire a changé depuis votre lecture. Rechargez sa version actuelle avant de continuer.',
    uncertain: 'L’enregistrement n’a pas pu être confirmé. Rechargez la mémoire pour vérifier son état avant de modifier à nouveau.',
    rejected: 'Un élément contient une instruction que la mémoire ne peut pas conserver. Reformulez-le comme une information ou retirez-le.',
    limit: 'Raccourcissez les éléments ou retirez-en pour respecter la capacité indiquée.',
    failed: 'La mémoire n’a pas pu être lue. Rechargez-la ; si le problème persiste, contactez AlpenData.',
  },
  en: {
    title: 'My memory', intro: 'Review and correct what your assistant remembers for you. These items remain private, including from your administrator.',
    effect: 'Changes apply to new conversations. They do not delete messages from your past conversations.',
    memory: 'My working notes', user: 'My preferences and profile',
    entry: 'Item', add: 'Add an item', remove: 'Remove', clear: 'Remove all', save: 'Save', reload: 'Reload',
    empty: 'No items remembered here.', loading: 'Loading…', saving: 'Saving…', saved: 'Your active memory has been saved.',
    count: 'characters', unavailable: 'AlpenData needs to finish configuring your assistant’s memory.',
    busy: 'Your assistant is running. Wait for it to finish or stop it in chat, then reload memory.',
    changed: 'Memory has changed since you read it. Reload its current version before continuing.',
    uncertain: 'The save could not be confirmed. Reload memory to check its state before making another change.',
    rejected: 'An item contains an instruction that memory cannot retain. Rephrase it as information or remove it.',
    limit: 'Shorten or remove items to stay within the displayed capacity.',
    failed: 'Memory could not be read. Reload it; if the issue persists, contact AlpenData.',
  },
};

function errorText(error: unknown, language: Language, saving = false) {
  const t = words[language];
  const codes: Record<string, string> = { agent_already_running: t.busy, memory_changed: t.changed,
    memory_limit_exceeded: t.limit, memory_content_rejected: t.rejected, memory_not_configured: t.unavailable };
  return error instanceof ApiError && codes[error.code] || (saving ? t.uncertain : t.failed);
}

function MemoryGroup({ target, value, path, language, accept }: { target: Target; value: Memory; path: string; language: Language; accept: (target: Target, value: Memory) => void }) {
  const t = words[language], id = useId();
  const [entries, setEntries] = useState(value.entries), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const [recovery, setRecovery] = useState(false), [saved, setSaved] = useState(false);
  const sending = useRef(false);
  const content = entries.map(item => item.trim()).filter(Boolean);
  const count = [...content.join('\n§\n')].length, dirty = JSON.stringify(content) !== JSON.stringify(value.entries);
  function edit(next: string[]) { setEntries(next); setSaved(false); }
  async function act(save: boolean) {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(null); setSaved(false);
    try {
      const response = await api<Memories>(save ? path + '/' + target : path, save ? { version: value.version, entries: content } : undefined, save ? 'PUT' : 'GET');
      if (!response.available) throw new ApiError(503, 'memory_not_configured');
      setEntries(response[target].entries); setRecovery(false); setSaved(save); accept(target, response[target]);
    } catch (cause) {
      setError(cause);
      setRecovery(!(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500 || cause.code === 'memory_changed');
    } finally { sending.current = false; setBusy(false); }
  }
  return <section className="memory-group" aria-labelledby={id}>
    <h3 id={id}>{t[target]}</h3>
    <fieldset disabled={busy || recovery}>
      {!entries.length && <p>{t.empty}</p>}
      {entries.map((entry, index) => <div className="memory-entry" key={index}>
        <label htmlFor={id + index}>{t.entry} {index + 1}</label>
        <textarea id={id + index} rows={3} value={entry} maxLength={65536} onChange={event => edit(entries.map((item, i) => i === index ? event.target.value : item))} />
        <button className="text-button" type="button" aria-label={`${t.remove} ${t.entry.toLowerCase()} ${index + 1}`} onClick={() => edit(entries.filter((_item, i) => i !== index))}>{t.remove}</button>
      </div>)}
      <div className="memory-actions"><button className="secondary" type="button" onClick={() => edit([...entries, ''])}>{t.add}</button><button className="text-button" type="button" disabled={!entries.length} onClick={() => edit([])}>{t.clear}</button></div>
    </fieldset>
    <p className="subtle">{count} / {value.limit} {t.count}</p>
    {count > value.limit && <Notice>{t.limit}</Notice>}
    <Notice>{error ? errorText(error, language, true) : ''}</Notice>
    <Notice success>{saved ? t.saved : ''}</Notice>
    <div className="memory-actions"><button className="primary" disabled={busy || recovery || !dirty || count > value.limit} onClick={() => void act(true)}>{busy ? t.saving : t.save}</button><button className="secondary" disabled={busy} onClick={() => void act(false)}>{t.reload}</button></div>
  </section>;
}

export function PersonalMemory({ organizationId, language }: { organizationId: string; language: Language }) {
  const t = words[language], path = `/api/organizations/${organizationId}/memory`;
  const [data, setData] = useState<Memories | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const loading = useRef(false);
  async function load() {
    if (loading.current) return;
    loading.current = true; setBusy(true); setError(null);
    try { setData(await api<Memories>(path)); } catch (cause) { setError(cause); }
    finally { loading.current = false; setBusy(false); }
  }
  return <details className="personal-memory" onToggle={event => { if (event.currentTarget.open && !data && !error) void load(); }}>
    <summary>{t.title}</summary><p>{t.intro}</p><p>{t.effect}</p>
    {busy && <p role="status">{t.loading}</p>}
    {!!error && <><Notice>{errorText(error, language)}</Notice><button className="secondary" disabled={busy} onClick={() => void load()}>{t.reload}</button></>}
    {data && !data.available && <p>{t.unavailable}</p>}
    {data?.available && (['memory', 'user'] as const).map(target => <MemoryGroup key={target} target={target} value={data[target]} path={path} language={language} accept={(key, value) => setData(current => current && { ...current, [key]: value })} />)}
  </details>;
}
