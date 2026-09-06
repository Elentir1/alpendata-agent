import { useEffect, useId, useRef, useState } from 'react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';
import { resourceWords } from './resourceTypes';
import type { CompanyResource, ResourceMember, ResourcePublication } from './resourceTypes';

export function CompanyResourceEditor({ path, item, mode, members, language, sourceDocument, done, close, closeLabel }: {
  path: string; item: CompanyResource | null; mode: 'content' | 'access'; members: ResourceMember[];
  language: Language; done: () => void; close: () => void;
  sourceDocument?: { id: string; filename: string };
  closeLabel?: string;
}) {
  const t = resourceWords[language], id = useId();
  const [title, setTitle] = useState(item?.title || sourceDocument?.filename.slice(0, 160) || ''), [kind, setKind] = useState(item?.kind || (sourceDocument ? 'document' : 'note'));
  const [text, setText] = useState(item?.text || ''), [file, setFile] = useState<File | null>(null);
  const [audience, setAudience] = useState(item?.audience || 'selected');
  const [grants, setGrants] = useState((item?.member_ids || []).filter(uid => members.some(m => m.user_id === uid && m.active && m.role !== 'admin')));
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false);
  const [error, setError] = useState(''), [recovery, setRecovery] = useState(false);
  const pending = useRef<ResourcePublication | null>(null), sending = useRef(false);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const accessOnly = mode === 'access';
  function edit(change: () => void) { change(); setConfirmed(false); }
  async function save() {
    if (sending.current || !confirmed || recovery && (item !== null || !pending.current)) return;
    sending.current = true; setBusy(true); setError('');
    try {
      let body: ResourcePublication | { version: number; audience: string; member_ids: string[]; confirmed: true };
      if (accessOnly && item) {
        body = { version: item.version, audience, member_ids: audience === 'team' ? [] : grants, confirmed: true };
      } else {
        if (!pending.current) {
          let document: ResourcePublication['document'];
          if (kind === 'document' && !sourceDocument) {
            if (!file || file.size > 5 * 1024 * 1024 || !/\.(pdf|docx|xlsx|pptx)$/i.test(file.name)) throw new ApiError(400, 'document_format_invalid');
            const bytes = new Uint8Array(await file.arrayBuffer());
            if (!alive.current) return;
            const chunks: string[] = [];
            for (let i = 0; i < bytes.length; i += 8192) chunks.push(String.fromCharCode(...bytes.subarray(i, i + 8192)));
            document = { filename: file.name, content_base64: btoa(chunks.join('')) };
          }
          pending.current = { title: title.trim(), kind, text: kind === 'note' ? text.trim() : '', document, ...(sourceDocument ? { source_document_id: sourceDocument.id } : {}),
            audience, member_ids: audience === 'team' ? [] : grants, confirmed: true,
            ...(item ? { version: item.version } : { request_id: crypto.randomUUID() }) };
        }
        body = pending.current;
      }
      await api(path + (item ? '/' + item.id + (accessOnly ? '/access' : '') : ''), body, item ? accessOnly ? 'PATCH' : 'PUT' : 'POST');
      if (alive.current) done();
    } catch (cause) {
      if (!alive.current) return;
      const apiError = cause instanceof ApiError ? cause : null;
      const uncertain = !apiError || apiError.status === 0 || apiError.status >= 500;
      const conflict = apiError?.status === 409;
      setRecovery(uncertain || conflict || [401, 403, 404].includes(apiError?.status || 0));
      setError(uncertain ? item ? t.uncertain : t.retryHint : conflict ? apiError?.code === 'company_resource_storage_full' ? t.quota : t.changed : t.invalid);
      if (!uncertain) pending.current = null;
    } finally { sending.current = false; if (alive.current) setBusy(false); }
  }
  return <form className="resource-editor" aria-label={accessOnly ? t.access : item ? t.edit : t.add} onSubmit={event => { event.preventDefault(); void save(); }}>
    <h3>{accessOnly ? t.access : item ? t.edit : t.add}{item && ` · ${item.title}`}</h3>
    <fieldset disabled={busy || recovery}>
      {!accessOnly && <>
        <label htmlFor={id + 'title'}>{t.name}</label><input id={id + 'title'} value={title} onChange={event => edit(() => setTitle(event.target.value))} required maxLength={160} />
        {sourceDocument ? <p>{t.source} : <strong>{sourceDocument.filename}</strong></p> : <><label htmlFor={id + 'kind'}>{t.kind}</label><select id={id + 'kind'} value={kind} onChange={event => edit(() => setKind(event.target.value as 'note' | 'document'))}><option value="note">{t.note}</option><option value="document">{t.document}</option></select></>}
        {kind === 'note' ? <><label htmlFor={id + 'text'}>{t.text}</label><textarea id={id + 'text'} value={text} onChange={event => edit(() => setText(event.target.value))} required maxLength={20000} rows={6} /></> : !sourceDocument && <><p>{t.formats}</p><label htmlFor={id + 'file'}>{t.file}</label><input id={id + 'file'} type="file" accept=".pdf,.docx,.xlsx,.pptx" required onChange={event => edit(() => setFile(event.target.files?.[0] || null))} /></>}
      </>}
      <label htmlFor={id + 'audience'}>{t.audience}</label><select id={id + 'audience'} value={audience} onChange={event => edit(() => setAudience(event.target.value as 'team' | 'selected'))}><option value="selected">{t.selected}</option><option value="team">{t.team}</option></select>
      {audience === 'selected' && <div className="resource-grants">{members.filter(m => m.active && m.role !== 'admin').map(m => <label key={m.user_id}><input type="checkbox" checked={grants.includes(m.user_id)} onChange={event => edit(() => setGrants(current => event.target.checked ? [...current, m.user_id] : current.filter(uid => uid !== m.user_id)))} />{m.display_name}</label>)}{!grants.length && <p>{t.onlyAdmins}</p>}</div>}
      <p className="subtle">{t.admin}</p>
      <label className="resource-confirm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} required />{accessOnly ? t.confirmAccess : t.confirm}</label>
    </fieldset>
    <Notice>{error}</Notice>
    <div className="resource-actions">
      <button className="primary" disabled={busy || !confirmed || recovery && (item !== null || !pending.current) || !accessOnly && (!title.trim() || kind === 'note' && !text.trim())}>{busy ? t.busy : recovery && !item ? t.retry : item ? t.save : t.publish}</button>
      <button className="secondary" type="button" disabled={busy} onClick={close}>{closeLabel || (recovery ? t.reload : t.close)}</button>
    </div>
  </form>;
}
