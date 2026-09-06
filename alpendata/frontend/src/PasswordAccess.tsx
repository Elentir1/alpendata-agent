import { useRef, useState } from 'react';
import { api, ApiError } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';

const words = {
  fr: {
    email: 'Adresse e-mail', password: 'Mot de passe', login: 'Se connecter', working: 'Vérification…',
    activate: 'Choisir mon mot de passe', activation: 'Activez votre compte AlpenData',
    explain: 'Choisissez le mot de passe du compte associé à ce lien. Vous serez connecté à ce compte.',
    policy: 'Utilisez entre 15 et 128 caractères. Une phrase longue est acceptée.',
    confirm: 'Confirmer le nouveau mot de passe', newPassword: 'Nouveau mot de passe', current: 'Mot de passe actuel',
    change: 'Changer mon mot de passe', save: 'Enregistrer mon mot de passe', saved: 'Mot de passe modifié. Les autres sessions sont déconnectées.',
    forgot: 'Mot de passe oublié ou lien expiré ? Contactez AlpenData pour recevoir un nouveau lien après vérification de votre identité.',
    invalid: 'L’adresse ou le mot de passe est incorrect.', expired: 'Ce lien a expiré ou a déjà été utilisé. Demandez un nouveau lien à AlpenData.',
    limited: 'Trop de tentatives. Réessayez dans quelques minutes.', mismatch: 'Les deux mots de passe doivent être identiques.',
    error: 'La demande n’a pas pu être confirmée. Essayez de vous connecter avec votre mot de passe ; si nécessaire, contactez AlpenData.',
  },
  en: {
    email: 'Email address', password: 'Password', login: 'Sign in', working: 'Checking…',
    activate: 'Set my password', activation: 'Activate your AlpenData account',
    explain: 'Choose the password for the account linked here. You will be signed in to that account.',
    policy: 'Use between 15 and 128 characters. A long passphrase is welcome.',
    confirm: 'Confirm new password', newPassword: 'New password', current: 'Current password',
    change: 'Change my password', save: 'Save my password', saved: 'Password changed. Other sessions have been signed out.',
    forgot: 'Forgot your password or link expired? Contact AlpenData for a new link after your identity is verified.',
    invalid: 'The email address or password is incorrect.', expired: 'This link has expired or has already been used. Request a new link from AlpenData.',
    limited: 'Too many attempts. Try again in a few minutes.', mismatch: 'Both passwords must match.',
    error: 'The request could not be confirmed. Try signing in with your password; contact AlpenData if needed.',
  },
};

const activationKey = 'alpendata.activation';
export function readActivation(): string | null {
  const fragment = new URLSearchParams(location.hash.slice(1));
  if (fragment.has('activation')) {
    const token = fragment.get('activation') || '';
    history.replaceState(null, '', location.pathname + location.search);
    if (/^[A-Za-z0-9_-]{32,512}$/.test(token)) sessionStorage.setItem(activationKey, token);
    else sessionStorage.removeItem(activationKey);
  }
  return sessionStorage.getItem(activationKey);
}
export function clearActivation() { sessionStorage.removeItem(activationKey); }

function failure(error: unknown, language: Language) {
  const t = words[language];
  const codes: Record<string, string> = { invalid_credentials: t.invalid, activation_invalid: t.expired,
    signin_rate_limited: t.limited, password_request_invalid: t.policy };
  return error instanceof ApiError && codes[error.code] || t.error;
}

export function PasswordAccess({ language, activation, done }: { language: Language; activation?: string | null; done: () => Promise<void> }) {
  const t = words[language];
  const [email, setEmail] = useState(''), [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const sending = useRef(false);
  return <form className="password-access" onSubmit={async event => {
    event.preventDefault(); if (sending.current) return;
    if (activation && password !== confirmation) { setError(t.mismatch); return; }
    sending.current = true; setBusy(true); setError('');
    try {
      await api('/api/auth/password/' + (activation ? 'activate' : 'login'), activation ? { token: activation, password } : { email: email.trim(), password });
      setPassword(''); setConfirmation(''); clearActivation(); await done();
    } catch (cause) { setError(failure(cause, language)); }
    finally { sending.current = false; setBusy(false); }
  }}>
    {activation ? <><h2>{t.activation}</h2><p>{t.explain}</p><p id="password-policy">{t.policy}</p></> : <><label htmlFor="signin-email">{t.email}</label><input id="signin-email" type="email" autoComplete="username" required maxLength={320} value={email} onChange={event => setEmail(event.target.value)} disabled={busy} /></>}
    <label htmlFor="signin-password">{activation ? t.newPassword : t.password}</label><input id="signin-password" type="password" autoComplete={activation ? 'new-password' : 'current-password'} required minLength={activation ? 15 : 1} maxLength={128} value={password} onChange={event => setPassword(event.target.value)} disabled={busy} aria-describedby={activation ? 'password-policy' : undefined} />
    {activation && <><label htmlFor="password-confirm">{t.confirm}</label><input id="password-confirm" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={busy} /></>}
    <Notice>{error}</Notice><button className="primary wide" disabled={busy}>{busy ? t.working : activation ? t.activate : t.login}</button>
    <p className="subtle">{t.forgot}</p>
  </form>;
}

export function PasswordChange({ language }: { language: Language }) {
  const t = words[language];
  const [current, setCurrent] = useState(''), [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [saved, setSaved] = useState(false);
  const sending = useRef(false);
  return <details className="password-change"><summary>{t.change}</summary><form onSubmit={async event => {
    event.preventDefault(); if (sending.current) return;
    if (password !== confirmation) { setError(t.mismatch); return; }
    sending.current = true; setBusy(true); setError(''); setSaved(false);
    try { await api('/api/auth/password/change', { current_password: current, password }); setCurrent(''); setPassword(''); setConfirmation(''); setSaved(true); }
    catch (cause) { setError(failure(cause, language)); }
    finally { sending.current = false; setBusy(false); }
  }}>
    <p>{t.policy}</p><label htmlFor="current-password">{t.current}</label><input id="current-password" type="password" autoComplete="current-password" required maxLength={128} value={current} onChange={e => setCurrent(e.target.value)} disabled={busy} />
    <label htmlFor="new-password">{t.newPassword}</label><input id="new-password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={password} onChange={e => setPassword(e.target.value)} disabled={busy} />
    <label htmlFor="confirm-password">{t.confirm}</label><input id="confirm-password" type="password" autoComplete="new-password" required minLength={15} maxLength={128} value={confirmation} onChange={e => setConfirmation(e.target.value)} disabled={busy} />
    <Notice>{error}</Notice><Notice success>{saved ? t.saved : ''}</Notice><button className="primary" disabled={busy}>{busy ? t.working : t.save}</button>
  </form></details>;
}
