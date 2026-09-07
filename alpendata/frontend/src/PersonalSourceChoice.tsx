import { useState } from 'react';
import { api } from './api';
import type { Language } from './locale';

export function PersonalSourceChoice({ organizationId, language, provider, choose, disabled }: {
  organizationId: string; language: Language; provider: string; choose: (provider: string) => void; disabled: boolean;
}) {
  const fr = language === 'fr', [connections, setConnections] = useState<{ provider: string; capabilities: string[] }[] | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(false);
  return <div>
    {connections === null && <button type="button" className="text-button" disabled={busy || disabled} onClick={async () => {
      setBusy(true); setError(false);
      try { const result = await api<{ connections: { provider: string; capabilities: string[] }[] }>(`/api/organizations/${organizationId}/chat`); setConnections(result.connections || []); }
      catch { setError(true); } finally { setBusy(false); }
    }}>{fr ? 'Choisir les outils de cet essai' : 'Choose tools for this trial'}</button>}
    {error && <p role="alert">{fr ? 'Vos connexions ne sont pas disponibles. Réessayez.' : 'Your connections are unavailable. Try again.'}</p>}
    {connections && !connections.length && <p className="subtle">{fr ? 'Aucun outil connecté. Les propositions utiliseront les informations de votre profil et de cette demande.' : 'No connected tools. Proposals will use your profile and this request.'}</p>}
    {connections && connections.length > 0 && <><label>{fr ? 'Connexion pour cet essai' : 'Connection for this trial'}<select disabled={disabled} value={provider} onChange={event => choose(event.target.value)}>
      <option value="">{fr ? 'Sélection automatique' : 'Automatic selection'}</option>
      {connections.map(connection => <option key={connection.provider} value={connection.provider}>{connection.provider === 'microsoft' ? 'Microsoft 365' : 'Infomaniak'}</option>)}
    </select></label><p className="subtle">{fr ? 'Seuls vos comptes personnels connectés sont proposés. Chaque essai utilise une seule connexion ; les comptes des collègues restent privés.' : 'Only your connected personal accounts are listed. Each trial uses one connection; colleagues’ accounts remain private.'}</p></>}
  </div>;
}
