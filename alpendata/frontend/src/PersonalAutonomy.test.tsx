import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { PersonalAutonomy } from './PersonalAutonomy';

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } });

test('enabling direct sends requires explicit acknowledgement and a lost response requires reload', async () => {
  let current = { version: 0, email_mode: 'confirm', automatic_allowed: true, automatic_available: false }, changes = 0;
  vi.stubGlobal('fetch', vi.fn(async (_path: string, options: RequestInit) => {
    if (options.method === 'PUT') {
      expect(JSON.parse(options.body as string)).toEqual({ version: 0, email_mode: 'automatic', acknowledged: true });
      current = { ...current, version: 1, email_mode: 'automatic' }; changes++;
      throw new Error('Response lost after saving');
    }
    return json(current);
  }));
  const props = { organizationId: 'company-a', language: 'en' as const, licensed: true };
  const view = render(<PersonalAutonomy {...props} />);
  await userEvent.click(screen.getByText('What your assistant can do'));
  await userEvent.click(await screen.findByLabelText('My assistant may send directly'));
  expect((screen.getByRole('button', { name: 'Save my choice' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Save my choice' }));
  await screen.findByRole('alert');
  expect((screen.getByRole('button', { name: 'Save my choice' }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(screen.getByRole('button', { name: 'Reload my choice' }));
  await screen.findByText(/direct sending also requires/);
  expect(changes).toBe(1);
  expect((screen.getByLabelText('My assistant may send directly') as HTMLInputElement).checked).toBe(true);
  view.rerender(<PersonalAutonomy {...props} language="fr" />);
  expect(screen.getByText(/l’envoi direct exige aussi/)).toBeTruthy();
});

test('a user can return to confirmation after company restriction and seat removal', async () => {
  vi.stubGlobal('fetch', vi.fn(async (_path: string, options: RequestInit) => {
    if (options.method === 'PUT') {
      expect(JSON.parse(options.body as string)).toEqual({ version: 2, email_mode: 'confirm', acknowledged: false });
      return json({ version: 3, email_mode: 'confirm', automatic_allowed: false, automatic_available: false });
    }
    return json({ version: 2, email_mode: 'automatic', automatic_allowed: false, automatic_available: false });
  }));
  render(<PersonalAutonomy organizationId="company-a" language="en" licensed={false} />);
  await userEvent.click(screen.getByText('What your assistant can do'));
  expect((await screen.findByLabelText('My assistant may send directly') as HTMLInputElement).disabled).toBe(true);
  await userEvent.click(screen.getByLabelText('I confirm every send'));
  await userEvent.click(screen.getByRole('button', { name: 'Save my choice' }));
  await screen.findByText('Your personal choice has been saved.');
});
