import { useState } from 'react';
import { SlidersHorizontal } from 'lucide-react';
import { Notice } from './feedback';
import { ProjectDialog } from './ProjectDialog';
import type { Language } from './locale';

export interface WorkSettings { depth: 'quick' | 'balanced' | 'deep'; autonomy: 'prepare' | 'confirm' | 'authorized'; sources: string[] }
export interface WorkConfiguration { work_settings: WorkSettings; integration_provider?: string }
export const defaultWorkSettings: WorkSettings = { depth: 'balanced', autonomy: 'confirm', sources: ['mail', 'calendar', 'files', 'documents', 'project', 'web'] };

export function WorkOptions({ researchAvailable = false, language, current, connections, disabled, existing, apply }: { researchAvailable?: boolean; language: Language; current: WorkConfiguration; connections: { provider: string; capabilities: string[] }[]; disabled: boolean; existing: boolean; apply: (value: WorkConfiguration) => Promise<void> }) {
  const fr = language === 'fr';
  const [error, setError] = useState(false);
  const [open, setOpen] = useState(false), [value, setValue] = useState(current), [saving, setSaving] = useState(false);
  const settings = value.work_settings;
  const available = new Set(['documents', 'project', ...(researchAvailable ? ['web'] : []), ...(connections.find(item => item.provider === value.integration_provider) || connections[0])?.capabilities || []]);
  const names: Record<string, string> = { mail: fr ? 'Ma messagerie' : 'My mailbox', calendar: fr ? 'Mon agenda' : 'My calendar', files: fr ? 'Mes fichiers connectés' : 'My connected files', documents: fr ? 'Pièces jointes de la discussion' : 'Conversation attachments', project: fr ? 'Contexte et ressources du projet' : 'Project context and resources', web: 'Web' };
  function change(update: Partial<WorkSettings>) { setValue({ ...value, work_settings: { ...settings, ...update } }); }
  return <><button type="button" className="composer-tools" disabled={disabled} onClick={() => { setValue(current); setOpen(true); }}><SlidersHorizontal size={16} /><span>{fr ? 'Réglages' : 'Work settings'}</span></button>
    {open && <ProjectDialog language={language} disabled={saving} close={() => setOpen(false)}><form onSubmit={async event => { event.preventDefault(); setSaving(true); setError(false); try { await apply(value); setOpen(false); } catch { setError(true); } finally { setSaving(false); } }}><h2>{fr ? 'Comment travailler ensemble' : 'How we work together'}</h2>
      <label>{fr ? 'Profondeur' : 'Depth'}<select value={settings.depth} onChange={event => change({ depth: event.target.value as WorkSettings['depth'] })}><option value="quick">{fr ? 'Rapide — aller à l’essentiel' : 'Quick — get to the point'}</option><option value="balanced">{fr ? 'Équilibrée — préparer et vérifier' : 'Balanced — prepare and check'}</option><option value="deep">{fr ? 'Approfondie — comparer et recouper' : 'Deep — compare and cross-check'}</option></select></label>
      {connections.length > 1 && <label>{fr ? 'Connexion personnelle' : 'Personal connection'}<select value={value.integration_provider || connections[0].provider} onChange={event => setValue({ ...value, integration_provider: event.target.value })}>{connections.map(item => <option key={item.provider} value={item.provider}>{item.provider === 'microsoft' ? 'Microsoft 365' : 'Infomaniak'}</option>)}</select></label>}
      <fieldset><legend>{fr ? 'Sources autorisées pour les prochains travaux' : 'Allowed sources for upcoming work'}</legend>{Object.entries(names).map(([key, name]) => <label className="archive-filter" key={key}><input type="checkbox" disabled={!available.has(key)} checked={available.has(key) && settings.sources.includes(key)} onChange={event => change({ sources: event.target.checked ? [...new Set([...settings.sources, key])] : settings.sources.filter(item => item !== key) })} />{name}{!available.has(key) && <small>{key === 'web' ? fr ? ' · à activer par AlpenData' : ' · AlpenData activation needed' : fr ? ' · à connecter' : ' · connection needed'}</small>}</label>)}</fieldset>
      <label>{fr ? 'Autonomie' : 'Autonomy'}<select value={settings.autonomy} onChange={event => change({ autonomy: event.target.value as WorkSettings['autonomy'] })}><option value="prepare">{fr ? 'Préparer uniquement' : 'Prepare only'}</option><option value="confirm">{fr ? 'Demander ma validation' : 'Ask for my approval'}</option><option value="authorized">{fr ? 'Exécuter les actions que j’ai autorisées' : 'Execute actions I have authorized'}</option></select></label>
      <p className="subtle">{fr ? 'Les droits de vos connexions et les règles de l’entreprise restent prioritaires. Un outil non configuré reste indisponible.' : 'Connection permissions and company rules still apply. Unconfigured tools remain unavailable.'}</p>
      {existing && <p>{fr ? 'Ces réglages ouvrent une nouvelle variante avec votre historique. Les actions passées ne seront pas rejouées.' : 'These settings open a new branch with your history. Past actions will not be replayed.'}</p>}
      <Notice>{error && (fr ? 'Ces réglages n’ont pas pu être appliqués. Ils restent affichés ici.' : 'These settings could not be applied. Your choices remain here.')}</Notice><button className="primary" disabled={saving}>{existing ? fr ? 'Continuer avec ces réglages' : 'Continue with these settings' : fr ? 'Appliquer' : 'Apply'}</button>
    </form></ProjectDialog>}
  </>;
}
