import { useEffect, useId, useRef, useState } from 'react';
import { Bell, X } from 'lucide-react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';

interface Item {
  id: string; title: string; status: 'completed' | 'failed' | 'interrupted' | 'missed' | 'blocked';
  error_code: string | null; created_at: number; read_at: number | null;
  schedule_id: string; conversation_id: string | null;
}
interface Cursor { at: number; id: string }
interface Page { notifications: Item[]; unread: number; next_before: Cursor | null }
const words = {
  fr: {
    title: 'Notifications', unread: 'non lues', close: 'Fermer les notifications',
    intro: 'Les résultats et les problèmes de vos automatisations, uniquement pour vous.',
    empty: 'Vous êtes à jour. Les prochaines nouvelles de vos automatisations apparaîtront ici.',
    loading: 'Chargement…', refresh: 'Actualiser', more: 'Voir les précédentes', open: 'Ouvrir le résultat',
    manage: 'Voir mes automatisations', read: 'Marquer comme lu', readLabel: 'Lu', newLabel: 'Non lu',
    failedRead: 'L’état de lecture n’a pas pu être confirmé. Actualisez ou réessayez ; cela ne relance pas la tâche.',
    unavailable: 'Les notifications n’ont pas pu être actualisées. Réessayez pour vérifier leur état.',
    completed: 'Résultat disponible', failed: 'La tâche a rencontré un problème', interrupted: 'La tâche a été interrompue',
    missed: 'Échéance manquée', blocked: 'Automatisation à vérifier',
    missedDetail: 'Cette échéance était trop ancienne pour être exécutée. Aucun résultat n’a été créé.',
    blockedDetail: 'Cette automatisation est suspendue. Consultez ses réglages et vos connexions.',
    problemDetail: 'Consultez le résultat et les reçus disponibles avant de décider de la suite.',
  },
  en: {
    title: 'Notifications', unread: 'unread', close: 'Close notifications',
    intro: 'Results and issues from your automations, visible only to you.',
    empty: 'You’re up to date. Future updates from your automations will appear here.',
    loading: 'Loading…', refresh: 'Refresh', more: 'Show older notifications', open: 'Open result',
    manage: 'View my automations', read: 'Mark as read', readLabel: 'Read', newLabel: 'Unread',
    failedRead: 'The read status could not be confirmed. Refresh or retry; this does not run the task again.',
    unavailable: 'Notifications could not be refreshed. Try again to check their current state.',
    completed: 'Result available', failed: 'The task encountered a problem', interrupted: 'The task was interrupted',
    missed: 'Missed run', blocked: 'Automation needs attention',
    missedDetail: 'This run was too old to execute. No result was created.',
    blockedDetail: 'This automation is suspended. Check its settings and your connections.',
    problemDetail: 'Review the result and any available receipts before deciding what to do next.',
  },
};

export function Notifications({ organizationId, language, onOpen, onManage }: {
  organizationId: string; language: Language; onOpen: (id: string) => void; onManage: () => void;
}) {
  const t = words[language], id = useId(), path = `/api/organizations/${organizationId}/notifications`;
  const [open, setOpen] = useState(false), [items, setItems] = useState<Item[]>([]), [unread, setUnread] = useState<number | null>(null);
  const [next, setNext] = useState<Cursor | null>(null), [busy, setBusy] = useState(false), [saving, setSaving] = useState(false);
  const [error, setError] = useState<'load' | 'read' | null>(null), [loaded, setLoaded] = useState(false);
  const alive = useRef(true), epoch = useRef(0), listing = useRef(false), reading = useRef(false);
  const countGeneration = useRef(0);
  const root = useRef<HTMLDivElement>(null), trigger = useRef<HTMLButtonElement>(null), panel = useRef<HTMLElement>(null);

  function failed(cause: unknown, kind: 'load' | 'read') {
    if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) {
      setItems([]); setNext(null); setUnread(null); setLoaded(false);
    }
    setError(kind);
  }
  async function count() {
    if (reading.current || listing.current) return;
    const request = epoch.current;
    const sequence = ++countGeneration.current;
    try {
      const response = await api<{ unread: number }>(path + '?count_only=true');
      if (alive.current && request === epoch.current && sequence === countGeneration.current) setUnread(response.unread);
    } catch (cause) { if (alive.current && request === epoch.current && sequence === countGeneration.current) failed(cause, 'load'); }
  }
  async function load(append = false) {
    if (listing.current || reading.current) return;
    listing.current = true; setBusy(true); setError(null);
    const request = ++epoch.current;
    const cursor = append ? next : null;
    try {
      const response = await api<Page>(path + (cursor ? `?before=${cursor.at}&before_id=${cursor.id}` : ''));
      if (!alive.current || request !== epoch.current) return;
      setItems(current => cursor ? [...current, ...response.notifications.filter(row => !current.some(old => old.id === row.id))] : response.notifications);
      setNext(response.next_before); setUnread(response.unread); setLoaded(true);
    } catch (cause) { if (alive.current && request === epoch.current) failed(cause, 'load'); }
    finally { listing.current = false; if (alive.current) setBusy(false); }
  }
  async function markRead(item: Item) {
    if (reading.current || listing.current || item.read_at !== null) return;
    reading.current = true; setSaving(true); setError(null); ++epoch.current;
    try {
      const response = await api<Item>(path + '/' + item.id + '/read', {}, 'PUT');
      if (alive.current) {
        setItems(current => current.map(row => row.id === item.id ? response : row));
        setUnread(current => current === null ? null : Math.max(0, current - 1));
      }
    } catch (cause) { if (alive.current) failed(cause, 'read'); }
    finally { reading.current = false; if (alive.current) { setSaving(false); void count(); } }
  }
  function close() { setOpen(false); trigger.current?.focus(); }
  useEffect(() => {
    alive.current = true; void count();
    const refresh = () => { if (document.visibilityState === 'visible') void count(); };
    const timer = window.setInterval(refresh, 30000);
    document.addEventListener('visibilitychange', refresh);
    return () => { alive.current = false; ++epoch.current; window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, [organizationId]);
  useEffect(() => {
    if (!open) return;
    panel.current?.focus();
    const key = (event: KeyboardEvent) => { if (event.key === 'Escape') close(); };
    const outside = (event: PointerEvent) => { if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener('keydown', key); document.addEventListener('pointerdown', outside);
    return () => { document.removeEventListener('keydown', key); document.removeEventListener('pointerdown', outside); };
  }, [open]);
  return <div className="notification-center" ref={root}>
    <button ref={trigger} className="icon-button notification-trigger" aria-label={`${t.title}${unread === null ? '' : `, ${unread} ${language === 'fr' && unread === 1 ? 'non lue' : t.unread}`}`} aria-expanded={open} aria-controls={id} onClick={() => { if (open) close(); else { setOpen(true); void load(); } }}>
      <Bell size={20} />{!!unread && <span className="notification-badge" aria-hidden="true">{unread > 99 ? '99+' : unread}</span>}
    </button>
    {open && <section id={id} ref={panel} className="notification-panel" role="dialog" aria-label={t.title} tabIndex={-1}>
      <div className="notification-heading"><h2>{t.title}</h2><button className="icon-button" onClick={close} aria-label={t.close}><X size={20} /></button></div>
      <p>{t.intro}</p><button className="secondary" disabled={busy || saving} onClick={() => void load()}>{busy ? t.loading : t.refresh}</button>
      <Notice>{error ? error === 'read' ? t.failedRead : t.unavailable : ''}</Notice>
      {loaded && !items.length && !error && <p className="notification-empty">{t.empty}</p>}
      <ul>{items.map(item => <li key={item.id} className={item.read_at === null ? 'unread' : ''}>
        <div className="notification-meta"><span>{t[item.status]}</span><span>{item.read_at === null ? t.newLabel : t.readLabel}</span></div>
        <h3>{item.title}</h3><time dateTime={new Date(item.created_at * 1000).toISOString()}>{new Intl.DateTimeFormat(language === 'fr' ? 'fr-CH' : 'en', { dateStyle: 'medium', timeStyle: 'short' }).format(item.created_at * 1000)}</time>
        {item.status !== 'completed' && <p>{item.status === 'missed' ? t.missedDetail : item.status === 'blocked' ? t.blockedDetail : t.problemDetail}</p>}
        <div className="notification-actions"><button className="secondary" disabled={busy || saving} onClick={() => { void markRead(item); if (item.conversation_id) onOpen(item.conversation_id); else onManage(); close(); }}>{item.conversation_id ? t.open : t.manage}</button>
          {item.read_at === null && <button className="text-button" disabled={busy || saving} onClick={() => void markRead(item)}>{t.read}</button>}</div>
      </li>)}</ul>
      {next && <button className="secondary" disabled={busy || saving} onClick={() => void load(true)}>{t.more}</button>}
    </section>}
  </div>;
}
