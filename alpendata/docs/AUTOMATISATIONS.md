# Automatisations personnelles

6 septembre 2026 — planification depuis la migration `0007`, destination d’envoi depuis `0015`.

## Parcours utilisateur

Après un essai terminé dont les sources nécessaires ont été effectivement consultées, l’utilisateur peut choisir « Planifier cette tâche ». Il règle une fréquence quotidienne, du lundi au vendredi ou hebdomadaire, une heure locale et un fuseau. La case de confirmation de lecture du résultat est obligatoire. L’activation n’exécute pas immédiatement la tâche : la prochaine occurrence est strictement future et sa date est affichée dans le fuseau choisi.

L’écran « Automatisations » présente les tâches de la personne connectée, leurs sources, horaires, états et résultats. Il permet de modifier l’horaire, suspendre, reprendre, refaire un essai ou retirer une automatisation. Le retrait arrête les occurrences et masque la tâche de la liste ; les résultats privés restent accessibles dans l’assistant. Un nouvel essai peut servir à recréer sa planification, sans effacer l’historique existant.

Une automatisation peut être remplacée par la validation d’un nouvel essai de la même proposition, avec la version courante de la planification. Les occurrences anciennes en attente sont annulées. Ce parcours sert notamment après un changement de modèle. La définition et les permissions utilisées pour chaque occurrence viennent du contexte de l’essai approuvé, pas du profil utilisateur éventuellement modifié depuis. Un changement de besoin se fait par une nouvelle proposition et un nouvel essai.

Les résultats restent dans l’application. Les recettes de lecture et de préparation n’effectuent pas d’envoi. La recette dédiée de briefing par e-mail exige les permissions personnelles, une destination choisie par le propriétaire, un essai d’envoi confirmé et l’autorisation des envois récurrents. Voir [Envois planifiés](ENVOIS_PLANIFIES.md). Les autres écritures et les notifications opérationnelles restent à compléter.

## Décision d’architecture

L’architecture initiale envisageait un scheduler Hermes par utilisateur avec une projection côté API. L’exécution mise en place utilise des conteneurs éphémères et un volume privé que l’agent peut modifier. Le magasin `cron/jobs.json` de ce volume ne peut donc pas servir de preuve de consentement à une tâche de l’entreprise. Maintenir en plus un ticker permanent par utilisateur et une projection bidirectionnelle créerait deux états à réconcilier pour l’activation, la suspension et les doublons.

La décision retenue est une seule autorité de planification dans PostgreSQL, sous les mêmes contrôles de propriété que les conversations. Le scheduler AlpenData inscrit une occurrence et un tour dans une transaction ; le processus de travail existant l’exécute avec le véritable Hermes dans l’environnement du propriétaire. Le ticker, le magasin cron et les outils cron d’Hermes ne sont pas lancés pour ces tâches. Le code amont reste inchangé. Cette adaptation conserve le moteur Hermes et les invariants utiles : session distincte par occurrence, arrêt au plus tard au budget prévu, pas de fournisseurs de mémoire en arrière-plan, pas d’injection d’un résultat dans une conversation interactive existante.

## Horaires et reprise

- Les fuseaux sont validés avec la base IANA ; `tzdata` est une dépendance explicite du backend pour les systèmes qui n’en disposent pas.
- Une heure inexistante au changement d’heure est sautée. Une heure répétée à l’automne utilise uniquement sa première occurrence. Les calculs portent sur des jours civils, pas sur des durées fixes de 24 heures.
- Une occurrence peut être rattrapée dans les deux heures suivant son horaire. Au-delà, elle est enregistrée comme manquée et la prochaine échéance est calculée après l’heure courante. Les journées manquées ne sont pas rejouées en masse.
- Les occurrences peuvent attendre dans la file derrière une exécution en cours du propriétaire ; une seule exécution Hermes reste active à la fois. Une occurrence encore en attente au-delà de sa fenêtre est refusée avant l’appel du modèle.
- La création de l’occurrence, du tour et de la prochaine échéance est atomique. Le verrou du membre puis celui de la planification sérialise deux tickers concurrents. Une contrainte unique sur la planification et son échéance empêche un doublon en base.
- Modifier l’horaire, suspendre ou retirer la planification annule ses occurrences en attente et demande l’arrêt de celle en cours. Reprendre calcule une échéance future et ne rejoue pas les anciennes tentatives.

## Droits, erreurs et délais

Les routes vérifient le membre, sa licence lorsque nécessaire et la propriété. Un administrateur ne peut ni lire ni lancer une automatisation personnelle d’un collègue. Les invitations ne recopient aucune planification.

Une déconnexion, une réduction des permissions qui enlève une source nécessaire ou un retrait d’accès/licence bloque les récurrences actives concernées et annule les occurrences en attente. La connexion rétablie ne les réactive pas automatiquement. Le worker vérifie aussi les droits, le bail et la version de la planification avant de continuer. Un changement de modèle exige un nouvel essai au lieu de changer silencieusement le modèle approuvé.

Un résultat sans lectures confirmées pour les sources requises est en échec. Trois échecs consécutifs bloquent la récurrence ; une reprise explicite remet le compteur à zéro. Une interruption ne provoque pas de nouvelle tentative automatique du même tour. Les reçus de lecture et de consommation conservent la distinction entre résultat confirmé et résultat inconnu.

Le budget d’une session planifiée est plafonné à 180 secondes, ou au budget opérateur inférieur. Le contrôleur surveille ce délai et l’annulation même pendant l’attente d’une réponse du broker. Un appel fournisseur déjà accepté peut encore revenir après l’arrêt du conteneur ; son reçu reste lié au tour d’origine, et une réponse tardive n’est pas envoyée à un nouvel agent. Si le processus hôte disparaît avant ce retour, le résultat reste inconnu. Le nettoyage et le contrôle des conteneurs orphelins restent ceux du runtime existant.

## Exploitation et API

Appliquer les migrations avant de démarrer les services. Avec les mêmes paramètres serveur que l’API et le chat, exécuter séparément :

```sh
uv run python -m alpendata_api.schedule_worker
uv run python -m alpendata_api.chat_worker
```

La première commande inspecte les échéances toutes les 30 secondes ; la seconde exécute la file. Elles se lancent depuis `alpendata/backend`, sur l’environnement d’exploitation configuré. Le scheduler n’a pas besoin d’accéder aux volumes des agents. Les [unités systemd et l'arrêt propre](SERVICES_CONTINUS.md) sont préparés : redémarrage après échec, limite de tentatives et fin du lot courant avant arrêt. Leur installation persistante et leur validation sur Infomaniak restent à réaliser.

Routes personnelles sous `/api/organizations/{organization_id}/schedules` :

| Route | Fonction |
|---|---|
| `GET` | Liste paginée des planifications non retirées. |
| `POST` | Activation avec `request_id`, `reviewed_trial_id`, `reviewed: true` et horaire ; `email_delivery_confirmed: true` pour un envoi et `replaces_schedule_version` pour remplacer une planification existante. |
| `PATCH /{id}` | Modification de l’horaire avec la version courante. |
| `POST /{id}/pause`, `/resume`, `/archive` | Changement d’état avec la version courante. |
| `GET /{id}/occurrences` | Historique paginé et liens vers les conversations privées. |

Les activations sont idempotentes par propriétaire. Les modifications concurrentes utilisent une version pour éviter un écrasement silencieux. Le navigateur conserve l’identifiant d’une activation ou d’un nouvel essai tant qu’une réponse réseau reste incertaine.

## Vérification et limites

La validation couvre les horaires suisses aux deux changements d’heure, les jours ouvrés, l’activation explicite et idempotente, la propriété, l’édition, la suspension d’une occurrence en cours, les déconnexions, le retrait de licence, les occurrences manquées, les échecs répétés, le nouvel essai et la réactivation. Deux activations et deux tickers concurrents sont exercés sur PostgreSQL réel.

Le scénario complet exécute trois conteneurs Hermes successifs : propositions, essai, occurrence planifiée. Il vérifie les sources du propriétaire et l’absence d’outil mémoire dans l’exécution planifiée. Un scénario de pipes réels vérifie que l’attente d’un broker ne prolonge pas le budget d’exécution. Le modèle et Microsoft restent des services synthétiques dans ces tests.

L’interface française et anglaise a été parcourue sur un aperçu séparé, explicitement fictif : résultat, case de revue, activation, gestion, historique et suspension. Les services de production, les récurrences sur le tenant pilote, les éventuels canaux de notification externes, les actions externes réelles et les procédures de restauration restent à valider ou à réaliser. Les [notifications personnelles dans l’application](NOTIFICATIONS.md) sont implémentées pour les résultats, les problèmes et les échéances manquées.
