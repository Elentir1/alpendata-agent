import { useRef, useState } from 'react';
import { errorText } from './locale';
import type { Text } from './locale';

export function useAction(t: Text) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const pending = useRef(false);
  async function run(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true; setBusy(true); setError('');
    try { await action(); } catch (cause) { setError(errorText(cause, t)); }
    finally { pending.current = false; setBusy(false); }
  }
  return { busy, error, run };
}

export function Notice({ children, success = false }: { children: React.ReactNode; success?: boolean }) {
  return children ? <div className={`notice ${success ? 'success' : 'error'}`} role={success ? 'status' : 'alert'}>{children}</div> : null;
}
