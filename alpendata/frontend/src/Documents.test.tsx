import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { Documents } from './Documents';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test('downloads server receipts through the private endpoint and handles expired access', async () => {
  const item = { id: 'document-a', filename: 'Séance.pdf', size: 1234, media_type: 'application/pdf' };
  const fetcher = vi.fn().mockResolvedValueOnce(new Response('{}', { status: 401 })).mockResolvedValueOnce(new Response('%PDF-test', { headers: { 'content-type': 'application/pdf' } }));
  vi.stubGlobal('fetch', fetcher);
  const create = vi.fn(() => 'blob:private-document'), revoke = vi.fn();
  vi.stubGlobal('URL', class extends URL { static createObjectURL = create; static revokeObjectURL = revoke; });
  const links: string[] = [];
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { links.push(this.download); });
  const view = render(<Documents items={[item]} organizationId="company-a" language="fr" />);
  await userEvent.click(screen.getByRole('button', { name: 'Télécharger Séance.pdf' }));
  expect((await screen.findByRole('alert')).textContent).toContain('Le téléchargement a échoué');
  expect(create).not.toHaveBeenCalled();
  view.rerender(<Documents items={[item]} organizationId="company-a" language="en" />);
  await userEvent.click(screen.getByRole('button', { name: 'Download Séance.pdf' }));
  await waitFor(() => expect(links).toEqual(['Séance.pdf']));
  expect(fetcher).toHaveBeenLastCalledWith('/api/organizations/company-a/documents/document-a/download', expect.objectContaining({ credentials: 'same-origin', cache: 'no-store' }));
  expect(create).toHaveBeenCalledOnce();
  expect(screen.queryByRole('alert')).toBeNull();
});
