export type Membership = { organization_id: string; user_id: string; role: 'admin' | 'member'; active: boolean; licensed: boolean };
export interface Member extends Membership { display_name: string; version: number }
export type Person = { id: string; display_name: string; memberships: Membership[]; password_account?: boolean };
export type Company = { id: string; name: string };
export type Options = { microsoft: boolean; invitation_email: boolean; password?: boolean };
export type Onboarding = { language: 'fr' | 'en'; step: string; answers: { role?: string; activity?: string; needs?: string; sector?: string; success?: string; preferred_output?: '' | 'document' | 'spreadsheet' | 'presentation' | 'checklist' } };

export class ApiError extends Error {
  constructor(public status: number, public code: string, public retryAfter = 0) { super(code); }
}

export async function api<T>(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST'): Promise<T> {
  if (!path.startsWith('/api/')) throw new Error('Invalid API path');
  const response = await fetch(path, {
    method, credentials: 'same-origin', cache: 'no-store',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => { throw new ApiError(0, 'network_error'); });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'request_failed', Number(response.headers.get('Retry-After')) || 0);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export type PendingInvitation = { token: string; verification_token?: string };
const storageKey = 'alpendata.pending-invitation';
const validToken = (value: unknown): value is string => typeof value === 'string' && /^[A-Za-z0-9_-]{32,512}$/.test(value);

export function rememberInvitation(value: PendingInvitation | null) {
  if (value) sessionStorage.setItem(storageKey, JSON.stringify(value));
  else sessionStorage.removeItem(storageKey);
}

export function readInvitation(): PendingInvitation | null {
  const fragment = new URLSearchParams(location.hash.slice(1));
  if (fragment.has('invitation')) {
    const token = fragment.get('invitation');
    const proof = fragment.get('verification');
    history.replaceState(null, '', location.pathname);
    if (validToken(token)) rememberInvitation({ token, ...(validToken(proof) ? { verification_token: proof } : {}) });
    else rememberInvitation(null);
  }
  try {
    const value = JSON.parse(sessionStorage.getItem(storageKey) || 'null');
    if (value && validToken(value.token) && (value.verification_token === undefined || validToken(value.verification_token))) return value;
  } catch { /* Invalid local data never becomes an authorization input. */ }
  return null;
}
