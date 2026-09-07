import { useEffect, useRef, useState } from 'react';
import { api } from './api';
import { Notice } from './feedback';
import { ProjectDialog } from './ProjectDialog';
import type { DocumentReceipt } from './Documents';
import type { Language } from './locale';

type Receipt = { id: string; filename: string; folder_name: string; status: string; replaces_existing: boolean; result?: { item_id: string; url: string } };
export function KDriveSave({ item, organizationId, language, close }: { item: DocumentReceipt; organizationId: string; language: Language; close: () => void }) {
  const fr = language === 'fr', root = `/api/organizations/${organizationId}/kdrive`;
  const [folder, setFolder] = useState('Lw'), [trail, setTrail] = useState<string[]>([]);
  const [listing, setListing] = useState<{ path: string; folders: { id: string; name: string }[]; partial: boolean } | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null), [busy, setBusy] = useState(false), [error, setError] = useState(false), [replace, setReplace] = useState(false);
  const request = useRef({ folder, id: crypto.randomUUID() });
  useEffect(() => { let active = true; setListing(null); setError(false); api<typeof listing>(root + '/folders', { folder_id: folder }).then(value => { if (active) setListing(value); }).catch(() => { if (active) setError(true); }); return () => { active = false; }; }, [root, folder]);
  async function action(work: () => Promise<void>) { setBusy(true); setError(false); try { await work(); } catch { setError(true); } finally { setBusy(false); } }
  return <ProjectDialog title={fr ? 'Enregistrer dans kDrive' : 'Save to kDrive'} language={language} disabled={busy} close={close}>
    <h3>{item.filename}</h3><Notice>{error && (fr ? 'L’opération n’a pas pu être confirmée. Vérifiez que votre kDrive est connecté avec l’autorisation de modification, puis consultez le reçu avant de réessayer.' : 'The operation could not be confirmed. Check that your kDrive is connected with write permission, then check the receipt before retrying.')}</Notice>
    {!receipt && <><p>{fr ? 'Choisissez le dossier dans votre kDrive personnel.' : 'Choose a folder in your personal kDrive.'}</p><strong>{listing?.path}</strong><div className="kdrive-folders">
      {!!trail.length && <button disabled={busy} onClick={() => { setFolder(trail.at(-1)!); setTrail(value => value.slice(0, -1)); }}>{fr ? 'Dossier précédent' : 'Previous folder'}</button>}
      {listing?.folders.map(child => <button key={child.id} disabled={busy} onClick={() => { setTrail(value => [...value, folder]); setFolder(child.id); }}>{child.name}</button>)}</div>
      {listing?.partial && <p>{fr ? 'Liste partielle des dossiers.' : 'Partial folder listing.'}</p>}
      <button className="primary" disabled={busy || !listing} onClick={() => void action(async () => { if (request.current.folder !== folder) request.current = { folder, id: crypto.randomUUID() }; setReceipt(await api<Receipt>(root + '/saves', { request_id: request.current.id, artifact_id: item.id, folder_id: folder })); })}>{fr ? 'Préparer l’enregistrement ici' : 'Prepare saving here'}</button></>}
    {receipt && <><p>{receipt.folder_name}{receipt.filename}</p>{receipt.status === 'review' ? <>
      {receipt.replaces_existing ? <label className="archive-filter"><input type="checkbox" checked={replace} onChange={event => setReplace(event.target.checked)} />{fr ? 'Je confirme le remplacement de ce fichier existant. Une modification intervenue depuis cet aperçu empêchera le remplacement.' : 'I confirm replacement of this existing file. A change since this preview will prevent replacement.'}</label> : <p>{fr ? 'Un nouveau fichier sera créé. Un fichier apparu entre-temps ne sera pas remplacé.' : 'A new file will be created. A file appearing in the meantime will not be replaced.'}</p>}
      <button className="primary" disabled={busy || (receipt.replaces_existing && !replace)} onClick={() => void action(async () => setReceipt(await api<Receipt>(root + '/saves/' + receipt.id + '/confirm', { replace_existing: replace })))}>{fr ? 'Confirmer l’enregistrement' : 'Confirm save'}</button>
    </> : <p role="status">{({ completed: fr ? 'Enregistré dans kDrive.' : 'Saved to kDrive.', running: fr ? 'Enregistrement en cours.' : 'Saving.', unknown: fr ? 'Résultat incertain : vérifiez le fichier dans kDrive. Aucun nouvel enregistrement automatique ne sera tenté.' : 'Outcome uncertain: check the file in kDrive. No automatic repeat will be attempted.', failed: fr ? 'Enregistrement non effectué ou refusé. Consultez la destination avant de préparer un nouvel essai.' : 'Save failed or was refused. Check the destination before preparing a new attempt.' } as Record<string, string>)[receipt.status]}</p>}
      <button className="text-button" disabled={busy} onClick={() => void action(async () => setReceipt(await api<Receipt>(root + '/saves/' + receipt.id)))}>{fr ? 'Vérifier le reçu' : 'Check receipt'}</button>
      {receipt.result?.item_id && <p className="subtle">{fr ? 'Identifiant du fichier' : 'File identifier'} : {receipt.result.item_id}</p>}
      <a href="https://ksuite.infomaniak.com/" target="_blank" rel="noreferrer">{fr ? 'Ouvrir kDrive' : 'Open kDrive'}</a>
    </>}
  </ProjectDialog>;
}
