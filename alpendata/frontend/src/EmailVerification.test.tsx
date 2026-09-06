import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { EmailDraft } from './EmailDraft';
import type { EmailReceipt } from './EmailDraft';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const initial: EmailReceipt = { id: 'email-a', version: 1, editable: false,
  message: { to: ['client@example.com'], cc: [], bcc: [], subject: 'Session', body: 'Your session notes.', attachment_ids: [] },
  attachments: [], attempts: [{ id: 'attempt-a', version: 1, status: 'unknown', error_code: 'email_send_unknown', can_verify: true, verification: null }] };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

test('an absent sent copy leaves sending locked; a later matching copy shows evidence without claiming delivery', async () => {
  let searches = 0;
  const fetcher = vi.fn(async (path: string, options: RequestInit) => {
    expect(path).toBe('/api/organizations/company-a/emails/email-a/attempts/attempt-a/verify');
    expect(options.method).toBe('POST');
    searches++;
    return json({ ...initial, attempts: [{ ...initial.attempts[0], verification: {
      checked_at: 1788670000 + searches, status: searches === 1 ? 'not_found' : 'found', searched: 100, partial: true,
      match_count: searches === 1 ? 0 : 1,
      copy: searches === 1 ? null : { item_id: 'sent-a', url: 'https://outlook.office.com/mail/sent-a', sent_at: '2026-09-06T09:00:00Z' },
    } }] });
  });
  vi.stubGlobal('fetch', fetcher);
  const props = { item: initial, organizationId: 'company-a', language: 'en' as const, licensed: true };
  const view = render(<EmailDraft {...props} />);
  await userEvent.click(screen.getByRole('button', { name: 'Find a sent copy' }));
  await screen.findByText(/No matching copy in the selection checked/);
  expect(screen.getByText(/The search covers the 100 most recent messages/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Send this email' })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Find a sent copy' }));
  await screen.findByText(/A matching copy was found.*does not confirm delivery/);
  expect(screen.getByRole('link', { name: 'Open the copy in Outlook' }).getAttribute('href')).toBe('https://outlook.office.com/mail/sent-a');
  expect(screen.queryByRole('button', { name: 'Find a sent copy' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Send this email' })).toBeNull();
  expect(fetcher).toHaveBeenCalledTimes(2);
  view.rerender(<EmailDraft {...props} language="fr" />);
  expect(screen.getByText(/Une copie correspondante a été retrouvée/)).toBeTruthy();
});

test('a lost verification response can be recovered by reading the receipt without another search or send', async () => {
  let searches = 0;
  vi.stubGlobal('fetch', vi.fn(async (path: string, options: RequestInit) => {
    if (path.endsWith('/verify')) { searches++; throw new Error('Response lost'); }
    expect(options.method).toBe('GET');
    return json({ ...initial, attempts: [{ ...initial.attempts[0], verification: {
      checked_at: 1788670000, status: 'found', searched: 10, partial: false, match_count: 1,
      copy: { item_id: 'sent-a', url: null, sent_at: '2026-09-06T09:00:00Z' },
    } }] });
  }));
  render(<EmailDraft item={initial} organizationId="company-a" language="en" licensed />);
  await userEvent.click(screen.getByRole('button', { name: 'Find a sent copy' }));
  await screen.findByRole('alert');
  await userEvent.click(screen.getByRole('button', { name: 'Check current status' }));
  await screen.findByText(/A matching copy was found/);
  await waitFor(() => expect(screen.queryByRole('alert')).toBeNull());
  expect(searches).toBe(1);
  expect(screen.queryByRole('button', { name: 'Send this email' })).toBeNull();
});
