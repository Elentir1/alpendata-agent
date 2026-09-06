import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { CompanyResources } from './CompanyResources';
import type { CompanyResource } from './resourceTypes';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
const note: CompanyResource = { id: 'note', created_by: 'admin', can_manage: true, title: 'Workshop guidance', kind: 'note', text: 'Agree on objectives first.', filename: null, media_type: null, size: 0, version: 1, audience: 'selected', member_ids: ['coach'] };

test('an explicitly shared copy survives a lost publication reply and access conflicts require a fresh read', async () => {
  let current: CompanyResource | null = null;
  const publications: unknown[] = [], accesses: unknown[] = [];
  vi.stubGlobal('fetch', vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/recipients')) return json({ members: [{ user_id: 'coach', display_name: 'Alex', role: 'member', active: true }] });
    if (init?.method === 'POST') {
      const body = JSON.parse(String(init.body)); publications.push(body);
      current = { ...note, kind: body.kind, title: body.title, text: body.text, member_ids: body.member_ids, filename: body.document?.filename || null };
      if (publications.length === 1) throw new Error('Reply lost after commit');
      return json(current, 201);
    }
    if (init?.method === 'PATCH') { accesses.push(JSON.parse(String(init.body))); current = { ...current!, version: 2, audience: 'team', member_ids: [] }; return json({ detail: 'company_resource_changed' }, 409); }
    if (path.endsWith('/note')) return json(current);
    return json({ resources: current ? [current] : [], next_offset: null });
  }));
  render(<CompanyResources organizationId="company" userId="admin" admin language="en" />);
  await userEvent.click(screen.getByText('Company resources', { exact: true }));
  await screen.findByText('No resources shared with you.');
  await userEvent.click(screen.getByRole('button', { name: 'Publish a resource' }));
  const editor = within(await screen.findByRole('form', { name: 'Publish a resource' }));
  await userEvent.type(editor.getByLabelText('Title'), note.title);
  await userEvent.type(editor.getByLabelText('Note content'), note.text!);
  await userEvent.click(editor.getByLabelText('Alex'));
  expect((editor.getByRole('button', { name: 'Publish copy' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(editor.getByLabelText('I confirm the content and the people allowed to read this copy.'));
  await userEvent.click(editor.getByRole('button', { name: 'Publish copy' }));
  await editor.findByText(/Publication could not be confirmed/);
  expect((editor.getByLabelText('Title') as HTMLInputElement).closest('fieldset')?.disabled).toBe(true);
  await userEvent.click(editor.getByRole('button', { name: 'Retry the same publication' }));
  await screen.findByText('The resource has been saved.');
  expect(publications).toHaveLength(2); expect(publications[0]).toEqual(publications[1]);
  expect(publications[0]).toMatchObject({ member_ids: ['coach'], audience: 'selected', confirmed: true, request_id: expect.any(String) });
  await userEvent.click(screen.getByRole('button', { name: 'Read Workshop guidance' }));
  await screen.findByText(note.text!);
  await userEvent.click(screen.getByRole('button', { name: 'Manage access' }));
  const access = within(await screen.findByRole('form', { name: 'Manage access' }));
  await userEvent.click(access.getByLabelText('Alex'));
  await userEvent.click(access.getByLabelText('I confirm the new access to this copy.'));
  await userEvent.click(access.getByRole('button', { name: 'Save' }));
  await access.findByText(/The resource or its access has changed/);
  expect(accesses).toEqual([{ version: 1, audience: 'selected', member_ids: [], confirmed: true }]);
  expect((access.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(access.getByRole('button', { name: 'Refresh' }));
  await screen.findByText('Note · v2');
  await userEvent.click(screen.getByRole('button', { name: 'Publish a resource' }));
  const upload = within(await screen.findByRole('form', { name: 'Publish a resource' }));
  await userEvent.type(upload.getByLabelText('Title'), 'Workshop template');
  await userEvent.selectOptions(upload.getByLabelText('Resource type'), 'document');
  const bytes = new TextEncoder().encode('%PDF-1.7\n% synthetic upload\n%%EOF');
  const file = new File([bytes], 'Workshop.pdf', { type: 'application/pdf' });
  // JSDOM lacks File.arrayBuffer; supply the browser operation on this actual File.
  Object.defineProperty(file, 'arrayBuffer', { value: async () => bytes.buffer });
  await userEvent.upload(upload.getByLabelText('File to share'), file);
  await userEvent.selectOptions(upload.getByLabelText('Who can read this copy?'), 'team');
  await userEvent.click(upload.getByLabelText('I confirm the content and the people allowed to read this copy.'));
  expect((upload.getByLabelText('File to share') as HTMLInputElement).files?.[0]).toBe(file);
  expect((upload.getByRole('button', { name: 'Publish copy' }) as HTMLButtonElement).disabled).toBe(false);
  // JSDOM's native required-file validation ignores userEvent's populated FileList.
  fireEvent.submit(screen.getByRole('form', { name: 'Publish a resource' }));
  await screen.findByText('Workshop.pdf · v1');
  expect(publications[2]).toMatchObject({ kind: 'document', text: '', audience: 'team', member_ids: [], document: { filename: file.name, content_base64: btoa(new TextDecoder().decode(bytes)) } });
});

test('revocation clears a previously viewed note and a late response cannot follow a change of employee', async () => {
  let revoked = false, late = false;
  let finishRead: (value: Response) => void = () => {};
  vi.stubGlobal('fetch', vi.fn(async (path: string) => {
    if (path.endsWith('/note')) {
      if (late) return new Promise<Response>(resolve => { finishRead = resolve; });
      return revoked ? json({ detail: 'company_resource_not_found' }, 404) : json({ ...note, can_manage: false });
    }
    return json({ resources: [note], next_offset: null });
  }));
  const view = render(<CompanyResources organizationId="company" userId="coach" admin={false} language="fr" />);
  await userEvent.click(screen.getByText('Ressources de l’entreprise', { exact: true }));
  await userEvent.click(await screen.findByRole('button', { name: 'Consulter Workshop guidance' }));
  await screen.findByText(note.text!);
  expect(screen.queryByRole('button', { name: 'Gérer les accès' })).toBeNull();
  revoked = true;
  await userEvent.click(screen.getByRole('button', { name: 'Consulter Workshop guidance' }));
  await screen.findByText(/Cette ressource n’est plus disponible/);
  expect(screen.queryByText(note.text!)).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Actualiser' }));
  late = true;
  await userEvent.click(await screen.findByRole('button', { name: 'Consulter Workshop guidance' }));
  view.rerender(<CompanyResources organizationId="company" userId="another-coach" admin={false} language="en" />);
  finishRead(json(note));
  await screen.findByText('Company resources', { exact: true });
  expect(screen.queryByText(note.text!)).toBeNull();
  expect(screen.queryByText(note.title)).toBeNull();
});
