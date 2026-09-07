import { useRef, useState } from 'react';
import { ArrowRight } from 'lucide-react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import { BusinessIdeas } from './BusinessIdeas';
import type { Language } from './locale';
import { RoutineTrialAction } from './RoutineTrialAction';
import type { EmailDelivery } from './RoutineTrialAction';

export type Proposal = { sends_email?: boolean; id: string; title: string; benefit: string; focus: string };
export type Trial = { requires_sources?: boolean; schedule_version?: number | null; email_delivery?: EmailDelivery | null; delivery_accepted?: boolean; can_replace_schedule?: boolean; schedule_id?: string | null; id: string; proposal_id: string; conversation_id: string; status: string; sources_verified: boolean };

const words = {
  fr: {
    title: 'Un premier résultat utile.', intro: 'Choisissez ce qui vous ferait gagner du temps aujourd’hui. Vous pouvez commencer avec les informations que vous donnez à l’assistant, puis connecter vos outils si nécessaire.',
    provided: 'Ce résultat repose sur les informations que vous avez fournies. Vérifiez-le avant de le réutiliser ; aucune source externe n’était nécessaire à cet essai.',
    question: 'Par quoi aimeriez-vous commencer ?', placeholder: 'Par exemple : repérer les demandes de mes clients qui nécessitent un suivi.',
    propose: 'Trouver mes premières tâches', working: 'Préparation…', try: 'Tester maintenant', retry: 'Réessayer',
    once: 'Chaque essai produit un résultat dans votre conversation. Les tâches d’envoi demandent une confirmation supplémentaire. Aucun essai ne programme de répétition.',
    access: 'Connectez les outils nécessaires dans votre espace personnel, puis réessayez.',
    profile: 'Complétez d’abord votre profil dans « Mon espace ».', busy: 'Votre assistant termine déjà une demande. Réessayez ensuite.',
    unavailable: 'AlpenData doit terminer la configuration de votre assistant.',
    error: 'La demande n’a pas pu aboutir. Réessayez.', uncertain: 'La réception n’est pas confirmée. Réessayez pour retrouver la même demande, sans doublon.',
    verified: 'L’essai est terminé et les sources nécessaires ont été consultées. Vérifiez le résultat avant de le réutiliser.',
    unverified: 'L’essai est terminé, mais la consultation de toutes les sources nécessaires n’a pas été confirmée.',
  },
  en: {
    title: 'Your first useful result.', intro: 'Choose what would save you time today. Start with the information you give your assistant and connect your tools when needed.',
    provided: 'This result is based on information you provided. Review it before reusing it; this trial required no external source.',
    question: 'What would you like to start with?', placeholder: 'For example: identify client requests that need a follow-up.',
    propose: 'Find my first tasks', working: 'Preparing…', try: 'Try now', retry: 'Retry',
    once: 'Each trial produces a result in your conversation. Sending tasks require an additional confirmation. No trial schedules a recurrence.',
    access: 'Connect the required tools in your personal workspace, then try again.',
    profile: 'Complete your profile in “My workspace” first.', busy: 'Your assistant is already working on a request. Try again afterwards.',
    unavailable: 'AlpenData needs to finish configuring your assistant.',
    error: 'The request could not be completed. Try again.', uncertain: 'Receipt is not confirmed. Retry to find the same request without duplicating it.',
    verified: 'The trial is complete and the required sources were consulted. Review the result before reusing it.',
    unverified: 'The trial is complete, but access to all required sources was not confirmed.',
  },
};

function failure(error: unknown, language: Language) {
  const c = words[language];
  if (!(error instanceof ApiError) || error.status === 0 || error.status >= 500 && error.code !== 'chat_not_configured') return c.uncertain;
  const messages: Record<string, string> = { microsoft_reconnect_required: c.access, routine_capabilities_changed: c.access, onboarding_required: c.profile, agent_already_running: c.busy, chat_not_configured: c.unavailable };
  return messages[error.code] || c.error;
}

export function FirstTasks({ organizationId, language, sector, initialFocus = '', onOpen }: { organizationId: string; language: Language; sector?: string; initialFocus?: string; onOpen: (id: string) => void }) {
  const c = words[language];
  const [refinement, setRefinement] = useState(initialFocus), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const pending = useRef<{ request_id: string; language: Language; refinement: string } | null>(null), sending = useRef(false);
  return <section className="first-tasks"><h2>{c.title}</h2><p>{c.intro}</p>
    <BusinessIdeas language={language} sector={sector} disabled={busy || !!pending.current} onChoose={setRefinement} />
    <form onSubmit={async event => {
      event.preventDefault(); if (sending.current) return; sending.current = true; setBusy(true); setError(null);
      const body = pending.current || { request_id: crypto.randomUUID(), language, refinement: refinement.trim() };
      pending.current = body;
      try {
        const result = await api<{ conversation: { id: string } }>(`/api/organizations/${organizationId}/onboarding/proposals`, body);
        pending.current = null; onOpen(result.conversation.id);
      } catch (cause) {
        if (cause instanceof ApiError && cause.status > 0 && cause.status < 500) pending.current = null;
        setError(cause);
      } finally { sending.current = false; setBusy(false); }
    }}>
      <label htmlFor="first-task-focus">{c.question}</label>
      <textarea id="first-task-focus" value={refinement} onChange={event => setRefinement(event.target.value)} placeholder={c.placeholder} required maxLength={4000} rows={3} disabled={busy || !!pending.current} />
      <Notice>{error ? failure(error, language) : ''}</Notice>
      <button className="primary" disabled={busy || !refinement.trim()}>{busy ? c.working : pending.current ? c.retry : c.propose}<ArrowRight size={17} /></button>
    </form>
  </section>;
}

export function RoutineCards({ proposals, organizationId, language, disabled, onOpen }: { proposals: Proposal[]; organizationId: string; language: Language; disabled: boolean; onOpen: (id: string) => void }) {
  const c = words[language];
  return <section className="routine-proposals"><p>{c.once}</p>
    <div className="routine-grid">{proposals.map(item => <article className="routine-card" key={item.id}>
      <h3>{item.title}</h3><p>{item.benefit}</p><p className="subtle">{item.focus}</p>
      <RoutineTrialAction organizationId={organizationId} proposalId={item.id} language={language} disabled={disabled} sendsEmail={item.sends_email} onOpen={onOpen} />
    </article>)}</div>
  </section>;
}

export function TrialEvidence({ trials, language }: { trials: Trial[]; language: Language }) {
  return <>{trials.filter(trial => trial.status === 'completed').map(trial => <p className="configuration-note" key={trial.id}>{trial.requires_sources === false ? words[language].provided : trial.sources_verified ? words[language].verified : words[language].unverified}</p>)}</>;
}
