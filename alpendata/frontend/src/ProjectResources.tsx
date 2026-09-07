import { useEffect, useState } from 'react';
import { api } from './api';
import { WorkspaceFiles } from './WorkspaceFiles';
import { Notice } from './feedback';
import { ProjectDialog } from './ProjectDialog';
import { ChatResponse } from './ChatResponse';
import type { Project } from './ProjectPanel';
import type { Language } from './locale';

interface Entry { id: string; title: string; content: string; kind: string; version: number; owner_id: string }
interface Member { user_id: string; display_name: string; role: string | null }

export function ProjectResources({ base, project, userId, language, close, choose }: {
  base: string; project: Project; userId?: string; language: Language; close: () => void; choose?: (prompt: string) => void;
}) {
  const [filesOpen, setFilesOpen] = useState(false);
  const fr = language === 'fr', path = `${base}/projects/${project.id}`;
  const [entries, setEntries] = useState<Entry[]>([]), [members, setMembers] = useState<Member[]>([]);
  const [title, setTitle] = useState(''), [content, setContent] = useState(''), [editing, setEditing] = useState<Entry | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(false);
  const [requestId, setRequestId] = useState(() => crypto.randomUUID());
  const owner = !project.role || project.role === 'owner';
  async function load() {
    const resources = await api<{ entries: Entry[] }>(path + '/entries'); setEntries(resources.entries);
    if (owner) setMembers((await api<{ members: Member[] }>(path + '/members')).members);
  }
  useEffect(() => { let active = true; api<{ entries: Entry[] }>(path + '/entries').then(value => { if (active) setEntries(value.entries); }).catch(() => { if (active) setError(true); });
    if (owner) api<{ members: Member[] }>(path + '/members').then(value => { if (active) setMembers(value.members); }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [path]);
  async function action(work: () => Promise<unknown>) { setBusy(true); setError(false); try { await work(); await load(); } catch { setError(true); } finally { setBusy(false); } }
  return <ProjectDialog language={language} close={close} disabled={busy}><section className="project-resources">
    <h3>{project.name}</h3><p>{fr ? 'Seules les ressources publiées ici sont partagées. Chaque discussion et chaque connexion restent personnelles.' : 'Only resources published here are shared. Conversations and connections remain personal.'}</p>
    <Notice>{error && (fr ? 'Impossible de confirmer la modification ou de charger le projet. Actualisez avant de réessayer.' : 'Could not confirm changes or load the project. Refresh before retrying.')}</Notice>
    {owner && <details><summary>{fr ? 'Membres et accès' : 'Members and access'}</summary>{members.map(member => <label className="project-member" key={member.user_id}><span>{member.display_name}</span><select aria-label={member.display_name} value={member.role || ''} disabled={busy || member.role === 'owner'} onChange={event => void action(() => event.target.value ? api(path + '/members', { user_id: member.user_id, role: event.target.value }, 'PUT') : api(path + '/members/' + member.user_id, undefined, 'DELETE'))}><option value="">{fr ? 'Pas d’accès' : 'No access'}</option><option value="reader">{fr ? 'Lecteur' : 'Reader'}</option><option value="contributor">{fr ? 'Contributeur' : 'Contributor'}</option><option value="owner" disabled>{fr ? 'Propriétaire' : 'Owner'}</option></select></label>)}</details>}
    {choose && <button className="secondary" onClick={() => setFilesOpen(true)}>{fr ? 'Documents du projet' : 'Project documents'}</button>}
    {filesOpen && choose && <WorkspaceFiles organizationId={base.split('/')[3]} projectId={project.id} language={language} licensed={project.role !== 'reader'} artifacts={[]} close={() => setFilesOpen(false)} choose={prompt => { close(); choose(prompt); }} />}
    <h4>{fr ? 'Connaissances et publications' : 'Knowledge and publications'}</h4>
    {entries.map(entry => <details key={entry.id}><summary>{entry.title} · v{entry.version}</summary><ChatResponse text={entry.content} language={language} />{(owner || entry.owner_id === userId) && <div className="message-actions"><button disabled={busy} onClick={() => { setEditing(entry); setTitle(entry.title); setContent(entry.content); }}>{fr ? 'Modifier' : 'Edit'}</button><button disabled={busy} onClick={() => void action(() => api(`${path}/entries/${entry.id}`, undefined, 'DELETE'))}>{fr ? 'Retirer du projet' : 'Remove from project'}</button></div>}</details>)}
    {!entries.length && <p className="subtle">{fr ? 'Ajoutez les informations que l’assistant doit pouvoir retrouver dans ce projet.' : 'Add information the assistant should be able to find in this project.'}</p>}
    {project.role !== 'reader' && <form onSubmit={event => { event.preventDefault(); void action(async () => {
      await api(path + '/entries' + (editing ? '/' + editing.id : ''), { request_id: requestId, title, content, kind: editing?.kind || 'note', version: editing?.version || 1 }, editing ? 'PUT' : 'POST');
      setEditing(null); setTitle(''); setContent(''); setRequestId(crypto.randomUUID());
    }); }}><label>{fr ? 'Titre de la ressource' : 'Resource title'}<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={160} /></label><label>{fr ? 'Contenu accessible aux membres du projet' : 'Content available to project members'}<textarea value={content} onChange={event => setContent(event.target.value)} required maxLength={100000} rows={5} /></label><button className="primary" disabled={busy || !content.trim() || !title.trim()}>{fr ? 'Publier dans le projet' : 'Publish to project'}</button></form>}
  </section></ProjectDialog>;
}

export function PublishConversation({ base, projectId, title, transcript, language, close, kind = 'publication' }: {
  base: string; projectId: string; title: string; transcript: string; language: Language; close: () => void; kind?: 'publication' | 'method';
}) {
  const fr = language === 'fr';
  const [requestId] = useState(() => crypto.randomUUID());
  const [content, setContent] = useState(transcript), [busy, setBusy] = useState(false), [error, setError] = useState(false);
  return <ProjectDialog language={language} close={close} disabled={busy}><form onSubmit={async event => {
    event.preventDefault(); setBusy(true); setError(false);
    try { await api(`${base}/projects/${projectId}/entries`, { request_id: requestId, title, content, kind }); close(); }
    catch { setError(true); } finally { setBusy(false); }
  }}><h3>{fr ? 'Choisir ce que vous publiez' : 'Choose what to publish'}</h3><p>{fr ? 'Retirez les passages privés avant de publier cette copie. Les membres du projet pourront la lire. Les pièces jointes et les connexions ne sont pas partagées.' : 'Remove private passages before publishing this copy. Project members will be able to read it. Attachments and connections are not shared.'}</p><label>{fr ? 'Aperçu modifiable de la publication' : 'Editable publication preview'}<textarea rows={12} maxLength={100000} value={content} onChange={event => setContent(event.target.value)} /></label><Notice>{error && (fr ? 'La publication n’a pas pu être confirmée. Vérifiez les ressources du projet avant de réessayer.' : 'Publication could not be confirmed. Check project resources before retrying.')}</Notice><button className="primary" disabled={busy || !content.trim()}>{fr ? 'Publier cette copie' : 'Publish this copy'}</button></form></ProjectDialog>;
}
