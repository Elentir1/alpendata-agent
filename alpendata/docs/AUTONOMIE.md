# Autonomie personnelle des e-mails

6 septembre 2026 — premier réglage personnel d’action directe.

## Parcours et autorisations

Dans « Mon espace », « Ce que votre assistant peut faire » propose deux choix : confirmer chaque envoi, choix par défaut, ou permettre à l’assistant d’envoyer directement. Le passage à l’envoi direct exige une case d’autorisation explicite. Les demandes de l’utilisateur ou ses tâches doivent prévoir l’envoi ; demander un brouillon ne constitue pas une demande d’envoi. Le choix est individuel et disponible en français et anglais.

Trois conditions distinctes sont nécessaires : l’entreprise autorise `mail_send` et `mail_autonomous`, le collaborateur choisit personnellement le mode automatique, et sa propre connexion Microsoft dispose de `Mail.Send`. Le réglage ne crée aucune connexion et ne fournit aucun accès aux intégrations des collègues. L’administrateur ne peut pas modifier le choix personnel d’un autre utilisateur.

`GET` et `PUT /api/organizations/{id}/action-policy` utilisent uniquement le propriétaire authentifié. La migration `0014` conserve le choix, sa version et sa date sous une clé liée au membre de l’entreprise. Une modification concurrente ou une réponse perdue exige de recharger l’état. Un membre actif sans licence peut revenir à la confirmation, mais ne peut pas activer l’autonomie.

## Conversations et envoi

Les nouvelles conversations de révision `4` figent la présence éventuelle de `alpendata_send_email`. Les anciennes conservent leurs outils et leur contexte système. Les conversations d’onboarding qui proposent des tâches ne reçoivent jamais cet outil. Les autorisations courantes sont revérifiées côté serveur avant chaque action, même dans une conversation qui avait obtenu l’outil.

Hermes doit préparer le message pendant le tour courant puis soumettre son identifiant et sa version exacts. Il ne peut pas envoyer un brouillon d’un autre tour. L’envoi emprunte la même chaîne durable que la confirmation dans le navigateur : contenu et pièces jointes privés, tentative enregistrée avant Microsoft, une seule soumission par version, et reçu conservé après la réponse. Le reçu distingue l’initiateur navigateur ou agent et conserve la version de l’autorisation personnelle.

Une tentative incertaine ou encore en cours interdit aussi l’envoi d’un autre brouillon préparé pendant ce tour. Cela évite de contourner l’interdiction de répétition en recréant le message. Cette protection ne déduplique pas sémantiquement tous les messages de conversations distinctes. La recherche de copie envoyée reste disponible selon les droits de lecture personnels ; elle ne rend jamais un envoi incertain répétable. Voir [E-mails](EMAILS.md).

## Révocation et tâches

Revenir à la confirmation, retirer l’autorisation commune ou perdre les accès nécessaires bloque les prochains envois. Les transactions verrouillent le membre pendant l’appel Microsoft : un envoi déjà engagé peut terminer avant que la révocation soit validée. Son résultat acquis reste conservé, même si le choix personnel change juste après.

Les tâches héritent des outils de leur essai relu. Une tâche préparée avec l’autonomie est suspendue si celle-ci est retirée ; ses occurrences en file sont annulées et celles en cours reçoivent une demande d’arrêt. Réautoriser l’autonomie ne réactive pas les tâches. Le parcours demande un nouvel essai avant activation après changement.

Le catalogue comprend désormais une recette de briefing envoyé par e-mail, avec destinataires et objet fixés par le propriétaire, essai d’envoi confirmé puis activation explicite de la récurrence. Les recettes de lecture et de préparation restent sans outil d’envoi. Le parcours et ses limites sont décrits dans [Envois planifiés](ENVOIS_PLANIFIES.md). Activer le réglage personnel ne transforme pas automatiquement un briefing existant en e-mail envoyé.

## Validation et limites

Les tests couvrent la séparation des propriétaires, les refus par défaut, la confirmation explicite du choix, les versions concurrentes, la stabilité des conversations, les reçus, les réponses incertaines, les tentatives de remplacement et la révocation par le collaborateur ou l’entreprise. Un test PostgreSQL maintient l’appel Microsoft ouvert pendant une révocation et vérifie les verrous. Un test utilise le véritable Hermes dans son conteneur isolé pour préparer puis soumettre un message via le broker autorisé.

Les transports Microsoft et modèle de ces tests sont synthétiques. Aucun e-mail réel n’a été envoyé. La compréhension de l’intention par un modèle commercial, les permissions Entra/Exchange et le parcours pilote restent à valider. L’autonomie des dépôts SharePoint, les brouillons Outlook et les réponses liées aux fils ne font pas partie de cette étape.
