import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { CompanyResources } from './CompanyResources';
import { Documents } from './Documents';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
const directory = { current_user_id: 'author', members: [
  { user_id: 'author', display_name: 'Camille', role: 'member', active: true },
  { user_id: 'reader', display_name: 'Alex', role: 'member', active: true },
  { user_id: 'admin', display_name: 'Administrator', role: 'admin', active: true },
] };
const confirmation = 'I confirm the content and the people allowed to read this copy.';

test('a colleague can publish and manage their own copy, reconfirming when its audience changes', async () => {
  let copy: Record<string, unknown> | null = null;
  const paths: string[] = [], publications: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    paths.push(path);
    if (path.endsWith('/recipients')) return json(directory);
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); publications.push(body);
      copy = { ...body, id: 'copy', created_by: 'author', can_manage: true, version: 1, size: 0 };
      return json(copy, 201);
    }
    if (path.endsWith('/copy')) return json(copy);
    return json({ resources: copy ? [copy] : [], next_offset: null });
  }));
  render(<CompanyResources organizationId="company" userId="author" admin={false} language="en" />);
  await userEvent.click(screen.getByText('Company resources', { exact: true }));
  await screen.findByText('No resources shared with you.');
  await userEvent.click(screen.getByRole('button', { name: 'Publish a resource' }));
  const editor = within(await screen.findByRole('form', { name: 'Publish a resource' }));
  expect(editor.queryByLabelText('Camille')).toBeNull();
  expect(editor.queryByLabelText('Administrator')).toBeNull();
  await userEvent.type(editor.getByLabelText('Title'), 'Session guidance');
  await userEvent.type(editor.getByLabelText('Note content'), 'Confirm the objectives with the client.');
  await userEvent.click(editor.getByLabelText(confirmation));
  await userEvent.click(editor.getByLabelText('Alex'));
  expect((editor.getByLabelText(confirmation) as HTMLInputElement).checked).toBe(false);
  expect((editor.getByRole('button', { name: 'Publish copy' }) as HTMLButtonElement).disabled).toBe(true);
  expect(publications).toHaveLength(0);
  await userEvent.click(editor.getByLabelText(confirmation));
  await userEvent.click(editor.getByRole('button', { name: 'Publish copy' }));
  await screen.findByText('The resource has been saved.');
  await userEvent.click(screen.getByRole('button', { name: 'Read Session guidance' }));
  await screen.findByRole('button', { name: 'Manage access' });
  expect(publications).toEqual([expect.objectContaining({ audience: 'selected', member_ids: ['reader'], confirmed: true })]);
  expect(paths.every(path => path.startsWith('/api/organizations/company/company-resources'))).toBe(true);
});

test('sharing a chat artifact requires confirmation and retries the same server copy after a lost reply', async () => {
  const paths: string[] = [], publications: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    paths.push(path);
    if (path.endsWith('/recipients')) return json(directory);
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); publications.push(body);
      if (publications.length === 1) throw new Error('Response lost after commit');
      return json({ id: 'published-copy' }, 201);
    }
    throw new Error('Unexpected request');
  }));
  render(<Documents organizationId="company" language="en" items={[{ id: 'my-artifact', filename: 'Session.pdf', size: 128, media_type: 'application/pdf' }]} />);
  await userEvent.click(screen.getByRole('button', { name: 'Share Session.pdf with the company' }));
  const editor = within(await screen.findByRole('form', { name: 'Publish a resource' }));
  expect(editor.queryByLabelText('File to share')).toBeNull();
  expect(editor.queryByLabelText('Camille')).toBeNull();
  expect(publications).toHaveLength(0);
  await userEvent.click(editor.getByLabelText('Alex'));
  await userEvent.click(editor.getByLabelText(confirmation));
  await userEvent.click(editor.getByRole('button', { name: 'Publish copy' }));
  await editor.findByText(/Publication could not be confirmed/);
  expect((editor.getByLabelText('Title') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true);
  await userEvent.click(editor.getByRole('button', { name: 'Retry the same publication' }));
  await screen.findByText('The copy is shared in company resources.');
  expect(publications).toHaveLength(2); expect(publications[1]).toEqual(publications[0]);
  expect(publications[0]).toEqual({ title: 'Session.pdf', kind: 'document', text: '', source_document_id: 'my-artifact', audience: 'selected', member_ids: ['reader'], confirmed: true, request_id: expect.any(String) });
  expect(paths.every(path => path.startsWith('/api/organizations/company/company-resources'))).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Close' }));
  expect(screen.queryByRole('form', { name: 'Publish a resource' })).toBeNull();
});
