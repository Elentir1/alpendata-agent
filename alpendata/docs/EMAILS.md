# Brouillons personnels et confirmation d’envoi

6 septembre 2026 — première chaîne de préparation, relecture et envoi depuis le compte Microsoft personnel.

## Parcours disponible

Dans une nouvelle conversation, Hermes peut préparer un brouillon structuré avec destinataires, copies, copies cachées, objet, texte et pièces jointes déjà publiées. Le brouillon apparaît dans le chat. Il reste dans AlpenData : cette étape ne crée pas de brouillon dans Outlook et ne constitue pas une réponse rattachée à un fil Outlook.

Le propriétaire peut corriger les champs, retirer des pièces jointes et enregistrer sa version. Une case de relecture et le bouton « Envoyer ce mail » confirment ensuite cette version précise. Toute modification retire la confirmation. Une version modifiée dans une autre fenêtre doit être rechargée. Le français et l’anglais sont disponibles. Les messages sont envoyés en texte brut ; les documents joints conservent leur format d’origine.

La préparation ne nécessite aucun droit d’envoi. L’administrateur doit autoriser « Envoyer des mails » dans les règles communes ; cette nouvelle capacité est interdite par défaut. Le collaborateur consent ensuite séparément à `Mail.Send` déléguée depuis « Envoyer mes mails ». L’identité Microsoft doit correspondre à son compte AlpenData. Autoriser cette capacité ne fournit pas de connexion et ne donne pas à l’administrateur l’accès aux messages personnels.

## Propriété et autorisation

La migration `0012` ajoute les brouillons privés et leurs tentatives d’envoi. Le brouillon est lié au tour, à l’entreprise et au propriétaire par une clé étrangère composée. Les tentatives héritent de cette même propriété. Les API `GET`, `PATCH` et `POST .../send` sous `/api/organizations/{id}/emails/{draft_id}` résolvent toujours l’utilisateur authentifié ; le rôle administrateur ne contourne pas cette vérification.

Les nouveaux outils n’apparaissent qu’à partir de la révision de conversation `3`. Les anciennes conversations gardent leurs schémas et leur contexte système. L’outil `alpendata_prepare_email` n’envoie rien. Le moteur reste sans réseau externe, sans jeton Microsoft et sans cookie de session navigateur. Par défaut, il ne reçoit aucun outil d’envoi ; la confirmation est une action authentifiée de l’application, protégée par les contrôles d’origine existants. Depuis la révision `4`, un choix personnel explicite, permis par l’entreprise et accompagné du consentement Microsoft, peut fournir un outil d’envoi aux nouvelles conversations. Cette chaîne et ses limites sont décrites dans [Autonomie personnelle](AUTONOMIE.md).

La création est idempotente par tour et empreinte du contenu initial. Répéter un appel de l’agent ne remplace pas les corrections du propriétaire. Les pièces jointes sont résolues côté serveur parmi ses documents privés immuables. Limites : dix brouillons par tour, vingt destinataires au total, cinq pièces jointes et 2 Mio cumulés, objet sur une ligne de 998 caractères maximum, corps de 32 000 caractères maximum. Les adresses sont validées sans recherche DNS. L’agent reçoit l’adresse de l’expéditeur lors de la lecture d’un mail, en plus de son nom, pour éviter de devoir la deviner.

## Reçus et absence de répétition automatique

La version relue et son contenu sont enregistrés dans une tentative durable avant tout appel externe. Le verrou du membre et l’unicité `(draft_id, version)` empêchent deux confirmations concurrentes de déclencher deux requêtes. L’envoi revérifie la licence, le compte, la connexion personnelle et les règles de l’entreprise dans la passerelle Microsoft. Le serveur appelle uniquement `POST /me/sendMail`, sans champ `from`, `sender` ou adresse de boîte fournie par l’agent.

Le transport ne suit pas de redirection et ne répète pas les requêtes. Les documents sont transmis directement, encodés en base64. La copie dans les éléments envoyés reste activée par le comportement par défaut de Microsoft.

- `accepted` : Microsoft a retourné HTTP 202. Cela confirme l’acceptation de la demande, **pas la livraison**.
- `failed` : un refus connu ou une autorisation manquante a empêché l’acceptation. Le propriétaire peut corriger puis enregistrer une nouvelle version avant une nouvelle confirmation.
- `unknown` : interruption réseau ou réponse inattendue après dispatch. Le brouillon reste verrouillé ; aucune répétition automatique n’est permise.
- `sending` : la tentative est encore en cours. Après trois minutes sans résultat, sa présentation devient incertaine ; elle ne redevient jamais un brouillon envoyable automatiquement.

Une réponse perdue entre navigateur et API conduit à lire le reçu. Elle ne déclenche pas un nouvel envoi. La copie exacte de chaque tentative reste en base ; une modification ultérieure après refus ne réécrit pas son historique. Un résultat acquis est conservé même si l’accès du propriétaire est révoqué juste après l’appel, puis l’accès à la réponse est revérifié.

## Recherche d’une copie envoyée

La migration `0013` ajoute à chaque nouvelle tentative un identifiant de corrélation aléatoire et une observation de vérification. Le serveur transmet l’identifiant dans l’en-tête `x-alpendata-message-id`, uniquement pour reconnaître la copie correspondante. Il ne contient ni identité du collaborateur ni identifiant d’entreprise, et n’est pas retourné dans les reçus du chat. Les anciennes tentatives restent sans identifiant : aucune corrélation n’est inventée après coup.

Le propriétaire peut demander `POST .../emails/{draft_id}/attempts/{attempt_id}/verify` pour une demande acceptée ou incertaine. La route revérifie sa propriété, sa licence, ses règles communes et son consentement personnel `Mail.Read`. Elle consulte uniquement `/me/mailFolders/sentitems/messages`. L’accès d’envoi ne donne pas l’accès de lecture ; une permission manquante est expliquée dans l’interface.

La recherche porte sur les cent messages les plus récents depuis cinq minutes avant la tentative, afin de tolérer un décalage d’horloge. Une limite ou une pagination supplémentaire est signalée ; les liens de pagination reçus ne sont pas suivis. Les appels gardent les limites du lecteur Graph : HTTPS fixe, absence de redirections, délai réseau et réponse JSON bornée à 2 Mio.

Une correspondance exige un seul en-tête de corrélation exact, le même objet, les mêmes destinataires/copies/copies cachées, un message non brouillon et une date d’envoi cohérente. L’observation conserve la date de vérification, le nombre de messages consultés, le nombre de correspondances et le lien Outlook de la première copie. Elle atteste la présence de cette copie dans les éléments envoyés au moment du contrôle ; elle ne prouve pas la livraison ni une identité binaire du corps ou des pièces jointes après traitement Exchange.

Une observation positive est conservée séparément du statut de soumission initial et n’est pas effacée par une vérification concurrente négative. Une absence ou une erreur de lecture ne rend jamais le message réenvoyable. La copie peut être absente de la sélection, déplacée, retardée ou filtrée : l’absence de résultat ne démontre pas l’absence d’envoi. L’interface permet une nouvelle recherche ou une vérification manuelle dans Outlook. Si plusieurs copies correspondent, elle l’indique explicitement.

## Validation et étapes restantes

Les tests utilisent le vrai serveur FastAPI, les migrations, MSAL et le coffre, avec des transports Microsoft synthétiques. Ils couvrent la propriété, les versions concurrentes, les pièces jointes, le refus de l’envoi par défaut, le consentement personnel, l’absence d’outil d’envoi dans Hermes sans autonomie personnelle et le refus de réessayer après une réponse perdue. Le test PostgreSQL maintient un envoi ouvert pendant une seconde confirmation. Le test OCI utilise le véritable Hermes pour produire un brouillon puis la route de confirmation pour soumettre le message synthétique.

La recherche des copies envoyées est testée avec HTTP synthétique : droits personnels, restrictions d’entreprise, marqueurs et destinataires incorrects, absence, copie trouvée, anciennes tentatives et erreurs Graph. Le navigateur teste aussi une réponse de vérification perdue et le rechargement du reçu. La résolution opérateur des résultats toujours incertains reste à réaliser ; aucune relance n’est activée par l’absence de copie. L’autonomie personnelle configurable des e-mails est implémentée, avec distinction de l’initiateur et version du choix dans les reçus. L’enregistrement de brouillons Outlook, les réponses attachées aux fils restent à implémenter. Le parcours dédié de briefing récurrent est maintenant décrit dans [Envois planifiés](ENVOIS_PLANIFIES.md). Aucun envoi vers une boîte réelle n’a été effectué lors de cette validation. Les essais Entra/Exchange et fournisseur IA réels restent nécessaires avant le pilote.

Référence primaire : [Microsoft Graph — sendMail](https://learn.microsoft.com/en-us/graph/api/user-sendmail?view=graph-rest-1.0), notamment permissions déléguées, pièces jointes JSON et signification de HTTP 202.

Références complémentaires : [Lister les messages Microsoft Graph](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0) pour la sélection, les filtres et la pagination ; [Ressource message](https://learn.microsoft.com/en-us/graph/api/resources/message?view=graph-rest-1.0) pour les en-têtes personnalisés. La conservation et la lecture de ces en-têtes dans Exchange réel restent à valider avant le pilote.
