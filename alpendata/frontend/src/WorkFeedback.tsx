import { useState } from 'react';
import { api } from './api';
import type { Language } from './locale';

export function WorkFeedback({ path, language, initial }: { path: string; language: Language; initial?: string | null }) {
  const fr = language === 'fr', [outcome, setOutcome] = useState(initial || ''), [busy, setBusy] = useState(false), [error, setError] = useState(false);
  return <div className="work-feedback" aria-label={fr ? 'Utilité de cette réponse' : 'Usefulness of this response'}>
    <span>{fr ? 'Ce résultat vous aide ?' : 'Does this result help?'}</span>
    {Object.entries({ useful: fr ? 'Utile' : 'Useful', needs_changes: fr ? 'À corriger' : 'Needs changes', not_useful: fr ? 'Pas utile' : 'Not useful' }).map(([key, label]) => <button key={key} aria-pressed={outcome === key} disabled={busy} onClick={async () => { setBusy(true); setError(false); try { const result = await api<{ outcome: string }>(path, { outcome: key }, 'PUT'); setOutcome(result.outcome); } catch { setError(true); } finally { setBusy(false); } }}>{label}</button>)}
    {error && <span role="status">{fr ? 'Avis non enregistré.' : 'Feedback not saved.'}</span>}
  </div>;
}
