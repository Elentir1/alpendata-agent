import { useEffect, useId, useRef, useState } from 'react';
import { api, ApiError } from './api';
import type { Language } from './locale';

interface Message { to: string[]; cc: string[]; bcc: string[]; subject: string; body: string; attachment_ids: string[] }
interface Attempt { id: string; version: number; status: string; error_code: string | null }
export interface EmailReceipt {
  id: string; version: number; message: Message; editable: boolean;
  attachments: { id: string; filename: string; size: number }[]; attempts: Attempt[];
}
const words = {
  fr: {
    title: 'Brouillon de mail', private: 'Ce brouillon reste dans AlpenData. Relisez les destinataires, le contenu et les pièces jointes avant de l’envoyer depuis votre compte Microsoft.',
    to: 'À', cc: 'Copie', bcc: 'Copie cachée', subject: 'Objet', body: 'Message', addresses: 'Séparez les adresses par une virgule ou un point-virgule.',
    save: 'Enregistrer le brouillon', send: 'Envoyer ce mail', confirm: 'J’ai vérifié les destinataires, le message et les pièces jointes.',
    saved: 'Le brouillon est enregistré. Vous pouvez maintenant confirmer son envoi.', dirty: 'Enregistrez vos modifications avant de confirmer l’envoi.',
    attachments: 'Pièces jointes', remove: 'Retirer', reload: 'Vérifier l’état actuel', working: 'Traitement…',
    sending: 'La demande d’envoi est en cours. Ne préparez pas un nouvel envoi de ce message.',
    accepted: 'Microsoft a accepté la demande d’envoi. Cela ne confirme pas la livraison au destinataire.',
    unknown: 'Le résultat de l’envoi est incertain. Vérifiez vos éléments envoyés dans Outlook avant toute nouvelle action. AlpenData ne renverra pas ce message automatiquement.',
    failed: 'L’envoi n’a pas été accepté. Vérifiez vos accès Microsoft et les règles de votre entreprise, puis enregistrez de nouveau le brouillon pour autoriser une nouvelle tentative.',
    error: 'L’opération n’a pas pu être confirmée. Vérifiez l’état actuel avant de continuer.',
    changed: 'Ce brouillon a changé ailleurs. Rechargez sa version actuelle avant de continuer.',
    permission: 'L’envoi exige l’autorisation de votre entreprise et l’accès « Envoyer mes mails » dans vos outils Microsoft.',
    invalid: 'Vérifiez les adresses et les champs du message. Les pièces jointes sont limitées à 2 Mo au total.',
  },
  en: {
    title: 'Email draft', private: 'This draft stays in AlpenData. Review recipients, content and attachments before sending it from your Microsoft account.',
    to: 'To', cc: 'Cc', bcc: 'Bcc', subject: 'Subject', body: 'Message', addresses: 'Separate addresses with a comma or semicolon.',
    save: 'Save email draft', send: 'Send this email', confirm: 'I have reviewed the recipients, message and attachments.',
    saved: 'The draft has been saved. You can now confirm sending it.', dirty: 'Save your changes before confirming the send.',
    attachments: 'Attachments', remove: 'Remove', reload: 'Check current status', working: 'Working…',
    sending: 'The send request is in progress. Do not prepare another send of this message.',
    accepted: 'Microsoft accepted the send request. This does not confirm delivery to the recipient.',
    unknown: 'The send outcome is uncertain. Check your Sent Items in Outlook before taking further action. AlpenData will not resend this message automatically.',
    failed: 'The send was not accepted. Check your Microsoft access and company rules, then save the draft again to authorize a new attempt.',
    error: 'The operation could not be confirmed. Check the current status before continuing.',
    changed: 'This draft changed elsewhere. Reload the current version before continuing.',
    permission: 'Sending requires your company’s permission and “Send my email” access in your Microsoft tools.',
    invalid: 'Check recipient addresses and message fields. Attachments are limited to 2 MB in total.',
  },
};
const fields = (message: Message) => ({ ...message, to: message.to.join(', '), cc: message.cc.join(', '), bcc: message.bcc.join(', ') });
const addresses = (value: string) => value.split(/[,;\n]/).map(item => item.trim()).filter(Boolean);

export function EmailDraft({ item, organizationId, language, licensed }: { item: EmailReceipt; organizationId: string; language: Language; licensed: boolean }) {
  const t = words[language], id = useId(), path = `/api/organizations/${encodeURIComponent(organizationId)}/emails/${encodeURIComponent(item.id)}`;
  const [receipt, setReceipt] = useState(item), [draft, setDraft] = useState(() => fields(item.message));
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false);
  const inFlight = useRef(false), mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const message: Message = { ...draft, to: addresses(draft.to), cc: addresses(draft.cc), bcc: addresses(draft.bcc) };
  const dirty = JSON.stringify(message) !== JSON.stringify(receipt.message);
  const latest = receipt.attempts.at(-1), sameAttempt = latest?.version === receipt.version;
  const editable = receipt.editable && licensed && !busy && !error;
  function accept(value: EmailReceipt) { setReceipt(value); setDraft(fields(value.message)); setConfirmed(false); }
  async function refresh() {
    const value = await api<EmailReceipt>(path);
    if (mounted.current) { accept(value); setError(''); }
  }
  useEffect(() => {
    if (latest?.status !== 'sending') return;
    const timer = window.setInterval(() => { void api<EmailReceipt>(path).then(value => {
      if (mounted.current) setReceipt(value);
    }).catch(() => { if (mounted.current) setError('request_failed'); }); }, 3000);
    return () => window.clearInterval(timer);
  }, [path, latest?.status]);
  async function act(action: 'save' | 'send' | 'reload') {
    if (inFlight.current) return;
    inFlight.current = true; setBusy(true); setSaved(false);
    try {
      if (action === 'reload') await refresh();
      else {
        const value = action === 'save'
          ? await api<EmailReceipt>(path, { version: receipt.version, message }, 'PATCH')
          : await api<EmailReceipt>(path + '/send', { version: receipt.version, confirmed: true });
        if (mounted.current) { accept(value); setError(''); setSaved(action === 'save'); }
      }
    } catch (cause) {
      if (mounted.current) { setError(cause instanceof ApiError ? cause.code : 'request_failed'); setConfirmed(false); }
      // A lost POST response never enables a second POST. Only inspect its receipt.
      if (action === 'send') { try { await refresh(); } catch { /* Keep the uncertainty visible. */ } }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const statusText: Record<string, string> = { sending: t.sending, accepted: t.accepted, unknown: t.unknown, failed: t.failed };
  return <section className="email-draft" aria-labelledby={id}>
    <h3 id={id}>{t.title}</h3><p>{t.private}</p>
    <fieldset disabled={!editable}>
      {(['to', 'cc', 'bcc'] as const).map(key => <label key={key}>{t[key]}<input value={draft[key]} onChange={event => { setDraft({ ...draft, [key]: event.target.value }); setConfirmed(false); setSaved(false); }} aria-describedby={id + '-addresses'} /></label>)}
      <p id={id + '-addresses'} className="subtle">{t.addresses}</p>
      <label>{t.subject}<input required maxLength={998} value={draft.subject} onChange={event => { setDraft({ ...draft, subject: event.target.value }); setConfirmed(false); setSaved(false); }} /></label>
      <label>{t.body}<textarea required maxLength={32000} rows={9} value={draft.body} onChange={event => { setDraft({ ...draft, body: event.target.value }); setConfirmed(false); setSaved(false); }} /></label>
      {draft.attachment_ids.length > 0 && <div><h4>{t.attachments}</h4><ul>{receipt.attachments.filter(file => draft.attachment_ids.includes(file.id)).map(file => <li key={file.id}>{file.filename} <button type="button" className="secondary" onClick={() => { setDraft({ ...draft, attachment_ids: draft.attachment_ids.filter(value => value !== file.id) }); setConfirmed(false); }}>{t.remove} {file.filename}</button></li>)}</ul></div>}
    </fieldset>
    {latest && <p role="status">{statusText[latest.status]}</p>}
    {receipt.editable && licensed && <>
      <button type="button" className="secondary" disabled={!editable || (!dirty && !sameAttempt)} onClick={() => void act('save')}>{t.save}</button>
      {dirty && <p>{t.dirty}</p>}{saved && <p role="status">{t.saved}</p>}
      <p className="subtle">{t.permission}</p>
      <label className="email-confirm"><input type="checkbox" checked={confirmed} disabled={!editable || dirty || sameAttempt} onChange={event => setConfirmed(event.target.checked)} /><span>{t.confirm}</span></label>
      <button type="button" className="primary" disabled={!editable || dirty || sameAttempt || !confirmed} onClick={() => void act('send')}>{busy ? t.working : t.send}</button>
    </>}
    {error && <p role="alert">{error === 'email_draft_changed' ? t.changed : error === 'request_failed' || error === 'email_attachments_too_large' ? t.invalid : t.error}</p>}
    <button type="button" className="secondary" disabled={busy} onClick={() => void act('reload')}>{t.reload}</button>
  </section>;
}
