import { useEffect, useState } from 'react';
import { api } from './api';
import { CompanyResourceEditor } from './CompanyResourceEditor';
import type { DocumentReceipt } from './Documents';
import type { Language } from './locale';
import { Notice } from './feedback';
import type { ResourceMember } from './resourceTypes';
import { resourceWords } from './resourceTypes';

interface Directory { current_user_id: string; members: ResourceMember[] }
export function DocumentShare({ item, organizationId, language, close }: { item: DocumentReceipt; organizationId: string; language: Language; close: () => void }) {
  const t = resourceWords[language], path = `/api/organizations/${encodeURIComponent(organizationId)}/company-resources`;
  const [directory, setDirectory] = useState<Directory | null>(null), [error, setError] = useState(false), [saved, setSaved] = useState(false), [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setError(false); setDirectory(null);
    api<Directory>(path + '/recipients').then(value => { if (active) setDirectory(value); }).catch(() => { if (active) setError(true); });
    return () => { active = false; };
  }, [path, attempt]);
  return <section className="document-share" aria-label={t.share}>
    <h3>{t.share}</h3><p>{t.personalCopy}</p><p className="subtle">{t.effect}</p>
    <Notice success>{saved ? t.shared : ''}</Notice>
    {saved ? <button className="secondary" onClick={close}>{t.close}</button> : directory ? <CompanyResourceEditor path={path} item={null} mode="content" sourceDocument={item} members={directory.members.filter(m => m.user_id !== directory.current_user_id)} language={language} done={() => setSaved(true)} close={close} closeLabel={t.close} /> : <>
      {error ? <><Notice>{t.failed}</Notice><button className="secondary" onClick={() => setAttempt(value => value + 1)}>{t.reload}</button></> : <p role="status">{t.loading}</p>}
      <button className="secondary" onClick={close}>{t.close}</button>
    </>}
  </section>;
}
