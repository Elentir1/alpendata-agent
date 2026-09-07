import { useEffect, useState } from 'react';
import { api } from './api';
import { InfomaniakDav } from './InfomaniakDav';
import { Notice } from './feedback';
import type { Language } from './locale';

interface Connection { available: boolean; status: string; email: string | null; capabilities: string[]; allowed_capabilities: string[] }
export function Infomaniak({ organizationId, language }: { organizationId: string; language: Language }) {
  const fr = language === 'fr', path = `/api/organizations/${organizationId}/integrations/infomaniak`;
  const [connection, setConnection] = useState<Connection | null>(null), [email, setEmail] = useState('');
  const [password, setPassword] = useState(''), [send, setSend] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(false);
  useEffect(() => { let active = true; api<Connection>(path).then(value => { if (active) setConnection(value); }).catch(() => { if (active) setError(true); }); return () => { active = false; }; }, [path]);
  return <section className="infomaniak-connection"><h3>Infomaniak Mail</h3><p>{fr ? 'Connectez votre propre boîte mail. Aucune connexion Microsoft n’est nécessaire.' : 'Connect your own mailbox. No Microsoft connection is required.'}</p>
    <Notice>{error && (fr ? 'La connexion n’a pas pu être vérifiée. Vérifiez les accès de votre boîte mail et réessayez.' : 'The connection could not be verified. Check your mailbox credentials and retry.')}</Notice>
    {connection?.capabilities.includes('mail') ? <><Notice success>{fr ? 'Connecté' : 'Connected'} · {connection.email}</Notice><p className="subtle">{fr ? 'Ouvrez une nouvelle discussion pour utiliser cette connexion.' : 'Open a new conversation to use this connection.'}</p></> : <form onSubmit={async event => {
      event.preventDefault(); setBusy(true); setError(false);
      try { await api(path, { email, password, capabilities: send ? ['mail', 'mail_send'] : ['mail'] }, 'PUT'); setPassword(''); setConnection(await api<Connection>(path)); }
      catch { setError(true); } finally { setBusy(false); }
    }}><label>{fr ? 'Adresse de la boîte mail' : 'Mailbox email'}<input type="email" autoComplete="username" value={email} onChange={event => setEmail(event.target.value)} required maxLength={320} /></label><label>{fr ? 'Mot de passe de la boîte mail' : 'Mailbox password'}<input type="password" autoComplete="off" value={password} onChange={event => setPassword(event.target.value)} required maxLength={1024} /></label><p className="subtle">{fr ? 'Utilisez le mot de passe de cette boîte mail, qui peut être différent de celui du Manager Infomaniak. Il est chiffré et n’est jamais transmis au modèle.' : 'Use this mailbox’s password, which may differ from your Infomaniak Manager password. It is encrypted and never sent to the model.'}</p><label className="archive-filter"><input type="checkbox" checked={send} disabled={!connection?.allowed_capabilities.includes('mail_send')} onChange={event => setSend(event.target.checked)} />{fr ? 'Autoriser aussi l’envoi selon mes réglages d’autonomie' : 'Also allow sending according to my autonomy settings'}</label><button className="primary" disabled={busy || !connection?.available}>{busy ? fr ? 'Vérification…' : 'Checking…' : fr ? 'Connecter ma messagerie' : 'Connect my mailbox'}</button>{connection && !connection.available && <p>{fr ? 'AlpenData doit activer le stockage chiffré des connexions.' : 'AlpenData must enable encrypted connection storage.'}</p>}</form>}
    {!!connection?.capabilities.length && <button className="secondary" disabled={busy} onClick={async () => { setBusy(true); try { await api(path, undefined, 'DELETE'); setConnection({ ...connection!, status: 'disconnected', capabilities: [] }); } catch { setError(true); } finally { setBusy(false); } }}>{fr ? 'Déconnecter tous mes services Infomaniak' : 'Disconnect all my Infomaniak services'}</button>}
    <InfomaniakDav path={path} language={language} available={!!connection?.available} capabilities={connection?.capabilities || []} changed={async () => setConnection(await api<Connection>(path))} />
    {!!connection?.capabilities.length && <p className="subtle">{fr ? 'Services connectés : ' : 'Connected services: '}{connection.capabilities.filter(item => !item.includes('_')).map(item => ({ mail: 'Mail', calendar: fr ? 'Agenda' : 'Calendar', files: 'kDrive' }[item] || item)).join(', ')}</p>}
  </section>;
}
