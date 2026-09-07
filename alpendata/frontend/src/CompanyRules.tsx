import { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';

type Capability = 'mail' | 'calendar' | 'files' | 'files_write' | 'mail_send' | 'mail_autonomous' | 'calendar_write' | 'calendar_autonomous';
interface Policy { version: number; allowed_capabilities: Capability[] }
const capabilities: Capability[] = ['mail', 'calendar', 'files', 'files_write', 'mail_send', 'mail_autonomous', 'calendar_write', 'calendar_autonomous'];
const words = {
  fr: { title: 'Règles de votre entreprise', intro: 'Choisissez les accès que chaque personne pourra autoriser avec son propre compte. Ces règles s’appliquent aussi à vous.',
    calendar_write: 'Modifier les agendas', calendar_autonomous: 'Permettre les modifications d’agenda autorisées sans validation',
    mail_autonomous: 'Permettre aux collaborateurs d’autoriser les envois directs', mail_send: 'Envoyer des mails', mail: 'Lire les mails', calendar: 'Consulter les agendas', files: 'Rechercher et lire les documents', files_write: 'Enregistrer des documents dans Microsoft 365',
    note: 'Un accès autorisé ici exige toujours la connexion personnelle du collaborateur. Les enregistrements de documents restent soumis à confirmation.',
    effect: 'Retirer un accès bloque les prochains appels et suspend les automatisations concernées. Les appels déjà en cours peuvent se terminer avant l’application des règles. Réautoriser un accès ne relance pas les tâches suspendues.',
    privacy: 'Ces réglages ne donnent aucun accès aux conversations, mémoires ou connexions personnelles. Ils ne suppriment pas les documents déjà conservés.',
    save: 'Enregistrer les règles', saved: 'Les règles de l’entreprise sont enregistrées.', loading: 'Chargement des règles…', busy: 'Application des règles…',
    changed: 'Les règles ont changé depuis leur ouverture. Rechargez la version actuelle avant de modifier vos choix.', reload: 'Recharger les règles actuelles',
    error: 'Les règles n’ont pas pu être confirmées. Rechargez leur état avant de réessayer.', },
  en: { title: 'Your company’s rules', intro: 'Choose the access each person may authorize with their own account. These rules also apply to you.',
    calendar_write: 'Update calendars', calendar_autonomous: 'Allow authorized calendar changes without confirmation',
    mail_autonomous: 'Let colleagues authorize direct sends', mail_send: 'Send email', mail: 'Read email', calendar: 'View calendars', files: 'Find and read documents', files_write: 'Save documents to Microsoft 365',
    note: 'Access allowed here still requires each colleague’s personal connection. Document saves continue to require confirmation.',
    effect: 'Removing access blocks subsequent calls and suspends affected automations. Calls already in progress may finish before the rules apply. Restoring access does not restart suspended tasks.',
    privacy: 'These settings do not give access to personal conversations, memories or connections. They do not delete previously saved documents.',
    save: 'Save company rules', saved: 'Your company rules have been saved.', loading: 'Loading rules…', busy: 'Applying rules…',
    changed: 'The rules changed since you opened them. Reload the current version before editing your choices.', reload: 'Reload current rules',
    error: 'The rules could not be confirmed. Reload their state before trying again.', },
};

export function CompanyRules({ organizationId, language }: { organizationId: string; language: Language }) {
  const t = words[language], path = `/api/organizations/${encodeURIComponent(organizationId)}/policy`;
  const [policy, setPolicy] = useState<Policy | null>(null), [selected, setSelected] = useState<Capability[]>([]);
  const [busy, setBusy] = useState(false), [saved, setSaved] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    api<Policy>(path).then(value => { if (active) { setPolicy(value); setSelected(value.allowed_capabilities); } })
      .catch(() => { if (active) setError('request_failed'); });
    return () => { active = false; };
  }, [path]);
  function choose(capability: Capability, enabled: boolean) {
    setSaved(false);
    setSelected(values => {
      const next = new Set(values);
      if (enabled) next.add(capability); else next.delete(capability);
      if (capability === 'files' && !enabled) next.delete('files_write');
      if (capability === 'calendar' && !enabled) { next.delete('calendar_write'); next.delete('calendar_autonomous'); }
      if (capability === 'calendar_write' && !enabled) next.delete('calendar_autonomous');
      if (capability === 'mail_send' && !enabled) next.delete('mail_autonomous');
      return capabilities.filter(value => next.has(value));
    });
  }
  const dirty = policy && capabilities.some(value => selected.includes(value) !== policy.allowed_capabilities.includes(value));
  return <section className="company-rules" aria-label={t.title}>
    <h2><ShieldCheck size={22} aria-hidden="true" />{t.title}</h2><p>{t.intro}</p>
    {!policy && !error && <p role="status">{t.loading}</p>}
    {policy && <form onSubmit={async event => {
      event.preventDefault(); if (busy || error) return; setBusy(true); setSaved(false);
      try { const value = await api<Policy>(path, { version: policy.version, allowed_capabilities: selected }, 'PUT'); setPolicy(value); setSelected(value.allowed_capabilities); setSaved(true); }
      catch (cause) { setError(cause instanceof ApiError ? cause.code : 'request_failed'); }
      finally { setBusy(false); }
    }}><fieldset disabled={busy || !!error} className="company-rule-choices">
      {capabilities.map(value => <label key={value}><input type="checkbox" checked={selected.includes(value)} disabled={(value === 'calendar_write' && !selected.includes('calendar')) || (value === 'calendar_autonomous' && !selected.includes('calendar_write')) || (value === 'files_write' && !selected.includes('files')) || (value === 'mail_autonomous' && !selected.includes('mail_send'))} onChange={event => choose(value, event.target.checked)} /><span>{t[value]}</span></label>)}
    </fieldset><p>{t.note}</p><p>{t.effect}</p><button className="primary" disabled={busy || !!error || !dirty}>{busy ? t.busy : t.save}</button></form>}
    <Notice success>{saved ? t.saved : ''}</Notice><Notice>{error ? error === 'company_policy_changed' ? t.changed : t.error : ''}</Notice>
    {error && <button type="button" className="secondary" disabled={busy} onClick={async () => {
      setBusy(true); try { const value = await api<Policy>(path); setPolicy(value); setSelected(value.allowed_capabilities); setError(''); setSaved(false); } catch { setError('request_failed'); } finally { setBusy(false); }
    }}>{t.reload}</button>}
    <p className="subtle">{t.privacy}</p>
  </section>;
}
