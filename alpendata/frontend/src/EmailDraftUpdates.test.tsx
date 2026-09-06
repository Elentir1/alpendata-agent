import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test } from 'vitest';
import { EmailDraft } from './EmailDraft';
import type { EmailReceipt } from './EmailDraft';

afterEach(cleanup);
const draft: EmailReceipt = { id: 'draft', version: 1, editable: true, attachments: [], attempts: [],
  message: { to: ['coach@example.com'], cc: [], bcc: [], subject: 'Briefing', body: 'Client updates', attachment_ids: [] } };

test('a receipt arriving through chat polling replaces the draft controls without offering another send', async () => {
  const props = { organizationId: 'company', licensed: true, language: 'en' as const };
  const view = render(<EmailDraft {...props} item={draft} />);
  expect(screen.getByRole('heading', { name: 'Email draft' })).toBeTruthy();
  const accepted: EmailReceipt = { ...draft, editable: false, attempts: [{ id: 'attempt', version: 1, status: 'accepted', error_code: null, initiator: 'agent' }] };
  view.rerender(<EmailDraft {...props} item={accepted} />);
  expect(screen.getByRole('heading', { name: 'Email and send receipt' })).toBeTruthy();
  expect(screen.getByText(/Microsoft accepted the send request/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: 'Send this email' })).toBeNull();
  // An older poll must not restore controls after the receipt was displayed.
  view.rerender(<EmailDraft {...props} item={{ ...draft }} />);
  expect(screen.queryByRole('button', { name: 'Send this email' })).toBeNull();
});

test('a poll showing another edit preserves local text and requires a reload', async () => {
  const props = { organizationId: 'company', licensed: true, language: 'en' as const };
  const view = render(<EmailDraft {...props} item={draft} />);
  await userEvent.type(screen.getByLabelText('Subject'), ' reviewed locally');
  view.rerender(<EmailDraft {...props} item={{ ...draft, version: 2, message: { ...draft.message, subject: 'Changed elsewhere' } }} />);
  expect((screen.getByLabelText('Subject') as HTMLInputElement).value).toBe('Briefing reviewed locally');
  expect(screen.getByRole('alert').textContent).toContain('changed elsewhere');
  expect((screen.getByRole('button', { name: 'Send this email' }) as HTMLButtonElement).disabled).toBe(true);
});
