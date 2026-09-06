import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { PersonalMemory } from './PersonalMemory';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const initial = { available: true, memory: { version: 'a'.repeat(64), entries: ['Workshop A', 'Workshop AB'], limit: 2200 },
  user: { version: 'b'.repeat(64), entries: ['Prefers French'], limit: 1375 } };
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });

test('memory loads on opening and saves one list without discarding unsaved edits to the other', async () => {
  const sent: unknown[] = [];
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'PUT') {
      const body = JSON.parse(String(init.body)); sent.push(body);
      if (path.endsWith('/user')) return json({ detail: 'memory_changed' }, 409);
      return json({ ...initial, memory: { ...initial.memory, version: 'c'.repeat(64), entries: body.entries },
        user: { ...initial.user, version: 'd'.repeat(64), entries: ['Changed by the assistant'] } });
    }
    return json(initial);
  });
  vi.stubGlobal('fetch', fetch);
  render(<PersonalMemory organizationId="company" language="en" />);
  expect(fetch).not.toHaveBeenCalled();
  await userEvent.click(screen.getByText('My memory', { exact: true }));
  const notes = within(await screen.findByRole('region', { name: 'My working notes' }));
  const profile = within(screen.getByRole('region', { name: 'My preferences and profile' }));
  await userEvent.type(profile.getByLabelText('Item 1'), ' for coaching');
  await userEvent.click(notes.getByRole('button', { name: 'Remove item 1' }));
  await userEvent.click(notes.getByRole('button', { name: 'Save' }));
  await notes.findByText('Your active memory has been saved.');
  expect(sent[0]).toEqual({ version: initial.memory.version, entries: ['Workshop AB'] });
  expect((profile.getByLabelText('Item 1') as HTMLTextAreaElement).value).toBe('Prefers French for coaching');
  await userEvent.click(profile.getByRole('button', { name: 'Save' }));
  await profile.findByText(/Memory has changed since you read it/);
  expect(sent[1]).toEqual({ version: initial.user.version, entries: ['Prefers French for coaching'] });
  await userEvent.type(profile.getByLabelText('Item 1'), ' should not be entered');
  expect((profile.getByLabelText('Item 1') as HTMLTextAreaElement).value).toBe('Prefers French for coaching');
});

test('removal saves an empty active memory and a lost reply requires reading before any further mutation', async () => {
  let current = structuredClone(initial), puts = 0;
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'PUT') {
      puts++;
      expect(JSON.parse(String(init.body))).toEqual({ version: initial.user.version, entries: [] });
      current = { ...current, user: { ...current.user, version: 'e'.repeat(64), entries: [] } };
      throw new Error('Response lost');
    }
    return json(current);
  }));
  const view = render(<PersonalMemory organizationId="company" language="fr" />);
  await userEvent.click(screen.getByText('Ma mémoire', { exact: true }));
  let profile = within(await screen.findByRole('region', { name: 'Mes préférences et mon profil' }));
  await userEvent.click(profile.getByRole('button', { name: 'Tout retirer' }));
  expect(puts).toBe(0);
  await userEvent.click(profile.getByRole('button', { name: 'Enregistrer' }));
  await profile.findByText(/L’enregistrement n’a pas pu être confirmé/);
  expect((profile.getByRole('button', { name: 'Enregistrer' }) as HTMLButtonElement).disabled).toBe(true);
  view.rerender(<PersonalMemory organizationId="company" language="en" />);
  profile = within(screen.getByRole('region', { name: 'My preferences and profile' }));
  await userEvent.click(profile.getByRole('button', { name: 'Reload' }));
  await profile.findByText('No items remembered here.');
  expect(puts).toBe(1);
  expect(profile.queryByRole('textbox')).toBeNull();
  expect(screen.getByText(/Changes apply to new conversations/)).toBeTruthy();
});
