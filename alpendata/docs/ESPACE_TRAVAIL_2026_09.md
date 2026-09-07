# Refonte de l’espace de travail AlpenData

Implémentation en cours du plan validé le 7 septembre 2026. Ce document décrit le code de cette branche, pas les fonctions déjà activées sur `agent.alpendata.ch`. La facturation existante reste indépendante.

## Fonctionnement implémenté

- Discussions privées, favoris, classement, archives, export, liens directs, brouillons persistants et variantes. Une variante copie le texte visible et la version courante des pièces jointes personnelles dans des fichiers indépendants ; elle ne copie pas les appels d’outils ni les autorisations d’actions passées. Le projet utilisé comme contexte reste celui de la discussion d’origine, même si son classement a changé.
- Recherche contextualisée dans les discussions personnelles, leurs fichiers analysés, les publications et documents des projets accessibles. Les résultats montrent un extrait ; les droits sont vérifiés à chaque requête.
- Suppression logique des discussions : accès bloqué, travaux interrompus et routines dépendantes désactivées. Les branches et publications indépendantes restent disponibles. Les objets et justificatifs sont conservés ; ce parcours ne constitue pas une purge physique.
- Événements persistants avec reprise SSE, réponse progressive, suivi des travaux et boîte « À suivre ». Une exécution active par branche, au plus trois par personne, avec une capacité réservée à l’analyse documentaire. Les discussions récentes utilisent des répertoires et verrous distincts ; les anciennes gardent leur mode de sérialisation.
- Projets privés, membres lecteurs ou contributeurs, notes et publications explicites. Une discussion classée dans un projet reste privée. Une publication textuelle ou documentaire produit une copie indépendante ; les identifiants personnels ne sont pas partagés.
- Préférences et méthodes personnelles consultables, modifiables et supprimables. Une méthode peut être publiée volontairement dans un projet. Les anciennes notes personnelles ne deviennent pas des connaissances de projet.
- Dépôt privé de PDF, DOCX, XLSX, PPTX, PNG, JPEG, CSV, Markdown et texte UTF-8 ; analyse dans un conteneur sans réseau ; références de pages, feuilles, diapositives ou lignes. Limites actuelles : 5 Mo par fichier et 500 Mo de versions par propriétaire. Les analyses incomplètes sont identifiées.
- Versions documentaires immuables, restauration dans une nouvelle version, édition de texte, comparaison bornée des passages extraits et sessions Collabora WOPI signées. La comparaison textuelle ne garantit pas une mise en page identique. L’importation d’un livrable dans une discussion est idempotente. Une édition concurrente ne remplace pas silencieusement une autre version. Les documents publiés sont accessibles selon les droits du projet ; une révocation bloque les prochains téléchargements et sauvegardes d’une session ouverte.
- Connexions Infomaniak personnelles : IMAP/SMTP, CalDAV, lecture et enregistrement kDrive WebDAV avec destination et remplacement explicitement validés. Les autorisations de calendrier et les propositions de rendez-vous utilisent un reçu persistant, un contrôle de version et un état incertain qui interdit la répétition automatique.
- Le choix des premières tâches peut utiliser explicitement l’un des comptes personnels connectés. Les essais et occurrences conservent le fournisseur, le projet et les réglages de leur modèle.
- Avis facultatifs sur les résultats (utile, à corriger, pas utile), agrégats administrateur sans contenu des échanges et mesure du délai jusqu’au premier résultat signalé utile. L’absence de résultat signalé après sept jours est un indicateur, pas une preuve d’abandon. Les anciens utilisateurs ne reçoivent pas de dates inventées.
- Recherche Brave et consultation HTTPS avec contrôle des adresses publiques, connexion à l’adresse IP vérifiée et analyse HTML dans un conteneur sans réseau. Aucun navigateur connecté au compte du client n’est utilisé pour cette recherche.
- Délégation Hermes limitée à deux tâches spécialisées par appel, deux appels par travail, avec les mêmes permissions que l’agent principal. Les étapes sont visibles ; le raisonnement interne n’est pas publié.
- Lecture d’images par un modèle Mistral configuré et dictée vers un texte modifiable avant insertion. Le fournisseur et le modèle spécialisé sont identifiés. L’audio brut de dictée n’est pas persisté par l’application ; le résultat textuel est conservé pour une reprise après déconnexion. Aucune transcription ne déclenche l’envoi d’un message.

## Configuration avant activation

| Réglage | Effet |
| --- | --- |
| `ALPENDATA_WORKSPACE_ORGANIZATIONS` | Identifiants d’entreprises séparés par des virgules, ou `*`. Sélectionne la nouvelle interface ; vide conserve l’interface précédente. Ce réglage de livraison ne remplace pas les contrôles d’accès des API. |
| `ALPENDATA_FILE_STORE_ROOT` | Répertoire privé local pour les objets, si Swift n’est pas configuré. Par défaut : sous-répertoire `objects` de l’état du moteur. |
| `ALPENDATA_SWIFT_CONTAINER_URL`, `ALPENDATA_SWIFT_TOKEN` | Conteneur Swift HTTPS privé et jeton opérateur. La rotation du jeton doit être organisée avant exploitation. |
| `ALPENDATA_OFFICE_ORIGIN`, `ALPENDATA_OFFICE_SECRET` | Origine HTTPS du serveur Collabora CODE et secret de signature WOPI d’au moins 32 caractères, conservé uniquement dans l’API. Le service doit être disponible et son origine autorisée dans la configuration d’entrée HTTP avant activation. Voir [COLLABORA_CODE.md](COLLABORA_CODE.md). |
| `ALPENDATA_BRAVE_API_KEY` | Active le service de recherche. Le choix est figé pour chaque nouvelle discussion et reste soumis aux sources autorisées. |
| `ALPENDATA_VISION_MODEL` | Identifiant du modèle Mistral de lecture d’images. Une modification du modèle demande une nouvelle discussion ou variante compatible. |
| `ALPENDATA_TRANSCRIPTION_MODEL` | Identifiant du modèle de transcription Mistral. Laisser vide masque la dictée. |
| `ALPENDATA_MISTRAL_SPECIALIST_KEY` | Clé Mistral réservée aux fonctions spécialisées, si nécessaire. Sinon, la clé du modèle principal est réutilisée uniquement lorsque son fournisseur est Mistral. |

Ne jamais transmettre ces secrets au navigateur ou au conteneur Hermes. Les paramètres Microsoft, les règles de l’entreprise et les autorisations personnelles continuent de s’appliquer séparément.

## Migration et exploitation

Les migrations `0024` à `0040` ajoutent branches, événements, partages, versions, connexions Infomaniak et résultats des modèles spécialisés. Les préfixes système des conversations existantes restent inchangés. Une migration d’une base déjà remplie est testée ; les notes personnelles ne sont pas publiées par la migration.

Une sauvegarde cohérente inclut la base, les états des anciennes discussions, les états isolés des nouvelles et les objets référencés par les versions documentaires. La restauration désactive les sessions, connexions, routines et écritures incertaines. Les objets Swift restaurés sont matérialisés dans le stockage local isolé : configurer explicitement la destination de stockage avant une remise en service.

Avant de lancer des exécutions avec une nouvelle image, l’initialiser **sous le compte du service** :

```sh
python -m alpendata_api.runtime_prepare --image sha256:IDENTIFIANT_COMPLET
```

Cette commande vérifie le démarrage avec le même espace d’identités utilisateur que le moteur, sans réseau ni montage de fichiers. L’initialisation initiale de Podman peut prendre plusieurs minutes et doit précéder l’admission des travaux. Elle ne doit pas être déplacée dans le délai d’une demande utilisateur.

Le retour à l’interface précédente utilise les composants conservés dans `frontend/src/legacy`, avec le backend et le schéma actuels. Une rétrogradation destructrice de la migration des projets est refusée : elle ne pourrait pas représenter les nouvelles appartenances et discussions privées de plusieurs propriétaires.

## Recette et travaux restant à terminer

Les tests locaux et l’environnement QA Linux utilisent de véritables bases, transports HTTP, conteneurs et outils Hermes avec des comptes et réponses fournisseurs synthétiques. Cela ne remplace pas une recette de bout en bout sur les comptes Microsoft 365 et Infomaniak du pilote.

Le relais réel Mistral a été testé avec `zai-glm-5-2` et un message synthétique : cinq mises à jour, premier texte en environ 0,35 seconde et compteurs d’usage reçus. Les adaptateurs spécialisés ont aussi été testés réellement : `mistral-small-2603` a identifié une image verte synthétique et `voxtral-mini-2602` a transcrit une phrase anglaise produite localement. Aucun document ni audio client n’a été utilisé. Ces mesures ponctuelles ne constituent pas un engagement de latence ou une recette de documents métier complexes.

Validation du socle : 132 tests Linux réussis, aucun échec, six tests ignorés pour des conditions environnementales distinctes ; 97 tests Windows réussis, 41 tests Linux exclus sur cet hôte. Les dernières corrections d’invitations CalDAV et d’import idempotent ont ensuite passé neuf tests ciblés sur PostgreSQL. L’interface passe 54 tests et les deux parcours navigateur ordinateur/mobile, incluant le brouillon après rechargement, le feedback et la suppression confirmée. Le build TypeScript/Vite réussit.

Restent notamment à terminer et valider avant de déclarer les quatre lots complets :

- déploiement durable de Collabora CODE pour le pilote, fichiers Office métier complexes et application des révisions à une sélection dans l’éditeur ; ouverture/sauvegarde des trois formats, capture vers le brouillon et conflits Word sont validés sur le vrai CODE en QA ;
- stockage objet Infomaniak configuré avec renouvellement d’accès opérationnel et vérification des ACL privées ; le stockage privé local du serveur sert actuellement de repli ;
- écritures et invitations réelles d’agenda, messagerie et fichiers sur les deux comptes de test ; une création CalDAV avec participants exige l’organisateur découvert sur le compte, sans supposer que l’identifiant de synchronisation est une adresse e-mail ;
- activation de Brave et recette Web réelle ; validation de la vision et dictée sur des cas métier FR/EN après leurs essais techniques réussis ;
- règles de rétention et cycle de purge physique, en conservant les copies explicitement publiées et les preuves d’actions nécessaires ;
- activation pilote puis recette des trois parcours du plan avec les coachs et AlpenData.

L’acquisition ONLYOFFICE est suspendue au profit de [Collabora CODE](COLLABORA_CODE.md), choisi par le propriétaire et testé sur QA. Les comptes de test sont disponibles côté propriétaire ; leur connexion et la recette suivent [RECETTE_PILOTE.md](RECETTE_PILOTE.md).

Le dernier contrôle de concurrence a également passé trois tests Linux : un document déposé est analysé par son vrai conteneur alors que les trois places de discussion sont occupées ; le cycle de démarrage et d’arrêt du service reste valide.

Complément Collabora CODE : huit contrôles de découverte/configuration, les scénarios WOPI et de révocation projet, cinq contrôles de fichiers privés/migrations/restauration et deux recettes réelles de navigateur passent. Les recettes ouvrent et sauvegardent DOCX, XLSX et PPTX en anglais sur ordinateur et en français sur mobile, puis relisent les contenus. La sélection Word et la copie après modification concurrente sont vérifiées avec le vrai serveur Collabora. Le build et les 54 tests d’interface restent valides.

Le code et les tests seuls ne justifient pas encore une activation générale.
