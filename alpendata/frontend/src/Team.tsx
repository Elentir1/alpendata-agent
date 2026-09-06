import { useEffect, useState } from 'react';
import { ArrowRight, Copy, LockKeyhole, Mail, UserRound, X } from 'lucide-react';
import { api, ApiError } from './api';
import type { Company, Member, Person } from './api';
import { errorText } from './locale';
import type { Language, Text } from './locale';
import { Notice, useAction } from './feedback';
import { CompanyRules } from './CompanyRules';
import { CompanyResources } from './CompanyResources';
import { MemberAccess, seatWords } from './MemberAccess';
import type { Seats } from './MemberAccess';

type InvitationRow = { id: string; email: string; expires_at: number };
export function Team({ company, user, t, language, refreshAccount }: { company: Company; user: Person; t: Text; language: Language; refreshAccount: () => Promise<void> }) {
  const [members, setMembers] = useState<Member[]>([]), [invitations, setInvitations] = useState<InvitationRow[]>([]);
  const [email, setEmail] = useState(''), [link, setLink] = useState(''), [copied, setCopied] = useState(false), [loadError, setLoadError] = useState('');
  const [seats, setSeats] = useState<Seats | null>(null), [editing, setEditing] = useState<Member | null>(null);
  const words = seatWords[language];
  const action = useAction(t); const base = `/api/organizations/${company.id}`;
  async function refresh() {
    try {
      const [people, pending] = await Promise.all([api<{ members: Member[]; seats: Seats }>(base + '/members'), api<{ invitations: InvitationRow[] }>(base + '/invitations')]);
      setMembers(people.members); setSeats(people.seats); setInvitations(pending.invitations); setLoadError('');
    } catch (cause) {
      if (cause instanceof ApiError && [401, 403, 404].includes(cause.status)) { setMembers([]); setInvitations([]); setSeats(null); setEditing(null); setLink(''); }
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
        <Mail size={19} /><span className="member-info">{invitation.email}</span><button className="icon-button" aria-label={`${t.cancelInvitation} ${invitation.email}`} disabled={action.busy || !!editing} onClick={() => action.run(async () => {
          await api(base + '/invitations/' + invitation.id, undefined, 'DELETE'); setLink(''); await refresh();
        })}><X size={18} /></button>
      </li>)}</ul>}
      <p className="privacy-inline"><LockKeyhole size={18} />{t.noPrivateAccess}</p>
    </div><div className="invite-panel">
      <div className="icon-tile"><Mail /></div>
      {link ? <><h2>{t.inviteReady}</h2><p>{t.inviteManual}</p><label htmlFor="invitation-link">{t.inviteLink}</label><input id="invitation-link" readOnly value={link} onFocus={event => event.target.select()} />
        <button className="secondary" onClick={() => action.run(async () => { await navigator.clipboard.writeText(link); setCopied(true); })}><Copy size={17} />{copied ? t.copied : t.copy}</button>
        <button className="text-button" onClick={() => { setLink(''); setEmail(''); }}>{t.inviteNew}</button></> :
        <form onSubmit={event => { event.preventDefault(); void action.run(async () => {
          const result = await api<{ token: string }>(base + '/invitations', { email });
          setLink(location.origin + '/join#invitation=' + encodeURIComponent(result.token)); setCopied(false); await refresh();
        }); }}><label htmlFor="invite-email">{t.inviteEmail}</label><input id="invite-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required maxLength={320} autoComplete="email" /><button className="primary" disabled={action.busy || !!editing}>{action.busy ? t.inviting : t.invite}<ArrowRight size={17} /></button></form>}
    </div></div>
    {editing && <MemberAccess key={`${editing.user_id}:${editing.version}`} item={editing} self={editing.user_id === user.id} seats={seats} lastAdmin={editing.active && editing.role === 'admin' && members.filter(m => m.active && m.role === 'admin').length === 1} language={language} close={() => setEditing(null)} reload={async () => { await action.run(async () => { await refreshAccount(); await refresh(); setEditing(null); }); }} done={async () => { await refreshAccount(); await refresh(); setEditing(null); }} />}
    <CompanyRules organizationId={company.id} language={language} />
    <CompanyResources organizationId={company.id} userId={user.id} admin language={language} />
  </section>;
}
