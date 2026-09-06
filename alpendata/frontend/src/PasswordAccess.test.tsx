import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { PasswordAccess, PasswordChange, readActivation } from './PasswordAccess';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); history.replaceState(null, '', '/'); });

test('activation is recoverable after a reload and requires matching passwords without storing them', async () => {
  const token = 'a'.repeat(64), password = 'My private passphrase 123!';
  history.replaceState(null, '', '/#activation=' + token);
  expect(readActivation()).toBe(token); expect(location.hash).toBe(''); expect(readActivation()).toBe(token);
  const fetch = vi.fn(async () => new Response(null, { status: 204 })), done = vi.fn(async () => {});
  vi.stubGlobal('fetch', fetch);
  render(<PasswordAccess activation={token} language="fr" done={done} />);
  await userEvent.type(screen.getByLabelText('Nouveau mot de passe'), password);
  await userEvent.type(screen.getByLabelText('Confirmer le nouveau mot de passe'), password + 'different');
  await userEvent.click(screen.getByRole('button', { name: 'Choisir mon mot de passe' }));
  expect(fetch).not.toHaveBeenCalled(); expect(screen.getByText(/Les deux mots de passe/)).toBeTruthy();
  await userEvent.clear(screen.getByLabelText('Confirmer le nouveau mot de passe'));
  await userEvent.type(screen.getByLabelText('Confirmer le nouveau mot de passe'), password);
  await userEvent.click(screen.getByRole('button', { name: 'Choisir mon mot de passe' }));
  expect(fetch).toHaveBeenCalledOnce(); expect(done).toHaveBeenCalledOnce();
  expect(readActivation()).toBeNull(); expect(JSON.stringify(sessionStorage)).not.toContain(password);
});

test('English login preserves password spaces and password change waits for server confirmation', async () => {
  const sent: { path: string; body: unknown }[] = [], done = vi.fn(async () => {});
  vi.stubGlobal('fetch', vi.fn(async (path: string, init: RequestInit) => {
    sent.push({ path, body: JSON.parse(String(init.body)) });
    return path.endsWith('/login') ? new Response(JSON.stringify({ detail: 'signin_rate_limited' }), { status: 429 }) : new Response(null, { status: 204 });
  }));
  const view = render(<PasswordAccess language="en" done={done} />);
  await userEvent.type(screen.getByLabelText('Email address'), 'coach@example.com');
  await userEvent.type(screen.getByLabelText('Password'), ' password with spaces ');
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
  expect(sent[0].body).toEqual({ email: 'coach@example.com', password: ' password with spaces ' });
  expect(done).not.toHaveBeenCalled(); expect(screen.getByText(/Too many attempts/)).toBeTruthy();
  view.unmount(); render(<PasswordChange language="en" />);
  await userEvent.click(screen.getByText('Change my password'));
  await userEvent.type(screen.getByLabelText('Current password'), ' password with spaces ');
  await userEvent.type(screen.getByLabelText('New password'), 'A different long passphrase');
  await userEvent.type(screen.getByLabelText('Confirm new password'), 'A different long passphrase');
  await userEvent.click(screen.getByRole('button', { name: 'Save my password' }));
  expect(screen.getByText(/Password changed. Other sessions/)).toBeTruthy();
  expect((screen.getByLabelText('Current password') as HTMLInputElement).value).toBe('');
});
