import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { SharePointSave } from './SharePointSave';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test('reviews the destination and requires explicit replacement; a lost response only reads status', async () => {
  const folder = { drive_id: 'drive', item_id: 'folder', name: 'Coaching', url: 'https://tenant.sharepoint.com/Coaching' };
  const review = { id: 'save-a', filename: 'Session.pdf', folder_name: 'Coaching', folder_url: folder.url,
    status: 'review', replaces_existing: true, result: null, error_code: null };
  let confirmations = 0;
  const fetcher = vi.fn(async (path: string, options: RequestInit) => {
    const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });
    if (path.includes('?artifact_id=')) return json({ saves: [] });
    if (path.endsWith('/folders/search')) return json({ folders: [folder] });
    if (path.endsWith('/folders/browse')) return json({ folder, folders: [], partial: false });
    if (path.endsWith('/saves')) return json(review);
    if (path.endsWith('/confirm')) {
      expect(JSON.parse(options.body as string)).toEqual({ replace_existing: true });
      confirmations++;
      throw new Error('Lost response after server acceptance');
    }
    if (path.endsWith('/saves/save-a')) return json({ ...review, status: 'unknown' });
    throw new Error('Unexpected request');
  });
  vi.stubGlobal('fetch', fetcher);
  const props = { item: { id: 'document-a', filename: 'Session.pdf', size: 100, media_type: 'application/pdf' },
    organizationId: 'company-a', language: 'en' as const, onClose: vi.fn() };
  const view = render(<SharePointSave {...props} />);
  await userEvent.type(screen.getByLabelText('Find a folder or a nearby document'), 'coaching');
  await userEvent.click(screen.getByRole('button', { name: 'Search' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Coaching' }));
  await userEvent.click(await screen.findByRole('button', { name: 'Prepare to save here' }));
  const confirm = await screen.findByRole('button', { name: 'Confirm save' });
  expect((confirm as HTMLButtonElement).disabled).toBe(true);
  expect(confirmations).toBe(0);
  await userEvent.click(screen.getByRole('checkbox', { name: 'I confirm replacing the existing file.' }));
  await userEvent.click(confirm);
  await screen.findByText(/The outcome needs checking/);
  expect(screen.queryByRole('button', { name: 'Confirm save' })).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: 'Refresh result' }));
  await waitFor(() => expect(confirmations).toBe(1));
  view.rerender(<SharePointSave {...props} language="fr" />);
  expect(screen.getByText(/Le résultat reste à vérifier/)).toBeTruthy();
});
