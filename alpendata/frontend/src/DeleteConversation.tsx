import { useState } from 'react';
import { api } from './api';
import { ProjectDialog } from './ProjectDialog';
import type { Language } from './locale';

export function DeleteConversation({ path, title, language, close, removed }: { path: string; title: string; language: Language; close: () => void; removed: () => void }) {
  const fr = language === 'fr', [busy, setBusy] = useState(false), [error, setError] = useState(false);
  return <ProjectDialog title={fr ? 'Supprimer la discussion' : 'Delete conversation'} language={language} close={close} disabled={busy}>
    <p><strong>{title}</strong></p><p>{fr ? 'Cette discussion et ses fichiers personnels ne seront plus accessibles. Les travaux en cours seront arrêtés et les routines qui en dépendent seront désactivées.' : 'This conversation and its personal files will no longer be accessible. Running work will stop and dependent routines will be disabled.'}</p>
    <p>{fr ? 'Les actions déjà effectuées, les copies publiées dans des projets et les autres variantes sont conservées.' : 'Actions already performed, copies published to projects and other branches are preserved.'}</p>
    {error && <p role="alert">{fr ? 'La suppression n’a pas pu être confirmée. Vous pouvez vérifier la même demande en réessayant.' : 'Deletion could not be confirmed. Retry to check the same request.'}</p>}
    <div className="message-actions"><button disabled={busy} onClick={close}>{fr ? 'Annuler' : 'Cancel'}</button><button className="primary" disabled={busy} onClick={async () => { setBusy(true); setError(false); try { await api(path, undefined, 'DELETE'); removed(); } catch { setError(true); } finally { setBusy(false); } }}>{fr ? 'Supprimer cette discussion' : 'Delete this conversation'}</button></div>
  </ProjectDialog>;
}
