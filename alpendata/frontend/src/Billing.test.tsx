import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, test, vi } from 'vitest';
import { Billing } from './Billing';

const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
const pilot = { configured: true, status: 'pilot', capacity: 3, assistant_available: true, can_manage: false, access_until: 0, cancel_at: null, synced_at: null, price: { currency: 'chf', unit_amount: 2300, interval: 'month' } };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); sessionStorage.clear(); });

test('an uncertain Checkout locks its terms and resumes the same reference after remounting', async () => {
  let saved: { request_id: string; quantity: number; language: string } | null = null;
  let writes = 0;
  const fetcher = vi.fn(async (path: string, init?: RequestInit) => {
    if (path.endsWith('/checkout')) {
      writes++;
      const body = JSON.parse(String(init?.body));
      if (!saved) { saved = body; throw new TypeError('Lost response'); }
      expect(body).toEqual(saved); return json({ status: 'open', url: 'https://checkout.stripe.com/c/pay/synthetic' });
    }
    return json({ ...pilot, checkout: saved });
  });
  vi.stubGlobal('fetch', fetcher);
  const navigate = vi.fn(), updated = vi.fn(async () => {});
  const first = render(<Billing organizationId="company-a" language="fr" updated={updated} navigate={navigate} />);
  await waitFor(() => expect((screen.getByRole('button', { name: 'Continuer vers le paiement' }) as HTMLButtonElement).disabled).toBe(false));
  await userEvent.click(screen.getByRole('button', { name: 'Continuer vers le paiement' }));
  await screen.findByRole('alert');
  expect((screen.getByLabelText('Nombre de places') as HTMLInputElement).disabled).toBe(true);
  expect(navigate).not.toHaveBeenCalled();
  first.unmount();
  render(<Billing organizationId="company-a" language="en" updated={updated} navigate={navigate} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Resume the same payment' }));
  await waitFor(() => expect(navigate).toHaveBeenCalledWith('https://checkout.stripe.com/c/pay/synthetic'));
  expect(saved).toMatchObject({ quantity: 3, language: 'fr' });
  expect(writes).toBe(2);
  expect(sessionStorage.getItem('alpendata.return-company')).toBe('company-a');
});

test('payment return keeps access suspended until the server confirms it and blocks foreign portal URLs', async () => {
  const navigate = vi.fn();
  let paid = false;
  const fetcher = vi.fn(async (path: string) => {
    if (path.endsWith('/portal')) return json({ url: 'https://billing.stripe.com.evil.example/session' });
    return json({ ...pilot, status: paid ? 'active' : 'incomplete', can_manage: true, assistant_available: paid, sync_error: paid ? null : 'billing_unavailable', next_sync_at: 1788693600, synced_at: 1788690000 });
  });
  vi.stubGlobal('fetch', fetcher);
  render(<Billing organizationId="company-a" language="en" updated={async () => {}} navigate={navigate} />);
  await screen.findByText(/Assistant executions are suspended/);
  expect(screen.getByText(/The last subscription check failed/)).toBeTruthy();
  await userEvent.click(screen.getByRole('button', { name: 'Manage subscription and invoices' }));
  await screen.findByText(/Billing could not be verified/);
  expect(navigate).not.toHaveBeenCalled();
  paid = true;
  await userEvent.click(screen.getByRole('button', { name: 'Refresh subscription' }));
  await screen.findByText('Active subscription');
  expect(screen.queryByText(/Assistant executions are suspended/)).toBeNull();
  expect(screen.queryByText(/The last subscription check failed/)).toBeNull();
  expect(fetcher.mock.calls.some(([path]) => path.endsWith('/checkout'))).toBe(false);
});
