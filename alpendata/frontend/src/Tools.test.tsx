import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, test, vi } from 'vitest';
import { Tools } from './Tools';

const base = '/api/organizations/company-a/microsoft';
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
beforeEach(() => { sessionStorage.clear(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test('company restrictions cannot be enabled from personal tool choices', async () => {
  const fetcher = vi.fn(async () => json({ available: true, status: 'connected', capabilities: ['files'], allowed_capabilities: ['files'], restricted_capabilities: ['mail'] }));
  vi.stubGlobal('fetch', fetcher);
  render(<Tools companyId="company-a" language="fr" />);
  const mail = await screen.findByRole('checkbox', { name: /Mes mails/ }) as HTMLInputElement;
  expect(mail.disabled).toBe(true); expect(mail.checked).toBe(false);
  await userEvent.click(mail);
  expect(mail.checked).toBe(false);
  expect(screen.queryByRole('button', { name: 'Voir mes derniers mails' })).toBeNull();
  expect(screen.getByText(/Les règles de votre entreprise limitent certains accès/)).toBeTruthy();
  expect(fetcher).toHaveBeenCalledOnce();
});

test('personal consent sends only chosen permissions and preserves them across languages', async () => {
  const assign = vi.fn();
  vi.stubGlobal('location', { assign });
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    expect(init?.credentials).toBe('same-origin');
    if (path === base) return json({ available: true, status: 'disconnected', capabilities: [] });
    if (path === base + '/connect') {
      expect(JSON.parse(String(init?.body))).toEqual({ capabilities: ['mail', 'files'] });
      return json({ authorization_url: 'https://login.microsoftonline.com/directory/oauth2/v2.0/authorize?state=synthetic' });
    }
    throw new Error('Unexpected read before consent');
  });
  vi.stubGlobal('fetch', fetcher);
  const view = render(<Tools companyId="company-a" language="fr" />);
  await userEvent.click(await screen.findByRole('checkbox', { name: /Mes documents et SharePoint/ }));
  view.rerender(<Tools companyId="company-a" language="en" />);
  expect((screen.getByRole('checkbox', { name: /My documents and SharePoint/ }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole('checkbox', { name: /My calendar/ }) as HTMLInputElement).checked).toBe(false);
  await userEvent.click(screen.getByRole('button', { name: 'Connect my tools' }));
  await waitFor(() => expect(assign).toHaveBeenCalledOnce());
  expect(assign.mock.calls[0][0]).toMatch(/^https:\/\/login.microsoftonline.com\//);
  expect(sessionStorage.getItem('alpendata.return-company')).toBe('company-a');
  expect(fetcher.mock.calls.map(([path]) => path)).toEqual([base, base + '/connect']);
});

test('mail is read on request, rendered as text, and cleared when its connection expires', async () => {
  let revoked = false;
  const fetcher = vi.fn(async (path: string) => {
    if (path === base) return json({ available: true, status: 'connected', capabilities: ['mail'] });
    if (path === base + '/mail') return revoked ? json({ detail: 'microsoft_reconnect_required' }, 409) : json({ messages: [{
      id: 'email', subject: 'Préparation de séance', sender: 'Camille', preview: '<img src=x onerror=alert(1)>', url: 'https://outlook.office.com/mail/message',
    }] });
    throw new Error('Unexpected request');
  });
  vi.stubGlobal('fetch', fetcher);
  render(<Tools companyId="company-a" language="fr" />);
  await screen.findByText('Vos outils sont connectés.');
  expect(fetcher).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('button', { name: 'Voir mes prochains rendez-vous' })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Voir mes derniers mails' }));
  await screen.findByText('<img src=x onerror=alert(1)>');
  expect(document.querySelector('.tool-results img')).toBeNull();
  expect(screen.getByRole('link', { name: 'Ouvrir dans Microsoft 365' }).getAttribute('rel')).toBe('noopener noreferrer');
  revoked = true;
  await userEvent.click(screen.getByRole('button', { name: 'Voir mes derniers mails' }));
  await waitFor(() => expect(screen.queryByText('Préparation de séance')).toBeNull());
  expect(screen.getByRole('button', { name: 'Connecter mes outils' })).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Voir mes derniers mails' })).toBeNull();
});
