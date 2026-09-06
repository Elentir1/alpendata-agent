# Invitations par e-mail

6 septembre 2026 — migration `0019`, formulaire français et anglais.

Dans « Mon entreprise », l'administrateur saisit l'adresse du collaborateur, choisit la langue de l'e-mail et envoie l'invitation. AlpenData utilise sa messagerie transactionnelle SMTP, indépendamment des connexions Microsoft personnelles. L'invitation réserve une place avant l'envoi ; son annulation ou son expiration libère cette réservation. Le prix et la synchronisation de cette capacité avec Stripe restent à définir.

L'invité ouvre le lien, se connecte à son compte puis vérifie son adresse. Cette preuve reste personnelle, fraîche et liée à ce compte et à cette invitation. L'e-mail initial ne dispense pas de cette vérification. Chaque collaborateur commence ensuite son propre onboarding, avec ses propres connexions et sa mémoire.

## Envoi et suivi

`POST /api/organizations/{organization_id}/invitations/email` reçoit `email`, `language` (`fr` ou `en`) et un `request_id` UUID. La création et la réservation de licence sont enregistrées dans une transaction avant le premier appel SMTP. Seul un administrateur actif de l'entreprise peut utiliser cette route ou consulter les invitations en attente.

La réponse contient l'identifiant de l'invitation, l'adresse, l'expiration, l'état d'envoi et les indicateurs d'acceptation ou d'annulation. Aucun jeton d'invitation n'est renvoyé par cette nouvelle route. Le jeton brut existe seulement dans la requête qui prépare le message ; la base conserve son empreinte. Le lien utilise un fragment `#invitation=...`, comme le parcours déjà existant.

Une même requête rejouée retourne son reçu sans envoyer un nouvel e-mail, même si l'invitation a ensuite été acceptée ou annulée. Une autre adresse ou langue avec le même UUID est refusée. La clé est propre à l'entreprise et les droits de l'appelant sont revérifiés. Deux requêtes concurrentes sous PostgreSQL réservent une seule place et font un seul envoi.

L'interface affiche :

| État | Signification |
| --- | --- |
| `manual` | Ancien lien créé pour partage manuel ; il conserve sa validité. |
| `sending` | La demande est enregistrée et l'envoi n'a pas encore de résultat final. |
| `submitted` | Le transport SMTP a terminé sans erreur. Cela ne prouve ni l'arrivée en boîte de réception ni la lecture. |
| `unknown` | Le résultat est incertain, ou une demande sans résultat a plus de deux minutes. Aucun nouvel envoi automatique n'est lancé. |

Si la réponse HTTP se perd, le formulaire conserve l'adresse, la langue et le même UUID pour vérifier l'envoi. Les états en cours ou incertains proposent aussi de revérifier le reçu. Après rechargement de la page, l'administrateur retrouve les invitations actives dans la liste. Le même destinataire ne peut pas recevoir une seconde invitation active de cette entreprise par une nouvelle clé de requête.

Une erreur SMTP après acceptation du message reste incertaine. L'invitation n'est pas invalidée silencieusement : elle peut avoir été reçue et reste utilisable tant qu'elle est active. L'administrateur peut vérifier avec le destinataire, puis annuler l'invitation avant d'en créer une nouvelle si nécessaire. L'annulation invalide le lien précédent ; elle ne rappelle pas un e-mail déjà transmis. Un appel déjà engagé peut terminer après une modification des droits ou une annulation.

Le nombre de nouveaux envois est limité à 20 par heure et par entreprise, y compris les invitations annulées. Les relectures d'un même reçu ne consomment pas cette limite. Un SMTP non configuré bloque l'envoi avant de réserver une place. Les domaines, la réputation d'envoi, les bounces et la délivrabilité réelle restent des éléments d'exploitation à valider.

## Compatibilité et exploitation

L'ancienne route `POST /invitations` reste disponible pour les clients API qui partagent un lien manuellement. Le nouveau formulaire utilise l'envoi direct. Les envois de preuve d'adresse conservent leur durée de validité et leur limite propres.

La migration ajoute les champs de suivi et un index unique sans recréer la table des invitations. Un exercice migre une base `0018` contenant une invitation et sa preuve : leur association et leurs empreintes sont conservées. Ce chemin est vérifié sur SQLite et PostgreSQL. À la restauration d'une sauvegarde, les invitations sont annulées et les envois encore marqués en cours deviennent incertains ; aucun envoi n'est repris automatiquement.

La sauvegarde et la maintenance exigent toujours l'arrêt et la fin des requêtes API déjà engagées. Le suivi d'envoi n'est pas une file SMTP permanente et ne rejoue pas un message après un crash. Les secrets SMTP restent dans la configuration serveur, jamais dans le navigateur, les reçus ou les unités de service.

Les tests utilisent PostgreSQL, des sessions synthétiques et un vrai serveur SMTP TLS local authentifié. Ils couvrent le destinataire, l'unicité de l'envoi, l'acceptation avec une preuve liée au bon compte, l'accusé SMTP perdu, les invitations annulées, les demandes restées en cours et la limite d'envoi. Les scénarios frontend vérifient la reprise du même envoi et les états incertain ou annulé. Le parcours Entra et la réception par les trois personnes du pilote restent à valider avec les services réels.
