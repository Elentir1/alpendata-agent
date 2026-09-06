import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { InvitationForm } from './InvitationForm';
import { copy } from './locale';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test('a lost delivery response keeps the same recipient, language and request ID on retry', async () => {
  const bodies: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_path, init) => {
    bodies.push(JSON.parse(init.body));
    if (bodies.length === 1) throw new TypeError('Lost response');
    return new Response(JSON.stringify({ id: 'one', email: 'coach@example.com', delivery_status: 'submitted' }), { status: 201 });
  }));
  const done = vi.fn(async () => {});
  render(<InvitationForm base="/api/organizations/a" language="fr" t={copy.fr} disabled={false} done={done} />);
  await userEvent.type(screen.getByLabelText(copy.fr.inviteEmail), 'coach@example.com');
  await userEvent.selectOptions(screen.getByLabelText('Langue de l’e-mail'), 'en');
  await userEvent.click(screen.getByRole('button', { name: 'Envoyer l’invitation' }));
  const retry = await screen.findByRole('button', { name: 'Vérifier le même envoi' });
  expect((screen.getByLabelText(copy.fr.inviteEmail) as HTMLInputElement).disabled).toBe(true);
  await userEvent.click(retry);
  await screen.findByRole('heading', { name: 'E-mail transmis · en attente d’acceptation' });
  expect(bodies).toHaveLength(2); expect(bodies[1]).toEqual(bodies[0]);
  expect(bodies[0]).toEqual({ email: 'coach@example.com', language: 'en', request_id: expect.any(String) });
  expect(done).toHaveBeenCalledTimes(1);
});

test('unknown delivery is explicit and a cancelled receipt stops showing a pending invitation', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ id: 'one', delivery_status: 'unknown' }), { status: 201 })));
  const props = { base: '/api/organizations/a', language: 'en' as const, t: copy.en, disabled: false, done: async () => {} };
  const view = render(<InvitationForm {...props} />);
  await userEvent.type(screen.getByLabelText(copy.en.inviteEmail), 'coach@example.com');
  await userEvent.click(screen.getByRole('button', { name: 'Send invitation' }));
  await screen.findByRole('heading', { name: 'Check delivery with the recipient' });
  view.rerender(<InvitationForm {...props} revokedId="one" />);
  await screen.findByRole('heading', { name: 'Invitation cancelled' });
  expect(screen.queryByText('If the email does not arrive, cancel this invitation before creating another one.')).toBeNull();
});
