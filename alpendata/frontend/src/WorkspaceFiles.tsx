import { useEffect, useRef, useState } from 'react';
import { FileText, Upload, X } from 'lucide-react';
import { api, ApiError } from './api';
import { Office, type EditorConfig } from './Office';
import { VersionComparison } from './VersionComparison';
import { FilePassages } from './FilePassages';
import { readChatValue, writeChatValue } from './conversationStorage';
import { PublishFile } from './PublishFile';
import { Notice } from './feedback';
import type { DocumentReceipt } from './Documents';
import type { Language } from './locale';

interface FileItem { id: string; filename: string; media_type: string; version: number; analysis_status?: string }
interface Version { version: number; size: number; created_at: number }
async function encode(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = reject; reader.readAsDataURL(file);
  });
}

export function WorkspaceFiles({ organizationId, conversationId, projectId, language, licensed, artifacts, close, choose }: {
  organizationId: string; conversationId?: string; projectId?: string; language: Language; licensed: boolean;
  artifacts: DocumentReceipt[]; close: () => void; choose: (prompt: string) => void;
}) {
  const fr = language === 'fr', root = `/api/organizations/${organizationId}`;
  const path = root + (projectId ? `/chat/projects/${projectId}/files` : `/chat/conversations/${conversationId}/files`);
  const [writable, setWritable] = useState(!projectId);
  const canEdit = licensed && writable;
  const [publishing, setPublishing] = useState(false);
  const [files, setFiles] = useState<FileItem[]>([]), [selected, setSelected] = useState<FileItem | null>(null);
  const [versions, setVersions] = useState<Version[]>([]), [text, setText] = useState('');
  const [comparison, setComparison] = useState<{ before: number; after: number } | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [status, setStatus] = useState('');
  const [editorAvailable, setEditorAvailable] = useState(false), [editor, setEditor] = useState<EditorConfig | null>(null);
  const input = useRef<HTMLInputElement>(null), alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  async function load() {
    const result = await api<{ files: FileItem[]; editor_available: boolean; writable?: boolean }>(path);
    if (alive.current) { setFiles(result.files); setEditorAvailable(result.editor_available); setWritable(result.writable !== false); }
  }
  useEffect(() => { void load().catch(() => setError(fr ? 'Les fichiers ne sont pas disponibles.' : 'Files are unavailable.')); }, [path]);
  const analyzing = files.some(item => ['queued', 'running'].includes(item.analysis_status || ''));
  useEffect(() => { if (!analyzing) return; const timer = setInterval(() => { void load().catch(() => undefined); }, 2500); return () => clearInterval(timer); }, [path, analyzing]);
  useEffect(() => {
    if (!editor || !selected) return;
    const timer = setInterval(() => {
      api<{ saved_version: number | null; conflict_file_id: string | null }>(`${root}/files/${selected.id}/editor/${editor.id}`).then(value => {
        if (!alive.current) return;
        if (value.conflict_file_id) { setStatus(fr ? 'Le document a changé ailleurs. Votre travail est conservé dans une copie distincte.' : 'The document changed elsewhere. Your work has been preserved in a separate copy.'); void load(); }
        else if (value.saved_version) { setStatus(`${fr ? 'Enregistré' : 'Saved'} · v${value.saved_version}`); }
      }).catch(() => { if (alive.current) setError(fr ? 'La sauvegarde ne peut pas être vérifiée. Gardez l’éditeur ouvert.' : 'Saving cannot be verified. Keep the editor open.'); });
    }, 4000);
    return () => clearInterval(timer);
  }, [editor?.id, selected?.id]);
  async function action(work: () => Promise<void>) {
    if (busy) return; setBusy(true); setError('');
    try { await work(); } catch (cause) { if (alive.current) setError(cause instanceof ApiError && cause.code === 'document_version_changed' ? fr ? 'Une version plus récente existe. Votre texte est conservé ici ; ouvrez la nouvelle version dans une autre fenêtre pour les comparer.' : 'A newer version exists. Your text remains here; open the new version in another window to compare.' : fr ? 'Cette opération n’a pas pu être confirmée. Vérifiez le résultat avant de réessayer.' : 'This operation could not be confirmed. Check the result before retrying.'); }
    finally { if (alive.current) setBusy(false); }
  }
  async function upload(items: File[]) {
    await action(async () => {
      for (const file of items) {
        if (file.size > 5 * 1024 * 1024) { setError(fr ? 'La limite est de 5 Mo par fichier.' : 'The limit is 5 MB per file.'); continue; }
        setStatus(`${fr ? 'Importation' : 'Uploading'} : ${file.name}`);
        const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer()))].map(value => value.toString(16).padStart(2, '0')).join('');
        const key = `upload.${organizationId}.${conversationId}.${hash}.${encodeURIComponent(file.name)}`;
        const requestId = readChatValue(key) || crypto.randomUUID(); writeChatValue(key, requestId);
        await api(path, { request_id: requestId, filename: file.name, content_base64: await encode(file) });
        writeChatValue(key, '');
      }
      await load(); setStatus(fr ? 'Fichiers disponibles pour cette discussion.' : 'Files available to this conversation.');
    });
  }
  async function open(item: FileItem) {
    await action(async () => {
      setEditor(null); setStatus('');
      const result = await api<{ file: FileItem; versions: Version[] }>(`${root}/files/${item.id}/versions`);
      setSelected(result.file); setVersions(result.versions);
      if (item.media_type === 'text/plain') {
        const response = await fetch(`${root}/files/${item.id}/versions/${result.file.version}/content`, { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) throw new Error('Download failed'); setText(await response.text());
      }
    });
  }
  return <aside className="agent-workbench file-workbench" aria-label={fr ? 'Fichiers de la discussion' : 'Conversation files'}>
    <header><div><span className="eyebrow">{fr ? 'DOCUMENTS ET VERSIONS' : 'DOCUMENTS AND VERSIONS'}</span><h2>{editor && selected ? selected.filename : fr ? 'Votre travail prend forme' : 'Your work takes shape'}</h2></div><button className="icon-button" onClick={close} aria-label={fr ? 'Fermer les fichiers' : 'Close files'}><X size={19} /></button></header>
    <div className="workbench-content" onDragOver={event => { if (canEdit && !projectId && !editor) event.preventDefault(); }} onDrop={event => { event.preventDefault(); if (canEdit && !projectId && !editor) void upload([...event.dataTransfer.files]); }}>
      <Notice>{error}</Notice>{status && <p role="status" className="subtle">{status}</p>}
      {!editor && <>
      {!projectId && <button className="file-dropzone" disabled={busy || !canEdit} onClick={() => input.current?.click()}><Upload size={22} /><strong>{fr ? 'Ajouter ou déposer des fichiers' : 'Add or drop files'}</strong><small>PDF, Word, Excel, PowerPoint, PNG, JPEG, CSV, TXT · 5 Mo</small></button>}
      {projectId && <p className="subtle">{fr ? 'Documents publiés explicitement dans ce projet. Ajoutez un fichier à une discussion personnelle, puis publiez la version choisie ici.' : 'Documents explicitly published to this project. Add a file to a personal conversation, then publish the selected version here.'}</p>}
      <input ref={input} className="sr-only" type="file" multiple accept=".pdf,.docx,.xlsx,.pptx,.png,.jpg,.jpeg,.csv,.txt,.md" onChange={event => { void upload([...event.target.files || []]); event.target.value = ''; }} />
      <div className="workspace-file-list">{files.map(item => <button disabled={busy} className={selected?.id === item.id ? 'selected' : ''} onClick={() => void open(item)} key={item.id}><FileText size={17} /><span>{item.filename}<small>v{item.version} · {({ queued: fr ? 'Analyse en attente' : 'Analysis queued', running: fr ? 'Analyse…' : 'Analyzing…', ready: fr ? 'Texte analysé' : 'Text analyzed', partial: fr ? 'Analyse partielle' : 'Partial analysis', failed: fr ? 'Lecture impossible' : 'Could not read', no_text: fr ? 'Aucun texte détecté' : 'No text detected', password_required: fr ? 'Protégé par mot de passe' : 'Password protected', vision_required: fr ? 'Lecture visuelle nécessaire' : 'Visual reading required' } as Record<string, string>)[item.analysis_status || ''] || ''}</small></span></button>)}</div>
      {!projectId && artifacts.length > 0 && <details><summary>{fr ? 'Ajouter un document créé par l’assistant' : 'Add an assistant-created document'}</summary>{artifacts.map(item => <button className="text-button" key={item.id} disabled={busy || !canEdit} onClick={() => void action(async () => { const imported = await api<FileItem>(path + '/from-artifact', { artifact_id: item.id }); await load(); setSelected(imported); setVersions((await api<{ versions: Version[] }>(`${root}/files/${imported.id}/versions`)).versions); })}>{item.filename}</button>)}</details>}
      {selected && <section className="file-detail"><h3>{selected.filename}</h3><div className="message-actions"><a href={`${root}/files/${selected.id}/versions/${selected.version}/content`} download>{fr ? 'Télécharger' : 'Download'} · v{selected.version}</a><button onClick={() => choose(`${fr ? 'Travaille sur le fichier' : 'Work on file'} « ${selected.filename} » (ID ${selected.id}, version ${selected.version}). ${fr ? 'Commence par le lire, cite les pages ou sections pertinentes et demande-moi le résultat souhaité.' : 'Read it first, cite relevant pages or sections, and ask for the desired outcome.'}`)}>{fr ? 'Travailler avec l’assistant' : 'Work with the assistant'}</button></div>
        {!projectId && <button className="secondary" disabled={busy || !licensed} onClick={() => setPublishing(true)}>{fr ? 'Publier une copie dans un projet' : 'Publish a copy to a project'}</button>}
        <FilePassages root={root} file={selected} language={language} choose={choose} />
        {selected.media_type === 'application/pdf' && <button className="secondary" onClick={() => choose(`${fr ? 'Crée une copie Word éditable de ce PDF' : 'Create an editable Word copy of this PDF'} « ${selected.filename} » (ID ${selected.id}, version ${selected.version}). ${fr ? 'Conserve le PDF original. Explique les différences de mise en page éventuelles et publie le nouveau fichier.' : 'Preserve the original PDF. Explain possible layout differences and publish the new file.'}`)}>{fr ? 'Préparer une copie Word avec l’assistant' : 'Prepare a Word copy with the assistant'}</button>}
        {selected.media_type === 'text/plain' && <form onSubmit={event => { event.preventDefault(); void action(async () => { const updated = await api<FileItem>(`${root}/files/${selected.id}/versions`, { expected_version: selected.version, filename: selected.filename, content_base64: await encode(new File([text], selected.filename)) }); setSelected(updated); setVersions((await api<{ versions: Version[] }>(`${root}/files/${updated.id}/versions`)).versions); await load(); setStatus(fr ? 'Nouvelle version enregistrée.' : 'New version saved.'); }); }}><textarea aria-label={fr ? 'Contenu du fichier' : 'File content'} rows={14} value={text} onChange={event => setText(event.target.value)} /><button className="primary" disabled={busy || !canEdit}>{fr ? 'Enregistrer une version' : 'Save a version'}</button></form>}
        {/\.(docx|xlsx|pptx)$/i.test(selected.filename) && editorAvailable && <button className="primary" disabled={busy || !canEdit} onClick={() => void action(async () => setEditor(await api<EditorConfig>(`${root}/files/${selected.id}/editor`, { language, mobile: window.innerWidth < 760 })))}>{fr ? 'Ouvrir l’éditeur' : 'Open editor'}</button>}
        <details><summary>{fr ? 'Historique des versions' : 'Version history'}</summary>{versions.map(version => <div className="file-version" key={version.version}><a href={`${root}/files/${selected.id}/versions/${version.version}/content`} download>v{version.version} · {new Date(version.created_at * 1000).toLocaleDateString(language)}</a>{version.version !== selected.version && <button disabled={busy} onClick={() => setComparison({ before: version.version, after: selected.version })}>{fr ? 'Comparer' : 'Compare'}</button>}{version.version !== selected.version && <button disabled={busy || !canEdit} onClick={() => void action(async () => { const updated = await api<FileItem>(`${root}/files/${selected.id}/restore`, { expected_version: selected.version, source_version: version.version }); setSelected(updated); setVersions((await api<{ versions: Version[] }>(`${root}/files/${updated.id}/versions`)).versions); await load(); })}>{fr ? 'Restaurer dans une nouvelle version' : 'Restore as a new version'}</button>}</div>)}</details>
      </section>}
      {comparison && selected && <VersionComparison root={root} fileId={selected.id} before={comparison.before} after={comparison.after} language={language} close={() => setComparison(null)} />}
      {publishing && selected && <PublishFile organizationId={organizationId} file={selected} language={language} close={() => setPublishing(false)} />}
      </>}
      {editor && selected && <button className="text-button office-back" onClick={() => void open(selected)}>{fr ? '← Retour aux fichiers et versions' : '← Back to files and versions'}</button>}
      {editor && selected && <Office configuration={editor} language={language} file={selected} choose={choose} failed={() => setError(fr ? 'L’éditeur est indisponible.' : 'The editor is unavailable.')} />}
    </div>
  </aside>;
}
