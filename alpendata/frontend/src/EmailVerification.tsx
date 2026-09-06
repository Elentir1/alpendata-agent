import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';
import type { EmailReceipt } from './EmailDraft';
import type { Language } from './locale';

interface Verification {
  status: 'found' | 'not_found'; checked_at: number; searched: number; partial: boolean; match_count: number;
  copy: { item_id: string; url: string | null; sent_at: string } | null;
}
export interface EmailAttemptReceipt {
  id: string; version: number; status: string; error_code: string | null;
  initiator?: 'browser' | 'agent'; autonomy_version?: number | null;
  can_verify?: boolean; verification?: Verification | null;
}
const words = {
  fr: {
    title: 'Vérification des éléments envoyés', check: 'Rechercher une copie envoyée', working: 'Recherche…',
    intro: 'Consulte vos éléments envoyés avec votre accès personnel de lecture des mails. Aucun message ne sera envoyé.',
    found: 'Une copie correspondante a été retrouvée dans vos éléments envoyés. Cela ne confirme pas la livraison au destinataire.',
    absent: 'Aucune copie correspondante dans la sélection consultée. Cela ne prouve pas que le mail n’a pas été envoyé. Attendez puis vérifiez de nouveau, ou consultez Outlook.',
    checked: 'Vérification du', count: 'Messages consultés :', partial: 'La recherche est limitée aux 100 messages les plus récents depuis la tentative. D’autres messages peuvent exister.',
    duplicates: 'Plusieurs copies correspondent à cette tentative. Vérifiez-les dans Outlook avant toute action.',
    open: 'Ouvrir la copie dans Outlook', permission: 'Autorisez « Mes mails » dans vos outils Microsoft pour effectuer cette vérification.',
    company: 'La lecture des mails est limitée par votre entreprise. Votre administrateur peut modifier cette règle.',
    reconnect: 'Reconnectez vos outils Microsoft avant de vérifier les éléments envoyés.',
    unavailable: 'Cette tentative ne permet pas de vérification automatique. Consultez vos éléments envoyés dans Outlook.',
    failed: 'La vérification n’a pas abouti. Le résultat de l’envoi reste inchangé. Vous pouvez réessayer cette recherche.',
  },
  en: {
    title: 'Sent Items check', check: 'Find a sent copy', working: 'Searching…',
    intro: 'Reads your Sent Items using your personal email access. No message will be sent.',
    found: 'A matching copy was found in your Sent Items. This does not confirm delivery to the recipient.',
    absent: 'No matching copy in the selection checked. This does not prove the email was not sent. Wait and check again, or consult Outlook.',
    checked: 'Checked on', count: 'Messages checked:', partial: 'The search covers the 100 most recent messages since the attempt. Other messages may exist.',
    duplicates: 'More than one copy matches this attempt. Check them in Outlook before taking any action.',
    open: 'Open the copy in Outlook', permission: 'Allow “My email” in your Microsoft tools to run this check.',
    company: 'Your company restricts email reading. Your administrator can change this rule.',
    reconnect: 'Reconnect your Microsoft tools before checking Sent Items.',
    unavailable: 'This attempt cannot be checked automatically. Consult your Sent Items in Outlook.',
    failed: 'The check could not finish. The send outcome is unchanged. You can try this search again.',
  },
};

export function EmailVerification({ attempt, path, language, licensed, onUpdated }: {
  attempt: EmailAttemptReceipt; path: string; language: Language; licensed: boolean; onUpdated: (receipt: EmailReceipt) => void;
}) {
  const t = words[language], [busy, setBusy] = useState(false), [error, setError] = useState('');
  const inFlight = useRef(false), verification = attempt.verification;
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { setError(''); }, [verification]);
  const errors: Record<string, string> = {
    microsoft_permission_required: t.permission, company_policy_denied: t.company,
    microsoft_reconnect_required: t.reconnect, email_verification_unavailable: t.unavailable,
  };
  if (!['accepted', 'unknown'].includes(attempt.status) && !verification) return null;
  return <section className="email-verification" aria-label={t.title}>
    <h4>{t.title}</h4>
    {verification && <>
      <p role="status">{verification.status === 'found' ? t.found : t.absent}</p>
      <p className="subtle">{t.checked} {new Date(verification.checked_at * 1000).toLocaleString(language === 'fr' ? 'fr-CH' : 'en-GB')} · {t.count} {verification.searched}</p>
      {verification.status !== 'found' && verification.partial && <p>{t.partial}</p>}
      {verification.match_count > 1 && <p>{t.duplicates}</p>}
      {verification.copy?.url?.startsWith('https://') && <a href={verification.copy.url} target="_blank" rel="noopener noreferrer">{t.open}</a>}
    </>}
    {verification?.status !== 'found' && (attempt.can_verify ? <>
      <p>{t.intro}</p>
      {licensed && <button type="button" className="secondary" disabled={busy} onClick={async () => {
        if (inFlight.current) return;
        inFlight.current = true; setBusy(true); setError('');
        try { const value = await api<EmailReceipt>(path + '/attempts/' + encodeURIComponent(attempt.id) + '/verify', {}); if (mounted.current) onUpdated(value); }
        catch (cause) { if (mounted.current) setError(cause instanceof ApiError ? cause.code : 'request_failed'); }
        finally { inFlight.current = false; if (mounted.current) setBusy(false); }
      }}>{busy ? t.working : t.check}</button>}
    </> : <p>{t.unavailable}</p>)}
    {error && <p role="alert">{errors[error] || t.failed}</p>}
  </section>;
}
