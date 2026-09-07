import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { Chat } from './Chat';
import { copy } from './locale';

const base = '/api/organizations/company-a/chat';
const conversation = { id: 'personal-chat', title: 'Mes rendez-vous', language: 'fr', created_at: 1 };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test('chat creates a conversation, sends a durable request and renders its returned text safely', async () => {
  let exists = false;
  const turns: unknown[] = [];
  let saved: { request_id: string; message: string } | null = null;
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    expect(init?.credentials).toBe('same-origin');
    if (path === base + '/projects') return json({ projects: [] });
    if (path === base) return json({ available: true, conversations: exists ? [conversation] : [], next_offset: null });
    if (path === base + '/conversations' && init?.method === 'POST') {
      expect(JSON.parse(String(init.body))).toEqual({ language: 'fr' }); exists = true; return json(conversation, 201);
    }
    if (path === base + '/conversations/personal-chat/turns') {
      saved = JSON.parse(String(init?.body));
      turns.push({ ...saved, id: 'turn-a', sequence: 1, response: '<img src=x onerror=alert(1)>', status: 'completed', cancel_requested: false });
      return json(turns[0], 202);
    }
    if (path.startsWith(base + '/conversations/personal-chat')) return json({ ...conversation, turns, next_after: null });
    throw new Error('Unexpected API request');
  }));
  const view = render(<Chat organizationId="company-a" licensed language="fr" t={copy.fr} />);
  await waitFor(() => expect((screen.getByRole('button', { name: 'Nouvelle conversation' }) as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(screen.getByRole('button', { name: 'Nouvelle conversation' }));
  const input = await screen.findByLabelText('Votre message');
  await userEvent.type(input, 'Prépare mes rendez-vous');
  view.rerender(<Chat organizationId="company-a" licensed language="en" t={copy.en} />);
  expect((screen.getByLabelText('Your message') as HTMLTextAreaElement).value).toBe('Prépare mes rendez-vous');
  await userEvent.click(screen.getByRole('button', { name: 'Send' }));
  expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeTruthy();
  expect(document.querySelector('.chat-messages img')).toBeNull();
  expect(saved).toEqual({ request_id: expect.any(String), message: 'Prépare mes rendez-vous' });
  expect((screen.getByLabelText('Your message') as HTMLTextAreaElement).value).toBe('');
});

test('an uncertain network send retries the same idempotency key', async () => {
  const sent: unknown[] = [];
  let completed: unknown = null;
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (path === base + '/projects') return json({ projects: [] });
    if (path === base) return json({ available: true, conversations: [conversation], next_offset: null });
    if (path.endsWith('/turns')) {
      sent.push(JSON.parse(String(init?.body)));
      if (sent.length === 1) throw new Error('Connection lost after submission');
      completed = { ...sent[0] as object, id: 'turn-a', sequence: 1, response: 'Verified reply', status: 'completed', cancel_requested: false };
      return json(completed, 202);
    }
    return json({ ...conversation, turns: completed ? [completed] : [], next_after: null });
  }));
  render(<Chat organizationId="company-a" licensed language="en" t={copy.en} />);
  await userEvent.type(await screen.findByLabelText('Your message'), 'Prepare a briefing');
  await userEvent.click(screen.getByRole('button', { name: 'Send' }));
  await screen.findByText(/Receipt of the message is not confirmed/);
  expect((screen.getByLabelText('Your message') as HTMLTextAreaElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Retry sending' }));
  await screen.findByText('Verified reply');
  expect(sent).toHaveLength(2);
  expect(sent[1]).toEqual(sent[0]);
});

test('running work can be stopped and suspended users retain private history', async () => {
  const turn = { id: 'turn-a', request_id: 'request-a', sequence: 1, message: 'My private task', response: null, status: 'running', cancel_requested: false };
  let cancelled = false;
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    if (path === base + '/projects') return json({ projects: [] });
    if (path === base) return json({ available: true, conversations: [conversation], next_offset: null });
    if (path.endsWith('/turn-a/cancel')) { cancelled = true; turn.status = 'cancelled'; turn.cancel_requested = true; return json(turn); }
    return json({ ...conversation, turns: [turn], next_after: null });
  }));
  render(<Chat organizationId="company-a" licensed={false} language="en" t={copy.en} />);
  await screen.findByText('My private task');
  expect((screen.getByRole('button', { name: 'New conversation' }) as HTMLButtonElement).disabled).toBe(true);
  expect((screen.getByLabelText('Your message') as HTMLTextAreaElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Stop' }));
  await screen.findByText('This request was stopped.');
  expect(cancelled).toBe(true);
});
