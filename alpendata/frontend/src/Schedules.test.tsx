import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { ScheduleActivation, Schedules } from './Schedules';
import { copy } from './locale';

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const trial = { id: 'trial', proposal_id: 'proposal', conversation_id: 'trial-conversation', status: 'completed', sources_verified: true };
const schedule = { id: 'schedule', title: 'Préparer mes clients', focus: 'Questions des clients', capabilities: ['mail'], status: 'active', version: 1, next_run_at: 1788771600, reason_code: null, frequency: 'weekdays', local_time: '09:00', timezone: 'Europe/Zurich', weekday: 0 };

test('recurrence activation requires review and retries an uncertain response with identical parameters', async () => {
  const sent: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    expect(path).toBe('/api/organizations/company/schedules'); sent.push(JSON.parse(String(init?.body)));
    if (sent.length === 1) throw new Error('Lost response');
    return json(schedule, 201);
  }));
  const view = render(<ScheduleActivation trial={{ ...trial, sources_verified: false }} organizationId="company" language="fr" disabled={false} />);
  expect(screen.queryByRole('button')).toBeNull();
  view.rerender(<ScheduleActivation trial={trial} organizationId="company" language="fr" disabled={false} />);
  await userEvent.click(screen.getByRole('button', { name: 'Planifier cette tâche' }));
  expect(sent).toHaveLength(0);
  expect((screen.getByRole('button', { name: 'Activer la récurrence' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.selectOptions(screen.getByLabelText('Fréquence'), 'weekly');
  await userEvent.selectOptions(screen.getByLabelText('Jour'), '2');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Activer la récurrence' }));
  await screen.findByText(/La réception n’est pas confirmée/);
  await userEvent.click(screen.getByRole('button', { name: 'Réessayer l’activation' }));
  await screen.findByText(/Prochaine exécution/);
  expect(sent).toHaveLength(2);
  expect(sent[1]).toEqual(sent[0]);
  expect(sent[0]).toMatchObject({ reviewed: true, reviewed_trial_id: trial.id, frequency: 'weekly', weekday: 2, timezone: 'Europe/Zurich' });
});

test('schedule management shows results and pauses using the current version', async () => {
  let row = { ...schedule };
  const open = vi.fn();
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (path === '/api/organizations/company/schedules') return json({ schedules: [row], next_offset: null });
    if (init?.method === 'PATCH') { const body = JSON.parse(String(init.body)); expect(body.version).toBe(row.version); row = { ...row, ...body, version: row.version + 1 }; return json(row); }
    if (path.endsWith('/pause')) { expect(JSON.parse(String(init?.body))).toEqual({ version: row.version }); row = { ...row, status: 'paused', version: row.version + 1 }; return json(row); }
    if (path.endsWith('/occurrences')) return json({ occurrences: [{ id: 'run', scheduled_for: 1788685200, status: 'completed', conversation_id: 'private-result' }], next_before: null });
    throw new Error('Unexpected request');
  }));
  render(<Schedules organizationId="company" licensed language="fr" t={copy.fr} onOpen={open} />);
  await screen.findByText('Préparer mes clients');
  await userEvent.click(screen.getByRole('button', { name: 'Dernières exécutions' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Voir le résultat' }));
  expect(open).toHaveBeenCalledWith('private-result');
  await userEvent.click(screen.getByRole('button', { name: 'Modifier l’horaire' }));
  await userEvent.selectOptions(screen.getByLabelText('Fréquence'), 'daily');
  await userEvent.click(screen.getByRole('button', { name: 'Enregistrer l’horaire' }));
  await screen.findByText(/Tous les jours/);
  await waitFor(() => expect((screen.getByRole('button', { name: 'Suspendre' }) as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(screen.getByRole('button', { name: 'Suspendre' }));
  await screen.findByText('Suspendue');
  await waitFor(() => expect((screen.getByRole('button', { name: 'Reprendre' }) as HTMLButtonElement).disabled).toBe(false));
});
