import { act, cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { Notifications } from './Notifications';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const first = { id: 'first', title: 'Briefing <img src=x onerror=alert(1)>', status: 'completed',
  created_at: 1788690000, read_at: null, conversation_id: 'result-one', schedule_id: 'schedule', error_code: null };
const second = { ...first, id: 'second', title: 'Vérifier les connexions', status: 'blocked', conversation_id: null };

test('private notification panel handles reading, stale counts, pagination and result navigation without execution', async () => {
  let resolveCount!: (response: Response) => void;
  const oldCount = new Promise<Response>(resolve => { resolveCount = resolve; });
  let counts = 0, readAt: number | null = null;
  const sent: string[] = [];
  const fetch = vi.fn(async (path: string, init?: RequestInit) => {
    if (init?.method === 'PUT') { sent.push(path); readAt = 1788690010; return json({ ...first, read_at: readAt }); }
    if (path.includes('count_only')) return ++counts === 1 ? oldCount : json({ unread: 1 });
    if (path.includes('before=')) return json({ unread: 1, notifications: [{ ...first, read_at: readAt }, { ...second, id: 'older', read_at: 1788600000 }], next_before: null });
    return json({ unread: 2, notifications: [first, second], next_before: { at: 1788690000, id: 'second' } });
  });
  vi.stubGlobal('fetch', fetch);
  const opened = vi.fn(), manage = vi.fn();
  const view = render(<Notifications organizationId="company" language="fr" onOpen={opened} onManage={manage} />);
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole('dialog')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Notifications' }));
  const panel = within(await screen.findByRole('dialog', { name: 'Notifications' }));
  await panel.findByText(first.title);
  expect(panel.queryByRole('img')).toBeNull();
  await userEvent.click(panel.getAllByRole('button', { name: 'Marquer comme lu' })[0]);
  await screen.findByRole('button', { name: 'Notifications, 1 non lue' });
  await act(async () => { resolveCount(json({ unread: 2 })); });
  expect(screen.getByRole('button', { name: 'Notifications, 1 non lue' })).toBeTruthy();
  await userEvent.click(panel.getByRole('button', { name: 'Voir les précédentes' }));
  await waitFor(() => expect(panel.getAllByRole('listitem')).toHaveLength(3));
  expect(panel.getAllByText(first.title)).toHaveLength(1);
  view.rerender(<Notifications organizationId="company" language="en" onOpen={opened} onManage={manage} />);
  await userEvent.click(panel.getByRole('button', { name: 'Open result' }));
  expect(opened).toHaveBeenCalledWith('result-one');
  expect(manage).not.toHaveBeenCalled();
  expect(sent).toEqual(['/api/organizations/company/notifications/first/read']);
  expect(screen.queryByRole('dialog')).toBeNull();
});

test('lost read response can be reconciled and revoked access removes notification content', async () => {
  let readAt: number | null = null, writes = 0, revoked = false;
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (revoked) return json({ detail: 'membership_not_found' }, 404);
    if (init?.method === 'PUT') { writes++; readAt = 1788690010; throw new Error('response lost'); }
    if (path.includes('count_only')) return json({ unread: readAt ? 0 : 1 });
    return json({ unread: readAt ? 0 : 1, notifications: [{ ...first, read_at: readAt }], next_before: null });
  }));
  render(<Notifications organizationId="company" language="en" onOpen={vi.fn()} onManage={vi.fn()} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Mark as read' }));
  await screen.findByText(/The read status could not be confirmed/);
  await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await screen.findByText('Read', { exact: true });
  expect(screen.queryByRole('button', { name: 'Mark as read' })).toBeNull();
  expect(writes).toBe(1);
  revoked = true;
  await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await screen.findByText(/Notifications could not be refreshed/);
  expect(screen.queryByText(first.title)).toBeNull();
  expect(screen.queryByRole('button', { name: 'Open result' })).toBeNull();
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Notifications' }));
});
