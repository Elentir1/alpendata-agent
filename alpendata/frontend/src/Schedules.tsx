import { useEffect, useId, useRef, useState } from 'react';
import { CalendarClock, Pause, Play, Settings2, Trash2 } from 'lucide-react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language, Text } from './locale';
import type { Trial } from './FirstTasks';

type Cadence = { frequency: 'daily' | 'weekdays' | 'weekly'; local_time: string; timezone: string; weekday: number };
type Schedule = Cadence & { id: string; proposal_id: string; title: string; focus: string; capabilities: string[]; status: string; version: number; next_run_at: number | null; reason_code: string | null };
type Occurrence = { id: string; scheduled_for: number; status: string; error_code: string | null; conversation_id: string | null };
type History = { occurrences: Occurrence[]; next_before: number | null };
const initial: Cadence = { frequency: 'weekdays', local_time: '09:00', timezone: 'Europe/Zurich', weekday: 0 };

const words = {
  fr: {
    title: 'Vos automatisations.', intro: 'Vos tâches récurrentes, leurs prochains passages et leurs résultats personnels.',
    replace: 'Replanifier avec ce nouvel essai', retest: 'Refaire un essai', plan: 'Planifier cette tâche', activate: 'Activer la récurrence', manage: 'Gérer mes automatisations',
    reviewed: 'J’ai relu le résultat de l’essai et je souhaite répéter cette tâche.',
    frequency: 'Fréquence', daily: 'Tous les jours', weekdays: 'Du lundi au vendredi', weekly: 'Chaque semaine', day: 'Jour',
    days: ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'], time: 'Heure locale', timezone: 'Fuseau horaire',
    note: 'Le résultat sera disponible dans votre assistant. Aucun e-mail ne sera envoyé. Vous pourrez suspendre cette tâche à tout moment.',
    dst: 'Si l’heure choisie n’existe pas lors du passage à l’heure d’été, cette occurrence sera sautée. À l’heure d’hiver, elle ne sera exécutée qu’une fois.',
    next: 'Prochaine exécution', pause: 'Suspendre', resume: 'Reprendre', edit: 'Modifier l’horaire', save: 'Enregistrer l’horaire',
    remove: 'Retirer', confirmRemove: 'Retirer cette automatisation et arrêter ses prochaines exécutions ? Les résultats restent dans votre assistant.',
    cancel: 'Annuler', history: 'Dernières exécutions', result: 'Voir le résultat', empty: 'Testez une proposition dans votre assistant pour créer votre première automatisation.',
    noRuns: 'Aucune occurrence enregistrée pour le moment.', more: 'Afficher la suite', busy: 'Enregistrement…', loading: 'Chargement…',
    active: 'Active', paused: 'Suspendue', blocked: 'À vérifier', archived: 'Retirée', queued: 'En attente', running: 'En cours', completed: 'Terminée', failed: 'Échouée', cancelled: 'Arrêtée', interrupted: 'Interrompue', missed: 'Horaire dépassé · non exécutée',
    sources: 'Sources', mail: 'Messagerie', calendar: 'Agenda', files: 'Documents',
    generic: 'La demande n’a pas pu aboutir. Réessayez.', access: 'Reconnectez vos outils personnels avant de reprendre cette tâche.',
    revoked: 'Votre accès ou votre licence doit être réactivé avant de reprendre.', changed: 'Cette automatisation a changé. Rechargez sa configuration avant de réessayer.',
    model: 'Le modèle a changé. Un nouvel essai est nécessaire avant de planifier cette tâche.', repeated: 'Trois exécutions ont échoué. Vérifiez leurs résultats avant de reprendre.',
    trial: 'Terminez un essai avec les sources nécessaires, puis relisez son résultat.', exists: 'Cette tâche est déjà planifiée. Retrouvez-la dans vos automatisations.',
    uncertain: 'La réception n’est pas confirmée. Réessayez pour retrouver la même activation sans doublon.', retry: 'Réessayer l’activation',
  },
  en: {
    title: 'Your automations.', intro: 'Your recurring tasks, their next runs and your private results.',
    replace: 'Reschedule with this new trial', retest: 'Try again', plan: 'Schedule this task', activate: 'Activate recurrence', manage: 'Manage my automations',
    reviewed: 'I have reviewed the trial result and want to repeat this task.',
    frequency: 'Frequency', daily: 'Every day', weekdays: 'Monday to Friday', weekly: 'Every week', day: 'Day',
    days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], time: 'Local time', timezone: 'Time zone',
    note: 'The result will be available in your assistant. No email will be sent. You can pause this task at any time.',
    dst: 'If your chosen time does not exist at the spring clock change, that occurrence is skipped. At the autumn clock change, it runs only once.',
    next: 'Next run', pause: 'Pause', resume: 'Resume', edit: 'Edit schedule', save: 'Save schedule',
    remove: 'Remove', confirmRemove: 'Remove this automation and stop its upcoming runs? Results remain in your assistant.',
    cancel: 'Cancel', history: 'Recent runs', result: 'View result', empty: 'Try a proposal in your assistant to create your first automation.',
    noRuns: 'No occurrences recorded yet.', more: 'Show more', busy: 'Saving…', loading: 'Loading…',
    active: 'Active', paused: 'Paused', blocked: 'Needs attention', archived: 'Removed', queued: 'Waiting', running: 'Running', completed: 'Completed', failed: 'Failed', cancelled: 'Stopped', interrupted: 'Interrupted', missed: 'Time window passed · not run',
    sources: 'Sources', mail: 'Email', calendar: 'Calendar', files: 'Documents',
    generic: 'The request could not be completed. Try again.', access: 'Reconnect your personal tools before resuming this task.',
    revoked: 'Your access or license must be restored before resuming.', changed: 'This automation has changed. Reload its configuration before trying again.',
    model: 'The model has changed. Try this task again before scheduling it.', repeated: 'Three runs failed. Review their results before resuming.',
    trial: 'Complete a trial with the required sources, then review its result.', exists: 'This task is already scheduled. Find it in your automations.',
    uncertain: 'Receipt is not confirmed. Retry to find the same activation without duplicating it.', retry: 'Retry activation',
  },
};

function errorMessage(error: unknown, language: Language) {
  if (error instanceof ApiError && error.code === 'company_policy_denied') return language === 'fr' ? 'Les règles de votre entreprise bloquent un accès nécessaire. Contactez votre administrateur.' : 'Your company rules block a required access. Contact your administrator.';
  const c = words[language];
  const codes: Record<string, string> = { email_confirmation_required: language === 'fr' ? 'Votre choix exige désormais une confirmation des envois. Refaites un essai de cette tâche pour préparer une version adaptée.' : 'Your choice now requires send confirmation. Run a new trial to prepare an updated version of this task.', microsoft_reconnect_required: c.access, agent_access_revoked: c.revoked, routine_version_changed: c.changed, routine_request_conflict: c.changed, chat_model_changed: c.model, routine_trial_required: c.trial, routine_already_exists: c.exists, routine_repeated_failures: c.repeated };
  if (error instanceof ApiError && error.code === 'routine_sources_missing') return language === 'fr' ? 'Les sources nécessaires n’ont pas été consultées.' : 'The required sources were not consulted.';
  if (error instanceof ApiError && error.code === 'routine_occurrence_expired') return language === 'fr' ? 'Le créneau de cette occurrence est dépassé.' : 'This occurrence is past its execution window.';
  return error instanceof ApiError ? codes[error.code] || c.generic : c.generic;
}

function dateLabel(stamp: number, zone: string, language: Language) {
  return new Intl.DateTimeFormat(language === 'fr' ? 'fr-CH' : 'en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: zone }).format(new Date(stamp * 1000));
}

function CadenceFields({ value, onChange, language, disabled }: { value: Cadence; onChange: (value: Cadence) => void; language: Language; disabled: boolean }) {
  const id = useId(), c = words[language];
  const zones = ['Europe/Zurich', 'Europe/Paris', 'Europe/London', 'America/Toronto', 'America/New_York', 'UTC'];
  return <fieldset className="cadence-fields" disabled={disabled}>
    <div><label htmlFor={id + '-frequency'}>{c.frequency}</label><select id={id + '-frequency'} value={value.frequency} onChange={event => onChange({ ...value, frequency: event.target.value as Cadence['frequency'] })}>{(['daily', 'weekdays', 'weekly'] as const).map(key => <option key={key} value={key}>{c[key]}</option>)}</select></div>
    {value.frequency === 'weekly' && <div><label htmlFor={id + '-day'}>{c.day}</label><select id={id + '-day'} value={value.weekday} onChange={event => onChange({ ...value, weekday: Number(event.target.value) })}>{c.days.map((name, index) => <option key={name} value={index}>{name}</option>)}</select></div>}
    <div><label htmlFor={id + '-time'}>{c.time}</label><input id={id + '-time'} type="time" required value={value.local_time} onChange={event => onChange({ ...value, local_time: event.target.value })} /></div>
    <div><label htmlFor={id + '-zone'}>{c.timezone}</label><select id={id + '-zone'} value={value.timezone} onChange={event => onChange({ ...value, timezone: event.target.value })}>{[...new Set([...zones, value.timezone])].map(zone => <option key={zone} value={zone}>{zone === 'Europe/Zurich' ? language === 'fr' ? 'Suisse · Zurich' : 'Switzerland · Zurich' : zone.replaceAll('_', ' ')}</option>)}</select></div>
  </fieldset>;
}

export function ScheduleActivation({ trial, organizationId, language, disabled, onManage }: { trial: Trial; organizationId: string; language: Language; disabled: boolean; onManage?: () => void }) {
  const c = words[language], [open, setOpen] = useState(false), [reviewed, setReviewed] = useState(false), [cadence, setCadence] = useState<Cadence>(initial);
  const [saved, setSaved] = useState<Schedule | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const pending = useRef<(Cadence & { reviewed: true; reviewed_trial_id: string; request_id: string }) | null>(null), sending = useRef(false);
  if (trial.schedule_id && !trial.can_replace_schedule || saved) return <div className="schedule-activation">{saved?.next_run_at && <p>{c.next} : {dateLabel(saved.next_run_at, saved.timezone, language)} ({saved.timezone})</p>}{onManage && <button className="secondary" onClick={onManage}><CalendarClock size={17} />{c.manage}</button>}</div>;
  if (!trial.sources_verified) return null;
  return <section className="schedule-activation">
    {!open ? <button className="secondary" disabled={disabled} onClick={() => setOpen(true)}><CalendarClock size={17} />{trial.can_replace_schedule ? c.replace : c.plan}</button> : <form onSubmit={async event => {
      event.preventDefault(); if (sending.current) return; sending.current = true; setBusy(true); setError(null);
      const body = pending.current || { ...cadence, reviewed: true as const, reviewed_trial_id: trial.id, request_id: crypto.randomUUID() }; pending.current = body;
      try { setSaved(await api<Schedule>(`/api/organizations/${organizationId}/schedules`, body)); pending.current = null; }
      catch (cause) { if (cause instanceof ApiError && cause.status > 0 && cause.status < 500) pending.current = null; setError(cause); }
      finally { sending.current = false; setBusy(false); }
    }}>
      <h3>{c.plan}</h3><p>{c.note}</p><CadenceFields value={cadence} onChange={setCadence} language={language} disabled={busy || disabled || !!pending.current} />
      <p className="subtle">{c.dst}</p><label className="review-trial"><input type="checkbox" required checked={reviewed} disabled={busy || disabled || !!pending.current} onChange={event => setReviewed(event.target.checked)} /><span>{c.reviewed}</span></label>
      <Notice>{error ? pending.current ? c.uncertain : errorMessage(error, language) : ''}</Notice>
      <button className="primary" disabled={busy || disabled || !reviewed}>{busy ? c.busy : pending.current ? c.retry : c.activate}</button>
    </form>}
  </section>;
}

export function Schedules({ organizationId, licensed, language, t, onOpen }: { organizationId: string; licensed: boolean; language: Language; t: Text; onOpen: (id: string) => void }) {
  const c = words[language], base = `/api/organizations/${organizationId}/schedules`;
  const [rows, setRows] = useState<Schedule[] | null>(null), [next, setNext] = useState<number | null>(null), [error, setError] = useState<unknown>(null), [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<Schedule | null>(null), [draft, setDraft] = useState<Cadence>(initial), [removing, setRemoving] = useState('');
  const [historyId, setHistoryId] = useState(''), [history, setHistory] = useState<History | null>(null);
  const trialRequests = useRef(new Map<string, string>());
  const alive = useRef(true), working = useRef(false), listingPages = useRef(1), historyPages = useRef(1);
  async function refresh() {
    let data = await api<{ schedules: Schedule[]; next_offset: number | null }>(base);
    const combined = [...data.schedules];
    for (let page = 1; page < listingPages.current && data.next_offset !== null; page++) { data = await api(`${base}?before=${data.next_offset}`); combined.push(...data.schedules); }
    if (alive.current) { setRows(combined); setNext(data.next_offset); }
  }
  useEffect(() => { alive.current = true; let timer: ReturnType<typeof setTimeout>;
    async function poll() { try { await refresh(); } catch (cause) { if (alive.current) { setError(cause); if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) setRows(null); } } if (alive.current) timer = setTimeout(poll, 10000); }
    void poll(); return () => { alive.current = false; clearTimeout(timer); };
  }, [base]);
  useEffect(() => { if (!historyId) return; let active = true, timer: ReturnType<typeof setTimeout>; historyPages.current = 1; setHistory(null);
    async function poll() { try { let data = await api<History>(`${base}/${historyId}/occurrences`); const combined = [...data.occurrences];
      for (let page = 1; page < historyPages.current && data.next_before !== null; page++) { data = await api<History>(`${base}/${historyId}/occurrences?before=${data.next_before}`); combined.push(...data.occurrences); }
      if (active) setHistory({ ...data, occurrences: combined }); } catch (cause) { if (active) { setError(cause); setHistory(null); } } if (active) timer = setTimeout(poll, 10000); }
    void poll(); return () => { active = false; clearTimeout(timer); };
  }, [base, historyId]);
  async function action(work: () => Promise<void>) { if (working.current) return; working.current = true; setBusy(true); setError(null); try { await work(); if (alive.current) await refresh(); } catch (cause) { if (alive.current) setError(cause); } finally { working.current = false; if (alive.current) setBusy(false); } }
  const status = (value: string) => (c as unknown as Record<string, string>)[value] || value;
  return <section className="schedules-page"><div className="page-heading"><span className="eyebrow">AlpenData</span><h1>{c.title}</h1><p>{c.intro}</p></div>
    <Notice>{error ? errorMessage(error, language) : ''}</Notice>{!licensed && <Notice>{t.license}</Notice>}
    {rows === null ? <p role="status">{c.loading}</p> : !rows.length ? <p className="configuration-note">{c.empty}</p> : rows.map(row => <article className="schedule-card" key={row.id}>
      <div className="schedule-heading"><h2>{row.title}</h2><span className={`schedule-state ${row.status}`}>{status(row.status)}</span></div><p>{row.focus}</p>
      <p className="subtle">{c.sources} : {row.capabilities.map(status).join(', ')}</p><p>{c[row.frequency]}{row.frequency === 'weekly' ? ` · ${c.days[row.weekday]}` : ''} · {row.local_time} · {row.timezone}</p>
      {row.next_run_at !== null && <p>{c.next} : <strong>{dateLabel(row.next_run_at, row.timezone, language)}</strong></p>}
      {row.reason_code && <Notice>{errorMessage(new ApiError(409, row.reason_code), language)}</Notice>}
      <div className="schedule-actions"><button className="secondary" disabled={busy || row.status !== 'active' && !licensed} onClick={() => action(async () => { await api(`${base}/${row.id}/${row.status === 'active' ? 'pause' : 'resume'}`, { version: row.version }); })}>{row.status === 'active' ? <Pause size={16} /> : <Play size={16} />}{row.status === 'active' ? c.pause : c.resume}</button>
        <button className="secondary" disabled={busy || !licensed} onClick={() => { setEditing(row); setDraft({ frequency: row.frequency, local_time: row.local_time, timezone: row.timezone, weekday: row.weekday }); }}><Settings2 size={16} />{c.edit}</button>
        <button className="secondary" disabled={busy || !licensed} onClick={() => action(async () => {
          const requestId = trialRequests.current.get(row.id) || crypto.randomUUID(); trialRequests.current.set(row.id, requestId);
          try { const trial = await api<Trial>(`/api/organizations/${organizationId}/routines/${row.proposal_id}/trial`, { request_id: requestId }); trialRequests.current.delete(row.id); onOpen(trial.conversation_id); }
          catch (cause) { if (cause instanceof ApiError && cause.status > 0 && cause.status < 500) trialRequests.current.delete(row.id); throw cause; }
        })}>{c.retest}</button>
        <button className="text-button" onClick={() => setHistoryId(historyId === row.id ? '' : row.id)}>{c.history}</button><button className="text-button" disabled={busy} onClick={() => setRemoving(row.id)}><Trash2 size={15} />{c.remove}</button>
      </div>
      {editing?.id === row.id && <form className="schedule-edit" onSubmit={event => { event.preventDefault(); void action(async () => { await api(`${base}/${row.id}`, { ...draft, version: editing.version }, 'PATCH'); setEditing(null); }); }}><CadenceFields value={draft} onChange={setDraft} language={language} disabled={busy || !licensed} /><p className="subtle">{c.dst}</p><button className="primary" disabled={busy || !licensed}>{c.save}</button><button type="button" className="text-button" onClick={() => setEditing(null)}>{c.cancel}</button></form>}
      {removing === row.id && <div className="configuration-note"><p>{c.confirmRemove}</p><button className="secondary" disabled={busy} onClick={() => action(async () => { await api(`${base}/${row.id}/archive`, { version: row.version }); setRemoving(''); })}>{c.remove}</button><button className="text-button" disabled={busy} onClick={() => setRemoving('')}>{c.cancel}</button></div>}
      {historyId === row.id && <div className="schedule-history">{history === null ? <p>{c.loading}</p> : !history.occurrences.length ? <p>{c.noRuns}</p> : <ul>{history.occurrences.map(run => <li key={run.id}><div><strong>{dateLabel(run.scheduled_for, row.timezone, language)}</strong><span>{status(run.status)}</span>{run.error_code && <span>{errorMessage(new ApiError(409, run.error_code), language)}</span>}</div>{run.conversation_id && <button className="text-button" onClick={() => onOpen(run.conversation_id!)}>{c.result}</button>}</li>)}</ul>}{history?.next_before && <button className="text-button" disabled={busy} onClick={() => action(async () => { const next = await api<History>(`${base}/${row.id}/occurrences?before=${history.next_before}`); if (alive.current) { historyPages.current++; setHistory(value => value && { ...next, occurrences: [...value.occurrences, ...next.occurrences] }); } })}>{c.more}</button>}</div>}
    </article>)}
    {next !== null && <button className="secondary" disabled={busy} onClick={() => action(async () => { const more = await api<{ schedules: Schedule[]; next_offset: number | null }>(`${base}?before=${next}`); if (alive.current) { listingPages.current++; setRows(value => [...value || [], ...more.schedules]); setNext(more.next_offset); } })}>{c.more}</button>}
  </section>;
}
