import { useEffect, useId, useRef, useState } from 'react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';
import { CompanyResourceEditor } from './CompanyResourceEditor';
import { resourceWords } from './resourceTypes';
import type { CompanyResource, ResourceMember } from './resourceTypes';

interface ResourcePage { resources: CompanyResource[]; next_offset: number | null }
interface Props { organizationId: string; userId: string; admin: boolean; language: Language }
export function CompanyResources(props: Props) {
  return <Resources key={`${props.organizationId}:${props.userId}:${props.admin}`} {...props} />;
}
function Resources({ organizationId, language, userId }: Props) {
  const t = resourceWords[language], id = useId(), base = `/api/organizations/${encodeURIComponent(organizationId)}`;
  const path = base + '/company-resources';
  const [page, setPage] = useState<ResourcePage | null>(null), [selected, setSelected] = useState<CompanyResource | null>(null);
  const [members, setMembers] = useState<ResourceMember[]>([]), [editor, setEditor] = useState<'content' | 'access' | null>(null);
  const [query, setQuery] = useState(''), [filter, setFilter] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false), [remove, setRemove] = useState(false);
  const pending = useRef(false), alive = useRef(true), downloadRequest = useRef<AbortController | null>(null);
  useEffect(() => { alive.current = true; return () => { alive.current = false; downloadRequest.current?.abort(); }; }, []);
  async function run(work: () => Promise<void>, mutation = false) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError('');
    try { await work(); } catch (cause) {
      if (!alive.current) return;
      setSelected(null); setEditor(null);
      const status = cause instanceof ApiError ? cause.status : 0;
      if ([401, 403, 404].includes(status)) setPage(null);
      setError(status === 404 ? t.missing : status === 409 ? t.changed : mutation ? t.uncertain : t.failed);
    } finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  async function load(offset = 0, search = filter) {
    setSelected(null); setEditor(null); setRemove(false);
    await run(async () => {
      const response = await api<ResourcePage>(`${path}?query=${encodeURIComponent(search)}&before=${offset}`);
      if (!alive.current) return;
      setPage(current => ({ ...response, resources: offset ? [...(current?.resources || []), ...response.resources.filter(item => !current?.resources.some(existing => existing.id === item.id))] : response.resources }));
      setFilter(search);
    });
  }
  async function read(item: CompanyResource) {
    setSelected(null); setEditor(null); setRemove(false); setSaved(false);
    await run(async () => {
      const response = await api<CompanyResource>(path + '/' + item.id);
      if (alive.current) setSelected(response);
    });
  }
  async function edit(mode: 'content' | 'access', create = false) {
    setSaved(false); setRemove(false);
    if (create) setSelected(null);
    await run(async () => {
      const response = await api<{ members: ResourceMember[] }>(path + '/recipients');
      if (alive.current) { setMembers(response.members); setEditor(mode); }
    });
  }
  async function download(item: CompanyResource) {
    await run(async () => {
      const controller = new AbortController(); downloadRequest.current = controller;
      const response = await fetch(path + '/' + item.id + '/download?version=' + item.version, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new ApiError(response.status, 'download_failed');
      if (response.headers.get('content-type')?.split(';')[0] !== item.media_type) throw new Error('Unexpected file type');
      const content = await response.blob();
      if (!alive.current) return;
      const url = URL.createObjectURL(content), link = document.createElement('a');
      link.href = url; link.download = item.filename || 'document'; document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000); downloadRequest.current = null;
    });
  }
  return <details className="company-resources" onToggle={event => { if (event.currentTarget.open && !page && !error) void load(); }}>
    <summary>{t.title}</summary><p>{t.intro}</p><p>{t.personalCopy}</p><p className="subtle">{t.effect}</p>
    <form className="resource-search" onSubmit={event => { event.preventDefault(); void load(0, query); }}><label htmlFor={id}>{t.search}</label><div className="resource-actions"><input id={id} value={query} maxLength={160} onChange={event => setQuery(event.target.value)} /><button className="secondary" disabled={busy || !!editor}>{t.find}</button></div></form>
    <div className="resource-actions"><button className="secondary" disabled={busy || !!editor} onClick={() => void load()}>{t.reload}</button><button className="primary" disabled={busy || !!editor} onClick={() => void edit('content', true)}>{t.add}</button></div>
    {busy && <p role="status">{t.loading}</p>}<Notice>{error}</Notice><Notice success>{saved ? t.saved : ''}</Notice>
    {page && !page.resources.length && <p>{t.empty}</p>}
    <ul className="resource-list">{page?.resources.map(item => <li key={item.id}><div><strong>{item.title}</strong><small>{item.kind === 'note' ? t.note : item.filename} · v{item.version}</small></div><button className="secondary" disabled={busy || !!editor} onClick={() => void read(item)} aria-label={`${t.open} ${item.title}`}>{t.open}</button></li>)}</ul>
    {page?.next_offset != null && <button className="secondary" disabled={busy || !!editor} onClick={() => void load(page.next_offset!)}>{t.more}</button>}
    {selected && !editor && <section className="resource-detail" aria-label={selected.title}>
      <h3>{selected.title} · v{selected.version}</h3>
      {selected.kind === 'note' ? <p className="resource-note">{selected.text}</p> : <><p>{selected.filename} · {Math.ceil(selected.size / 1024)} {language === 'fr' ? 'Ko' : 'KB'}</p><button className="secondary" disabled={busy} onClick={() => void download(selected)}>{t.download}</button></>}
      {selected.can_manage && <><div className="resource-actions"><button className="secondary" disabled={busy} onClick={() => void edit('content')}>{t.edit}</button><button className="secondary" disabled={busy} onClick={() => void edit('access')}>{t.access}</button></div>
        <label className="resource-confirm"><input type="checkbox" checked={remove} disabled={busy} onChange={event => setRemove(event.target.checked)} />{t.confirmRemove}</label><button className="text-button" disabled={busy || !remove} onClick={() => void run(async () => { await api(path + '/' + selected.id, { version: selected.version }, 'DELETE'); if (alive.current) { setPage(current => current && { ...current, resources: current.resources.filter(item => item.id !== selected.id) }); setSelected(null); setRemove(false); } }, true)}>{t.remove}</button></>}
    </section>}
    {editor && <CompanyResourceEditor key={`${selected?.id || 'new'}:${selected?.version || 0}:${editor}`} path={path} item={selected} mode={editor} members={members.filter(m => m.user_id !== (selected?.created_by || userId))} language={language} done={() => { if (alive.current) { setSaved(true); void load(); } }} close={() => void load()} />}
  </details>;
}
