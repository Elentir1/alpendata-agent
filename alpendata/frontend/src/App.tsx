import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowRight, CalendarClock, Check, CheckCircle2, ChevronRight, Copy, Globe2, LockKeyhole, LogOut, Mail, MessageSquare, ShieldCheck, UserRound, UsersRound, X } from 'lucide-react';
import { api, ApiError, readInvitation, rememberInvitation } from './api';
import type { Company, Membership, Onboarding, Options, PendingInvitation, Person } from './api';
import { copy, errorText } from './locale';
import type { Language, Text } from './locale';
import { Notice, useAction } from './feedback';
import { Tools } from './Tools';
import { Chat } from './Chat';
import { FirstTasks } from './FirstTasks';
import { Schedules } from './Schedules';
import { CompanyRules } from './CompanyRules';
import { PersonalAutonomy } from './PersonalAutonomy';
import { PersonalMemory } from './PersonalMemory';

function Brand() {
  return <a className="brand" href="/" aria-label="AlpenData"><img src="/brand/logo.webp" alt="" /><span>Alpen<span>Data</span></span></a>;
}

function SignIn({ t, options }: { t: Text; options: Options }) {
  const action = useAction(t);
  return <section className="welcome-grid">
    <div className="welcome-panel">
      <div className="eyebrow">ALPENDATA · {t.workspace.toUpperCase()}</div>
      <h1>{t.welcome}</h1><p className="lead">{t.welcomeText}</p>
      <button className="primary wide" disabled={!options.microsoft || action.busy} onClick={() => action.run(async () => {
        const result = await api<{ authorization_url: string }>('/api/auth/microsoft/start', {});
        const url = new URL(result.authorization_url);
        if (url.origin !== 'https://login.microsoftonline.com') throw new Error('Unexpected identity provider');
        location.assign(url.href);
      })}><span className="microsoft-mark" aria-hidden="true"><i /><i /><i /><i /></span>{action.busy ? t.signingIn : t.signIn}<ArrowRight size={19} /></button>
      {!options.microsoft && <p className="configuration-note">{t.unavailable} <a href="https://www.alpendata.ch/contact">{t.support}</a></p>}
      <Notice>{action.error}</Notice>
      <div className="language-note"><Globe2 size={16} />{t.languageNote}</div>
    </div>
    <aside className="principles">
      <div className="principle"><div className="icon-tile"><LockKeyhole /></div><h2>{t.personal}</h2><p>{t.personalText}</p></div>
      <div className="principle"><div className="icon-tile"><UsersRound /></div><h2>{t.simple}</h2><p>{t.simpleText}</p></div>
      <div className="brand-rule" aria-hidden="true"><span /><span /><span /></div>
    </aside>
  </section>;
}

function CreateCompany({ t, done }: { t: Text; done: (id: string) => Promise<void> }) {
  const [name, setName] = useState(''); const action = useAction(t);
  return <section className="form-page"><div className="icon-tile"><UsersRound /></div><h1>{t.createTitle}</h1><p className="lead">{t.createText}</p>
    <form onSubmit={(event) => { event.preventDefault(); void action.run(async () => {
      const company = await api<Company>('/api/organizations', { name }); await done(company.id);
    }); }}>
      <label htmlFor="company-name">{t.companyName}</label><input id="company-name" value={name} onChange={e => setName(e.target.value)} required maxLength={160} autoComplete="organization" placeholder={t.companyExample} />
      <Notice>{action.error}</Notice><button className="primary" disabled={action.busy}>{action.busy ? t.creating : t.create}<ArrowRight size={18} /></button>
    </form><p className="subtle">{t.invitedNote}</p>
  </section>;
}

function Join({ invitation, t, language, options, user, done }: { invitation: PendingInvitation; t: Text; language: Language; options: Options; user: Person; done: (id: string) => Promise<void> }) {
  const action = useAction(t); const [recipient, setRecipient] = useState('');
  return <section className="form-page"><div className="icon-tile"><Mail /></div><h1>{t.joinTitle}</h1>
    <p>{t.currentAccount} : <strong>{user.display_name}</strong></p>
    <p className="lead">{invitation.verification_token ? t.confirmJoin : t.joinText}</p>
    <Notice success>{recipient && <>{t.sent} <strong>{recipient}</strong>. {t.sentText}</>}</Notice>
    <Notice>{action.error}</Notice>
    {invitation.verification_token && <button className="primary" disabled={action.busy} onClick={() => action.run(async () => {
      const result = await api<{ organization_id: string }>('/api/invitations/accept', invitation);
      rememberInvitation(null); history.replaceState(null, '', '/'); await done(result.organization_id);
    })}>{action.busy ? t.accepting : t.accept}<ArrowRight size={18} /></button>}
    {(!invitation.verification_token || action.error) && <button className={invitation.verification_token ? 'secondary' : 'primary'} disabled={action.busy || !options.invitation_email} onClick={() => action.run(async () => {
      const result = await api<{ recipient_hint: string }>('/api/invitations/verify', { token: invitation.token, language });
      setRecipient(result.recipient_hint);
    })}>{action.busy ? t.verifying : t.verify}<Mail size={18} /></button>}
    {!options.invitation_email && <p className="configuration-note">{t.noMail}</p>}
  </section>;
}

function Steps({ t, current }: { t: Text; current: number }) {
  return <ol className="steps">{[t.stepOne, t.stepTwo, t.stepThree].map((name, index) => <li key={name} aria-current={index === current ? 'step' : undefined} className={index < current ? 'completed' : ''}>
    <span>{index < current ? <Check size={15} /> : index + 1}</span>{name}{index < 2 && <ChevronRight className="step-chevron" size={16} />}
  </li>)}</ol>;
}

function PersonalWorkspace({ company, membership, language, t, onOpen }: { company: Company; membership: Membership; language: Language; t: Text; onOpen: (id: string) => void }) {
  const [profile, setProfile] = useState<Onboarding | null>(null), [loadError, setLoadError] = useState('');
  const [role, setRole] = useState(''), [activity, setActivity] = useState(''), [needs, setNeeds] = useState('');
  const [editing, setEditing] = useState(false); const action = useAction(t);
  useEffect(() => {
    let active = true;
    api<Onboarding>(`/api/organizations/${company.id}/onboarding`).then(data => {
      if (!active) return; setProfile(data); setRole(data.answers.role || ''); setActivity(data.answers.activity || ''); setNeeds(data.answers.needs || '');
    }).catch(error => { if (active) setLoadError(errorText(error, t)); });
    return () => { active = false; };
  }, [company.id]);
  if (!membership.licensed) return <Notice>{t.license}</Notice>;
  if (loadError) return <Notice>{loadError}</Notice>;
  if (!profile) return <p role="status">{t.loading}</p>;
  const saved = profile.step !== 'introduction' && !editing;
  async function save(event: FormEvent) {
    event.preventDefault(); await action.run(async () => {
      const next = await api<Onboarding>(`/api/organizations/${company.id}/onboarding`, { language, role, activity, needs }, 'PUT');
      setProfile(next); setEditing(false);
    });
  }
  return <><Steps t={t} current={saved ? profile.step === 'first_result' ? 2 : 1 : 0} /><section className="onboarding-grid">
    <div className="profile-main">
      <div className="eyebrow">{company.name}</div>
      <h1>{saved ? t.nextTitle : t.profileTitle}</h1><p className="lead">{saved ? t.nextText : t.profileText}</p>
      {saved ? <><Notice success><CheckCircle2 size={18} />{t.saved}</Notice><button className="secondary" onClick={() => setEditing(true)}>{t.edit}</button><Tools companyId={company.id} language={language} /><PersonalAutonomy organizationId={company.id} language={language} licensed={membership.licensed} /><PersonalMemory organizationId={company.id} language={language} /><FirstTasks organizationId={company.id} language={language} onOpen={onOpen} /></> :
        <form onSubmit={save}>
          <label htmlFor="role">{t.role}</label><input id="role" value={role} onChange={e => setRole(e.target.value)} required maxLength={160} placeholder={t.roleExample} autoComplete="organization-title" />
          <label htmlFor="activity">{t.activity}</label><textarea id="activity" value={activity} onChange={e => setActivity(e.target.value)} maxLength={500} rows={2} placeholder={t.activityExample} />
          <label htmlFor="needs">{t.needs}</label><textarea id="needs" value={needs} onChange={e => setNeeds(e.target.value)} required maxLength={4000} rows={3} placeholder={t.needsExample} />
          <Notice>{action.error}</Notice><button className="primary" disabled={action.busy}>{action.busy ? t.saving : t.continue}<ArrowRight size={18} /></button>
        </form>}
    </div>
    <aside className="privacy-note"><ShieldCheck size={27} /><h2>{t.personal}</h2><p>{t.privateNote}</p><p>{t.personalText}</p></aside>
  </section></>;
}

type Member = Membership & { display_name: string };
type InvitationRow = { id: string; email: string; expires_at: number };
function Team({ company, user, t, language }: { company: Company; user: Person; t: Text; language: Language }) {
  const [members, setMembers] = useState<Member[]>([]), [invitations, setInvitations] = useState<InvitationRow[]>([]);
  const [email, setEmail] = useState(''), [link, setLink] = useState(''), [copied, setCopied] = useState(false), [loadError, setLoadError] = useState('');
  const action = useAction(t); const base = `/api/organizations/${company.id}`;
  async function refresh() {
    const [people, pending] = await Promise.all([api<{ members: Member[] }>(base + '/members'), api<{ invitations: InvitationRow[] }>(base + '/invitations')]);
    setMembers(people.members); setInvitations(pending.invitations);
  }
  useEffect(() => { void refresh().catch(error => setLoadError(errorText(error, t))); }, [company.id]);
  return <section className="team-page"><h1>{t.manageTitle}</h1><p className="lead">{t.manageText}</p><Notice>{loadError || action.error}</Notice>
    <div className="team-grid"><div>
      <h2>{t.members}</h2><ul className="member-list">{members.map(member => <li key={member.user_id}>
        <div className="avatar"><UserRound size={20} /></div><div className="member-info"><strong>{member.display_name}{member.user_id === user.id && ` · ${t.you}`}</strong><span>{member.role === 'admin' ? t.admin : t.member}</span></div>
        <span className={`status-badge ${member.active && member.licensed ? 'enabled' : ''}`}>{!member.active ? t.inactive : member.licensed ? t.licenseActive : t.licenseInactive}</span>
      </li>)}</ul>
      {invitations.length > 0 && <ul className="member-list pending-list">{invitations.map(invitation => <li key={invitation.id}>
        <Mail size={19} /><span className="member-info">{invitation.email}</span><button className="icon-button" aria-label={`${t.cancelInvitation} ${invitation.email}`} disabled={action.busy} onClick={() => action.run(async () => {
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
        }); }}><label htmlFor="invite-email">{t.inviteEmail}</label><input id="invite-email" type="email" value={email} onChange={e => setEmail(e.target.value)} required maxLength={320} autoComplete="email" /><button className="primary" disabled={action.busy}>{action.busy ? t.inviting : t.invite}<ArrowRight size={17} /></button></form>}
    </div></div>
    <CompanyRules organizationId={company.id} language={language} />
  </section>;
}

export default function App() {
  const [connectionInterrupted] = useState(() => {
    const query = new URLSearchParams(location.search);
    const interrupted = query.get('connection_error') === 'interrupted';
    if (query.has('connection_error')) { query.delete('connection_error'); history.replaceState(null, '', location.pathname + (query.size ? '?' + query : '') + location.hash); }
    return interrupted;
  });
  const [signinInterrupted] = useState(() => {
    const query = new URLSearchParams(location.search);
    const interrupted = query.get('signin_error') === 'interrupted';
    if (query.has('signin_error')) { query.delete('signin_error'); history.replaceState(null, '', location.pathname + (query.size ? '?' + query : '') + location.hash); }
    return interrupted;
  });
  const [language, setLanguage] = useState<Language>(() => localStorage.getItem('alpendata.language') === 'en' ? 'en' : 'fr');
  const t = copy[language]; const [pendingInvitation, setPendingInvitation] = useState(readInvitation);
  const [user, setUser] = useState<Person | null>(null), [options, setOptions] = useState<Options | null>(null);
  const [companies, setCompanies] = useState<Company[]>([]), [companyId, setCompanyId] = useState('');
  const [chatId, setChatId] = useState('');
  const [section, setSection] = useState<'personal' | 'team' | 'chat' | 'schedules'>('personal'), [loading, setLoading] = useState(true), [error, setError] = useState('');
  const generation = useRef(0); const signOutAction = useAction(t);
  async function refresh(preferred?: string) {
    const request = ++generation.current; setError('');
    try {
      const [configuration, person] = await Promise.all([api<Options>('/api/auth/options'), api<Person>('/api/me').catch(cause => {
        if (cause instanceof ApiError && cause.status === 401) return null; throw cause;
      })]);
      const organizations = person ? await Promise.all(person.memberships.map(m => api<Company>(`/api/organizations/${m.organization_id}`))) : [];
      if (request !== generation.current) return;
      setOptions(configuration); setUser(person); setCompanies(organizations);
      const returnCompany = sessionStorage.getItem('alpendata.return-company'); sessionStorage.removeItem('alpendata.return-company');
      setCompanyId(organizations.find(item => item.id === (preferred || returnCompany))?.id || organizations[0]?.id || '');
      setPendingInvitation(readInvitation());
    } catch (cause) { if (request === generation.current) setError(errorText(cause, t)); }
    finally { if (request === generation.current) setLoading(false); }
  }
  useEffect(() => { void refresh(); return () => { generation.current++; }; }, []);
  useEffect(() => { document.documentElement.lang = language === 'fr' ? 'fr-CH' : 'en'; localStorage.setItem('alpendata.language', language); document.title = `AlpenData · ${t.workspace}`; }, [language, t.workspace]);
  const company = companies.find(item => item.id === companyId);
  const membership = user?.memberships.find(item => item.organization_id === companyId);
  return <div className={`app ${user && company && !pendingInvitation ? 'with-sidebar' : ''}`}>
    <header className="topbar"><Brand /><div className="top-actions">
      <label className="language-select"><Globe2 size={17} /><span className="sr-only">{t.language}</span><select aria-label={t.language} value={language} onChange={e => setLanguage(e.target.value as Language)}><option value="fr">FR</option><option value="en">EN</option></select></label>
      {user && <button className="icon-button sign-out" aria-label={pendingInvitation ? t.anotherAccount : t.signOut} title={t.signOut} disabled={signOutAction.busy} onClick={() => signOutAction.run(async () => {
        await api('/api/logout', {}).catch(cause => { if (!(cause instanceof ApiError && cause.status === 401)) throw cause; }); setChatId(''); setSection('personal'); await refresh();
      })}><LogOut size={19} /><span>{pendingInvitation ? t.anotherAccount : t.signOut}</span></button>}
    </div></header>
    {user && company && membership && !pendingInvitation && <aside className="sidebar">
      <label className="company-selector"><span>{t.company}</span><select aria-label={t.company} value={companyId} onChange={e => { setCompanyId(e.target.value); setChatId(''); setSection('personal'); }}>{companies.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
      <nav aria-label={t.workspace}><button className={section === 'personal' ? 'selected' : ''} onClick={() => setSection('personal')}><UserRound size={19} />{t.workspace}</button><button className={section === 'chat' ? 'selected' : ''} onClick={() => setSection('chat')}><MessageSquare size={19} />Assistant</button><button className={section === 'schedules' ? 'selected' : ''} onClick={() => setSection('schedules')}><CalendarClock size={19} />{language === 'fr' ? 'Automatisations' : 'Automations'}</button>{membership.role === 'admin' && <button className={section === 'team' ? 'selected' : ''} onClick={() => setSection('team')}><UsersRound size={19} />{t.company}</button>}</nav>
      <div className="sidebar-person"><div className="avatar"><UserRound size={19} /></div><div><strong>{user.display_name}</strong><span>{t.personal}</span></div></div>
    </aside>}
    <main id="main"><Notice>{signOutAction.error}</Notice>
      {signinInterrupted && <Notice>{t.signInFailed}</Notice>}
      {connectionInterrupted && <Notice>{t.connectionFailed}</Notice>}
      {loading ? <p className="loading" role="status">{t.loading}</p> : error ? <section className="form-page"><Notice>{error}</Notice><button className="primary" onClick={() => refresh()}>{t.retry}</button></section> : !user && options ? <SignIn t={t} options={options} /> : user && options ?
        pendingInvitation ? <Join invitation={pendingInvitation} t={t} language={language} options={options} user={user} done={refresh} /> : location.pathname === '/join' ? <section className="form-page"><Notice>{t.expired}</Notice></section> : !company || !membership ? <CreateCompany t={t} done={refresh} /> :
          section === 'schedules' ? <Schedules key={`${company.id}:${user.id}`} organizationId={company.id} licensed={membership.licensed} language={language} t={t} onOpen={id => { setChatId(id); setSection('chat'); }} /> : section === 'chat' ? <Chat onManage={() => setSection('schedules')} key={`${company.id}:${user.id}`} initialConversationId={chatId} organizationId={company.id} licensed={membership.licensed} language={language} t={t} /> : section === 'team' && membership.role === 'admin' ? <Team key={company.id} company={company} user={user} t={t} language={language} /> : <PersonalWorkspace key={company.id} onOpen={id => { setChatId(id); setSection('chat'); }} company={company} membership={membership} language={language} t={t} />
        : null}
    </main>
    <footer><span>AlpenData</span><a href="https://www.alpendata.ch/contact">{t.support}</a></footer>
  </div>;
}
