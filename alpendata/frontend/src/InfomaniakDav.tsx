import { useState } from 'react';
import { api } from './api';
import { Notice } from './feedback';
import type { Language } from './locale';

export function InfomaniakDav({ path, language, available, capabilities, changed }: { path: string; language: Language; available: boolean; capabilities: string[]; changed: () => Promise<void> }) {
  const fr = language === 'fr';
  const [service, setService] = useState('calendar'), [username, setUsername] = useState(''), [password, setPassword] = useState('');
  const [calendarUrl, setCalendarUrl] = useState('https://sync.infomaniak.com/'), [driveId, setDriveId] = useState('');
  const [allowWrite, setAllowWrite] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(false);
  return <details className="dav-connection"><summary>{fr ? 'Connecter mon agenda ou kDrive' : 'Connect my calendar or kDrive'}</summary>
    <p>{fr ? 'Chaque service utilise vos accès personnels. Les services déjà connectés restent disponibles.' : 'Each service uses your personal credentials. Previously connected services remain available.'}</p>
    <Notice>{error && (fr ? 'Le service n’a pas pu être vérifié. Contrôlez le compte, le mot de passe d’application et l’accès au service.' : 'The service could not be verified. Check your account, app password and service access.')}</Notice>
    <form onSubmit={async event => { event.preventDefault(); setBusy(true); setError(false); try {
      await api(path + '/dav', { service, username, password, calendar_url: calendarUrl, drive_id: driveId, allow_write: allowWrite }, 'PUT');
      setPassword(''); await changed();
    } catch { setError(true); } finally { setBusy(false); } }}>
      <label>{fr ? 'Service' : 'Service'}<select value={service} onChange={event => setService(event.target.value)}><option value="calendar">{fr ? 'Agenda Infomaniak' : 'Infomaniak Calendar'}</option><option value="files">kDrive</option></select></label>
      {capabilities.includes(service) && <Notice success>{fr ? 'Ce service est connecté. Ce formulaire permet de remplacer ses accès.' : 'This service is connected. This form replaces its credentials.'}</Notice>}
      <p>{service === 'calendar' ? fr ? 'Retrouvez les identifiants de synchronisation de votre agenda dans l’assistant Infomaniak.' : 'Find your calendar synchronization credentials in the Infomaniak setup assistant.' : fr ? 'kDrive doit inclure l’accès WebDAV. Le numéro du kDrive apparaît dans son adresse, après /drive/.' : 'Your kDrive plan must include WebDAV. Its number appears in its URL after /drive/.'} <a href={service === 'calendar' ? 'https://config.infomaniak.com/' : 'https://www.infomaniak.com/en/support/faq/2409/connect-to-kdrive-via-webdav'} target="_blank" rel="noreferrer">{fr ? 'Ouvrir l’aide Infomaniak' : 'Open Infomaniak help'}</a></p>
      <label>{fr ? 'Identifiant de connexion' : 'Sign-in username'}<input required autoComplete="username" value={username} onChange={event => setUsername(event.target.value)} maxLength={256} /></label>
      <label>{fr ? 'Mot de passe d’application' : 'App password'}<input required type="password" autoComplete="off" value={password} onChange={event => setPassword(event.target.value)} maxLength={1024} /></label>
      {service === 'calendar' ? <label>{fr ? 'Adresse de synchronisation indiquée par Infomaniak' : 'Synchronization URL supplied by Infomaniak'}<input required type="url" value={calendarUrl} onChange={event => setCalendarUrl(event.target.value)} maxLength={2048} /></label> : <label>{fr ? 'Numéro du kDrive' : 'kDrive number'}<input required inputMode="numeric" pattern="[1-9][0-9]*" value={driveId} onChange={event => setDriveId(event.target.value)} maxLength={16} /></label>}
      <label className="archive-filter"><input type="checkbox" checked={allowWrite} onChange={event => setAllowWrite(event.target.checked)} />{fr ? 'Autoriser les modifications selon mes réglages et les règles de l’entreprise' : 'Allow changes according to my settings and company rules'}</label>
      <button className="primary" disabled={!available || busy}>{busy ? fr ? 'Vérification…' : 'Checking…' : fr ? 'Vérifier et connecter' : 'Check and connect'}</button>
    </form>
  </details>;
}
