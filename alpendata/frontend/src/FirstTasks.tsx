import { useRef, useState } from 'react';
import { ArrowRight, Play } from 'lucide-react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';

export type Proposal = { id: string; title: string; benefit: string; focus: string };
export type Trial = { id: string; proposal_id: string; conversation_id: string; status: string; sources_verified: boolean };

const words = {
  fr: {
    title: 'Un premier résultat utile.', intro: 'Après avoir connecté vos outils, choisissez ce qui vous ferait gagner du temps aujourd’hui.',
    question: 'Par quoi aimeriez-vous commencer ?', placeholder: 'Par exemple : repérer les demandes de mes clients qui nécessitent un suivi.',
    propose: 'Trouver mes premières tâches', working: 'Préparation…', try: 'Tester maintenant', retry: 'Réessayer',
    once: 'Chaque essai consulte vos outils et produit un résultat dans votre conversation. Il ne programme aucune répétition.',
    access: 'Connectez les outils nécessaires dans votre espace personnel, puis réessayez.',
    profile: 'Complétez d’abord votre profil dans « Mon espace ».', busy: 'Votre assistant termine déjà une demande. Réessayez ensuite.',
    unavailable: 'AlpenData doit terminer la configuration de votre assistant.',
    error: 'La demande n’a pas pu aboutir. Réessayez.', uncertain: 'La réception n’est pas confirmée. Réessayez pour retrouver la même demande, sans doublon.',
    verified: 'L’essai est terminé et les sources nécessaires ont été consultées. Vérifiez le résultat avant de le réutiliser.',
    unverified: 'L’essai est terminé, mais la consultation de toutes les sources nécessaires n’a pas été confirmée.',
  },
  en: {
    title: 'Your first useful result.', intro: 'After connecting your tools, choose what would save you time today.',
    question: 'What would you like to start with?', placeholder: 'For example: identify client requests that need a follow-up.',
    propose: 'Find my first tasks', working: 'Preparing…', try: 'Try now', retry: 'Retry',
    once: 'Each trial reads your tools and produces a result in your conversation. It does not schedule any recurrence.',
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

export function FirstTasks({ organizationId, language, onOpen }: { organizationId: string; language: Language; onOpen: (id: string) => void }) {
  const c = words[language];
  const [refinement, setRefinement] = useState(''), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const pending = useRef<{ request_id: string; language: Language; refinement: string } | null>(null), sending = useRef(false);
  return <section className="first-tasks"><h2>{c.title}</h2><p>{c.intro}</p>
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
  const [busy, setBusy] = useState(false), [error, setError] = useState<unknown>(null);
  const pending = useRef<{ proposal: string; request_id: string } | null>(null), sending = useRef(false);
  return <section className="routine-proposals"><p>{c.once}</p><Notice>{error ? failure(error, language) : ''}</Notice>
    <div className="routine-grid">{proposals.map(item => <article className="routine-card" key={item.id}>
      <h3>{item.title}</h3><p>{item.benefit}</p><p className="subtle">{item.focus}</p>
      <button className="secondary" disabled={disabled || busy || !!pending.current && pending.current.proposal !== item.id} onClick={async () => {
        if (sending.current) return; sending.current = true; setBusy(true); setError(null);
        const intent = pending.current || { proposal: item.id, request_id: crypto.randomUUID() }; pending.current = intent;
        try {
          const trial = await api<Trial>(`/api/organizations/${organizationId}/routines/${intent.proposal}/trial`, { request_id: intent.request_id });
          pending.current = null; onOpen(trial.conversation_id);
        } catch (cause) {
          if (cause instanceof ApiError && cause.status > 0 && cause.status < 500) pending.current = null;
          setError(cause);
        } finally { sending.current = false; setBusy(false); }
      }}><Play size={16} />{busy ? c.working : pending.current ? c.retry : c.try}</button>
    </article>)}</div>
  </section>;
}

export function TrialEvidence({ trials, language }: { trials: Trial[]; language: Language }) {
  return <>{trials.filter(trial => trial.status === 'completed').map(trial => <p className="configuration-note" key={trial.id}>{trial.sources_verified ? words[language].verified : words[language].unverified}</p>)}</>;
}
