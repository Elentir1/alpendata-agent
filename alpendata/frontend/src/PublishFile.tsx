import { useEffect, useState } from 'react';
import { api } from './api';
import { Notice } from './feedback';
import { ProjectDialog } from './ProjectDialog';
import type { Project } from './ProjectPanel';
import type { Language } from './locale';

export function PublishFile({ organizationId, file, language, close }: {
  organizationId: string; file: { id: string; filename: string; version: number }; language: Language; close: () => void;
}) {
  const fr = language === 'fr', root = `/api/organizations/${organizationId}`;
  const [projects, setProjects] = useState<Project[]>([]), [project, setProject] = useState('');
  const [requestId] = useState(() => crypto.randomUUID()), [busy, setBusy] = useState(false), [error, setError] = useState(false);
  useEffect(() => { let active = true; api<{ projects: Project[] }>(root + '/chat/projects').then(value => { if (active) setProjects(value.projects.filter(item => item.role !== 'reader')); }).catch(() => { if (active) setError(true); }); return () => { active = false; }; }, [root]);
  return <ProjectDialog language={language} close={close} disabled={busy}><form onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError(false);
    try { await api(`${root}/chat/projects/${project}/files`, { request_id: requestId, file_id: file.id, version: file.version }); close(); }
    catch { setError(true); } finally { setBusy(false); }
  }}><h3>{fr ? 'Publier cette version' : 'Publish this version'}</h3>
    <p><strong>{file.filename} · v{file.version}</strong></p>
    <a href={`${root}/files/${file.id}/versions/${file.version}/content`} download>{fr ? 'Relire le fichier avant publication' : 'Review the file before publication'}</a>
    <p>{fr ? 'Les membres du projet auront accès à une copie de ce fichier. Les contributeurs pourront la modifier. L’original, ses autres versions et votre discussion restent privés.' : 'Project members will receive a copy of this file. Contributors can edit it. The original, its other versions and your conversation remain private.'}</p>
    <label>{fr ? 'Projet destinataire' : 'Destination project'}<select required value={project} disabled={busy} onChange={event => setProject(event.target.value)}><option value="">{fr ? 'Choisir…' : 'Choose…'}</option>{projects.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    <Notice>{error && (fr ? 'Publication non confirmée. Vérifiez les documents du projet avant de réessayer.' : 'Publication not confirmed. Check project documents before retrying.')}</Notice>
    <button className="primary" disabled={busy || !project}>{fr ? 'Publier cette copie' : 'Publish this copy'}</button>
  </form></ProjectDialog>;
}
