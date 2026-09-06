import { useRef, useState } from 'react';
import { ArrowRight, Mail } from 'lucide-react';
import { api, ApiError } from './api';
import { Notice, useAction } from './feedback';
import type { Language, Text } from './locale';

export interface InvitationReceipt { id: string; email: string; revoked?: boolean; accepted?: boolean; delivery_status?: 'manual' | 'sending' | 'submitted' | 'unknown' }
export const invitationWords = {
  fr: { send: 'Envoyer l’invitation', language: 'Langue de l’e-mail', retry: 'Vérifier le même envoi', another: 'Inviter une autre personne', pending: 'La réponse a été interrompue. Vérifiez cet envoi avant de créer une autre invitation.', manual: 'Lien créé à partager', sending: 'Envoi en cours', submitted: 'E-mail transmis · en attente d’acceptation', unknown: 'Envoi à vérifier avec le destinataire', detail: 'Si l’e-mail n’arrive pas, annulez cette invitation avant d’en créer une nouvelle.' },
  en: { send: 'Send invitation', language: 'Email language', retry: 'Check the same delivery', another: 'Invite another person', pending: 'The response was interrupted. Check this delivery before creating another invitation.', manual: 'Link created for sharing', sending: 'Sending', submitted: 'Email submitted · awaiting acceptance', unknown: 'Check delivery with the recipient', detail: 'If the email does not arrive, cancel this invitation before creating another one.' },
};

export function InvitationForm({ base, t, language, disabled, done, revokedId }: { base: string; t: Text; language: Language; disabled: boolean; done: () => Promise<void>; revokedId?: string }) {
  const [email, setEmail] = useState(''), [mailLanguage, setMailLanguage] = useState<Language>(language);
  const [receipt, setReceipt] = useState<InvitationReceipt | null>(null), [uncertain, setUncertain] = useState(false);
  const request = useRef<{ request_id: string; email: string; language: Language } | null>(null);
  const action = useAction(t), words = invitationWords[language];
  const closed = receipt && (receipt.revoked || receipt.accepted || receipt.id === revokedId);
  const receiptTitle = receipt && ((receipt.revoked || receipt.id === revokedId) ? (language === 'fr' ? 'Invitation annulée' : 'Invitation cancelled') : receipt.accepted ? (language === 'fr' ? 'Invitation acceptée' : 'Invitation accepted') : words[receipt.delivery_status ?? 'manual']);
  return <div className="invite-panel"><div className="icon-tile"><Mail /></div>
    <Notice>{action.error}</Notice>
    {receipt ? <><h2>{receiptTitle}</h2>{!closed && <p>{words.detail}</p>}{!closed && ['sending', 'unknown'].includes(receipt.delivery_status ?? '') && <button className="secondary" disabled={disabled || action.busy} onClick={() => action.run(async () => { if (request.current) { setReceipt(await api<InvitationReceipt>(base + '/invitations/email', request.current)); await done(); } })}>{words.retry}</button>}<button className="text-button" onClick={() => { setReceipt(null); setEmail(''); request.current = null; }}>{words.another}</button></> :
      <form onSubmit={event => { event.preventDefault(); void action.run(async () => {
        const body = request.current ?? { request_id: crypto.randomUUID(), email, language: mailLanguage };
        request.current = body;
        try {
          const result = await api<InvitationReceipt>(base + '/invitations/email', body);
          setReceipt(result); setUncertain(false); await done();
        } catch (cause) {
          const lost = !(cause instanceof ApiError) || cause.status === 0 || (cause.status >= 500 && cause.code !== 'transactional_mail_not_configured');
          setUncertain(lost); if (!lost) request.current = null;
          throw cause;
        }
      }); }}>
        <label htmlFor="invite-email">{t.inviteEmail}</label><input id="invite-email" type="email" value={email} onChange={e => setEmail(e.target.value)} disabled={disabled || action.busy || uncertain} required maxLength={320} autoComplete="email" />
        <label htmlFor="invite-language">{words.language}</label><select id="invite-language" value={mailLanguage} disabled={disabled || action.busy || uncertain} onChange={e => setMailLanguage(e.target.value as Language)}><option value="fr">Français</option><option value="en">English</option></select>
        {uncertain && <p>{words.pending}</p>}
        <button className="primary" disabled={disabled || action.busy}>{action.busy ? t.inviting : uncertain ? words.retry : words.send}<ArrowRight size={17} /></button>
      </form>}
  </div>;
}
