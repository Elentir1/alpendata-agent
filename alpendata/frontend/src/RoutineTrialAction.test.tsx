import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { RoutineTrialAction } from './RoutineTrialAction';
import { ScheduleActivation } from './Schedules';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });
const json = (value: unknown) => new Response(JSON.stringify(value), { status: 202 });

test('a sending trial requires a fixed envelope and confirmation and recovers the same request across languages', async () => {
  const sent: unknown[] = [], open = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    expect(path).toBe('/api/organizations/company/routines/proposal/trial');
    sent.push(JSON.parse(String(init?.body)));
    if (sent.length === 1) throw new Error('Lost reply');
    return json({ conversation_id: 'private-trial' });
  }));
  const props = { organizationId: 'company', proposalId: 'proposal', disabled: false, sendsEmail: true, onOpen: open };
  const view = render(<RoutineTrialAction {...props} language="fr" />);
  await userEvent.click(screen.getByRole('button', { name: 'Tester avec un envoi' }));
  expect(sent).toHaveLength(0);
  expect(screen.getByText(/Cet essai envoie un véritable e-mail/)).toBeTruthy();
  await userEvent.type(screen.getByLabelText('Destinataires'), 'coach@example.com, team@example.com');
  await userEvent.type(screen.getByLabelText('Objet du briefing'), 'Clients');
  expect((screen.getByRole('button', { name: 'Tester avec un envoi' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.type(screen.getByLabelText('Objet du briefing'), ' du jour');
  expect((screen.getByRole('checkbox') as HTMLInputElement).checked).toBe(false);
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Tester avec un envoi' }));
  await screen.findByText(/La réception n’est pas confirmée/);
  expect((screen.getByLabelText('Destinataires') as HTMLInputElement).disabled).toBe(true);
  view.rerender(<RoutineTrialAction {...props} language="en" />);
  await userEvent.click(screen.getByRole('button', { name: 'Retrieve this trial' }));
  expect(sent[1]).toEqual(sent[0]);
  expect(sent[0]).toEqual({ request_id: expect.any(String), email_delivery: { to: ['coach@example.com', 'team@example.com'], subject: 'Clients du jour' }, email_send_confirmed: true });
  expect(open).toHaveBeenCalledWith('private-trial');
});

test('recurrence requires an accepted trial and explicit review of recipients, including replacement version', async () => {
  const sent: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init?: RequestInit) => {
    sent.push(JSON.parse(String(init?.body))); return json({ id: 'schedule' });
  }));
  const trial = { id: 'trial', proposal_id: 'proposal', conversation_id: 'private-trial', status: 'completed', sources_verified: true,
    email_delivery: { to: ['coach@example.com'], subject: 'Briefing' }, delivery_accepted: false,
    schedule_id: 'schedule', schedule_version: 4, can_replace_schedule: true };
  const view = render(<ScheduleActivation trial={trial} organizationId="company" language="fr" disabled={false} />);
  expect(screen.queryByRole('button')).toBeNull();
  view.rerender(<ScheduleActivation trial={{ ...trial, delivery_accepted: true }} organizationId="company" language="en" disabled={false} />);
  await userEvent.click(screen.getByRole('button', { name: 'Reschedule with this new trial' }));
  expect(screen.getByText(/Each run sends a new briefing/)).toBeTruthy();
  expect(screen.getByText('coach@example.com')).toBeTruthy();
  expect(screen.queryByText(/No email will be sent/)).toBeNull();
  expect((screen.getByRole('button', { name: 'Activate recurrence' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('checkbox', { name: /authorize future sends to these recipients/ }));
  await userEvent.click(screen.getByRole('button', { name: 'Activate recurrence' }));
  expect(sent[0]).toMatchObject({ reviewed: true, reviewed_trial_id: 'trial', replaces_schedule_version: 4, email_delivery_confirmed: true });
});

test('reloading a lost sending trial retrieves its private receipt without storing the envelope or sending again', async () => {
  const sent: { request_id: string }[] = [], reads: string[] = [], open = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'POST') { sent.push(JSON.parse(String(init.body))); throw new Error('Lost reply'); }
    reads.push(path); return json({ trial: { conversation_id: 'received-trial' } });
  }));
  const props = { organizationId: 'company', proposalId: 'private-proposal', disabled: false, sendsEmail: true, onOpen: open };
  const view = render(<RoutineTrialAction {...props} language="fr" />);
  await userEvent.click(screen.getByRole('button', { name: 'Tester avec un envoi' }));
  await userEvent.type(screen.getByLabelText('Destinataires'), 'coach@example.com');
  await userEvent.type(screen.getByLabelText('Objet du briefing'), 'Private client briefing');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Tester avec un envoi' }));
  await screen.findByText(/La réception n’est pas confirmée/);
  expect(JSON.stringify(sessionStorage)).not.toMatch(/coach@example.com|Private client briefing/);
  view.unmount(); render(<RoutineTrialAction {...props} language="en" />);
  expect(reads).toHaveLength(0); expect(sent).toHaveLength(1);
  expect(screen.queryByLabelText('Recipients')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Retrieve this trial' }));
  expect(reads).toEqual(['/api/organizations/company/routines/private-proposal/trial?request_id=' + sent[0].request_id]);
  expect(sent).toHaveLength(1); expect(open).toHaveBeenCalledWith('received-trial');
  expect(sessionStorage.length).toBe(0);
});

test('failed recovery cannot create a trial and a missing receipt keeps the original request ID', async () => {
  const sent: { request_id: string }[] = [], open = vi.fn(); let reads = 0;
  vi.stubGlobal('fetch', vi.fn(async (_path: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      sent.push(JSON.parse(String(init.body)));
      if (sent.length === 1) throw new Error('Request lost');
      return json({ conversation_id: 'recovered-trial' });
    }
    if (++reads === 1) throw new Error('Cannot verify receipt');
    return json({ trial: null });
  }));
  const props = { organizationId: 'company', proposalId: 'private-proposal', disabled: false, onOpen: open };
  const view = render(<RoutineTrialAction {...props} language="en" />);
  await userEvent.click(screen.getByRole('button', { name: 'Try now' }));
  await screen.findByText(/Receipt is not confirmed/);
  view.unmount(); render(<RoutineTrialAction {...props} language="en" />);
  await userEvent.click(screen.getByRole('button', { name: 'Retrieve this trial' }));
  expect(sent).toHaveLength(1); expect(screen.queryByRole('button', { name: 'Try now' })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Retrieve this trial' }));
  await screen.findByText(/No trial was found/);
  await userEvent.click(screen.getByRole('button', { name: 'Try now' }));
  expect(sent).toHaveLength(2); expect(sent[1].request_id).toBe(sent[0].request_id);
  expect(open).toHaveBeenCalledWith('recovered-trial'); expect(sessionStorage.length).toBe(0);
});
