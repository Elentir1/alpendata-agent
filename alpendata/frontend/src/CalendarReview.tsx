import { useEffect, useState } from 'react';
import { CalendarDays } from 'lucide-react';
import { api } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';

interface Appointment { subject: string; description: string; start: string; end: string; location: string; attendees: string[]; event_id: string; calendar_id: string }
export interface CalendarReceipt { id: string; version: number; status: string; provider: string; message: Appointment; previous: { subject?: string; calendar_name?: string }; attempts: { status: string; error?: string; result?: { url?: string; event_id?: string } }[] }

function localTime(value: string) { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16); }
export function CalendarReview({ item, organizationId, language, licensed }: { item: CalendarReceipt; organizationId: string; language: Language; licensed: boolean }) {
  const fr = language === 'fr', root = `/api/organizations/${organizationId}/calendar-actions/${item.id}`;
  const [current, setCurrent] = useState(item), [editing, setEditing] = useState(false), [message, setMessage] = useState(item.message);
  const [attendees, setAttendees] = useState(item.message.attendees.join(', '));
  const [busy, setBusy] = useState(false), [error, setError] = useState(false);
  useEffect(() => { if (!editing) { setCurrent(item); setMessage(item.message); } }, [item.id, item.version, item.status]);
  const labels: Record<string, string> = { draft: fr ? 'Rendez-vous à valider' : 'Appointment to review', dispatching: fr ? 'Enregistrement en cours' : 'Saving appointment', completed: fr ? 'Rendez-vous enregistré' : 'Appointment saved', failed: fr ? 'Rendez-vous non enregistré' : 'Appointment not saved', unknown: fr ? 'Résultat à vérifier dans votre agenda' : 'Check the result in your calendar' };
  async function run(operation: () => Promise<CalendarReceipt>) { setBusy(true); setError(false); try { const saved = await operation(); setCurrent(saved); setMessage(saved.message); setEditing(false); } catch { setError(true); } finally { setBusy(false); } }
  return <section className="calendar-review"><h3><CalendarDays size={18} />{labels[current.status]}</h3><p className="subtle">{current.provider === 'microsoft' ? 'Microsoft 365' : 'Infomaniak'} · {current.previous.calendar_name || (fr ? 'Mon agenda' : 'My calendar')} · v{current.version}</p>
    <Notice>{error && (fr ? 'L’opération n’a pas pu être confirmée. Vérifiez vos droits et le résultat avant de réessayer.' : 'The operation could not be confirmed. Check your permissions and the result before retrying.')}</Notice>
    {current.previous.subject && <p>{fr ? 'Modification de : ' : 'Updating: '}{current.previous.subject}</p>}
    {editing ? <form onSubmit={event => { event.preventDefault(); void run(() => api(root, { version: current.version, message: { ...message, attendees: attendees.split(',').map(value => value.trim()).filter(Boolean) } }, 'PUT')); }}>
      <label>{fr ? 'Titre du rendez-vous' : 'Appointment title'}<input required maxLength={500} value={message.subject} onChange={event => setMessage({ ...message, subject: event.target.value })} /></label>
      {(['start', 'end'] as const).map(key => <label key={key}>{key === 'start' ? fr ? 'Début' : 'Start' : fr ? 'Fin' : 'End'}<input type="datetime-local" required value={localTime(message[key])} onChange={event => { if (event.target.value) setMessage({ ...message, [key]: new Date(event.target.value).toISOString() }); }} /></label>)}
      <p className="subtle">{Intl.DateTimeFormat().resolvedOptions().timeZone}</p>
      <label>{fr ? 'Lieu' : 'Location'}<input maxLength={500} value={message.location} onChange={event => setMessage({ ...message, location: event.target.value })} /></label>
      <label>{fr ? 'Participants, séparés par des virgules' : 'Attendees, separated by commas'}<input value={attendees} onChange={event => setAttendees(event.target.value)} /></label>
      <label>{fr ? 'Description' : 'Description'}<textarea rows={4} maxLength={20000} value={message.description} onChange={event => setMessage({ ...message, description: event.target.value })} /></label>
      <button className="secondary" disabled={busy}>{fr ? 'Enregistrer la proposition' : 'Save proposal'}</button><button type="button" className="text-button" disabled={busy} onClick={() => setEditing(false)}>{fr ? 'Annuler' : 'Cancel'}</button>
    </form> : <><h4>{current.message.subject}</h4><p>{new Date(current.message.start).toLocaleString(language)} → {new Date(current.message.end).toLocaleString(language)}<br />{current.message.location}</p><p>{current.message.description}</p><p>{current.message.attendees.join(', ')}</p>
      {['draft', 'failed'].includes(current.status) && <div className="message-actions"><button disabled={busy || !licensed} onClick={() => { setMessage(current.message); setAttendees(current.message.attendees.join(', ')); setEditing(true); }}>{fr ? 'Corriger la proposition' : 'Edit proposal'}</button>{current.status === 'draft' && <button disabled={busy || !licensed} onClick={() => void run(() => api(root + '/execute', { version: current.version }))}>{fr ? 'Valider et enregistrer dans mon agenda' : 'Approve and save to my calendar'}</button>}</div>}
      {current.status === 'draft' && !!current.message.attendees.length && <p className="subtle">{fr ? 'La validation peut envoyer une invitation aux participants indiqués.' : 'Approving may send an invitation to the listed attendees.'}</p>}
      {current.status === 'unknown' && <Notice>{fr ? 'La réponse du fournisseur a été perdue. Aucun nouvel envoi automatique ne sera tenté.' : 'The provider response was lost. No automatic resend will be attempted.'}</Notice>}
    </>}
  </section>;
}
