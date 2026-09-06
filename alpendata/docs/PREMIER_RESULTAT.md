# Onboarding et premier résultat personnel

Implémentation du 6 septembre 2026. La migration `0006` ajoute les propositions, les essais, les preuves de lecture et le type des conversations. Les conversations existantes conservent le type `chat`.

## Parcours

Chaque utilisateur complète son propre rôle et son besoin. L’écran du premier résultat reprend ce besoin dans un champ modifiable et place le lancement des propositions avant les réglages complémentaires. Le changement de langue conserve la saisie en cours. Les connexions Microsoft sont facultatives et personnelles : des tâches de préparation restent disponibles sans intégration. Le formulaire crée une conversation d’onboarding et une demande durable. Hermes reçoit le profil personnel et le catalogue des tâches réalisables avec les accès accordés à cette personne.

L’outil de session `alpendata_propose_routines` enregistre deux ou trois propositions. Le serveur vérifie leur nombre, leur unicité, leur recette et leurs permissions ; les titres, bénéfices et critères de recherche sont personnalisés par le modèle. Une conversation conserve son premier ensemble de propositions afin de ne pas modifier un essai déjà consulté. Une nouvelle demande depuis l’onboarding produit une nouvelle sélection. Si Hermes termine sans enregistrer de propositions, le tour échoue avec `routine_proposals_missing` plutôt que d’afficher une préparation réussie.

Le bouton « Tester maintenant » crée une nouvelle conversation et un seul tour d’exécution. Les sources disponibles sont limitées aux besoins de la recette. Le résultat et les références des sources consultées apparaissent dans le chat. Aucun essai ne programme de répétition. Les recettes de préparation n’envoient pas de message ; la recette distincte de [briefing envoyé](ENVOIS_PLANIFIES.md) exige la confirmation des destinataires, de l’objet et d’un envoi unique.

## Tâches disponibles

| Accès personnel | Exemples proposés |
|---|---|
| Aucune intégration | Structure de processus, liste de travail et trame de document à partir des informations personnelles fournies. |
| Messagerie | Briefing récent, suivi des échanges, préparation d’une réponse sous forme de texte dans le chat. |
| Agenda | Agenda à venir, liste de préparation. |
| Agenda et messagerie | Préparation des rendez-vous à partir des sources qui correspondent effectivement. |
| Fichiers | Recherche de documents, inventaire de supports à partir de leurs métadonnées. |

Les limites des lectures Microsoft restent explicites : dix mails récents avec aperçu, vingt rendez-vous sur sept jours, dix résultats de recherche de fichiers. Les recettes de recherche se fondent sur les métadonnées et ne doivent pas être présentées comme une vérification du contenu. La lecture et la génération des fichiers dans le chat sont décrites dans [Documents](DOCUMENTS.md).

## API et preuves

Routes sous `/api/organizations/{organization_id}` :

- `POST /onboarding/proposals` : `request_id`, `language` et `refinement`. Retourne la conversation et le tour mis en file.
- `POST /routines/{proposal_id}/trial` : `request_id`. Retourne l’essai et sa conversation.
- `GET /routines/{proposal_id}/trial?request_id=…` : recherche l’essai du propriétaire sans créer de travail. Retourne `trial: null` si cette demande est absente, ou un conflit si elle correspond à une autre opération.
- `GET /chat/conversations/{conversation_id}` : ajoute `proposals`, `trials` et les `sources` de chaque tour retourné.

Les identifiants de demande sont idempotents au niveau du propriétaire. Réutiliser une demande pour une autre proposition ou un autre message produit un conflit. Une nouvelle tentative dans la même page conserve la demande et ses paramètres en mémoire. Pour les essais, seul l’identifiant opaque est également conservé dans `sessionStorage`, sous une clé propre à l’entreprise et à la proposition personnelle ; les destinataires, l’objet et le contenu ne sont pas stockés par ce mécanisme.

Après rechargement de cet onglet, « Retrouver cet essai » effectue uniquement la lecture du reçu. Une panne de cette lecture ne déclenche aucun nouvel essai. Si aucun reçu n’existe, le formulaire demande une nouvelle revue et conserve le même identifiant, y compris si la première requête arrive tardivement au serveur. Le marqueur est retiré après réception confirmée du résultat de création ou de récupération. Cette protection dépend de la conservation de la session de l’onglet ; l’historique reste le point de reprise si le stockage a été effacé ou l’onglet fermé.

Chaque lecture effectuée par le broker a un reçu `ToolRead`, lié au tour, à l’entreprise et au propriétaire par une clé étrangère composée. Le reçu contient son état et les références retournées par Microsoft, jamais une liste de sources inventée par le modèle. Une lecture interrompue dont le résultat n’est pas confirmé reste en échec. L’état `sources_verified` d’un essai exige à la fois un tour terminé et des lectures réussies pour toutes les sources nécessaires. Une boîte vide reste une lecture valide ; ce statut ne certifie ni la pertinence ni l’exactitude du texte produit. L’interface invite à relire le résultat.

Le modèle ne peut pas choisir le propriétaire, les jetons ou un destinataire externe. L’administrateur ne bénéficie d’aucun accès aux propositions, essais ou références d’un collègue. Les permissions sont revérifiées au lancement et à chaque lecture. Le profil est figé dans le contexte de chaque nouvelle conversation, conformément au cache Hermes ; les outils de planification restent disponibles uniquement dans les conversations d’onboarding.

## Validation et suite

Les tests de contrat utilisent l’API, les migrations, MSAL et SQLite/PostgreSQL réels, avec réponses Microsoft synthétiques. Le test OCI exécute le véritable Hermes dans deux conteneurs successifs : création des propositions puis essai de messagerie. Il vérifie l’enregistrement par le bon outil, le jeton du propriétaire, les sources et l’absence de sources du collègue. Le modèle répond via un serveur HTTP local synthétique.

Le navigateur a été contrôlé sur un aperçu séparé et explicitement fictif : saisie du besoin, cartes, lancement d’un essai, sources et passage anglais/français. Cette vérification visuelle ne constitue pas un test avec Entra, un modèle commercial ou le tenant du pilote.

L’[activation explicite des récurrences](AUTOMATISATIONS.md) est implémentée après revue d’un essai, avec suspension, suivi et droits revérifiés à chaque exécution. La génération de documents et les écritures autorisées disposent de parcours dédiés. Leur validation avec les comptes commerciaux et le déploiement applicatif Infomaniak restent à réaliser.
