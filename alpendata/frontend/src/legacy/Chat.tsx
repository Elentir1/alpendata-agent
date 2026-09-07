// Previous interface retained for a compatible UI rollback.
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowDown, ChevronDown, FileText, LockKeyhole, MessageSquare, PanelLeftClose, PanelLeftOpen, Plus, Search, Send, Sparkles, Square, X } from 'lucide-react';
import { api, ApiError } from '../api';
import type { Language, Text } from '../locale';
import { errorText } from '../locale';
import { Notice } from '../feedback';
import { RoutineCards, TrialEvidence } from '../FirstTasks';
import type { Proposal, Trial } from '../FirstTasks';
import { ScheduleActivation } from '../Schedules';
import { Documents } from '../Documents';
import { EmailDraft } from '../EmailDraft';
import type { EmailReceipt } from '../EmailDraft';
import type { DocumentReceipt } from '../Documents';
import { ChatResponse } from '../ChatResponse';
import { ActionCards, AgentWorkbench } from './AgentWorkbench';
import type { WorkbenchTab } from './AgentWorkbench';
import { ProjectPanel, ConversationOrganizer } from './ProjectPanel';
import type { Project } from './ProjectPanel';

type Conversation = { id: string; title: string; language: Language; created_at: number; project_id?: string | null; archived?: boolean; model?: string; tool_revision?: number };
type Source = { kind: string; label: string; url: string | null };
type Turn = { emails?: EmailReceipt[]; artifacts?: DocumentReceipt[]; sources?: Source[]; id: string; request_id: string; sequence: number; message: string; response: string | null; status: string; error_code: string | null; cancel_requested: boolean };
type Detail = Conversation & { proposals?: Proposal[]; trials?: Trial[]; turns: Turn[]; next_after: number | null };
type Listing = { available: boolean; model?: string; conversations: Conversation[]; next_offset: number | null };

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

export function Chat({ organizationId, licensed, language, t, initialConversationId = '', onManage, navigation, companyName }: { userId?: string; navigation?: ReactNode; companyName?: string; onManage?: () => void; initialConversationId?: string; organizationId: string; licensed: boolean; language: Language; t: Text }) {
  const c = words[language], base = `/api/organizations/${organizationId}/chat`;
  const [listing, setListing] = useState<Listing | null>(null), [selected, setSelected] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null), [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null), [revision, setRevision] = useState(0);
  const [uncertain, setUncertain] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(() => window.innerWidth > 760), [panel, setPanel] = useState<WorkbenchTab | null>(null);
  const [awayFromBottom, setAwayFromBottom] = useState(false);
  const transcript = useRef<HTMLDivElement>(null), composer = useRef<HTMLTextAreaElement>(null);
  const nextDraft = useRef(''), followBottom = useRef(true);
  const fr = language === 'fr';
  const [projects, setProjects] = useState<Project[]>([]), [project, setProject] = useState('');
  const [search, setSearch] = useState(''), [archived, setArchived] = useState(false), [listRevision, setListRevision] = useState(0);
  const filters = new URLSearchParams();
  if (project) filters.set('project', project);
  if (search.trim()) filters.set('q', search.trim());
  if (archived) filters.set('archived', 'true');
  const listUrl = base + (filters.size ? '?' + filters : '');
  const sending = useRef(false), pending = useRef<{ request_id: string; message: string } | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { setDraft(nextDraft.current); nextDraft.current = ''; followBottom.current = true; setAwayFromBottom(false); }, [selected]);
  useEffect(() => { if (followBottom.current && transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight; }, [detail]);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => api<Listing>(listUrl).then(value => { if (active) { setListing(value); setSelected(current => (search && current) || value.conversations.some(item => item.id === current) ? current : !project && !search && !archived && initialConversationId ? initialConversationId : value.conversations[0]?.id || ''); } }).catch(cause => { if (active) setError(cause); }), search ? 250 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [listUrl, initialConversationId, listRevision]);
  useEffect(() => {
    if (!selected) { setDetail(null); return; }
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
    const list = await api<Listing>(listUrl);
    if (alive.current) setListing(list);
  }
  async function createConversation(prompt = '') {
    const created = await api<Conversation>(base + '/conversations', { language, ...(project && project !== 'unfiled' ? { project_id: project } : {}) });
    if (!alive.current) return;
    nextDraft.current = prompt;
    setListing(value => value && { ...value, conversations: [created, ...value.conversations] });
    setSelected(created.id); setSearch(''); setArchived(false); setPanel(null);
    if (window.innerWidth <= 760) setSidebarOpen(false);
  }
  function prepare(prompt: string) {
    if (!selected || modelChanged || (detail?.tool_revision !== undefined && detail.tool_revision < 6)) { void action(() => createConversation(prompt)); return; }
    setDraft(value => value ? value + '\n\n' + prompt : prompt); setPanel(null); composer.current?.focus();
  }
  function openConversation(id: string) {
    setSelected(id); setDraft(''); setError(null); setPanel(null);
    setProject(''); setSearch(''); setArchived(false); setListRevision(value => value + 1);
  }
  const running = detail?.turns.find(turn => ['queued', 'running'].includes(turn.status));
  const modelChanged = !!detail?.model && !!listing?.model && detail.model !== listing.model;
  const messages: Record<string, string> = { routine_email_not_accepted: language === 'fr' ? 'L’envoi prévu n’a pas été confirmé comme accepté. Consultez son reçu avant toute autre action.' : 'The expected send was not confirmed as accepted. Review its receipt before taking further action.', routine_sources_missing: language === 'fr' ? 'Les sources nécessaires n’ont pas été consultées. Vérifiez vos connexions.' : 'The required sources were not consulted. Check your connections.', routine_occurrence_expired: language === 'fr' ? 'Le créneau de cette occurrence est dépassé.' : 'This occurrence is past its execution window.', chat_not_configured: c.unavailable, agent_already_running: c.busy, chat_model_changed: c.changed, agent_recovery_required: c.recovery, onboarding_required: language === 'fr' ? 'Complétez votre profil dans « Mon espace » pour commencer.' : 'Complete your profile in “My workspace” to get started.' };
  const failureText = error instanceof ApiError ? messages[error.code] || errorText(error, t) : error ? errorText(error, t) : '';
  const labels: Record<string, string> = { queued: c.queued, running: c.running, cancelled: c.cancelled, interrupted: c.interrupted, failed: c.failed };
  const documents = [...new Map((detail?.turns.flatMap(turn => turn.artifacts || []) || []).map(item => [item.id, item])).values()];
  const canPrepare = !!listing?.available && licensed && !busy && !uncertain && !running;
  const modelName = (detail?.model || listing?.model) === 'zai-glm-5-2' ? 'GLM 5.2' : detail?.model || listing?.model;
  const dateLabel = (timestamp: number) => {
    const date = new Date(timestamp * 1000), today = new Date();
    if (date.toDateString() === today.toDateString()) return fr ? 'Aujourd’hui' : 'Today';
    today.setDate(today.getDate() - 1);
    if (date.toDateString() === today.toDateString()) return fr ? 'Hier' : 'Yesterday';
    return new Intl.DateTimeFormat(language, { month: 'long', year: 'numeric' }).format(date);
  };
  return <section className={`chat-page ${sidebarOpen ? '' : 'history-collapsed'} ${panel ? 'workbench-open' : ''}`}>
    <aside id="conversation-sidebar" className="conversation-list" aria-label={c.conversations} inert={!sidebarOpen}>
      <div className="history-top"><span>{fr ? 'Votre espace de travail' : 'Your workspace'}</span><button className="icon-button" aria-label={fr ? 'Masquer les discussions' : 'Hide conversations'} onClick={() => setSidebarOpen(false)}><PanelLeftClose size={18} /></button></div>
      <button className="new-conversation" disabled={!listing?.available || !licensed || busy || uncertain} onClick={() => void action(() => createConversation())}><Plus size={18} />{c.new}</button>
      <div className="history-search"><Search size={16} /><label htmlFor="conversation-search" className="sr-only">{fr ? 'Rechercher une discussion' : 'Search conversations'}</label><input id="conversation-search" placeholder={fr ? 'Rechercher une discussion' : 'Search conversations'} value={search} onChange={event => setSearch(event.target.value)} maxLength={160} disabled={busy || uncertain} type="search" /></div>
      <div className="history-scroll">
        <ProjectPanel base={base} language={language} projects={projects} onProjects={setProjects} selected={project} onSelect={value => { setProject(value); setDraft(''); }} disabled={busy || uncertain || !licensed} onError={setError} />
        <div className="history-heading"><strong>{fr ? 'Discussions' : 'Conversations'}</strong><label className="archive-filter"><input type="checkbox" aria-label={fr ? 'Discussions archivées' : 'Archived conversations'} checked={archived} onChange={event => setArchived(event.target.checked)} disabled={busy || uncertain} /><span>{fr ? 'Archives' : 'Archive'}</span><span className="sr-only">{fr ? 'Discussions archivées' : 'Archived conversations'}</span></label></div>
        {listing?.conversations.map((item, index, all) => <div key={item.id}>
          {(index === 0 || dateLabel(all[index - 1].created_at) !== dateLabel(item.created_at)) && <p className="history-date">{dateLabel(item.created_at)}</p>}
          <button className={`conversation-link ${selected === item.id ? 'selected' : ''}`} aria-current={selected === item.id ? 'page' : undefined} disabled={busy || uncertain} onClick={() => { setSelected(item.id); setDraft(''); setError(null); if (window.matchMedia('(max-width: 760px)').matches) setSidebarOpen(false); }}><MessageSquare size={15} /><span>{item.title}</span></button>
        </div>)}
        {listing && !listing.conversations.length && <p className="history-empty">{search ? fr ? 'Aucune discussion trouvée.' : 'No conversations found.' : fr ? 'Vos discussions apparaîtront ici.' : 'Your conversations will appear here.'}</p>}
        {listing?.next_offset !== null && listing?.next_offset !== undefined && <button className="text-button" disabled={busy} onClick={() => action(async () => {
          const next = await api<Listing>(`${listUrl}${filters.size ? '&' : '?'}before=${listing.next_offset}`);
          if (alive.current) setListing(value => value && { ...next, conversations: [...value.conversations, ...next.conversations] });
        })}>{c.more}</button>}
      </div>
      <div className="history-bottom"><button className="workspace-shortcut" onClick={() => setPanel(panel ? null : 'actions')}><Sparkles size={17} /><span>{fr ? 'Explorer les capacités' : 'Explore capabilities'}</span></button>
        {navigation && <details className="workspace-menu"><summary><span className="company-monogram">{companyName?.slice(0, 1) || 'A'}</span><span>{companyName || 'AlpenData'}<small>{fr ? 'Compte et entreprise' : 'Account and company'}</small></span><ChevronDown size={15} /></summary><div>{navigation}</div></details>}
        <p className="chat-privacy"><LockKeyhole size={11} />{fr ? 'Espace personnel' : 'Personal workspace'}</p>
      </div>
    </aside>
    <div className="chat-conversation">
      <header className="conversation-topbar"><button className="icon-button" aria-label={fr ? 'Afficher les discussions' : 'Show conversations'} aria-expanded={sidebarOpen} aria-controls="conversation-sidebar" onClick={() => setSidebarOpen(value => !value)}><PanelLeftOpen size={19} /></button>
        <div className="conversation-heading">{detail ? <ConversationOrganizer key={detail.id} title={detail.title} projectId={detail.project_id} archived={detail.archived} projects={projects} language={language} disabled={busy || uncertain || !!running || !licensed} onSave={async value => action(async () => {
          const updated = await api<Conversation>(`${base}/conversations/${detail.id}`, value, 'PUT');
          if (!alive.current) return;
          setDetail(current => current && { ...current, ...updated }); setListRevision(value => value + 1);
        })} /> : <h1>{fr ? 'Assistant' : 'Assistant'}</h1>}<span className="model-label">{modelName || 'AlpenData'}{detail?.project_id && <> · {projects.find(item => item.id === detail.project_id)?.name}</>}</span></div>
        <div className="conversation-header-actions"><button className={panel === 'documents' ? 'selected' : ''} onClick={() => setPanel(panel === 'documents' ? null : 'documents')} aria-label={fr ? 'Livrables de la discussion' : 'Conversation deliverables'}><FileText size={17} /><span>{fr ? 'Livrables' : 'Deliverables'}</span>{documents.length > 0 && <b>{documents.length}</b>}</button><button className={panel === 'actions' ? 'selected' : ''} onClick={() => setPanel(panel ? null : 'actions')} aria-label={fr ? 'Ouvrir les capacités de l’agent' : 'Open agent capabilities'}><Sparkles size={17} /><span>{fr ? 'Capacités' : 'Capabilities'}</span></button></div>
      </header>
      <div className="conversation-notices"><Notice>{failureText}</Notice>{listing && !listing.available && <p className="configuration-note">{c.unavailable}</p>}{!licensed && <Notice>{t.license}</Notice>}{modelChanged && <p className="configuration-note">{c.changed}</p>}</div>
      <div className="transcript-scroll" ref={transcript} onScroll={event => { const el = event.currentTarget; followBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 100; setAwayFromBottom(!followBottom.current); }}>
        <div className="transcript-width">
          {selected && !detail ? <p role="status">{t.loading}</p> : !detail?.turns.length ? <div className="chat-empty"><div className="agent-mark"><Sparkles size={27} /></div><span className="eyebrow">{fr ? 'DU MESSAGE AU RÉSULTAT' : 'FROM MESSAGE TO RESULT'}</span><h2>{fr ? 'Qu’allons-nous accomplir ?' : 'What shall we accomplish?'}</h2><p>{fr ? 'Un document à produire, une décision à préparer, une méthode à transmettre. Votre agent s’en occupe avec vous.' : 'A document to create, a decision to prepare, a workflow to teach. Your agent works on it with you.'}</p><ActionCards language={language} disabled={!canPrepare} choose={prepare} compact /></div> : <div className="chat-messages" aria-label={c.conversations}>
            {detail.turns.map(turn => <div className="chat-turn" key={turn.id}>
              <article className="chat-message from-user"><strong className="sr-only">{c.you}</strong><p>{turn.message}</p></article>
              {turn.response !== null && <article className="chat-message from-assistant"><div className="assistant-signature"><Sparkles size={16} /><strong>{c.assistant}</strong></div><ChatResponse text={turn.response} language={language} />{!!turn.sources?.length && <details className="chat-sources"><summary>{fr ? 'Sources consultées' : 'Sources consulted'} · {turn.sources.length}</summary><ul>{turn.sources.map((source, index) => <li key={index}>{source.url && source.url.startsWith('https://') ? <a href={source.url} target="_blank" rel="noreferrer">{source.label || source.kind}</a> : <span>{source.label || source.kind}</span>}</li>)}</ul></details>}</article>}
              {turn.status !== 'completed' && <p className={`chat-status ${['queued', 'running'].includes(turn.status) ? 'is-working' : ''}`} role="status">{turn.error_code ? messages[turn.error_code] || labels[turn.status] : labels[turn.status]}</p>}
              {!!turn.artifacts?.length && <details className="turn-deliverables"><summary><FileText size={17} />{fr ? 'Documents créés' : 'Created documents'} · {turn.artifacts.length}<span>{turn.artifacts.map(item => item.filename).join(', ')}</span></summary><Documents key={`${organizationId}/${turn.id}`} items={turn.artifacts} organizationId={organizationId} language={language} /></details>}
              {(turn.emails || []).map(item => <EmailDraft key={`${organizationId}/${item.id}`} item={item} organizationId={organizationId} language={language} licensed={licensed} />)}
            </div>)}
          </div>}
          {!!detail?.proposals?.length && <RoutineCards key={selected} proposals={detail.proposals} organizationId={organizationId} language={language} disabled={busy || uncertain || !!running || !licensed || !listing?.available} onOpen={openConversation} />}
          <TrialEvidence trials={detail?.trials || []} language={language} />
          {detail?.trials?.map(trial => <ScheduleActivation key={trial.id} trial={trial} organizationId={organizationId} language={language} disabled={busy || !!running || !licensed} onManage={onManage} />)}
        </div>
      </div>
      <div className="composer-dock">
        {awayFromBottom && <button className="latest-message" onClick={() => { followBottom.current = true; transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: 'smooth' }); }}><ArrowDown size={15} />{fr ? 'Derniers messages' : 'Latest messages'}</button>}
        {selected ? <form className="chat-composer" onSubmit={event => { event.preventDefault(); followBottom.current = true; void action(send); }}>
          {uncertain && <Notice>{c.uncertain}</Notice>}
          <label htmlFor="chat-message" className="sr-only">{c.message}</label>
          <textarea id="chat-message" ref={composer} value={draft} onChange={event => { setDraft(event.target.value); event.target.style.height = 'auto'; event.target.style.height = Math.min(event.target.scrollHeight, 200) + 'px'; }} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !busy && !running && draft.trim() && licensed && listing?.available && detail && !modelChanged) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} rows={2} maxLength={32000} placeholder={fr ? 'Demandez à AlpenData de préparer, analyser, créer…' : 'Ask AlpenData to prepare, analyze, create…'} disabled={busy || uncertain || !licensed || !listing?.available || modelChanged} />
          <div className="chat-send-actions"><button type="button" className="composer-tools" onClick={() => setPanel(panel ? null : 'actions')}><Plus size={18} /><span>{fr ? 'Outils et méthodes' : 'Tools and workflows'}</span></button><span className="composer-key-hint">{fr ? 'Maj + Entrée pour une nouvelle ligne' : 'Shift + Enter for a new line'}</span>
            {running ? <button type="button" className="secondary" disabled={busy || running.cancel_requested} onClick={() => action(async () => {
              await api(`${base}/conversations/${selected}/turns/${running.id}/cancel`, {}); if (alive.current) setRevision(value => value + 1);
            })}><Square size={15} />{running.cancel_requested ? c.stopping : c.stop}</button> : <button className="primary send-button" disabled={busy || !draft.trim() || !licensed || !listing?.available || !detail || modelChanged} aria-label={busy ? c.sending : uncertain ? c.retrySend : c.send}><Send size={17} /><span>{busy ? c.sending : uncertain ? c.retrySend : c.send}</span></button>}
          </div>
        </form> : <button className="primary begin-chat" disabled={!canPrepare} onClick={() => void action(() => createConversation())}><Plus size={17} />{fr ? 'Commencer une discussion' : 'Start a conversation'}</button>}
        <p className="composer-note"><LockKeyhole size={11} />{c.private}</p>
      </div>
    </div>
    {panel && <AgentWorkbench tab={panel} setTab={setPanel} close={() => setPanel(null)} organizationId={organizationId} language={language} licensed={licensed} documents={documents} choose={prepare} disabled={!canPrepare} onOpen={openConversation} onManage={onManage} />}
    {sidebarOpen && <button className="history-backdrop" aria-label={fr ? 'Fermer les discussions' : 'Close conversations'} onClick={() => setSidebarOpen(false)}><X size={20} /></button>}
  </section>;
}
