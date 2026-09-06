import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { CompanyRules } from './CompanyRules';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

test('document limits stay consistent and concurrent administrator changes require reloading', async () => {
  let policy = { version: 0, allowed_capabilities: ['mail', 'calendar', 'files', 'files_write'] };
  const writes: unknown[] = [];
  let conflict = false;
  vi.stubGlobal('fetch', vi.fn(async (_path: string, options: RequestInit) => {
    const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } });
    if (options.method === 'PUT') {
      const body = JSON.parse(options.body as string); writes.push(body);
      if (conflict) { policy = { version: 2, allowed_capabilities: ['files'] }; return json({ detail: 'company_policy_changed' }, 409); }
      policy = { ...body, version: body.version + 1 };
    }
    return json(policy);
  }));
  const view = render(<CompanyRules organizationId="company-a" language="fr" />);
  await userEvent.click(await screen.findByRole('checkbox', { name: 'Rechercher et lire les documents' }));
  const writing = screen.getByRole('checkbox', { name: 'Enregistrer des documents dans Microsoft 365' }) as HTMLInputElement;
  expect(writing.checked).toBe(false); expect(writing.disabled).toBe(true);
  view.rerender(<CompanyRules organizationId="company-a" language="en" />);
  await userEvent.click(screen.getByRole('button', { name: 'Save company rules' }));
  await screen.findByText('Your company rules have been saved.');
  expect(writes).toEqual([{ version: 0, allowed_capabilities: ['mail', 'calendar'] }]);
  conflict = true;
  await userEvent.click(screen.getByRole('checkbox', { name: 'Read email' }));
  await userEvent.click(screen.getByRole('button', { name: 'Save company rules' }));
  await screen.findByText(/The rules changed since you opened them/);
  expect((screen.getByRole('button', { name: 'Save company rules' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Reload current rules' }));
  expect((await screen.findByRole('checkbox', { name: 'Find and read documents' }) as HTMLInputElement).checked).toBe(true);
  expect((screen.getByRole('checkbox', { name: 'Read email' }) as HTMLInputElement).checked).toBe(false);
  expect(writes).toHaveLength(2);
});
