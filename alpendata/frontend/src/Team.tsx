import { useEffect, useState } from 'react';
import { LockKeyhole, Mail, UserRound, X } from 'lucide-react';
import { api, ApiError } from './api';
import type { Company, Member, Person } from './api';
import { errorText } from './locale';
import type { Language, Text } from './locale';
import { Notice, useAction } from './feedback';
import { CompanyRules } from './CompanyRules';
import { CompanyResources } from './CompanyResources';
import { InvitationForm, invitationWords } from './InvitationForm';
import type { InvitationReceipt } from './InvitationForm';
import { MemberAccess, seatWords } from './MemberAccess';
import type { Seats } from './MemberAccess';

interface InvitationRow extends InvitationReceipt { expires_at: number }
export function Team({ company, user, t, language, refreshAccount }: { company: Company; user: Person; t: Text; language: Language; refreshAccount: () => Promise<void> }) {
  const [members, setMembers] = useState<Member[]>([]), [invitations, setInvitations] = useState<InvitationRow[]>([]);
  const [loadError, setLoadError] = useState('');
  const [revokedId, setRevokedId] = useState('');
  const [seats, setSeats] = useState<Seats | null>(null), [editing, setEditing] = useState<Member | null>(null);
  const words = seatWords[language];
  const action = useAction(t); const base = `/api/organizations/${company.id}`;
  async function refresh() {
    try {
      const [people, pending] = await Promise.all([api<{ members: Member[]; seats: Seats }>(base + '/members'), api<{ invitations: InvitationRow[] }>(base + '/invitations')]);
      setMembers(people.members); setSeats(people.seats); setInvitations(pending.invitations); setLoadError('');
    } catch (cause) {
      if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) { setMembers([]); setInvitations([]); setSeats(null); setEditing(null); }
      throw cause;
    }
  }
  useEffect(() => { void refresh().catch(error => setLoadError(errorText(error, t))); }, [company.id]);
  return <section className="team-page"><h1>{t.manageTitle}</h1><p className="lead">{t.manageText}</p><Notice>{loadError || action.error}</Notice>
    {seats && <section className="seat-summary" aria-label={words.title}><h2>{words.title}</h2><p>{seats.capacity} {words.capacity}</p><dl><div><dt>{words.assigned}</dt><dd>{seats.assigned}</dd></div><div><dt>{words.reserved}</dt><dd>{seats.reserved}</dd></div><div><dt>{words.available}</dt><dd>{seats.available}</dd></div></dl><p>{words.explanation}</p></section>}
    <button className="secondary" disabled={action.busy || !!editing} onClick={() => void action.run(async () => { await refreshAccount(); await refresh(); })}>{words.reload}</button>
    <div className="team-grid"><div>
      <h2>{t.members}</h2><ul className="member-list">{members.map(member => <li key={member.user_id}>
        <div className="avatar"><UserRound size={20} /></div><div className="member-info"><strong>{member.display_name}{member.user_id === user.id && ` · ${t.you}`}</strong><span>{member.role === 'admin' ? t.admin : t.member}</span></div>
        <span className={`status-badge ${member.active && member.licensed ? 'enabled' : ''}`}>{!member.active ? t.inactive : member.licensed ? t.licenseActive : t.licenseInactive}</span>
        <button className="secondary" disabled={action.busy || !!editing || !member.version} aria-label={`${words.manage} ${member.display_name}`} onClick={() => setEditing(member)}>{words.manage}</button>
      </li>)}</ul>
      {invitations.length > 0 && <ul className="member-list pending-list">{invitations.map(invitation => <li key={invitation.id}>
        <Mail size={19} /><span className="member-info">{invitation.email}<span>{invitationWords[language][invitation.delivery_status ?? 'manual']}</span></span><button className="icon-button" aria-label={`${t.cancelInvitation} ${invitation.email}`} disabled={action.busy || !!editing} onClick={() => action.run(async () => {
          await api(base + '/invitations/' + invitation.id, undefined, 'DELETE'); setRevokedId(invitation.id); await refresh();
        })}><X size={18} /></button>
      </li>)}</ul>}
      <p className="privacy-inline"><LockKeyhole size={18} />{t.noPrivateAccess}</p>
    </div><InvitationForm key={company.id} base={base} t={t} language={language} disabled={action.busy || !!editing} done={refresh} revokedId={revokedId} /></div>
    {editing && <MemberAccess key={`${editing.user_id}:${editing.version}`} item={editing} self={editing.user_id === user.id} seats={seats} lastAdmin={editing.active && editing.role === 'admin' && members.filter(m => m.active && m.role === 'admin').length === 1} language={language} close={() => setEditing(null)} reload={async () => { await action.run(async () => { await refreshAccount(); await refresh(); setEditing(null); }); }} done={async () => { await refreshAccount(); await refresh(); setEditing(null); }} />}
    <CompanyRules organizationId={company.id} language={language} />
    <CompanyResources organizationId={company.id} userId={user.id} admin language={language} />
  </section>;
}
