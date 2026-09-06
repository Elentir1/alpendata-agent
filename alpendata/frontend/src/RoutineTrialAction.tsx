import { useId, useRef, useState } from 'react';
import { Play } from 'lucide-react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';
import type { Trial } from './FirstTasks';

export interface EmailDelivery { to: string[]; subject: string }
interface TrialIntent { request_id: string; email_delivery?: EmailDelivery; email_send_confirmed?: true }
interface Props {
  organizationId: string; proposalId: string; language: Language; disabled: boolean;
  sendsEmail?: boolean; initialDelivery?: EmailDelivery | null; label?: string;
  onOpen: (id: string) => void;
}

const words = {
  fr: {
    try: 'Tester maintenant', sending: 'Tester avec un envoi', preparing: 'Préparation…', retry: 'Retrouver cet essai',
    to: 'Destinataires', subject: 'Objet du briefing', placeholder: 'vous@entreprise.ch, collegue@entreprise.ch',
    note: 'Cet essai envoie un véritable e-mail depuis votre compte. Il ne programme aucune répétition. Le briefing est envoyé en texte, sans copie ni pièce jointe.',
    confirm: 'Je confirme ces destinataires et cet objet et demande un envoi unique pour cet essai.',
    changed: 'Modifier un destinataire ou l’objet après activation demandera un nouvel essai.',
    uncertain: 'La réception n’est pas confirmée. Retrouvez le même essai sans déclencher un deuxième envoi.',
    error: 'L’essai n’a pas pu démarrer. Réessayez.',
    access: 'Vérifiez vos outils et votre choix d’envoi direct dans « Mon espace », ainsi que les règles de votre entreprise.',
    busy: 'Votre assistant termine déjà une demande. Réessayez ensuite.',
  },
  en: {
    try: 'Try now', sending: 'Try with an email send', preparing: 'Preparing…', retry: 'Retrieve this trial',
    to: 'Recipients', subject: 'Briefing subject', placeholder: 'you@company.ch, colleague@company.ch',
    note: 'This trial sends a real email from your account. It does not schedule any recurrence. The briefing is sent as text, without copies or attachments.',
    confirm: 'I confirm these recipients and subject and request one email send for this trial.',
    changed: 'Changing recipients or the subject after activation will require a new trial.',
    uncertain: 'Receipt is not confirmed. Retrieve the same trial without triggering a second send.',
    error: 'The trial could not start. Try again.',
    access: 'Check your tools and direct sending choice in “My workspace”, and your company rules.',
    busy: 'Your assistant is already working on a request. Try again afterwards.',
  },
};

export function DeliverySummary({ delivery, language }: { delivery: EmailDelivery; language: Language }) {
  const c = words[language];
  return <div className="configuration-note"><p><strong>{c.to} :</strong> {delivery.to.join(', ')}</p><p><strong>{c.subject} :</strong> {delivery.subject}</p></div>;
}

export function RoutineTrialAction({ organizationId, proposalId, language, disabled, sendsEmail, initialDelivery, label, onOpen }: Props) {
  const c = words[language], id = useId();
  const [open, setOpen] = useState(false), [to, setTo] = useState(initialDelivery?.to.join(', ') || ''), [subject, setSubject] = useState(initialDelivery?.subject || '');
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const pending = useRef<TrialIntent | null>(null), sending = useRef(false);
  const locked = disabled || busy || !!pending.current;
  async function run() {
    if (sending.current) return;
    sending.current = true; setBusy(true); setError(null);
    const body = pending.current || { request_id: crypto.randomUUID(), ...(sendsEmail ? {
      email_delivery: { to: to.split(',').map(value => value.trim()), subject: subject.trim() }, email_send_confirmed: true as const,
    } : {}) };
    pending.current = body;
    try {
      const trial = await api<Trial>(`/api/organizations/${organizationId}/routines/${proposalId}/trial`, body);
      pending.current = null; onOpen(trial.conversation_id);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status > 0 && cause.status < 500) pending.current = null;
      setError(cause);
    } finally { sending.current = false; setBusy(false); }
  }
  const accessErrors = ['microsoft_reconnect_required', 'email_confirmation_required', 'company_policy_denied'];
  const failure = pending.current ? c.uncertain : error instanceof ApiError && accessErrors.includes(error.code) ? c.access : error instanceof ApiError && error.code === 'agent_already_running' ? c.busy : c.error;
  return <div className="routine-trial-action">
    {sendsEmail && !open ? <><p>{c.note}</p><button className="secondary" disabled={disabled} onClick={() => setOpen(true)}><Play size={16} />{label || c.sending}</button></> :
      <form onSubmit={event => { event.preventDefault(); if (!sendsEmail || confirmed) void run(); }}>
        {sendsEmail && <>
          <p>{c.note}</p>
          <label htmlFor={id + '-to'}>{c.to}</label><input id={id + '-to'} type="email" multiple required maxLength={5200} placeholder={c.placeholder} value={to} disabled={locked} onChange={event => { setTo(event.target.value); setConfirmed(false); }} />
          <label htmlFor={id + '-subject'}>{c.subject}</label><input id={id + '-subject'} required maxLength={998} value={subject} disabled={locked} onChange={event => { setSubject(event.target.value); setConfirmed(false); }} />
          <p className="subtle">{c.changed}</p>
          <label className="review-trial"><input type="checkbox" required checked={confirmed} disabled={locked} onChange={event => setConfirmed(event.target.checked)} /><span>{c.confirm}</span></label>
        </>}
        <Notice>{error ? failure : ''}</Notice>
        <button className="secondary" disabled={disabled || busy || !!sendsEmail && !confirmed}><Play size={16} />{busy ? c.preparing : pending.current ? c.retry : sendsEmail ? c.sending : label || c.try}</button>
      </form>}
  </div>;
}
