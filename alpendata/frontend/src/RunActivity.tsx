import { useEffect, useRef, useState } from 'react';
import { Activity, Check, LoaderCircle } from 'lucide-react';
import type { Language } from './locale';

interface RunEvent { id: number; turn_id: string; kind: string; label: string; created_at: number }
const labels: Record<string, [string, string]> = {
  response_updated: ['Rédaction en cours', 'Writing response'],
  queued: ['En attente', 'Queued'], running: ['Travail commencé', 'Work started'],
  completed: ['Résultat disponible', 'Result available'], failed: ['Intervention nécessaire', 'Needs attention'],
  cancelled: ['Travail arrêté', 'Work stopped'], interrupted: ['Travail interrompu', 'Work interrupted'],
  stopping: ['Arrêt demandé', 'Stop requested'],
};
const tools: Record<string, [string, string]> = {
  alpendata_research: ['Recherche et lecture des sources Web', 'Searching and reading Web sources'],
  alpendata_calendar_action: ['Préparation ou validation du rendez-vous', 'Preparing or approving appointment'],
  alpendata_delegate: ['Analyses spécialisées', 'Specialized analysis'],
  alpendata_workspace_file: ['Lecture et version du document', 'Reading and versioning document'],
  alpendata_knowledge: ['Consultation des préférences et méthodes', 'Reading preferences and methods'],
  alpendata_mail: ['Lecture des e-mails', 'Reading emails'],
  alpendata_calendar: ['Consultation de l’agenda', 'Reading calendar'],
  alpendata_files: ['Recherche de fichiers', 'Finding files'],
  alpendata_download_file: ['Lecture du document', 'Reading document'],
  alpendata_publish_document: ['Publication du document', 'Publishing document'],
  alpendata_prepare_email: ['Préparation du message', 'Preparing email'],
  alpendata_send_email: ['Demande d’envoi', 'Requesting email send'],
  terminal: ['Traitement dans l’espace de travail', 'Processing in workspace'],
  todo_list: ['Organisation des étapes', 'Organizing steps'],
  skill_manage: ['Enregistrement de la méthode', 'Saving workflow'],
};

export function RunActivity({ base, conversationId, language, onUpdate, onRevoked }: {
  base: string; conversationId: string; language: Language; onUpdate: () => void; onRevoked: () => void;
}) {
  const [events, setEvents] = useState<RunEvent[]>([]), [connected, setConnected] = useState(true);
  const callbacks = useRef({ onUpdate, onRevoked }); callbacks.current = { onUpdate, onRevoked };
  useEffect(() => {
    setEvents([]);
    if (!conversationId || typeof EventSource === 'undefined') return;
    const source = new EventSource(`${base}/conversations/${conversationId}/events?stream=true`);
    let timer: ReturnType<typeof setTimeout> | undefined;
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener('revoked', () => { setEvents([]); source.close(); callbacks.current.onRevoked(); });
    source.addEventListener('activity', raw => {
      const event: RunEvent = JSON.parse((raw as MessageEvent).data);
      setEvents(previous => previous.some(item => item.id === event.id) ? previous : [...previous.filter(item => event.kind !== 'response_updated' || item.kind !== 'response_updated' || item.turn_id !== event.turn_id), event].slice(-100));
      clearTimeout(timer); timer = setTimeout(() => callbacks.current.onUpdate(), 300);
    });
    return () => { clearTimeout(timer); source.close(); };
  }, [base, conversationId]);
  if (!events.length) return null;
  const index = language === 'fr' ? 0 : 1;
  const label = (event: RunEvent) => labels[event.kind]?.[index] || tools[event.label]?.[index] || (event.label.startsWith('delegated_task_') ? index === 0 ? 'Analyse spécialisée' : 'Specialized analysis' : '') || (index === 0 ? 'Utilisation d’un outil autorisé' : 'Using an authorized tool');
  return <details className="run-activity"><summary><Activity size={15} />{label(events[events.length - 1])}<span>{index === 0 ? 'Voir les étapes' : 'View steps'}</span></summary>
    {!connected && <p role="status">{index === 0 ? 'Reconnexion au suivi… Le travail continue.' : 'Reconnecting to activity… Work continues.'}</p>}
    <ol>{events.map(event => <li key={event.id}>{['completed', 'tool_finished'].includes(event.kind) ? <Check size={14} /> : <LoaderCircle size={14} />}<span>{label(event)}{event.kind === 'tool_finished' ? index === 0 ? ' · terminé' : ' · finished' : ''}</span><time>{new Date(event.created_at * 1000).toLocaleTimeString(language, { hour: '2-digit', minute: '2-digit' })}</time></li>)}</ol>
  </details>;
}
