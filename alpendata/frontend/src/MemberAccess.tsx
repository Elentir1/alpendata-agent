import { useEffect, useId, useRef, useState } from 'react';
import { api, ApiError } from './api';
import type { Member } from './api';
import type { Language } from './locale';
import { Notice } from './feedback';

export interface Seats { capacity: number; assigned: number; reserved: number; available: number }
export const seatWords = {
  fr: {
    title: 'Licences de l’entreprise', assigned: 'attribuées', reserved: 'réservées par les invitations', available: 'disponibles', capacity: 'places au total',
    explanation: 'Une invitation en attente réserve une place jusqu’à son acceptation, son expiration ou son annulation. Attribuer ou retirer une licence ne modifie pas le nombre de places de votre offre.',
    manage: 'Gérer les accès', reload: 'Actualiser les membres', role: 'Rôle dans l’entreprise', admin: 'Administrateur', member: 'Collaborateur',
    active: 'Accès à l’entreprise', enabled: 'Actif', disabled: 'Désactivé', licensed: 'Licence de l’assistant', yes: 'Attribuée', no: 'Non attribuée',
    notice: 'Les connexions, conversations et la mémoire restent personnelles. Le rôle administrateur permet de gérer les membres et les copies publiées pour l’entreprise.',
    revoke: 'La désactivation bloque l’accès à cette entreprise. Les automatisations concernées seront bloquées, sans suppression ni transfert des données personnelles.',
    unlicense: 'Sans licence, ce collaborateur ne peut plus exécuter son assistant. Ses automatisations sont bloquées ; les historiques restent accessibles tant que son compte est actif.',
    resume: 'Rétablir un accès ou une licence ne relance pas les automatisations bloquées. Leur propriétaire devra les reprendre.',
    confirm: 'Je confirme ces changements d’accès.', save: 'Enregistrer les accès', cancel: 'Annuler', busy: 'Enregistrement…',
    changed: 'Les accès ont changé depuis votre lecture. Actualisez les membres avant de continuer.', uncertain: 'Le changement n’a pas pu être confirmé. Actualisez les membres pour vérifier son état.',
    last: 'L’entreprise doit garder au moins un administrateur actif.', full: 'Toutes les places sont attribuées ou réservées. Libérez une place avant d’attribuer cette licence.',
    failed: 'Les accès n’ont pas pu être modifiés. Actualisez les membres pour réessayer.', self: 'Vous modifiez vos propres accès. Ce changement peut fermer votre espace d’administration.',
  },
  en: {
    title: 'Company licences', assigned: 'assigned', reserved: 'reserved by invitations', available: 'available', capacity: 'total seats',
    explanation: 'A pending invitation reserves a seat until it is accepted, expires or is cancelled. Assigning or removing a licence does not change the number of seats in your plan.',
    manage: 'Manage access', reload: 'Refresh members', role: 'Company role', admin: 'Administrator', member: 'Member',
    active: 'Company access', enabled: 'Active', disabled: 'Deactivated', licensed: 'Assistant licence', yes: 'Assigned', no: 'Not assigned',
    notice: 'Connections, conversations and memory remain personal. Administrators can manage members and copies published for the company.',
    revoke: 'Deactivation blocks access to this company. Related automations will be blocked without deleting or transferring personal data.',
    unlicense: 'Without a licence, this colleague cannot run their assistant. Their automations are blocked; history remains accessible while their account is active.',
    resume: 'Restoring access or a licence does not restart blocked automations. Their owner will need to resume them.',
    confirm: 'I confirm these access changes.', save: 'Save access', cancel: 'Cancel', busy: 'Saving…',
    changed: 'Access has changed since you read it. Refresh members before continuing.', uncertain: 'The change could not be confirmed. Refresh members to check its state.',
    last: 'The company must keep at least one active administrator.', full: 'All seats are assigned or reserved. Free a seat before assigning this licence.',
    failed: 'Access could not be changed. Refresh members to try again.', self: 'You are changing your own access. This change may close your administration area.',
  },
};

export function MemberAccess({ item, self, seats, lastAdmin, language, done, reload, close }: {
  item: Member; self: boolean; seats: Seats | null; lastAdmin: boolean; language: Language;
  done: (member: Member) => Promise<void>; reload: () => Promise<void>; close: () => void;
}) {
  const t = seatWords[language], id = useId();
  const [role, setRole] = useState(item.role), [active, setActive] = useState(item.active), [licensed, setLicensed] = useState(item.licensed);
  const [confirmed, setConfirmed] = useState(false), [busy, setBusy] = useState(false), [recovery, setRecovery] = useState(false), [error, setError] = useState('');
  const pending = useRef(false);
  const alive = useRef(true), heading = useRef<HTMLHeadingElement | null>(null);
  useEffect(() => { alive.current = true; heading.current?.focus(); return () => { alive.current = false; }; }, []);
  const needsSeat = active && licensed && !(item.active && item.licensed);
  const full = needsSeat && (!seats || seats.available < 1);
  const losingLast = lastAdmin && (!active || role !== 'admin');
  const dirty = role !== item.role || active !== item.active || licensed !== item.licensed;
  function edit(change: () => void) { change(); setConfirmed(false); }
  async function save() {
    if (pending.current || !confirmed || !dirty || recovery || full || losingLast) return;
    pending.current = true; setBusy(true); setError('');
    try {
      const result = await api<Member>(`/api/organizations/${item.organization_id}/members/${item.user_id}`, { version: item.version, role, active, licensed }, 'PATCH');
      if (!alive.current) return;
      await done({ ...item, ...result });
    } catch (cause) {
      if (!alive.current) return;
      const code = cause instanceof ApiError ? cause.code : '';
      const known: Record<string, string> = { member_state_changed: t.changed, no_available_license: t.full, last_administrator: t.last };
      setError(known[code] || (cause instanceof ApiError && cause.status > 0 && cause.status < 500 ? t.failed : t.uncertain));
      setRecovery(true);
    } finally { pending.current = false; if (alive.current) setBusy(false); }
  }
  return <form className="member-access" aria-label={`${t.manage} ${item.display_name}`} onSubmit={event => { event.preventDefault(); void save(); }}>
    <h3 ref={heading} tabIndex={-1}>{t.manage} · {item.display_name}</h3><p>{t.notice}</p>{self && <p>{t.self}</p>}
    <fieldset disabled={busy || recovery}>
      <label htmlFor={id + 'role'}>{t.role}</label><select id={id + 'role'} value={role} onChange={event => edit(() => setRole(event.target.value as Member['role']))}><option value="member">{t.member}</option><option value="admin">{t.admin}</option></select>
      <label htmlFor={id + 'active'}>{t.active}</label><select id={id + 'active'} value={String(active)} onChange={event => edit(() => setActive(event.target.value === 'true'))}><option value="true">{t.enabled}</option><option value="false">{t.disabled}</option></select>
      <label htmlFor={id + 'licensed'}>{t.licensed}</label><select id={id + 'licensed'} value={String(licensed)} onChange={event => edit(() => setLicensed(event.target.value === 'true'))}><option value="true">{t.yes}</option><option value="false">{t.no}</option></select>
      {!active && <p>{t.revoke}</p>}{active && !licensed && <p>{t.unlicense}</p>}{active && licensed && !(item.active && item.licensed) && <p>{t.resume}</p>}
      {full && <Notice>{t.full}</Notice>}{losingLast && <Notice>{t.last}</Notice>}
      <label className="member-confirm"><input type="checkbox" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} required />{t.confirm}</label>
    </fieldset>
    <Notice>{error}</Notice><div className="member-actions"><button className="primary" disabled={busy || recovery || !confirmed || !dirty || full || losingLast}>{busy ? t.busy : t.save}</button>
      {recovery ? <button className="secondary" type="button" disabled={busy} onClick={() => void reload()}>{t.reload}</button> : <button className="secondary" type="button" disabled={busy} onClick={close}>{t.cancel}</button>}
    </div>
  </form>;
}
