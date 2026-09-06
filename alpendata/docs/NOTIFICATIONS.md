# Notifications personnelles

La cloche de l'interface affiche le nombre de notifications non lues pour l'entreprise actuellement sélectionnée. Son panneau présente les résultats, échecs et interruptions des tâches planifiées, ainsi que les échéances manquées et les automatisations bloquées. Les textes existent en français et anglais.

« Ouvrir le résultat » ouvre la conversation privée correspondante et enregistre la lecture de la notification. Sans résultat, « Voir mes automatisations » ouvre leur gestion. « Marquer comme lu » conserve l'état sans exécuter de tâche. Lire une notification ne confirme pas un envoi et ne réactive pas une automatisation.

## Origine et cohérence

La migration `0016` ajoute `alpendata_personal_notifications`. L'événement est écrit dans la transaction qui clôture l'occurrence, constate une échéance manquée ou bloque la tâche. Il n'existe pas de second worker de notifications à synchroniser. La source est l'état validé par le backend, jamais une affirmation du modèle dans une réponse.

Une clé de source unique par propriétaire identifie l'occurrence ou la version du blocage. Les créations prennent le verrou du propriétaire et les contraintes PostgreSQL empêchent les doublons. Les clés étrangères composées lient entreprise, propriétaire, planification et tour. Le titre, le statut et l'horaire sont conservés ; le contenu de la réponse, les mails et les fichiers ne sont pas copiés dans la notification.

Une annulation volontaire ne crée pas d'alerte de résultat. Le blocage d'une automatisation produit sa propre alerte ; si un échec d'exécution provoque également un blocage après plusieurs échecs, les deux événements restent distincts et compréhensibles. Les historiques antérieurs à la migration restent accessibles dans les automatisations ; aucun rattrapage massif de notifications n'est créé.

## API et accès

Routes sous `/api/organizations/{organization_id}/notifications` :

| Route | Fonction |
| --- | --- |
| `GET` | 25 notifications, compteur non lu et curseur de page suivante. |
| `GET ?count_only=true` | Compteur personnel uniquement. |
| `GET ?before=…&before_id=…` | Page antérieure selon le couple horaire/identifiant, y compris en cas d'horaires identiques. |
| `PUT /{id}/read`, corps `{}` | Lecture idempotente, avec le même premier horaire conservé lors d'une répétition. |

Le propriétaire est exclusivement l'utilisateur authentifié. Un administrateur client ne peut ni consulter ni marquer les notifications d'un collaborateur. Un membre actif sans licence conserve l'accès à ces informations existantes ; la désactivation de son compte ou de son adhésion retire l'accès. Les règles de cookie, d'origine des mutations et de cache privé sont celles de l'API.

## Interface et réponses tardives

Le compteur est vérifié à l'ouverture de l'application, toutes les 30 secondes quand l'onglet est visible, et au retour sur l'onglet. Le panneau charge sa liste à l'ouverture ; « Actualiser » récupère les nouveaux éléments. Le changement de langue conserve les états de lecture. L'affichage est recréé lors d'un changement d'entreprise ou de compte.

Les réponses obsolètes ne rétablissent pas un ancien compteur après une lecture. Après une réponse de lecture perdue, l'utilisateur peut actualiser ou répéter la lecture ; cela ne rejoue aucune action métier. Une révocation détectée efface le contenu du panneau. Les titres sont rendus comme du texte. Échap ferme le panneau et rend le focus à la cloche ; les boutons restent accessibles sur un écran étroit.

Cette fonctionnalité est une boîte de notifications dans l'application. Elle n'envoie pas de mail supplémentaire et ne demande pas de permission de notification au navigateur. Les éventuels canaux externes et leurs préférences restent à définir séparément. Les règles de conservation de cette nouvelle table doivent être incluses dans la politique de données du service.

## Vérification

Les tests utilisent les véritables transactions de planification et de clôture, avec les transports Microsoft synthétiques. Ils couvrent résultat, échec, interruption, échéance manquée, déconnexion, doublons, accès administrateur refusé, retrait de licence, désactivation, lecture concurrente et pagination avec horaires égaux. Le reste de la suite vérifie les parcours Hermes dans les conteneurs réels.

Les tests frontend couvrent réponse tardive du compteur, état lu, pagination, navigation, changement de langue, réponse de lecture perdue et retrait d'accès. Le rendu est vérifié sur un aperçu local explicitement fictif, en français, anglais et dans un viewport mobile. Le pilote réel et l'exploitation Infomaniak restent à valider.
