import { useEffect, useState } from 'react';
import { api, ApiError } from './api';
import type { Language } from './locale';

interface Policy { version: number; email_mode: 'confirm' | 'automatic'; automatic_allowed: boolean; automatic_available: boolean }
const words = {
  fr: {
    title: 'Ce que votre assistant peut faire', intro: 'Votre choix personnel s’applique aux e-mails de vos conversations et de vos tâches planifiées. Il ne modifie pas les choix de vos collègues.',
    confirm: 'Je confirme chaque envoi', automatic: 'Mon assistant peut envoyer directement',
    acknowledgement: 'J’autorise mon assistant à envoyer des e-mails depuis mon compte, avec leurs pièces jointes, sans me demander de confirmation lorsque mes demandes ou mes tâches planifiées le prévoient.',
    effect: 'L’activation s’applique aux nouvelles conversations et aux nouveaux essais de tâches. Revenir à la confirmation bloque les prochains envois de l’agent et suspend les tâches préparées avec cette autonomie. Un envoi déjà en cours peut se terminer.',
    task: 'Après un changement, refaites un essai des tâches concernées avant de les activer à nouveau.',
    restricted: 'Votre entreprise n’autorise pas les envois directs. Votre administrateur peut modifier cette règle.',
    connect: 'Votre choix est enregistré, mais l’envoi direct exige aussi « Envoyer mes mails » dans vos outils Microsoft.',
    save: 'Enregistrer mon choix', saved: 'Votre choix personnel est enregistré.', loading: 'Chargement…', reload: 'Recharger mon choix',
    error: 'Le choix n’a pas pu être confirmé. Rechargez son état avant de continuer.', changed: 'Votre choix a changé ailleurs. Rechargez la version actuelle avant de continuer.',
  },
  en: {
    title: 'What your assistant can do', intro: 'Your personal choice applies to emails in your conversations and scheduled tasks. It does not change your colleagues’ choices.',
    confirm: 'I confirm every send', automatic: 'My assistant may send directly',
    acknowledgement: 'I authorize my assistant to send emails and their attachments from my account without asking for confirmation when my requests or scheduled tasks call for it.',
    effect: 'Enabling applies to new conversations and new task trials. Returning to confirmation blocks subsequent agent sends and suspends tasks prepared with this autonomy. A send already in progress may finish.',
    task: 'After a change, run a new trial of affected tasks before activating them again.',
    restricted: 'Your company does not allow direct sends. Your administrator can change this rule.',
    connect: 'Your choice is saved, but direct sending also requires “Send my email” in your Microsoft tools.',
    save: 'Save my choice', saved: 'Your personal choice has been saved.', loading: 'Loading…', reload: 'Reload my choice',
    error: 'The choice could not be confirmed. Reload its state before continuing.', changed: 'Your choice changed elsewhere. Reload the current version before continuing.',
  },
};

export function PersonalAutonomy({ organizationId, language, licensed, expanded = false }: { organizationId: string; language: Language; licensed: boolean; expanded?: boolean }) {
  const t = words[language], path = `/api/organizations/${encodeURIComponent(organizationId)}/action-policy`;
  const [policy, setPolicy] = useState<Policy | null>(null), [mode, setMode] = useState<Policy['email_mode']>('confirm');
  const [acknowledged, setAcknowledged] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false);
  function accept(value: Policy) { setPolicy(value); setMode(value.email_mode); setAcknowledged(false); }
  useEffect(() => {
    let active = true;
    api<Policy>(path).then(value => { if (active) accept(value); }).catch(() => { if (active) setError('request_failed'); });
    return () => { active = false; };
  }, [path]);
  return <details open={expanded || undefined} className="personal-autonomy"><summary>{t.title}</summary><p>{t.intro}</p>
    {!policy && !error && <p role="status">{t.loading}</p>}
    {policy && <form onSubmit={async event => {
      event.preventDefault(); if (busy || error) return; setBusy(true); setSaved(false);
      try { const value = await api<Policy>(path, { version: policy.version, email_mode: mode, acknowledged }, 'PUT'); accept(value); setError(''); setSaved(true); }
      catch (cause) { setError(cause instanceof ApiError ? cause.code : 'request_failed'); }
      finally { setBusy(false); }
    }}>
      <fieldset disabled={busy || !!error} className="company-rule-choices">
        <label><input type="radio" name="email-autonomy" checked={mode === 'confirm'} onChange={() => { setMode('confirm'); setAcknowledged(false); setSaved(false); }} /><span>{t.confirm}</span></label>
        <label><input type="radio" name="email-autonomy" checked={mode === 'automatic'} disabled={!licensed || !policy.automatic_allowed} onChange={() => { setMode('automatic'); setAcknowledged(false); setSaved(false); }} /><span>{t.automatic}</span></label>
        {mode === 'automatic' && policy.email_mode !== 'automatic' && <label><input type="checkbox" checked={acknowledged} disabled={!licensed || !policy.automatic_allowed} onChange={event => setAcknowledged(event.target.checked)} /><span>{t.acknowledgement}</span></label>}
      </fieldset>
      {!policy.automatic_allowed && <p>{t.restricted}</p>}
      {policy.email_mode === 'automatic' && policy.automatic_allowed && !policy.automatic_available && <p>{t.connect}</p>}
      <p>{t.effect}</p><p>{t.task}</p>
      <button className="secondary" disabled={busy || !!error || mode === policy.email_mode || (mode === 'automatic' && (!acknowledged || !licensed || !policy.automatic_allowed))}>{t.save}</button>
    </form>}
    {saved && <p role="status">{t.saved}</p>}
    {error && <><p role="alert">{error === 'personal_policy_changed' ? t.changed : t.error}</p><button type="button" className="secondary" disabled={busy} onClick={async () => {
      setBusy(true); try { accept(await api<Policy>(path)); setError(''); setSaved(false); } catch { setError('request_failed'); } finally { setBusy(false); }
    }}>{t.reload}</button></>}
  </details>;
}
