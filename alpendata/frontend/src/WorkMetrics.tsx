import { useState } from 'react';
import { api } from './api';
import type { Language } from './locale';

interface Metrics { executions: Record<string, number>; feedback: Record<string, number>; feedback_count: number; first_useful_median_seconds: number | null; first_useful_sample_size: number; onboarding_started: number; without_reported_useful_result_after_days: { days: number; count: number } }
export function WorkMetrics({ organizationId, language }: { organizationId: string; language: Language }) {
  const fr = language === 'fr', [value, setValue] = useState<Metrics | null>(null), [error, setError] = useState(false);
  const finished = value && ['completed', 'failed', 'cancelled', 'interrupted'].reduce((total, key) => total + (value.executions[key] || 0), 0);
  return <details className="company-rules" onToggle={event => { if (event.currentTarget.open) { setError(false); api<Metrics>(`/api/organizations/${organizationId}/work-metrics`).then(setValue).catch(() => setError(true)); } }}><summary>{fr ? 'Résultats et adoption' : 'Results and adoption'}</summary>
    <p>{fr ? 'Indicateurs agrégés de votre entreprise. Les discussions et les réponses individuelles restent privées. Les avis sont facultatifs.' : 'Aggregated company indicators. Individual conversations and responses remain private. Feedback is optional.'}</p>
    {error && <p role="status">{fr ? 'Indicateurs indisponibles.' : 'Metrics unavailable.'}</p>}
    {value && <dl><dt>{fr ? 'Exécutions terminées avec succès' : 'Executions completed successfully'}</dt><dd>{value.executions.completed || 0} / {finished || 0}</dd>
      <dt>{fr ? 'Résultats jugés utiles' : 'Results rated useful'}</dt><dd>{value.feedback.useful || 0} / {value.feedback_count} {fr ? 'avis' : 'ratings'}</dd>
      <dt>{fr ? 'Résultats à corriger' : 'Results needing changes'}</dt><dd>{value.feedback.needs_changes || 0}</dd>
      <dt>{fr ? 'Délai médian avant le premier avis utile' : 'Median time to first useful rating'}</dt><dd>{value.first_useful_median_seconds === null ? '—' : Math.round(value.first_useful_median_seconds / 60) + ' min'} · n={value.first_useful_sample_size}</dd>
      <dt>{fr ? 'Onboardings commencés depuis le début des mesures' : 'Onboardings started since measurement began'}</dt><dd>{value.onboarding_started}</dd>
      <dt>{fr ? 'Sans résultat signalé utile après 7 jours' : 'Without a useful result reported after 7 days'}</dt><dd>{value.without_reported_useful_result_after_days.count}</dd></dl>}
    <p className="subtle">{fr ? 'L’absence d’avis ne prouve pas un abandon. Les anciennes périodes non mesurées ne sont pas reconstituées.' : 'A missing rating does not prove abandonment. Unmeasured historical periods are not reconstructed.'}</p>
  </details>;
}
