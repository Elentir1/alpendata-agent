import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { EmailDraft } from './EmailDraft';
import type { EmailReceipt } from './EmailDraft';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const initial: EmailReceipt = { id: 'email-a', version: 1, editable: true,
  message: { to: ['client@example.com'], cc: [], bcc: [], subject: 'Session', body: 'Please find your session notes.', attachment_ids: ['document-a'] },
  attachments: [{ id: 'document-a', filename: 'Session.pdf', size: 300 }], attempts: [] };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });

test('saves the reviewed recipients and requires confirmation; a lost send response only inspects its receipt', async () => {
  let current = structuredClone(initial), sends = 0;
  vi.stubGlobal('fetch', vi.fn(async (path: string, options: RequestInit) => {
    if (options.method === 'PATCH') {
      const body = JSON.parse(options.body as string);
      expect(body.version).toBe(1); expect(body.message.to).toEqual(['reviewed@example.com']);
      current = { ...current, message: body.message, version: 2 };
      return json(current);
    }
    if (path.endsWith('/send')) {
      expect(JSON.parse(options.body as string)).toEqual({ version: 2, confirmed: true });
      sends++;
      current = { ...current, editable: false, attempts: [{ id: 'attempt-a', version: 2, status: 'unknown', error_code: 'email_send_unknown' }] };
      throw new Error('Response lost after dispatch');
    }
    return json(current);
  }));
  const props = { item: initial, organizationId: 'company-a', language: 'en' as const, licensed: true };
  const view = render(<EmailDraft {...props} />);
  expect((screen.getByRole('button', { name: 'Send this email' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.clear(screen.getByLabelText('To', { exact: true }));
  await userEvent.type(screen.getByLabelText('To', { exact: true }), 'reviewed@example.com');
  expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Save email draft' }));
  await screen.findByText(/The draft has been saved/);
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Send this email' }));
  await screen.findByText(/The send outcome is uncertain/);
  expect(screen.queryByRole('button', { name: 'Send this email' })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Check current status' }));
  await waitFor(() => expect(sends).toBe(1));
  view.rerender(<EmailDraft {...props} language="fr" />);
  expect(screen.getByText(/Le résultat de l’envoi est incertain/)).toBeTruthy();
});

test('a concurrent edit requires reloading and accepting the new content before sending', async () => {
  const changed = { ...initial, version: 2, message: { ...initial.message, subject: 'Changed elsewhere' } };
  vi.stubGlobal('fetch', vi.fn(async (_path: string, options: RequestInit) => options.method === 'PATCH'
    ? json({ detail: 'email_draft_changed' }, 409) : json(changed)));
  render(<EmailDraft item={initial} organizationId="company-a" language="en" licensed />);
  await userEvent.type(screen.getByLabelText('Subject'), ' reviewed');
  await userEvent.click(screen.getByRole('button', { name: 'Save email draft' }));
  await screen.findByRole('alert');
  expect((screen.getByRole('checkbox') as HTMLInputElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Check current status' }));
  await waitFor(() => expect((screen.getByLabelText('Subject') as HTMLInputElement).value).toBe('Changed elsewhere'));
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
  expect((screen.getByRole('button', { name: 'Send this email' }) as HTMLButtonElement).disabled).toBe(true);
});
