import { useEffect, useState } from 'react';
import { Folder, Plus } from 'lucide-react';
import { api } from './api';
import { ProjectDialog } from './ProjectDialog';
import type { Language } from './locale';

export interface Project { id: string; name: string; instructions: string }

export function ProjectPanel({ base, language, projects, onProjects, selected, onSelect, disabled, onError }: { base: string; language: Language; projects: Project[]; onProjects: (items: Project[]) => void; selected: string; onSelect: (id: string) => void; disabled: boolean; onError: (error: unknown) => void }) {
  const fr = language === 'fr';
  const [editing, setEditing] = useState<string | null>(null), [name, setName] = useState(''), [instructions, setInstructions] = useState(''), [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    api<{ projects: Project[] }>(base + '/projects').then(data => { if (active) onProjects(data.projects); }).catch(error => { if (active) onError(error); });
    return () => { active = false; };
  }, [base]);
  const current = projects.find(item => item.id === selected);
  function edit(item?: Project) { setEditing(item?.id || ''); setName(item?.name || ''); setInstructions(item?.instructions || ''); }
  return <div className="project-panel">
    <div className="project-heading"><strong>{fr ? 'Mes projets' : 'My projects'}</strong><button className="icon-button" aria-label={fr ? 'Créer un projet' : 'Create a project'} disabled={disabled || saving} onClick={() => edit()}><Plus size={17} /></button></div>
    {[{ id: '', name: fr ? 'Toutes les discussions' : 'All conversations' }, { id: 'unfiled', name: fr ? 'Sans projet' : 'Unfiled' }, ...projects].map(item => <button className={`conversation-link ${selected === item.id ? 'selected' : ''}`} key={item.id} aria-pressed={selected === item.id} disabled={disabled || saving} onClick={() => onSelect(item.id)}><Folder size={15} /><span>{item.name}</span></button>)}
    {current && <><p className="subtle">{current.instructions || (fr ? 'Ajoutez le contexte et les consignes de ce projet.' : 'Add context and instructions for this project.')}</p><button className="text-button" disabled={disabled || saving} onClick={() => edit(current)}>{fr ? 'Modifier le projet' : 'Edit project'}</button></>}
    {editing !== null && <ProjectDialog language={language} disabled={saving} close={() => setEditing(null)}><form className="project-editor" onSubmit={async event => {
      event.preventDefault(); if (saving) return; setSaving(true);
      try {
        const item = await api<Project>(base + '/projects' + (editing ? '/' + editing : ''), { name, instructions }, editing ? 'PUT' : 'POST');
        onProjects([...projects.filter(value => value.id !== item.id), item].sort((a, b) => a.name.localeCompare(b.name)));
        onSelect(item.id); setEditing(null);
      } catch (error) { onError(error); } finally { setSaving(false); }
    }}>
      <label htmlFor="project-name">{fr ? 'Nom du projet' : 'Project name'}</label><input id="project-name" value={name} onChange={event => setName(event.target.value)} required maxLength={160} placeholder={fr ? 'Ex. Client Dupont' : 'E.g. Client Acme'} />
      <label htmlFor="project-instructions">{fr ? 'Contexte et consignes' : 'Context and instructions'}</label><textarea id="project-instructions" value={instructions} onChange={event => setInstructions(event.target.value)} maxLength={8000} rows={4} placeholder={fr ? 'Objectif, public, ton souhaité, points à respecter…' : 'Goal, audience, tone, requirements…'} />
      <p className="subtle">{fr ? 'Ces consignes accompagnent les nouvelles discussions du projet. Les discussions existantes conservent leur contexte initial. Le projet reste personnel.' : 'These instructions apply to new project conversations. Existing conversations keep their original context. This project stays personal.'}</p>
      <button className="primary" disabled={saving || !name.trim()}>{fr ? 'Enregistrer le projet' : 'Save project'}</button><button type="button" className="text-button" disabled={saving} onClick={() => setEditing(null)}>{fr ? 'Annuler' : 'Cancel'}</button>
    </form></ProjectDialog>}
  </div>;
}

export function ConversationOrganizer({ title, projectId, archived, projects, language, disabled, onSave }: { title: string; projectId?: string | null; archived?: boolean; projects: Project[]; language: Language; disabled: boolean; onSave: (value: { title: string; project_id: string | null; archived: boolean }) => Promise<void> }) {
  const fr = language === 'fr';
  const [editing, setEditing] = useState(false), [name, setName] = useState(title), [project, setProject] = useState(projectId || '');
  return <div className="conversation-organizer">
    <h2>{title}</h2>
    <button className="text-button" disabled={disabled} onClick={() => { setName(title); setProject(projectId || ''); setEditing(!editing); }}>{fr ? 'Organiser' : 'Organize'}</button>
    {editing && <form onSubmit={async event => { event.preventDefault(); await onSave({ title: name, project_id: project || null, archived: !!archived }); }}>
      <label htmlFor="conversation-title">{fr ? 'Titre de la discussion' : 'Conversation title'}</label><input id="conversation-title" value={name} onChange={event => setName(event.target.value)} required maxLength={160} />
      <label htmlFor="conversation-project">{fr ? 'Classer dans un projet' : 'Move to project'}</label><select id="conversation-project" value={project} onChange={event => setProject(event.target.value)}><option value="">{fr ? 'Sans projet' : 'Unfiled'}</option>{projects.map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select>
      <p className="subtle">{fr ? 'Le classement ne modifie pas le contexte des messages déjà échangés.' : 'Moving a conversation does not change its existing message context.'}</p>
      <button type="button" className="text-button" onClick={() => setEditing(false)}>{fr ? 'Fermer' : 'Close'}</button>
      <button className="secondary" disabled={disabled || !name.trim()}>{fr ? 'Enregistrer' : 'Save'}</button>
      <button type="button" className="text-button" disabled={disabled} onClick={() => onSave({ title, project_id: projectId || null, archived: !archived })}>{fr ? archived ? 'Restaurer la discussion' : 'Archiver la discussion' : archived ? 'Restore conversation' : 'Archive conversation'}</button>
    </form>}
  </div>;
}
