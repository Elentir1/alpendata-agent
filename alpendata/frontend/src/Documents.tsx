import { useEffect, useRef, useState } from 'react';
import { Download, FileText } from 'lucide-react';
import type { Language } from './locale';
import { SharePointSave } from './SharePointSave';
import { DocumentShare } from './DocumentShare';

export interface DocumentReceipt { id: string; filename: string; size: number; media_type: string }

export function Documents({ items, organizationId, language }: { items: DocumentReceipt[]; organizationId: string; language: Language }) {
  const [busy, setBusy] = useState(''), [failed, setFailed] = useState(false);
  const [saving, setSaving] = useState<DocumentReceipt | null>(null);
  const [sharing, setSharing] = useState<DocumentReceipt | null>(null);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => { pending.current?.abort(); }, []);
  if (!items.length) return null;
  const fr = language === 'fr';

  async function download(item: DocumentReceipt) {
    if (pending.current) return;
    const controller = new AbortController(); pending.current = controller;
    setBusy(item.id); setFailed(false);
    try {
      const response = await fetch(`/api/organizations/${encodeURIComponent(organizationId)}/documents/${encodeURIComponent(item.id)}/download`, {
        credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
      });
      if (!response.ok || response.headers.get('content-type')?.split(';')[0] !== item.media_type) throw new Error('Download unavailable');
      const content = await response.blob();
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(content), link = document.createElement('a');
      link.href = url; link.download = item.filename;
      document.body.append(link); link.click(); link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    } finally {
      pending.current = null;
      if (!controller.signal.aborted) setBusy('');
    }
  }

  return <section className="chat-documents" aria-label={fr ? 'Documents créés' : 'Created documents'}>
    <strong>{fr ? 'Documents créés' : 'Created documents'}</strong>
    <ul>{items.map(item => <li key={item.id}><FileText size={18} aria-hidden="true" /><span>{item.filename}<small>{new Intl.NumberFormat(language, { maximumFractionDigits: 1 }).format(item.size / 1024)} {fr ? 'Ko' : 'KB'}</small></span><button type="button" className="secondary" disabled={!!busy} onClick={() => void download(item)} aria-label={`${fr ? 'Télécharger' : 'Download'} ${item.filename}`}><Download size={16} aria-hidden="true" />{busy === item.id ? '…' : fr ? 'Télécharger' : 'Download'}</button></li>)}</ul>
    {failed && <p role="alert">{fr ? 'Le téléchargement a échoué. Vérifiez votre connexion et réessayez.' : 'Download failed. Check your connection and try again.'}</p>}
    <div className="save-shortcuts">{items.map(item => <div className="document-actions" key={item.id}><button type="button" className="secondary" disabled={!!sharing} onClick={() => setSaving(item)}>{fr ? 'Enregistrer' : 'Save'} {item.filename} {fr ? 'dans Microsoft 365' : 'to Microsoft 365'}</button><button type="button" className="secondary" disabled={!!saving || !!sharing} onClick={() => setSharing(item)}>{fr ? 'Partager' : 'Share'} {item.filename} {fr ? 'dans l’entreprise' : 'with the company'}</button></div>)}</div>
    {saving && <SharePointSave key={saving.id} item={saving} organizationId={organizationId} language={language} onClose={() => setSaving(null)} />}
    {sharing && <DocumentShare key={sharing.id} item={sharing} organizationId={organizationId} language={language} close={() => setSharing(null)} />}
  </section>;
}
