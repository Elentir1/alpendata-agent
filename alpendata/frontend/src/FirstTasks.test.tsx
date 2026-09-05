import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { FirstTasks } from './FirstTasks';
import { Chat } from './Chat';
import { copy } from './locale';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test('personal onboarding retains the same request and language after an uncertain submission', async () => {
  const sent: unknown[] = [], open = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    expect(path).toBe('/api/organizations/my-company/onboarding/proposals');
    sent.push(JSON.parse(String(init?.body)));
    if (sent.length === 1) throw new Error('Response lost');
    return json({ conversation: { id: 'private-plan' } }, 202);
  }));
  const view = render(<FirstTasks organizationId="my-company" language="fr" onOpen={open} />);
  await userEvent.type(screen.getByLabelText('Par quoi aimeriez-vous commencer ?'), 'Préparer mes clients');
  await userEvent.click(screen.getByRole('button', { name: 'Trouver mes premières tâches' }));
  await screen.findByText(/La réception n’est pas confirmée/);
  expect((screen.getByLabelText('Par quoi aimeriez-vous commencer ?') as HTMLTextAreaElement).disabled).toBe(true);
  view.rerender(<FirstTasks organizationId="my-company" language="en" onOpen={open} />);
  await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
  expect(sent[1]).toEqual(sent[0]);
  expect(sent[1]).toEqual({ request_id: expect.any(String), language: 'fr', refinement: 'Préparer mes clients' });
  expect(open).toHaveBeenCalledWith('private-plan');
});

test('a proposal launches only on user choice and opens its private result with returned sources', async () => {
  const base = '/api/organizations/my-company';
  const plan = { id: 'plan', title: 'My first tasks', language: 'en', created_at: 1 };
  const trial = { id: 'trial-chat', title: 'Client briefing', language: 'en', created_at: 2 };
  const launched: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (path === base + '/chat') return json({ available: true, conversations: launched.length ? [trial, plan] : [plan], next_offset: null });
    if (path === base + '/chat/conversations/plan') return json({ ...plan, turns: [], next_after: null, proposals: [{ id: 'proposal', title: 'Client briefing', benefit: 'Prepare coaching follow-ups', focus: 'Client questions' }] });
    if (path === base + '/routines/proposal/trial') { launched.push(JSON.parse(String(init?.body))); return json({ conversation_id: trial.id }, 202); }
    if (path === base + '/chat/conversations/trial-chat') return json({ ...trial, next_after: null,
      trials: [{ id: 'trial', status: 'completed', sources_verified: true }],
      turns: [{ id: 'turn', sequence: 1, request_id: 'request', message: 'Try once', response: 'Your result', status: 'completed', sources: [
        { kind: 'mail', label: 'Client request', url: 'https://outlook.office.com/mail/message' },
        { kind: 'mail', label: '<script>Untrusted subject</script>', url: 'javascript:alert(1)' },
      ] }],
    });
    throw new Error('Unexpected path: ' + path);
  }));
  render(<Chat organizationId="my-company" licensed language="en" t={copy.en} initialConversationId="plan" />);
  await screen.findByText('Prepare coaching follow-ups');
  expect(launched).toHaveLength(0);
  await userEvent.click(screen.getByRole('button', { name: 'Try now' }));
  await screen.findByText('Your result');
  expect(launched).toEqual([{ request_id: expect.any(String) }]);
  expect(screen.getByRole('link', { name: 'Client request' }).getAttribute('href')).toBe('https://outlook.office.com/mail/message');
  expect(screen.queryByRole('link', { name: '<script>Untrusted subject</script>' })).toBeNull();
  expect(document.querySelector('.chat-sources script')).toBeNull();
  expect(screen.getByText(/The trial is complete and the required sources were consulted/)).toBeTruthy();
});
