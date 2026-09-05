import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import App from './App';
import type { Onboarding, Person } from './api';

const member = { organization_id: 'company-a', user_id: 'coach', role: 'member' as const, active: true, licensed: true };
const person: Person = { id: 'coach', display_name: 'Camille', memberships: [member] };
const company = { id: 'company-a', name: 'Horizon Coaching' };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); history.replaceState(null, '', '/'); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test('sign-in availability is honest and changing language updates the working interface', async () => {
  history.replaceState(null, '', '/?signin_error=interrupted');
  const fetcher = vi.fn(async (path: string) => {
    if (path === '/api/auth/options') return json({ microsoft: false, invitation_email: false });
    if (path === '/api/me') return json({ detail: 'authentication_required' }, 401);
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<App />);
  expect((await screen.findByRole('button', { name: 'Continuer avec Microsoft' }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole('alert').textContent).toContain('La connexion n’a pas abouti.');
  expect(location.search).toBe('');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Langue' }), 'en');
  expect(screen.getByRole('heading', { level: 1 }).textContent).toBe('An assistant that understands your work.');
  expect((screen.getByRole('button', { name: 'Continue with Microsoft' }) as HTMLButtonElement).disabled).toBe(true);
  expect(fetcher.mock.calls.some(([path]) => path.includes('/microsoft/start'))).toBe(false);
});

test('personal onboarding keeps unsaved answers when language changes and persists through the API', async () => {
  let profile: Onboarding = { language: 'fr', step: 'introduction', answers: {} };
  let saved: unknown;
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    expect(init?.credentials).toBe('same-origin');
    if (path === '/api/auth/options') return json({ microsoft: true, invitation_email: true });
    if (path === '/api/me') return json(person);
    if (path === '/api/organizations/company-a') return json(company);
    if (path === '/api/organizations/company-a/microsoft') return json({ available: false, status: 'disconnected', capabilities: [] });
    if (path === '/api/organizations/company-a/onboarding') {
      if (init?.method === 'PUT') {
        const payload = JSON.parse(String(init.body)); saved = payload;
        const { language, ...answers } = payload; profile = { language, step: 'connect_tools', answers };
      }
      return json(profile);
    }
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal('fetch', fetcher);
  const view = render(<App />);
  await userEvent.type(await screen.findByLabelText('Quel est votre rôle ?'), 'Coach indépendant');
  await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Langue' }), 'en');
  expect((screen.getByLabelText('What is your role?') as HTMLInputElement).value).toBe('Coach indépendant');
  await userEvent.type(screen.getByLabelText('What would you like to simplify first?'), 'Prepare my client meetings');
  await userEvent.click(screen.getByRole('button', { name: 'Save and continue' }));
  await screen.findByRole('heading', { name: 'Next: your tools.' });
  expect(saved).toEqual({ language: 'en', role: 'Coach indépendant', activity: '', needs: 'Prepare my client meetings' });
  expect(within(screen.getByRole('navigation')).queryByRole('button', { name: 'My company' })).toBeNull();
  view.unmount(); render(<App />);
  await screen.findByRole('heading', { name: 'Next: your tools.' });
  await userEvent.click(screen.getByRole('button', { name: 'Edit my answers' }));
  expect((screen.getByLabelText('What is your role?') as HTMLInputElement).value).toBe('Coach indépendant');
});

test('a verified invitation is consumed through the API before a new personal onboarding is shown', async () => {
  const token = 'a'.repeat(64), proof = 'b'.repeat(64);
  history.replaceState(null, '', `/join#invitation=${token}&verification=${proof}`);
  let joined = false;
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === '/api/auth/options') return json({ microsoft: true, invitation_email: true });
    if (path === '/api/me') return json({ ...person, memberships: joined ? [member] : [] });
    if (path === '/api/invitations/accept') {
      expect(JSON.parse(String(init?.body))).toEqual({ token, verification_token: proof });
      expect(init?.credentials).toBe('same-origin'); joined = true; return json({ organization_id: company.id });
    }
    if (path === '/api/organizations/company-a') return json(company);
    if (path === '/api/organizations/company-a/onboarding') return json({ language: 'fr', step: 'introduction', answers: {} });
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<App />);
  await screen.findByRole('heading', { name: 'Rejoignez votre entreprise.' });
  expect(location.hash).toBe(''); expect(screen.getByText('Camille')).toBeTruthy();
  expect(joined).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Rejoindre l’entreprise' }));
  await screen.findByLabelText('Quel est votre rôle ?');
  expect(sessionStorage.getItem('alpendata.pending-invitation')).toBeNull();
  expect((screen.getByLabelText('Quel est votre rôle ?') as HTMLInputElement).value).toBe('');
  expect(fetcher.mock.calls.filter(([path]) => path === '/api/invitations/accept').length).toBe(1);
});

test('administrator invitations can be created and revoked without displaying private colleague data', async () => {
  let pending: { id: string; email: string }[] = [];
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === '/api/auth/options') return json({ microsoft: true, invitation_email: true });
    if (path === '/api/me') return json({ ...person, memberships: [{ ...member, role: 'admin' }] });
    if (path === '/api/organizations/company-a') return json(company);
    if (path.endsWith('/onboarding')) return json({ language: 'fr', step: 'introduction', answers: {} });
    if (path.endsWith('/members')) return json({ members: [{ ...member, role: 'admin', display_name: person.display_name }] });
    if (path.endsWith('/invitations')) {
      if (init?.method === 'POST') { expect(JSON.parse(String(init.body))).toEqual({ email: 'colleague@example.com' }); pending = [{ id: 'invite-1', email: 'colleague@example.com' }]; return json({ token: 'c'.repeat(64) }, 201); }
      return json({ invitations: pending });
    }
    if (path.endsWith('/invitations/invite-1') && init?.method === 'DELETE') { pending = []; return new Response(null, { status: 204 }); }
    throw new Error(`Unexpected request: ${path}`);
  });
  vi.stubGlobal('fetch', fetcher);
  render(<App />);
  await userEvent.click(await screen.findByRole('button', { name: 'Mon entreprise' }));
  await userEvent.type(await screen.findByLabelText('Adresse professionnelle du collaborateur'), 'colleague@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Créer une invitation' }));
  const link = await screen.findByLabelText('Lien à partager avec votre collaborateur');
  expect((link as HTMLInputElement).value).toBe(`https://alpendata.example.test/join#invitation=${'c'.repeat(64)}`);
  await userEvent.click(await screen.findByRole('button', { name: 'Annuler l’invitation de colleague@example.com' }));
  await waitFor(() => expect(screen.queryByText('colleague@example.com')).toBeNull());
  expect(fetcher.mock.calls.some(([path]) => path.includes('/personal-resources'))).toBe(false);
});

test('an expired session can return to sign-in without trapping the user in a failing logout', async () => {
  let expired = false;
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    if (path === '/api/auth/options') return json({ microsoft: true, invitation_email: true });
    if (path === '/api/me') return expired ? json({ detail: 'invalid_session' }, 401) : json(person);
    if (path === '/api/organizations/company-a') return json(company);
    if (path.endsWith('/onboarding')) return json({ language: 'fr', step: 'introduction', answers: {} });
    if (path === '/api/logout') { expired = true; return json({ detail: 'invalid_session' }, 401); }
    throw new Error(`Unexpected request: ${path}`);
  }));
  render(<App />);
  await screen.findByLabelText('Quel est votre rôle ?');
  await userEvent.click(screen.getByRole('button', { name: 'Se déconnecter' }));
  await screen.findByRole('button', { name: 'Continuer avec Microsoft' });
  expect(screen.queryByLabelText('Quel est votre rôle ?')).toBeNull();
});
