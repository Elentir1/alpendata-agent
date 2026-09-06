import type { Membership } from './api';

export interface CompanyResource {
  id: string; title: string; kind: 'note' | 'document'; text?: string;
  filename: string | null; media_type: string | null; size: number; version: number;
  audience?: 'team' | 'selected'; member_ids?: string[];
}
export interface ResourceMember extends Membership { display_name: string }
export interface ResourcePublication {
  title: string; kind: 'note' | 'document'; text: string;
  audience: 'team' | 'selected'; member_ids: string[]; confirmed: true;
  document?: { filename: string; content_base64: string };
  request_id?: string; version?: number;
}
export const resourceWords = {
  fr: {
    title: 'Ressources de l’entreprise', intro: 'Les notes et documents publiés ici sont des copies partagées avec vous. Vos connexions et votre mémoire restent personnelles.',
    admin: 'Les administrateurs peuvent consulter et gérer toutes ces copies. Choisissez précisément les collaborateurs qui pourront aussi les lire avec leur assistant.',
    effect: 'Disponibles pour l’assistant dans les nouvelles conversations. Retirer un accès bloque les prochaines lectures, sans effacer les copies déjà consultées ou téléchargées.',
    empty: 'Aucune ressource partagée avec vous.', reload: 'Actualiser', more: 'Voir la suite', add: 'Publier une ressource', open: 'Consulter', download: 'Télécharger', edit: 'Modifier le contenu', access: 'Gérer les accès',
    close: 'Fermer', save: 'Enregistrer', publish: 'Publier la copie', retry: 'Réessayer la même publication', loading: 'Chargement…', busy: 'En cours…',
    name: 'Titre', kind: 'Type de ressource', note: 'Note', document: 'Document', text: 'Contenu de la note', file: 'Fichier à partager',
    formats: 'PDF, Word (.docx), Excel (.xlsx) ou PowerPoint (.pptx), jusqu’à 5 Mo. Le fichier est copié ; il ne sera pas synchronisé avec son original.',
    audience: 'Qui peut consulter cette copie ?', team: 'Toute l’équipe, y compris les futurs collaborateurs', selected: 'Certains collaborateurs', onlyAdmins: 'Sans collaborateur sélectionné, seuls les administrateurs y auront accès.',
    confirm: 'Je confirme le contenu et les personnes autorisées à consulter cette copie.', confirmAccess: 'Je confirme les nouveaux accès à cette copie.',
    remove: 'Retirer la ressource', confirmRemove: 'Je confirme le retrait de cette copie pour toute l’entreprise.', removed: 'La copie a été retirée.', saved: 'La ressource est enregistrée.',
    failed: 'Impossible de charger ces ressources. Actualisez pour réessayer.', missing: 'Cette ressource n’est plus disponible. Actualisez la liste.',
    changed: 'La ressource ou ses accès ont changé. Actualisez avant de continuer.', uncertain: 'La modification n’a pas pu être confirmée. Actualisez pour vérifier son état.',
    retryHint: 'La publication n’a pas pu être confirmée. Réessayer conserve la même demande pour éviter de créer un doublon.',
    invalid: 'Vérifiez le fichier, le contenu et les collaborateurs sélectionnés, puis réessayez.', quota: 'La capacité de partage de l’entreprise est atteinte. Retirez des copies inutilisées.',
    search: 'Rechercher un titre', find: 'Rechercher', admins: 'Administrateur',
  },
  en: {
    title: 'Company resources', intro: 'Notes and documents published here are copies shared with you. Your connections and memory remain personal.',
    admin: 'Administrators can read and manage all these copies. Choose which colleagues can also read them with their assistant.',
    effect: 'Available to the assistant in new conversations. Removing access blocks future reads without erasing copies already read or downloaded.',
    empty: 'No resources shared with you.', reload: 'Refresh', more: 'Show more', add: 'Publish a resource', open: 'Read', download: 'Download', edit: 'Edit content', access: 'Manage access',
    close: 'Close', save: 'Save', publish: 'Publish copy', retry: 'Retry the same publication', loading: 'Loading…', busy: 'Working…',
    name: 'Title', kind: 'Resource type', note: 'Note', document: 'Document', text: 'Note content', file: 'File to share',
    formats: 'PDF, Word (.docx), Excel (.xlsx) or PowerPoint (.pptx), up to 5 MB. The file is copied; it will not sync with its original.',
    audience: 'Who can read this copy?', team: 'The whole team, including future colleagues', selected: 'Selected colleagues', onlyAdmins: 'With no colleagues selected, only administrators will have access.',
    confirm: 'I confirm the content and the people allowed to read this copy.', confirmAccess: 'I confirm the new access to this copy.',
    remove: 'Remove resource', confirmRemove: 'I confirm removing this copy for the whole company.', removed: 'The copy has been removed.', saved: 'The resource has been saved.',
    failed: 'Resources could not be loaded. Refresh to try again.', missing: 'This resource is no longer available. Refresh the list.',
    changed: 'The resource or its access has changed. Refresh before continuing.', uncertain: 'The change could not be confirmed. Refresh to check its state.',
    retryHint: 'Publication could not be confirmed. Retrying keeps the same request to avoid creating a duplicate.',
    invalid: 'Check the file, content and selected colleagues, then try again.', quota: 'Company sharing capacity has been reached. Remove unused copies.',
    search: 'Search by title', find: 'Search', admins: 'Administrator',
  },
};
