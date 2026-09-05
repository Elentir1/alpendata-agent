import { ApiError } from './api';

export const copy = {
  fr: {
    connectionFailed: 'La connexion à vos outils n’a pas abouti. Réessayez avec le même compte Microsoft que pour AlpenData.',
    reconnect: 'Reconnectez votre compte Microsoft pour retrouver cet accès.', permission: 'Cet accès n’est pas autorisé. Vérifiez vos choix et les droits de votre compte Microsoft.', microsoftRate: 'Microsoft demande de patienter avant de réessayer.',
    language: 'Langue', loading: 'Ouverture de votre espace…', retry: 'Réessayer', support: 'Contacter AlpenData',
    welcome: 'Un assistant qui connaît votre travail.', welcomeText: 'Commencez avec votre compte professionnel. Votre espace et vos connexions vous appartiennent.',
    signIn: 'Continuer avec Microsoft', signingIn: 'Connexion en cours…', signInFailed: 'La connexion n’a pas abouti. Réessayez avec votre compte professionnel.', unavailable: 'La connexion n’est pas encore disponible dans cet environnement.',
    personal: 'Votre espace personnel', personalText: 'Vos conversations et votre mémoire restent privées, y compris vis-à-vis de l’administrateur.',
    simple: 'Vos outils habituels', simpleText: 'Vous choisirez ensuite les applications et les accès utiles à votre travail.',
    languageNote: 'Disponible en français et en anglais', signOut: 'Se déconnecter', workspace: 'Mon espace', company: 'Mon entreprise',
    createTitle: 'Commençons par votre entreprise.', createText: 'Vous pourrez ensuite inviter vos collaborateurs. Chacun créera son propre espace.',
    companyName: 'Nom de l’entreprise', companyExample: 'Ex. Horizon Coaching', create: 'Créer mon entreprise', creating: 'Création…',
    invitedNote: 'Vous avez reçu une invitation ? Ouvrez son lien pour rejoindre votre entreprise.',
    hello: 'Bienvenue', profileTitle: 'Faisons connaissance.', profileText: 'Quelques repères pour préparer un assistant adapté à votre quotidien.',
    stepOne: 'Votre activité', stepTwo: 'Vos outils', stepThree: 'Votre premier résultat',
    role: 'Quel est votre rôle ?', roleExample: 'Ex. Coach et consultant', activity: 'Que faites-vous au quotidien ?',
    activityExample: 'Ex. Accompagner des dirigeants et préparer des ateliers', needs: 'Qu’aimeriez-vous simplifier en premier ?',
    needsExample: 'Ex. Retrouver les échanges et documents avant chaque séance client', continue: 'Enregistrer et continuer', saving: 'Enregistrement…',
    saved: 'Vos réponses sont enregistrées.', nextTitle: 'La prochaine étape : vos outils.',
    nextText: 'Choisissez les outils utiles à votre travail. Vous pourrez vérifier vos accès dès la connexion.',
    edit: 'Modifier mes réponses', privateNote: 'Ces réponses sont personnelles. Elles ne sont pas copiées à vos collaborateurs.',
    license: 'Votre accès à l’assistant est suspendu. Contactez l’administrateur de votre entreprise.',
    joinTitle: 'Rejoignez votre entreprise.', joinText: 'Confirmez que vous avez accès à la boîte mail destinataire de l’invitation.',
    verify: 'Recevoir le lien de vérification', verifying: 'Envoi…', sent: 'Un lien de vérification a été envoyé à',
    sentText: 'Ouvrez-le avec ce compte pour continuer. Il reste valable 15 minutes.', accept: 'Rejoindre l’entreprise', accepting: 'Vérification…',
    confirmJoin: 'Votre lien de vérification est prêt. Confirmez pour créer votre espace personnel dans l’entreprise.',
    noMail: 'L’envoi des invitations n’est pas encore disponible. Contactez AlpenData.',
    currentAccount: 'Compte connecté', anotherAccount: 'Changer de compte', manageTitle: 'Votre équipe, simplement.', manageText: 'Invitez vos collaborateurs. Leurs connexions et leurs contenus resteront personnels.',
    inviteEmail: 'Adresse professionnelle du collaborateur', invite: 'Créer une invitation', inviting: 'Création…',
    inviteReady: 'Votre invitation est prête.', inviteLink: 'Lien à partager avec votre collaborateur', copy: 'Copier le lien', copied: 'Lien copié',
    inviteManual: 'Partagez ce lien avec le destinataire. Il devra confirmer son accès à cette adresse avant de rejoindre votre entreprise.',
    members: 'Membres', cancelInvitation: 'Annuler l’invitation de', admin: 'Administrateur', member: 'Collaborateur', active: 'Actif', inactive: 'Désactivé',
    you: 'Vous', licenseActive: 'Licence active', licenseInactive: 'Sans licence', inviteNew: 'Inviter une autre personne',
    noPrivateAccess: 'La gestion de l’équipe ne donne pas accès aux conversations, mémoires ou applications des collaborateurs.',
    error: 'L’action n’a pas pu aboutir. Réessayez dans un instant.', network: 'Votre espace est momentanément inaccessible. Vérifiez votre connexion et réessayez.',
    expired: 'Ce lien a expiré ou a déjà été utilisé. Demandez une nouvelle invitation.', proofRequired: 'Vérifiez votre invitation avec le compte qui a demandé le lien. Vous pouvez aussi recevoir un nouveau lien.',
    full: 'Toutes les places sont utilisées ou réservées par des invitations.', duplicate: 'Cette personne est déjà membre ou possède une invitation en attente.',
    rate: 'Patientez avant de demander un nouveau lien.', fields: 'Vérifiez les informations saisies.', sessionExpired: 'Votre session a expiré. Reconnectez-vous.',
  },
  en: {
    connectionFailed: 'Your tools could not be connected. Try again with the same Microsoft account you use for AlpenData.',
    reconnect: 'Reconnect your Microsoft account to restore access.', permission: 'This access is not allowed. Check your choices and your Microsoft account permissions.', microsoftRate: 'Microsoft asks you to wait before trying again.',
    language: 'Language', loading: 'Opening your workspace…', retry: 'Try again', support: 'Contact AlpenData',
    welcome: 'An assistant that understands your work.', welcomeText: 'Start with your work account. Your workspace and connections belong to you.',
    signIn: 'Continue with Microsoft', signingIn: 'Signing in…', signInFailed: 'Sign-in did not complete. Please try again with your work account.', unavailable: 'Sign-in is not available in this environment yet.',
    personal: 'Your personal workspace', personalText: 'Your conversations and memory remain private, including from your administrator.',
    simple: 'Your familiar tools', simpleText: 'Next, you will choose the applications and access needed for your work.',
    languageNote: 'Available in French and English', signOut: 'Sign out', workspace: 'My workspace', company: 'My company',
    createTitle: 'Let’s start with your company.', createText: 'You can then invite your colleagues. Each person will set up their own workspace.',
    companyName: 'Company name', companyExample: 'E.g. Horizon Coaching', create: 'Create my company', creating: 'Creating…',
    invitedNote: 'Received an invitation? Open its link to join your company.',
    hello: 'Welcome', profileTitle: 'Let’s get to know your work.', profileText: 'A few details to prepare an assistant that fits your day.',
    stepOne: 'Your work', stepTwo: 'Your tools', stepThree: 'Your first result',
    role: 'What is your role?', roleExample: 'E.g. Coach and consultant', activity: 'What do you do day to day?',
    activityExample: 'E.g. Support business leaders and prepare workshops', needs: 'What would you like to simplify first?',
    needsExample: 'E.g. Find the conversations and documents I need before each client session', continue: 'Save and continue', saving: 'Saving…',
    saved: 'Your answers have been saved.', nextTitle: 'Next: your tools.',
    nextText: 'Choose the tools you need for your work. You can check your access as soon as you connect.',
    edit: 'Edit my answers', privateNote: 'These answers are personal. They are not copied to your colleagues.',
    license: 'Your assistant access is suspended. Contact your company administrator.',
    joinTitle: 'Join your company.', joinText: 'Confirm that you have access to the email address receiving this invitation.',
    verify: 'Send me a verification link', verifying: 'Sending…', sent: 'A verification link has been sent to',
    sentText: 'Open it with this account to continue. It is valid for 15 minutes.', accept: 'Join the company', accepting: 'Verifying…',
    confirmJoin: 'Your verification link is ready. Confirm to create your personal workspace within the company.',
    noMail: 'Invitation emails are not available yet. Contact AlpenData.',
    currentAccount: 'Signed in as', anotherAccount: 'Switch account', manageTitle: 'Your team, made simple.', manageText: 'Invite your colleagues. Their connections and content stay personal.',
    inviteEmail: 'Colleague’s work email', invite: 'Create invitation', inviting: 'Creating…',
    inviteReady: 'Your invitation is ready.', inviteLink: 'Link to share with your colleague', copy: 'Copy link', copied: 'Link copied',
    inviteManual: 'Share this link with the recipient. They will confirm access to this email address before joining your company.',
    members: 'Members', cancelInvitation: 'Cancel invitation for', admin: 'Administrator', member: 'Team member', active: 'Active', inactive: 'Deactivated',
    you: 'You', licenseActive: 'Active licence', licenseInactive: 'No licence', inviteNew: 'Invite someone else',
    noPrivateAccess: 'Managing the team does not grant access to colleagues’ conversations, memories or applications.',
    error: 'This action could not be completed. Please try again shortly.', network: 'Your workspace is temporarily unavailable. Check your connection and try again.',
    expired: 'This link has expired or has already been used. Ask for a new invitation.', proofRequired: 'Verify your invitation with the account that requested the link. You can also request a new link.',
    full: 'All places are in use or reserved by pending invitations.', duplicate: 'This person is already a member or has a pending invitation.',
    rate: 'Please wait before requesting another link.', fields: 'Check the information you entered.', sessionExpired: 'Your session has expired. Please sign in again.',
  },
};
export type Language = keyof typeof copy;
export type Text = typeof copy.fr;

export function errorText(error: unknown, t: Text): string {
  if (!(error instanceof ApiError)) return t.error;
  if (error.status === 0) return t.network;
  if (error.status === 401) return t.sessionExpired;
  if (error.status === 422) return t.fields;
  if (error.status === 429) return `${error.code === 'microsoft_rate_limited' ? t.microsoftRate : t.rate}${error.retryAfter ? ` (${error.retryAfter} s)` : ''}`;
  const messages: Record<string, string> = {
    invitation_not_found: t.expired, invitation_email_verification_required: t.proofRequired,
    no_available_license: t.full, already_member_or_invited: t.duplicate,
    microsoft_signin_not_configured: t.unavailable, transactional_mail_not_configured: t.noMail,
    license_required: t.license, microsoft_reconnect_required: t.reconnect,
    microsoft_permission_required: t.permission, microsoft_access_denied: t.permission,
  };
  return messages[error.code] || t.error;
}
