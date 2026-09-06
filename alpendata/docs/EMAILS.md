# Brouillons personnels et confirmation d’envoi

6 septembre 2026 — première chaîne de préparation, relecture et envoi depuis le compte Microsoft personnel.

## Parcours disponible

Dans une nouvelle conversation, Hermes peut préparer un brouillon structuré avec destinataires, copies, copies cachées, objet, texte et pièces jointes déjà publiées. Le brouillon apparaît dans le chat. Il reste dans AlpenData : cette étape ne crée pas de brouillon dans Outlook et ne constitue pas une réponse rattachée à un fil Outlook.

Le propriétaire peut corriger les champs, retirer des pièces jointes et enregistrer sa version. Une case de relecture et le bouton « Envoyer ce mail » confirment ensuite cette version précise. Toute modification retire la confirmation. Une version modifiée dans une autre fenêtre doit être rechargée. Le français et l’anglais sont disponibles. Les messages sont envoyés en texte brut ; les documents joints conservent leur format d’origine.

La préparation ne nécessite aucun droit d’envoi. L’administrateur doit autoriser « Envoyer des mails après confirmation » dans les règles communes ; cette nouvelle capacité est interdite par défaut. Le collaborateur consent ensuite séparément à `Mail.Send` déléguée depuis « Envoyer mes mails ». L’identité Microsoft doit correspondre à son compte AlpenData. Autoriser cette capacité ne fournit pas de connexion et ne donne pas à l’administrateur l’accès aux messages personnels.

## Propriété et autorisation

La migration `0012` ajoute les brouillons privés et leurs tentatives d’envoi. Le brouillon est lié au tour, à l’entreprise et au propriétaire par une clé étrangère composée. Les tentatives héritent de cette même propriété. Les API `GET`, `PATCH` et `POST .../send` sous `/api/organizations/{id}/emails/{draft_id}` résolvent toujours l’utilisateur authentifié ; le rôle administrateur ne contourne pas cette vérification.

Les nouveaux outils n’apparaissent qu’à partir de la révision de conversation `3`. Les anciennes conversations gardent leurs schémas et leur contexte système. L’outil `alpendata_prepare_email` n’envoie rien. Le moteur reste sans réseau externe, sans jeton Microsoft et sans cookie de session navigateur. Il ne reçoit aucun outil d’envoi ; la confirmation est une action authentifiée de l’application, protégée par les contrôles d’origine existants.

La création est idempotente par tour et empreinte du contenu initial. Répéter un appel de l’agent ne remplace pas les corrections du propriétaire. Les pièces jointes sont résolues côté serveur parmi ses documents privés immuables. Limites : dix brouillons par tour, vingt destinataires au total, cinq pièces jointes et 2 Mio cumulés, objet sur une ligne de 998 caractères maximum, corps de 32 000 caractères maximum. Les adresses sont validées sans recherche DNS. L’agent reçoit l’adresse de l’expéditeur lors de la lecture d’un mail, en plus de son nom, pour éviter de devoir la deviner.

## Reçus et absence de répétition automatique

La version relue et son contenu sont enregistrés dans une tentative durable avant tout appel externe. Le verrou du membre et l’unicité `(draft_id, version)` empêchent deux confirmations concurrentes de déclencher deux requêtes. L’envoi revérifie la licence, le compte, la connexion personnelle et les règles de l’entreprise dans la passerelle Microsoft. Le serveur appelle uniquement `POST /me/sendMail`, sans champ `from`, `sender` ou adresse de boîte fournie par l’agent.

Le transport ne suit pas de redirection et ne répète pas les requêtes. Les documents sont transmis directement, encodés en base64. La copie dans les éléments envoyés reste activée par le comportement par défaut de Microsoft.

- `accepted` : Microsoft a retourné HTTP 202. Cela confirme l’acceptation de la demande, **pas la livraison**.
- `failed` : un refus connu ou une autorisation manquante a empêché l’acceptation. Le propriétaire peut corriger puis enregistrer une nouvelle version avant une nouvelle confirmation.
- `unknown` : interruption réseau ou réponse inattendue après dispatch. Le brouillon reste verrouillé ; aucune répétition automatique n’est permise.
- `sending` : la tentative est encore en cours. Après trois minutes sans résultat, sa présentation devient incertaine ; elle ne redevient jamais un brouillon envoyable automatiquement.

Une réponse perdue entre navigateur et API conduit à lire le reçu. Elle ne déclenche pas un nouvel envoi. La copie exacte de chaque tentative reste en base ; une modification ultérieure après refus ne réécrit pas son historique. Un résultat acquis est conservé même si l’accès du propriétaire est révoqué juste après l’appel, puis l’accès à la réponse est revérifié.

## Validation et étapes restantes

Les tests utilisent le vrai serveur FastAPI, les migrations, MSAL et le coffre, avec des transports Microsoft synthétiques. Ils couvrent la propriété, les versions concurrentes, les pièces jointes, le refus de l’envoi par défaut, le consentement personnel, l’absence d’outil d’envoi dans Hermes et le refus de réessayer après une réponse perdue. Le test PostgreSQL maintient un envoi ouvert pendant une seconde confirmation. Le test OCI utilise le véritable Hermes pour produire un brouillon puis la route de confirmation pour soumettre le message synthétique.

La vérification automatique des éléments envoyés et la résolution opérateur des résultats incertains restent à réaliser. L’écran invite actuellement à vérifier Outlook ; l’absence d’un message visible ne prouve pas qu’il n’a pas été envoyé. L’enregistrement de brouillons Outlook, les réponses attachées aux fils et l’autonomie personnelle configurable restent également à implémenter. Aucun envoi vers une boîte réelle n’a été effectué lors de cette validation. Les essais Entra/Exchange et fournisseur IA réels restent nécessaires avant le pilote.

Référence primaire : [Microsoft Graph — sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0), notamment permissions déléguées, pièces jointes JSON et signification de HTTP 202.
