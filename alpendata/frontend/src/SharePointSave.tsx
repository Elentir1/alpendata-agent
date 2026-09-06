import { useEffect, useState } from 'react';
import { ExternalLink, FolderOpen, X } from 'lucide-react';
import { api, ApiError } from './api';
import type { DocumentReceipt } from './Documents';
import type { Language } from './locale';

interface Folder { drive_id: string; item_id: string; name: string; url: string | null }
interface Save {
  id: string; filename: string; folder_name: string; folder_url: string | null;
  status: 'review' | 'running' | 'completed' | 'failed' | 'unknown'; replaces_existing: boolean;
  error_code: string | null; result: { url: string | null } | null;
}
const words = {
  fr: {
    title: 'Enregistrer dans Microsoft 365', close: 'Fermer', search: 'Rechercher un dossier ou un document proche',
    find: 'Rechercher', empty: 'Aucun dossier trouvé. Essayez le nom d’un document qui s’y trouve.',
    name: 'Nom du fichier', use: 'Préparer l’enregistrement ici', back: 'Dossier précédent',
    confirm: 'Confirmer l’enregistrement', replace: 'Je confirme le remplacement du fichier existant.',
    review: 'Vérifiez le nom et la destination avant de confirmer.', change: 'Changer la destination ou le nom',
    sharing: 'Le document sera accessible aux personnes qui ont accès à ce dossier Microsoft 365.',
    saved: 'Document enregistré.', running: 'Enregistrement en cours…', failed: 'Le document n’a pas été enregistré.',
    unknown: 'Le résultat reste à vérifier dans Microsoft 365. Cet enregistrement ne sera pas relancé automatiquement.',
    open: 'Ouvrir dans Microsoft 365', refresh: 'Actualiser le résultat', verify: 'Vérifier le document enregistré', wait: 'Chargement…', history: 'Derniers enregistrements',
    partial: 'Cette sélection est partielle. Utilisez la recherche pour retrouver un dossier absent.',
    permission: 'Activez « Enregistrer mes documents » dans vos connexions Microsoft, puis revenez ici.',
    reconnect: 'Reconnectez votre compte Microsoft dans vos outils personnels.',
    conflict: 'La destination a changé. Préparez à nouveau l’enregistrement pour examiner la version actuelle.',
    expired: 'Cette préparation a expiré. Préparez à nouveau l’enregistrement.',
    error: 'L’opération a échoué. Vérifiez votre connexion et réessayez.',
  },
  en: {
    title: 'Save to Microsoft 365', close: 'Close', search: 'Find a folder or a nearby document',
    find: 'Search', empty: 'No folders found. Try the name of a document in that folder.',
    name: 'File name', use: 'Prepare to save here', back: 'Previous folder',
    confirm: 'Confirm save', replace: 'I confirm replacing the existing file.',
    review: 'Check the name and destination before confirming.', change: 'Change destination or name',
    sharing: 'People with access to this Microsoft 365 folder will be able to access the document.',
    saved: 'Document saved.', running: 'Saving…', failed: 'The document was not saved.',
    unknown: 'The outcome needs checking in Microsoft 365. This save will not be retried automatically.',
    open: 'Open in Microsoft 365', refresh: 'Refresh result', verify: 'Check the saved document', wait: 'Loading…', history: 'Recent saves',
    partial: 'This selection is partial. Use search to find a missing folder.',
    permission: 'Enable “Save my documents” in your Microsoft connections, then return here.',
    reconnect: 'Reconnect your Microsoft account in your personal tools.',
    conflict: 'The destination changed. Prepare the save again to review the current version.',
    expired: 'This review expired. Prepare the save again.',
    error: 'The operation failed. Check your connection and try again.',
  },
};

export function SharePointSave({ item, organizationId, language, onClose }: {
  item: DocumentReceipt; organizationId: string; language: Language; onClose: () => void;
}) {
  const t = words[language], base = `/api/organizations/${encodeURIComponent(organizationId)}/sharepoint`;
  const [query, setQuery] = useState(''), [filename, setFilename] = useState(item.filename);
  const [folders, setFolders] = useState<Folder[] | null>(null), [trail, setTrail] = useState<Folder[]>([]);
  const [partial, setPartial] = useState(false), [review, setReview] = useState<Save | null>(null);
  const [replace, setReplace] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [history, setHistory] = useState<Save[]>([]);
  const current = trail.at(-1);
  const errorMessages: Record<string, string> = {
    microsoft_permission_required: t.permission, microsoft_reconnect_required: t.reconnect,
    sharepoint_destination_changed: t.conflict, sharepoint_review_expired: t.expired,
    sharepoint_save_unknown: t.unknown, sharepoint_save_unresolved: t.unknown,
  };

  useEffect(() => {
    let active = true;
    api<{ saves: Save[] }>(base + '/saves?artifact_id=' + encodeURIComponent(item.id))
      .then(value => { if (active) setHistory(value.saves.filter(save => save.status !== 'review')); })
      .catch(() => { if (active) setError('request_failed'); });
    return () => { active = false; };
  }, [base, item.id]);

  useEffect(() => {
    if (review?.status !== 'running') return;
    let active = true;
    const timer = window.setTimeout(() => {
      api<Save>(base + '/saves/' + review.id)
        .then(value => { if (active) setReview(value); })
        .catch(() => { if (active) setError('request_failed'); });
    }, 2000);
    return () => { active = false; window.clearTimeout(timer); };
  }, [base, review]);

  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError('');
    try { await action(); }
    catch (error) { setError(error instanceof ApiError ? error.code : 'request_failed'); }
    finally { setBusy(false); }
  }
  async function browse(folder: Folder, nextTrail: Folder[]) {
    const result = await api<{ folder: Folder; folders: Folder[]; partial: boolean }>(base + '/folders/browse', {
      drive_id: folder.drive_id, item_id: folder.item_id,
    });
    setFolders(result.folders); setTrail([...nextTrail, result.folder]); setPartial(result.partial);
  }
  function source(url: string | null | undefined) {
    return url?.startsWith('https://') ? <a href={url} target="_blank" rel="noopener noreferrer">{t.open}<ExternalLink size={14} aria-hidden="true" /></a> : null;
  }
  function result(save: Save) {
    const states = { review: t.review, running: t.running, completed: t.saved, failed: t.failed, unknown: t.unknown };
    return <div className="save-result" key={save.id}><strong>{save.filename}</strong><p>{save.folder_name}</p><p role="status">{states[save.status]}</p>
      {save.status === 'failed' && save.error_code && <p>{errorMessages[save.error_code] || t.error}</p>}
      {source(save.result?.url || save.folder_url)}
      {(save.status === 'running' || save.status === 'unknown') && <button type="button" className="secondary" disabled={busy} onClick={() => void run(async () => setReview(await api<Save>(base + '/saves/' + save.id)))}>{t.refresh}</button>}
      {save.status === 'unknown' && <button type="button" className="secondary" disabled={busy} onClick={() => void run(async () => setReview(await api<Save>(base + '/saves/' + save.id + '/verify', {})))}>{t.verify}</button>}
    </div>;
  }

  return <section className="sharepoint-save" aria-label={t.title}>
    <div className="save-heading"><h3>{t.title}</h3><button type="button" className="secondary" onClick={onClose} aria-label={t.close}><X size={16} /></button></div>
    {review ? <>
      {review.status === 'review' ? <div className="save-review"><p>{t.review}</p><strong>{review.filename}</strong><p>{review.folder_name}</p>{source(review.folder_url)}<p>{t.sharing}</p>
        {review.replaces_existing && <label><input type="checkbox" checked={replace} disabled={busy} onChange={event => setReplace(event.target.checked)} /> {t.replace}</label>}
        <button type="button" className="primary" disabled={busy || (review.replaces_existing && !replace)} onClick={() => void run(async () => {
          try { setReview(await api<Save>(base + '/saves/' + review.id + '/confirm', { replace_existing: replace })); }
          catch (error) {
            // A lost POST response never triggers another write. Read its durable receipt.
            setReview(await api<Save>(base + '/saves/' + review.id).catch(() => ({ ...review, status: 'unknown' as const })));
            throw error;
          }
        })}>{busy ? t.wait : t.confirm}</button>
      </div> : result(review)}
      {['review', 'failed', 'completed'].includes(review.status) && <button type="button" className="secondary" disabled={busy} onClick={() => { setReview(null); setReplace(false); setError(''); }}>{t.change}</button>}
    </> : <>
      <label>{t.name}<input value={filename} maxLength={180} disabled={busy} onChange={event => setFilename(event.target.value)} /></label>
      <form onSubmit={event => { event.preventDefault(); void run(async () => {
        const value = await api<{ folders: Folder[] }>(base + '/folders/search', { query });
        setFolders(value.folders); setTrail([]); setPartial(false);
      }); }}><label>{t.search}<input value={query} required maxLength={256} disabled={busy} onChange={event => setQuery(event.target.value)} /></label><button className="secondary" disabled={busy || !query.trim()}>{t.find}</button></form>
      {current && <div className="save-destination"><strong>{trail.map(folder => folder.name).join(' / ')}</strong>{source(current.url)}
        {trail.length > 1 && <button type="button" className="secondary" disabled={busy} onClick={() => void run(() => browse(trail[trail.length - 2], trail.slice(0, -2)))}>{t.back}</button>}
        <button type="button" className="primary" disabled={busy || !filename.trim()} onClick={() => void run(async () => {
          setReview(await api<Save>(base + '/saves', { artifact_id: item.id, drive_id: current.drive_id, item_id: current.item_id, filename })); setReplace(false);
        })}>{t.use}</button>
      </div>}
      {folders && !folders.length && !current && <p>{t.empty}</p>}
      <div className="save-folders">{folders?.map(folder => <button type="button" className="secondary" key={folder.drive_id + ':' + folder.item_id} disabled={busy} onClick={() => void run(() => browse(folder, trail))}><FolderOpen size={17} aria-hidden="true" />{folder.name}</button>)}</div>
      {partial && <p>{t.partial}</p>}
      {!!history.length && <details><summary>{t.history}</summary>{history.map(result)}</details>}
    </>}
    {error && <p role="alert">{errorMessages[error] || t.error}</p>}
  </section>;
}
