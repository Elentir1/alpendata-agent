import { useEffect, useState } from 'react';
import { Inbox } from 'lucide-react';
import { api } from './api';
import { Notice } from './feedback';
import { ProjectDialog } from './ProjectDialog';
import { Notifications } from './Notifications';
import type { Language } from './locale';

interface Item { id: string; conversation_id: string; title: string; message: string; status: string; read: boolean; created_at: number }
interface Page { items: Item[]; unread: number; next_offset: number | null }
export function WorkInbox({ organizationId, language, onOpen, onManage }: { organizationId: string; language: Language; onOpen: (id: string) => void; onManage?: () => void }) {
  const fr = language === 'fr', path = `/api/organizations/${organizationId}/work-inbox`;
  const [open, setOpen] = useState(false), [page, setPage] = useState<Page | null>(null), [error, setError] = useState(false);
  const labels: Record<string, string> = { completed: fr ? 'Résultat disponible' : 'Result available', review: fr ? 'Action à valider' : 'Review required', failed: fr ? 'À vérifier' : 'Needs attention', interrupted: fr ? 'Interrompu' : 'Interrupted', cancelled: fr ? 'Arrêté' : 'Stopped' };
  useEffect(() => {
    let active = true;
    const load = () => api<Page>(path).then(value => { if (active) { setPage(value); setError(false); } }).catch(() => { if (active) setError(true); });
    void load(); const timer = setInterval(load, open ? 5000 : 20000);
    return () => { active = false; clearInterval(timer); };
  }, [path, open]);
  return <><button className="workspace-shortcut" onClick={() => setOpen(true)}><Inbox size={18} /><span>{fr ? 'À suivre' : 'Follow-up'}</span>{!!page?.unread && <b>{page.unread}</b>}</button>
    {open && <ProjectDialog language={language} disabled={false} close={() => setOpen(false)}><section className="work-inbox"><h2>{fr ? 'À suivre' : 'Follow-up'}</h2><p>{fr ? 'Vos résultats, validations et travaux à reprendre.' : 'Your results, reviews and work to resume.'}</p>
      <Notice>{error && (fr ? 'Impossible d’actualiser les résultats.' : 'Could not refresh results.')}</Notice>
      {page?.items.map(item => <article key={item.id} className={item.read ? 'read' : 'unread'}><small>{labels[item.status] || item.status} · {new Date(item.created_at * 1000).toLocaleString(language)}</small><h3>{item.title}</h3><p>{item.message}</p><button className="secondary" onClick={() => {
        onOpen(item.conversation_id); setOpen(false);
        void api(path + '/' + item.id + '/read', {}, 'PUT').catch(() => setError(true));
      }}>{fr ? 'Ouvrir le travail' : 'Open work'}</button></article>)}
      {page && !page.items.length && <p>{fr ? 'Les prochains résultats apparaîtront ici, même si vous fermez la page.' : 'Future results will appear here, even if you close the page.'}</p>}
      {page?.next_offset != null && <button className="text-button" onClick={() => { void api<Page>(path + '?offset=' + page.next_offset).then(next => setPage({ ...next, items: [...page.items, ...next.items] })).catch(() => setError(true)); }}>{fr ? 'Voir les précédents' : 'Show older results'}</button>}
      <Notifications organizationId={organizationId} language={language} onOpen={id => { onOpen(id); setOpen(false); }} onManage={() => { onManage?.(); setOpen(false); }} />
    </section></ProjectDialog>}
  </>;
}
