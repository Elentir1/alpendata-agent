# Chat personnel et exécutions durables

6 septembre 2026 — implémentation locale reliée à Hermes réel ; services externes réels et déploiement encore à configurer.

## Parcours

L’entrée « Assistant » ouvre les conversations du seul utilisateur connecté dans l’entreprise sélectionnée. L’interface française/anglaise permet de créer une conversation, envoyer un message, consulter le résultat et arrêter une demande. Elle affiche les états d’attente, d’exécution et d’interruption. Les réponses sont rendues comme du texte, sans interprétation HTML. Les propositions, essais et automatisations personnelles sont maintenant reliés au chat ; la production des documents reste à réaliser.

Un envoi HTTP crée un travail en base puis répond `202`. Un processus distinct, `alpendata_api.chat_worker`, prend ce travail et exécute Hermes. Le rechargement du navigateur ou le redémarrage de l’API ne perdent donc pas la demande. Une clé UUID fournie par le navigateur rend le même envoi idempotent ; réutiliser cette clé avec un autre contenu est refusé. Une réponse réseau incertaine garde la même demande pour sa vérification, sans produire un second travail.

## Propriété et contexte

Les conversations, tours et relevés de consommation portent une entreprise et un propriétaire. Des clés étrangères composées interdisent de rattacher un tour ou une consommation au contenu d’un autre utilisateur. L’administrateur n’a aucun accès supplémentaire à ces données.

Le profil, la langue de réponse, le modèle et les capacités disponibles sont fixés au début de la conversation pour préserver le contexte Hermes. La connexion Microsoft actuelle est cependant vérifiée à chaque lecture. Une déconnexion retire donc immédiatement les futurs accès, même si l’outil reste décrit dans le contexte de cette conversation. Une connexion supplémentaire devient disponible dans une nouvelle conversation. Un changement du modèle configuré exige aussi une nouvelle conversation.

L’historique technique de reprise est lu dans la base SessionDB du volume personnel Hermes, y compris après une interruption partiellement enregistrée. Le client HTTP ne fournit ni cet historique ni le contexte système. Le navigateur reçoit les messages utilisateur et réponses finales de la projection métier, sans les traces internes de raisonnement ou les secrets.

## File de travail et interruptions

PostgreSQL verrouille l’adhésion avant les tours et connexions. Une seule exécution Hermes peut être active par propriétaire dans une entreprise. Les demandes interactives refusent une file déjà occupée ; les occurrences planifiées peuvent y attendre, puis sont exécutées successivement. Plusieurs processus de travail peuvent réclamer des propriétaires différents grâce à `SKIP LOCKED`. Le superviseur conserve également son verrou de fichiers par propriétaire.

Un travail actif possède un bail de 120 secondes, renouvelé toutes les trois secondes. Ce délai laisse passer un renouvellement de jeton suivi d’une lecture Graph tenant les verrous d’autorisation. La perte du bail, la désactivation de l’utilisateur ou du membre, le retrait de licence et l’annulation empêchent de continuer ou livrer le résultat. Le contrôle d’annulation et du délai continue pendant l’attente des appels du broker. Le conteneur peut être arrêté pendant cette attente ; une requête déjà reçue par le fournisseur ne peut pas être retirée, et son éventuel reçu tardif reste lié au tour d’origine.

Au redémarrage, un bail expiré devient une interruption visible. Le travail n’est jamais rejoué automatiquement. Une consommation commencée sans réponse reste inconnue. Si un conteneur orphelin existe encore, le superviseur refuse de lancer un second écrivain et signale `agent_recovery_required`. La procédure opérateur de récupération contrôlée et les exercices de restauration restent à compléter avant exploitation.

## Consommation

Chaque appel de modèle est enregistré avant son départ, avec le tour, le propriétaire et la configuration serveur. Les compteurs confirmés sont enregistrés avant de livrer la réponse à Hermes. Ils restent conservés si l’utilisateur annule ou perd ses droits pendant l’appel. Les appels auxiliaires autorisés suivent le même chemin ; le titrage secondaire Hermes est désactivé puisque le produit nomme déjà les conversations. Des chiffres absents ou un appel interrompu ne deviennent pas une consommation nulle. La tarification CHF, le registre de facturation et sa réconciliation avec Stripe restent à relier.

## Routes

Préfixe : `/api/organizations/{organization_id}/chat`.

| Route | Fonction |
|---|---|
| `GET /` | Disponibilité et liste personnelle, paginée avec `before` comme décalage. |
| `POST /conversations` | Créer une conversation ; `language` et titre facultatif. |
| `GET /conversations/{id}` | Lire les tours ; `after` est la dernière séquence reçue. |
| `POST /conversations/{id}/turns` | Envoyer `request_id` UUID et `message`, jusqu’à 32 000 caractères. |
| `POST /conversations/{id}/turns/{turn_id}/cancel` | Annuler une demande en attente ou demander l’arrêt d’une exécution. |

La lecture de son historique et l’arrêt restent possibles pour un membre actif sans licence. La création et l’exécution exigent une licence. Une désactivation de membre retire également la lecture.

## Démarrage

Appliquer les migrations jusqu’à `0005`. Sur l’hôte Linux, construire l’image selon le [README du runtime](../runtime/README.md). Fournir à l’API et au processus de travail la même configuration :

| Variable | Contenu |
|---|---|
| `ALPENDATA_DATABASE_URL` | Base PostgreSQL dédiée. |
| `ALPENDATA_MODEL_PROVIDER` | `mistral` ou `openrouter`. |
| `ALPENDATA_MODEL_ID` | Modèle choisi et validé pour les outils de l’agent. |
| `ALPENDATA_MODEL_API_KEY` | Secret du fournisseur, uniquement côté serveur. |
| `ALPENDATA_MODEL_ALLOWED_PROVIDERS` | Liste facultative de fournisseurs OpenRouter séparés par des virgules. |
| `ALPENDATA_RUNTIME_STATE_ROOT` | Dossier Linux absolu contenant les volumes privés. |
| `ALPENDATA_RUNTIME_IMAGE` | Identifiant local immuable `sha256:…`. |

Les paramètres Microsoft et les clés du coffre sont également nécessaires au processus de travail pour lire les intégrations personnelles. La configuration de chat est facultative mais doit être complète : en son absence, l’interface annonce que le service n’est pas activé et aucune exécution ne démarre.

Depuis le backend, après installation de ses dépendances :

```sh
uv run python -m alpendata_api.chat_worker
```

L’API est démarrée séparément comme documenté dans son README. En production, un gestionnaire de services devra superviser ces processus. Aucun secret du modèle ou de Microsoft ne doit figurer dans le bundle Vite ou les variables `VITE_*`.

## Preuves et limites

Le test de bout en bout utilise PostgreSQL, MSAL, un serveur HTTP de modèle et des conteneurs Hermes réels. Les réponses Microsoft/Graph et du modèle sont synthétiques. Il vérifie un redémarrage d’API avant exécution, les jetons du propriétaire, la reprise du même contexte, la déconnexion Microsoft, l’annulation pendant un appel et la conservation de sa consommation, puis le retrait des droits avant un travail en attente.

L’interface dispose de tests JSDOM et a été contrôlée dans le navigateur intégré avec un build réel et des données fictives explicitement signalées : navigation vers le chat, rendu d’un historique, saisie/envoi et changement français/anglais. Aucun service client réel n’a été connecté dans cette vérification visuelle. Le pilote réel, la disponibilité du processus de travail, la supervision et le déploiement Infomaniak restent à valider.

## Extension du premier résultat

La migration `0006` et le [parcours d’onboarding](PREMIER_RESULTAT.md) ajoutent les conversations de planification, les propositions et les essais personnels. Les nouveaux chats exigent un profil personnel renseigné. Les sources affichées proviennent des lectures confirmées par le broker. Le type de conversation, le contexte et les permissions sont figés à sa création ; l’outil de proposition reste propre aux conversations d’onboarding.

Les [automatisations](AUTOMATISATIONS.md) utilisent des sessions distinctes, un budget maximal de 180 secondes et aucun fournisseur de mémoire en arrière-plan.
