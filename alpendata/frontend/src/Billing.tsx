import { useEffect, useRef, useState } from 'react';
import { api, ApiError } from './api';
import type { Language } from './locale';
import { Notice } from './feedback';

interface Checkout { request_id: string; quantity: number; language: Language }
interface BillingState {
  configured: boolean; status: string; capacity: number; assistant_available: boolean;
  access_until: number; cancel_at: number | null; synced_at: number | null; can_manage: boolean;
  checkout?: Checkout | null; price?: { currency: string; unit_amount: number; interval: string };
}
const words = {
  fr: {
    title: 'Abonnement et factures', unavailable: 'La facturation en ligne n’est pas encore ouverte. Votre capacité pilote reste gérée par AlpenData.',
    pilot: 'Offre pilote', active: 'Abonnement actif', attention: 'Abonnement à vérifier', suspended: 'Les exécutions de l’assistant sont suspendues. Vérifiez le paiement et que le nombre de licences attribuées ne dépasse pas votre abonnement. Les historiques et l’administration restent accessibles.',
    quantity: 'Nombre de places', month: 'par place et par mois', total: 'Licences par mois', terms: 'Le montant final est présenté par Stripe avant confirmation. La consommation IA et les prestations ne sont pas facturées par ce parcours.',
    checkout: 'Continuer vers le paiement', resume: 'Reprendre le même paiement', portal: 'Gérer l’abonnement et les factures', refresh: 'Actualiser l’abonnement', busy: 'Vérification…',
    cancel: 'Fin prévue le', paid: 'Accès confirmé jusqu’au', error: 'La facturation n’a pas pu être vérifiée. Réessayez ; une demande déjà engagée conserve sa référence.',
    pending: 'Un paiement est déjà en préparation. Actualisez puis reprenez la même demande.', occupied: 'Choisissez au moins autant de places que de licences attribuées et d’invitations en attente.', review: 'AlpenData doit vérifier cette demande avant un nouveau paiement. Aucun nouvel abonnement n’a été demandé.',
  },
  en: {
    title: 'Subscription and invoices', unavailable: 'Online billing is not open yet. Your pilot capacity is managed by AlpenData.',
    pilot: 'Pilot plan', active: 'Active subscription', attention: 'Check your subscription', suspended: 'Assistant executions are suspended. Check payment and that assigned licences do not exceed your subscription. History and administration remain available.',
    quantity: 'Number of seats', month: 'per seat per month', total: 'Monthly licences', terms: 'Stripe shows the final amount before confirmation. AI usage and services are not billed through this flow.',
    checkout: 'Continue to payment', resume: 'Resume the same payment', portal: 'Manage subscription and invoices', refresh: 'Refresh subscription', busy: 'Checking…',
    cancel: 'Scheduled to end on', paid: 'Access confirmed until', error: 'Billing could not be verified. Try again; a request already started keeps its reference.',
    pending: 'A payment is already being prepared. Refresh and resume the same request.', occupied: 'Choose at least as many seats as assigned licences and pending invitations.', review: 'AlpenData needs to review this request before a new payment. No new subscription was requested.',
  },
};

export function Billing({ organizationId, language, updated, navigate = (url: string) => location.assign(url) }: { organizationId: string; language: Language; updated: () => Promise<void>; navigate?: (url: string) => void }) {
  const [state, setState] = useState<BillingState | null>(null), [quantity, setQuantity] = useState(3);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const request = useRef<Checkout | null>(null); const base = `/api/organizations/${organizationId}/billing`, t = words[language];
  function failed(cause: unknown) {
    const codes: Record<string, string> = { billing_checkout_pending: t.pending, billing_seats_in_use: t.occupied, billing_reconciliation_required: t.review };
    setError(cause instanceof ApiError ? codes[cause.code] || t.error : t.error);
  }
  useEffect(() => {
    let active = true;
    void api<BillingState>(base).then(async data => {
      if (!active) return;
      setState(data); setQuantity(data.checkout?.quantity ?? data.capacity); request.current = data.checkout ?? null;
      if (data.configured) {
        const fresh = await api<BillingState>(base + '/refresh', {});
        if (active) { setState(previous => ({ ...previous, ...fresh })); await updated(); }
      }
    }).catch(cause => { if (active) failed(cause); });
    return () => { active = false; };
  }, [base]);
  async function run(work: () => Promise<void>) { setBusy(true); setError(''); try { await work(); } catch (cause) { if (cause instanceof ApiError && (cause.status === 422 || cause.code === 'billing_seats_in_use')) request.current = null; failed(cause); } finally { setBusy(false); } }
  async function refresh() {
    const snapshot = await api<BillingState>(base);
    request.current = snapshot.checkout ?? null;
    if (request.current) setQuantity(request.current.quantity);
    const fresh = await api<BillingState>(base + '/refresh', {});
    setState({ ...snapshot, ...fresh }); await updated();
  }
  function go(url: string, host: string) {
    const target = new URL(url);
    if (target.protocol !== 'https:' || target.host !== host || target.username || target.password) throw new Error('Invalid payment destination');
    sessionStorage.setItem('alpendata.return-company', organizationId); navigate(target.href);
  }
  const price = state?.price;
  const money = (cents: number) => new Intl.NumberFormat(language === 'fr' ? 'fr-CH' : 'en-CH', { style: 'currency', currency: 'CHF' }).format(cents / 100);
  const date = (at: number) => new Date(at * 1000).toLocaleDateString(language === 'fr' ? 'fr-CH' : 'en-CH');
  const canSubscribe = state && ['pilot', 'canceled', 'incomplete_expired'].includes(state.status);
  return <section className="seat-summary" aria-label={t.title}><h2>{t.title}</h2><Notice>{error}</Notice>
    {state && !state.configured && <p>{t.unavailable}</p>}
    {state?.configured && <>
      <p><strong>{state.status === 'pilot' ? t.pilot : state.assistant_available ? t.active : t.attention}</strong></p>
      {!state.assistant_available && <Notice>{t.suspended}</Notice>}
      {!!state.access_until && <p>{t.paid} {date(state.access_until)}</p>}{!!state.cancel_at && <p>{t.cancel} {date(state.cancel_at)}</p>}
      {canSubscribe && <form onSubmit={event => { event.preventDefault(); void run(async () => {
        request.current ??= { request_id: crypto.randomUUID(), quantity, language };
        const result = await api<{ status: string; url: string | null }>(base + '/checkout', request.current);
        if (result.url) go(result.url, 'checkout.stripe.com');
        else { request.current = null; await refresh(); request.current = null; }
      }); }}>
        <label htmlFor="billing-quantity">{t.quantity}</label><input id="billing-quantity" type="number" min={1} max={1000} value={quantity} disabled={busy || !!request.current} onChange={event => setQuantity(Number(event.target.value))} required />
        {price && <p>{money(price.unit_amount)} {t.month} · {t.total} : <strong>{money(price.unit_amount * quantity)}</strong></p>}
        <p>{t.terms}</p><button className="primary" disabled={busy || !price}>{busy ? t.busy : request.current ? t.resume : t.checkout}</button>
      </form>}
      <div className="billing-actions"><button className="secondary" disabled={busy} onClick={() => void run(refresh)}>{t.refresh}</button>
        {state.can_manage && <button className="secondary" disabled={busy} onClick={() => void run(async () => { const result = await api<{ url: string }>(base + '/portal', { language }); go(result.url, 'billing.stripe.com'); })}>{t.portal}</button>}
      </div>
    </>}
  </section>;
}
