import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { Team } from './Team';
import { MemberAccess } from './MemberAccess';
import type { Member, Person } from './api';
import { copy } from './locale';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const coach: Member = { organization_id: 'company', user_id: 'coach', display_name: 'Alex', version: 1, role: 'member', active: true, licensed: true };
const admin: Member = { ...coach, user_id: 'admin', display_name: 'Camille', role: 'admin' };
const person: Person = { id: 'admin', display_name: 'Camille', memberships: [admin] };
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });

test('the roster reconciles a lost licence update before another edit and preserves invitations as reserved seats', async () => {
  let members = [admin, coach], patches = 0;
  const refreshAccount = vi.fn(async () => {});
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'PATCH') {
      patches++;
      expect(JSON.parse(String(init.body))).toEqual({ version: coach.version, role: 'member', active: true, licensed: false });
      members = [admin, { ...coach, licensed: false, version: 2 }];
      throw new Error('Saved, but reply lost');
    }
    if (path.endsWith('/members')) return json({ members, seats: { capacity: 3, assigned: members.filter(m => m.licensed).length, reserved: 1, available: 2 - members.filter(m => m.licensed).length } });
    if (path.endsWith('/invitations')) return json({ invitations: [{ id: 'invite', email: 'invited@example.test', expires_at: 2000000000 }] });
    if (path.endsWith('/policy')) return json({ version: 1, allowed_capabilities: [] });
    throw new Error('Unexpected path');
  }));
  const view = render(<Team company={{ id: 'company', name: 'Coaching' }} user={person} t={copy.fr} language="fr" refreshAccount={refreshAccount} />);
  const summary = within(await screen.findByRole('region', { name: 'Licences de l’entreprise' }));
  expect(summary.getByText('réservées par les invitations').parentElement?.textContent).toContain('1');
  await userEvent.click(screen.getByRole('button', { name: 'Gérer les accès Alex' }));
  const edit = within(screen.getByRole('form', { name: 'Gérer les accès Alex' }));
  await userEvent.selectOptions(edit.getByLabelText('Licence de l’assistant'), 'false');
  expect((edit.getByRole('button', { name: 'Enregistrer les accès' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(edit.getByLabelText('Je confirme ces changements d’accès.'));
  await userEvent.click(edit.getByRole('button', { name: 'Enregistrer les accès' }));
  await edit.findByText(/Le changement n’a pas pu être confirmé/);
  expect((edit.getByRole('button', { name: 'Enregistrer les accès' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(edit.getByRole('button', { name: 'Actualiser les membres' }));
  await screen.findByText('Sans licence');
  expect(patches).toBe(1); expect(refreshAccount).toHaveBeenCalledOnce();
  view.rerender(<Team company={{ id: 'company', name: 'Coaching' }} user={person} t={copy.en} language="en" refreshAccount={refreshAccount} />);
  await userEvent.click(screen.getByRole('button', { name: 'Manage access Alex' }));
  expect((screen.getByLabelText('Assistant licence') as HTMLSelectElement).value).toBe('false');
});

test('seat reservations and the final administrator prevent invalid changes, while confirmation follows the reviewed choices', async () => {
  const done = vi.fn(async () => {}), reload = vi.fn(async () => {}), close = vi.fn();
  const fetcher = vi.fn(async (_path: string, _init?: RequestInit) => json({ ...coach, licensed: true, version: 3 }));
  vi.stubGlobal('fetch', fetcher);
  const props = { self: false, language: 'en' as const, done, reload, close };
  const view = render(<MemberAccess {...props} item={{ ...coach, licensed: false, version: 2 }} lastAdmin={false} seats={{ capacity: 3, assigned: 2, reserved: 1, available: 0 }} />);
  await userEvent.selectOptions(screen.getByLabelText('Assistant licence'), 'true');
  await screen.findByText(/All seats are assigned or reserved/);
  await userEvent.click(screen.getByLabelText('I confirm these access changes.'));
  expect((screen.getByRole('button', { name: 'Save access' }) as HTMLButtonElement).disabled).toBe(true);
  view.rerender(<MemberAccess {...props} item={{ ...coach, licensed: false, version: 2 }} lastAdmin={false} seats={{ capacity: 3, assigned: 1, reserved: 1, available: 1 }} />);
  await userEvent.selectOptions(screen.getByLabelText('Company role'), 'admin');
  expect((screen.getByLabelText('I confirm these access changes.') as HTMLInputElement).checked).toBe(false);
  await userEvent.click(screen.getByLabelText('I confirm these access changes.'));
  await userEvent.click(screen.getByRole('button', { name: 'Save access' }));
  expect(fetcher).toHaveBeenCalledOnce(); expect(done).toHaveBeenCalledOnce();
  expect(JSON.parse(String(fetcher.mock.calls[0]?.[1]?.body))).toMatchObject({ role: 'admin', licensed: true, version: 2 });
  view.unmount();
  render(<MemberAccess {...props} item={admin} self lastAdmin seats={{ capacity: 3, assigned: 1, reserved: 0, available: 2 }} />);
  await userEvent.selectOptions(screen.getByLabelText('Company access'), 'false');
  await screen.findByText('The company must keep at least one active administrator.');
  expect((screen.getByRole('button', { name: 'Save access' }) as HTMLButtonElement).disabled).toBe(true);
  expect(fetcher).toHaveBeenCalledOnce();
});
