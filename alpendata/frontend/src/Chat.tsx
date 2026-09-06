import { useEffect, useRef, useState } from 'react';
import { MessageSquare, Plus, Send, Square } from 'lucide-react';
import { api, ApiError } from './api';
import type { Language, Text } from './locale';
import { errorText } from './locale';
import { Notice } from './feedback';
import { RoutineCards, TrialEvidence } from './FirstTasks';
import type { Proposal, Trial } from './FirstTasks';
import { ScheduleActivation } from './Schedules';
import { Documents } from './Documents';
import type { DocumentReceipt } from './Documents';

type Conversation = { id: string; title: string; language: Language; created_at: number };
type Source = { kind: string; label: string; url: string | null };
type Turn = { artifacts?: DocumentReceipt[]; sources?: Source[]; id: string; request_id: string; sequence: number; message: string; response: string | null; status: string; error_code: string | null; cancel_requested: boolean };
type Detail = Conversation & { proposals?: Proposal[]; trials?: Trial[]; turns: Turn[]; next_after: number | null };
type Listing = { available: boolean; conversations: Conversation[]; next_offset: number | null };

const words = {
  fr: {
    title: 'Votre assistant personnel.', intro: 'Posez une question, retrouvez une information ou préparez votre prochain rendez-vous.',
    new: 'Nouvelle conversation', conversations: 'Mes conversations', empty: 'Commençons par votre travail.',
    emptyText: 'Créez une conversation et dites à votre assistant ce que vous souhaitez préparer.',
    private: 'Vos conversations et vos connexions restent personnelles.', unavailable: 'Le chat n’est pas encore activé. AlpenData doit terminer sa configuration.',
    message: 'Votre message', placeholder: 'Par exemple : prépare un briefing à partir de mes derniers e-mails.',
    send: 'Envoyer', retrySend: 'Réessayer l’envoi', sending: 'Envoi…', stop: 'Arrêter', stopping: 'Arrêt demandé…',
    you: 'Vous', assistant: 'AlpenData', queued: 'Votre demande est en attente.', running: 'Votre assistant travaille…',
    cancelled: 'Cette demande a été arrêtée.', interrupted: 'L’exécution a été interrompue. Elle n’a pas été relancée automatiquement.',
    failed: 'Votre assistant n’a pas pu terminer cette demande.', busy: 'Une demande est déjà en cours dans votre espace personnel.',
    changed: 'Le modèle a changé. Créez une nouvelle conversation pour continuer.', more: 'Afficher les conversations précédentes',
    recovery: 'Cette exécution nécessite une vérification par AlpenData avant de reprendre.',
    uncertain: 'La réception du message n’est pas confirmée. Réessayez : la même demande sera vérifiée, sans doublon.',
  },
  en: {
    title: 'Your personal assistant.', intro: 'Ask a question, find information or prepare your next meeting.',
    new: 'New conversation', conversations: 'My conversations', empty: 'Let’s start with your work.',
    emptyText: 'Create a conversation and tell your assistant what you would like to prepare.',
    private: 'Your conversations and connections stay personal.', unavailable: 'Chat is not enabled yet. AlpenData needs to finish its configuration.',
    message: 'Your message', placeholder: 'For example: prepare a briefing from my latest emails.',
    send: 'Send', retrySend: 'Retry sending', sending: 'Sending…', stop: 'Stop', stopping: 'Stop requested…',
    you: 'You', assistant: 'AlpenData', queued: 'Your request is waiting.', running: 'Your assistant is working…',
    cancelled: 'This request was stopped.', interrupted: 'Execution was interrupted. It was not restarted automatically.',
    failed: 'Your assistant could not finish this request.', busy: 'A request is already running in your personal workspace.',
    changed: 'The model has changed. Create a new conversation to continue.', more: 'Show earlier conversations',
    recovery: 'AlpenData needs to review this execution before it can resume.',
    uncertain: 'Receipt of the message is not confirmed. Retry to check the same request without duplicating it.',
  },
};

export function Chat({ organizationId, licensed, language, t, initialConversationId = '', onManage }: { onManage?: () => void; initialConversationId?: string; organizationId: string; licensed: boolean; language: Language; t: Text }) {
  const c = words[language], base = `/api/organizations/${organizationId}/chat`;
  const [listing, setListing] = useState<Listing | null>(null), [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null), [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null), [revision, setRevision] = useState(0);
  const [uncertain, setUncertain] = useState(false);
  const sending = useRef(false), pending = useRef<{ request_id: string; message: string } | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => {
    let active = true;
    api<Listing>(base).then(value => { if (active) { setListing(value); setSelected(initialConversationId || value.conversations[0]?.id || ''); } }).catch(cause => { if (active) setError(cause); });
    return () => { active = false; };
  }, [base, initialConversationId]);
  useEffect(() => {
    if (!selected) return;
    let active = true, timer: ReturnType<typeof setTimeout>;
    let previous: Detail | null = null;
    setDetail(null);
    async function refresh() {
      try {
        const after = previous?.turns.at(-1)?.sequence;
        let page = await api<Detail>(`${base}/conversations/${selected}${after ? `?after=${after - 1}` : ''}`);
        if (!active) return;
        const turns = new Map((previous?.turns || []).map(turn => [turn.sequence, turn]));
        page.turns.forEach(turn => turns.set(turn.sequence, turn));
        const first = page;
        while (page.next_after !== null) {
          page = await api<Detail>(`${base}/conversations/${selected}?after=${page.next_after}`);
          if (!active) return;
          page.turns.forEach(turn => turns.set(turn.sequence, turn));
        }
        previous = { ...first, turns: [...turns.values()].sort((a, b) => a.sequence - b.sequence), next_after: null };
        setDetail(previous);
        if (pending.current && previous.turns.some(turn => turn.request_id === pending.current?.request_id)) {
          pending.current = null; setUncertain(false); setDraft('');
        }
        const running = previous.turns.some(turn => ['queued', 'running'].includes(turn.status));
        timer = setTimeout(refresh, running ? 1500 : 10000);
      } catch (cause) {
        if (!active) return;
        setError(cause);
        if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) { setDetail(null); setListing(null); }
        else timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => { active = false; clearTimeout(timer); };
  }, [base, selected, revision]);

  async function action(work: () => Promise<void>) {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(null);
    try { await work(); } catch (cause) { if (alive.current) setError(cause); }
    finally { sending.current = false; if (alive.current) setBusy(false); }
  }
  async function send() {
    const request = pending.current || { request_id: crypto.randomUUID(), message: draft.trim() };
    if (!request.message || !selected) return;
    pending.current = request;
    try {
      await api(`${base}/conversations/${selected}/turns`, request);
      if (!alive.current) return;
      pending.current = null; setUncertain(false); setDraft(''); setRevision(value => value + 1);
    } catch (cause) {
      if (!pending.current) return;
      if (!(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500) setUncertain(true);
      else { pending.current = null; setUncertain(false); }
      throw cause;
    }
    const list = await api<Listing>(base);
    if (alive.current) setListing(list);
  }
  const running = detail?.turns.find(turn => ['queued', 'running'].includes(turn.status));
  const messages: Record<string, string> = { routine_sources_missing: language === 'fr' ? 'Les sources nécessaires n’ont pas été consultées. Vérifiez vos connexions.' : 'The required sources were not consulted. Check your connections.', routine_occurrence_expired: language === 'fr' ? 'Le créneau de cette occurrence est dépassé.' : 'This occurrence is past its execution window.', chat_not_configured: c.unavailable, agent_already_running: c.busy, chat_model_changed: c.changed, agent_recovery_required: c.recovery, onboarding_required: language === 'fr' ? 'Complétez votre profil dans « Mon espace » pour commencer.' : 'Complete your profile in “My workspace” to get started.' };
  const failureText = error instanceof ApiError ? messages[error.code] || errorText(error, t) : error ? errorText(error, t) : '';
  const labels: Record<string, string> = { queued: c.queued, running: c.running, cancelled: c.cancelled, interrupted: c.interrupted, failed: c.failed };
  return <section className="chat-page">
    <div className="page-heading"><span className="eyebrow">AlpenData</span><h1>{c.title}</h1><p>{c.intro}</p></div>
    <Notice>{failureText}</Notice>
    {listing && !listing.available && <p className="configuration-note">{c.unavailable}</p>}
    {!licensed && <Notice>{t.license}</Notice>}
    <div className="chat-layout">
      <aside className="conversation-list" aria-label={c.conversations}>
        <button className="secondary" disabled={!listing?.available || !licensed || busy || uncertain} onClick={() => action(async () => {
          const created = await api<Conversation>(base + '/conversations', { language });
          if (!alive.current) return;
          setListing(value => value && { ...value, conversations: [created, ...value.conversations] });
          setSelected(created.id); setDraft('');
        })}><Plus size={17} />{c.new}</button>
        {listing?.conversations.map(item => <button key={item.id} className={`conversation-link ${selected === item.id ? 'selected' : ''}`} aria-current={selected === item.id ? 'page' : undefined} disabled={busy || uncertain} onClick={() => { setSelected(item.id); setDraft(''); setError(null); }}><MessageSquare size={16} /><span>{item.title}</span></button>)}
        {listing?.next_offset !== null && listing?.next_offset !== undefined && <button className="text-button" disabled={busy} onClick={() => action(async () => {
          const next = await api<Listing>(`${base}?before=${listing.next_offset}`);
          if (alive.current) setListing(value => value && { ...next, conversations: [...value.conversations, ...next.conversations] });
        })}>{c.more}</button>}
        <p className="chat-privacy">{c.private}</p>
      </aside>
      <div className="chat-conversation">
        {selected && !detail ? <p role="status">{t.loading}</p> : !detail?.turns.length ? <div className="chat-empty"><MessageSquare size={32} /><h2>{c.empty}</h2><p>{c.emptyText}</p></div> : <div className="chat-messages" aria-label={c.conversations}>
          {detail.turns.map(turn => <div className="chat-turn" key={turn.id}>
            <article className="chat-message from-user"><strong>{c.you}</strong><p>{turn.message}</p></article>
            {turn.response !== null && <article className="chat-message from-assistant"><strong>{c.assistant}</strong><p>{turn.response}</p>{!!turn.sources?.length && <div className="chat-sources"><strong>{language === 'fr' ? 'Sources consultées' : 'Sources consulted'}</strong><ul>{turn.sources.map((source, index) => <li key={index}>{source.url && source.url.startsWith('https://') ? <a href={source.url} target="_blank" rel="noreferrer">{source.label || source.kind}</a> : <span>{source.label || source.kind}</span>}</li>)}</ul></div>}</article>}
            {turn.status !== 'completed' && <p className="chat-status" role="status">{turn.error_code ? messages[turn.error_code] || labels[turn.status] : labels[turn.status]}</p>}
            <Documents key={`${organizationId}/${turn.id}`} items={turn.artifacts || []} organizationId={organizationId} language={language} />
          </div>)}
        </div>}
        {!!detail?.proposals?.length && <RoutineCards key={selected} proposals={detail.proposals} organizationId={organizationId} language={language} disabled={busy || uncertain || !!running || !licensed || !listing?.available} onOpen={id => {
          setSelected(id); setDraft(''); setError(null);
          void api<Listing>(base).then(value => { if (alive.current) setListing(value); }).catch(cause => { if (alive.current) setError(cause); });
        }} />}
        <TrialEvidence trials={detail?.trials || []} language={language} />
        {detail?.trials?.map(trial => <ScheduleActivation key={trial.id} trial={trial} organizationId={organizationId} language={language} disabled={busy || !!running || !licensed} onManage={onManage} />)}
        {selected && <form className="chat-composer" onSubmit={event => { event.preventDefault(); void action(send); }}>
          {uncertain && <Notice>{c.uncertain}</Notice>}
          <label htmlFor="chat-message">{c.message}</label>
          <textarea id="chat-message" value={draft} onChange={event => setDraft(event.target.value)} rows={3} maxLength={32000} placeholder={c.placeholder} disabled={busy || uncertain || !licensed || !listing?.available} />
          <div className="chat-send-actions">
            {running && <button type="button" className="secondary" disabled={busy || running.cancel_requested} onClick={() => action(async () => {
              await api(`${base}/conversations/${selected}/turns/${running.id}/cancel`, {}); if (alive.current) setRevision(value => value + 1);
            })}><Square size={15} />{running.cancel_requested ? c.stopping : c.stop}</button>}
            <button className="primary" disabled={busy || !!running || !draft.trim() || !licensed || !listing?.available || !detail}><Send size={17} />{busy ? c.sending : uncertain ? c.retrySend : c.send}</button>
          </div>
        </form>}
      </div>
    </div>
  </section>;
}
