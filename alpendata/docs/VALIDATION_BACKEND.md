# Vérification du premier backend

## Lecture du contenu SharePoint — 6 septembre 2026

La suite complète passe **41 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l’image `sha256:3d58b390f8943cdb18fed899ab9d79f4dc8238290134ea7f12a2dc4934e525d2`. Le frontend passe ses **15 scénarios JSDOM** et son build TypeScript/Vite. Ruff et le contrôle des espaces passent.

Le nouveau scénario utilise MSAL, l’API et Hermes réels, avec Microsoft Graph et le modèle simulés au niveau HTTP. Hermes recherche un fichier, le télécharge via la connexion de son propriétaire, ouvre réellement le PDF avec pypdf puis le publie sous son nom d’origine. Les octets téléchargés par l’API correspondent à la source ; l’administrateur reçoit un refus. Les requêtes du modèle ne contiennent ni jeton Microsoft ni URL de téléchargement préauthentifiée.

Les tests du broker couvrent les connexions personnelles, la déconnexion, les capacités absentes, les anciennes conversations, les destinations refusées, l’expiration du lien temporaire, le changement d’ETag et les dépassements de taille avant ou pendant le transfert. La migration `0009` est exercée sur les bases temporaires ; elle conserve les anciens outils et fige la nouvelle révision pour les nouvelles conversations. Les essais avec Entra et les fichiers réels du pilote restent à réaliser. Voir [Documents](DOCUMENTS.md).

## Génération documentaire — 6 septembre 2026

La suite complète passe **38 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l’image `sha256:32b95a02d526073ae49c8ca414c99dd454d51f3fd2fb716a9d7d275c6ff7aa85`. Après correction visuelle des styles Word, le parcours documentaire complet est retesté avec succès sur l’image finale `sha256:349e453517fcbbe3fb69cf4fe3804024a1fb74e062dc723a07e534de74f55ad5`.

Le vrai Hermes lit le guide interne puis utilise son terminal pour créer DOCX, PDF, XLSX et PPTX. Les contrôles rouvrent les fichiers avec leurs bibliothèques, modifient du contenu Word et PowerPoint, recalculent une modification Excel avec LibreOffice et vérifient les valeurs/formules conservées. Les rendus comportent une page Word, une page PDF, une page Excel et deux diapositives PowerPoint ; les textes attendus sont extraits. Les quatre fichiers sont ensuite publiés par l’outil et récupérés via l’API avec contrôle de propriété. Aucun fournisseur commercial ou compte Microsoft réel n’intervient dans ce scénario.

Les cinq PNG du dernier rendu ont été inspectés : titres, accents, tableaux et corps de texte lisibles, sans chevauchement constaté. Ces fichiers de contrôle restent hors de Git dans l’espace local de prévisualisation. Le calcul Excel contient aussi une cellule de test commençant par `=` pour vérifier qu’un libellé reste du texte. Les sorties de contrôle ne sont pas des documents du client pilote.

Le premier essai a détecté le choix du Python système par le terminal ; le guide utilise désormais explicitement `/opt/venv/bin/python`. Le guide et les bibliothèques sont embarqués, sans dépendance au poste utilisateur. Ruff et la vérification des espaces passent. Voir [Documents](DOCUMENTS.md) pour la portée et les limites.

## Documents privés — 6 septembre 2026

Après la migration `0008`, la suite complète passe **36 scénarios sous Linux/PostgreSQL avec l’image `sha256:acbd8d15b9c59a97425671e677fcae5714ac05ddc0b93f48e853eb2cf22158e8`**, sans échec ni scénario ignoré. Un contrôle supplémentaire des conteneurs Office et des tailles a ensuite été ajouté ; les deux tests du fichier documents passent sous Windows/SQLite. Le frontend passe **15 scénarios JSDOM** et son build TypeScript/Vite.

Le nouveau parcours exécute le vrai Hermes sans connexion Microsoft : création d’un PDF de test dans le terminal, refus des chemins sortants et liens symboliques, publication idempotente, conservation des octets et téléchargement réservé au propriétaire. Les autres tests vérifient la continuité après interruption, les refus d’accès, les noms, les types et les plafonds. Les réponses de modèle restent synthétiques. Les paquets Office du test vérifient uniquement le contrôle de format ; les exemples métier et leur rendu restent à produire.

Le build a été contrôlé dans un navigateur sur un aperçu séparé explicitement fictif : bloc du document, nom, taille, téléchargement indisponible et changement anglais/français. Aucune erreur JavaScript observée. Cet aperçu a été fermé et arrêté. La base de prévisualisation normale a été sauvegardée et migrée en `0008`, puis l’API redémarrée. La route de téléchargement est présente ; Microsoft et SMTP restent correctement annoncés comme non configurés.

Le périmètre et les limites sont décrits dans [Documents](DOCUMENTS.md). L’historique des vérifications précédentes suit ci-dessous.

5 septembre 2026. Périmètre : `alpendata/backend`, migrations `0001` à `0004`.

## Résultats

| Environnement | Résultat du lanceur officiel |
|---|---|
| Windows, Python 3.11.15, SQLite | 14 réussites, 0 échec, 4 scénarios Linux ignorés. |
| Debian 13 sous WSL, Python 3.13.5, PostgreSQL 17.11 | 18 réussites, 0 échec, aucun scénario ignoré, avec l’image runtime fournie. |
| Ruff | Aucun problème de lint restant. |

Les dépendances des deux environnements sont issues du même `uv.lock`. Les tests passent par `scripts/run_tests.sh`, qui crée les processus de test avec un environnement nettoyé. Chaque scénario reconstruit une base temporaire à partir des migrations et vérifie leur cohérence avec les modèles SQLAlchemy.

Le premier passage PostgreSQL a détecté un problème de comparaison des contraintes sans nom explicite. Les contraintes ont reçu des noms stables dans les modèles et la migration initiale ; les passages suivants sont réussis. La migration initiale n’avait pas été publiée ni appliquée à une base client.

## Comportements exercés

- Un membre ne peut pas lire les ressources d’une autre entreprise.
- Un administrateur ne peut ni lire, ni lister, ni supprimer les contenus privés d’un collègue.
- L’invitation crée un onboarding neuf, sans copie des réponses de l’administrateur.
- Les invitations expirent et se révoquent ; leur acceptation est liée à une adresse vérifiée et ne se répète pas.
- Deux demandes simultanées pour la dernière place ne créent qu’une invitation ; deux acceptations simultanées du même lien ne créent qu’un membre.
- Les changements de licence, la désactivation d’un membre et la révocation d’une session sont appliqués aux appels suivants.
- Le navigateur qui commence la connexion Microsoft est le seul à pouvoir la terminer ; une tentative consommée ne peut être rejouée.
- L’échange MSAL emploie PKCE et nonce. Les erreurs de nonce, audience, émetteur ou expiration ne créent ni utilisateur ni session.
- Un changement d’adresse ne change pas l’identité ; un compte portant la même adresse dans un autre annuaire ne fusionne pas avec elle.
- Les mutations par cookie demandent l’origine attendue. La déconnexion invalide aussi une copie du jeton opaque.

## Limites de cette preuve

Microsoft est simulé au niveau HTTP dans les tests. La bibliothèque MSAL, le chiffrement, l’API et les bases sont réels. Aucun compte client, consentement Entra ou jeton Microsoft réel n’a été utilisé.

Les invitations exigent désormais une preuve envoyée à la boîte destinataire, liée au compte connecté et à l’invitation. Les scénarios exercent cette preuve avec des messages capturés en mémoire ; un scénario distinct utilise un véritable serveur SMTP TLS local, sans relais externe. Le certificat non approuvé est refusé, et une coupure simulée après envoi invalide la preuve. Le relais de production reste à valider. L’écran de confirmation est implémenté et vérifié séparément dans les tests JSDOM de l’interface ; le parcours navigateur avec les services réels reste à valider. Ces scénarios d’API ne constituent pas à eux seuls une preuve d’isolation des processus Hermes. Le scénario conteneurisé ajouté ensuite est décrit ci-dessous ; son raccordement au chat web reste à réaliser.

Le démon Docker Desktop local a rencontré une erreur d’accès à son socket de démarrage. Les tests PostgreSQL ont donc été réalisés dans Debian avec des serveurs temporaires accessibles par socket Unix privé, sans modifier ni réinitialiser les données Docker existantes.

La procédure reproductible est décrite dans le [README du backend](../backend/README.md). Aucun déploiement Infomaniak n’a été réalisé à ce stade.

Après ajout des lectures administrateur (noms des membres et invitations en attente) et du retour HTML après interruption de connexion, les deux fichiers de tests concernés ont de nouveau passé 7 scénarios sous Windows et PostgreSQL Linux. Les lectures restent refusées aux collaborateurs et ne renvoient pas de jetons.


Les connexions Microsoft 365 sont exercées avec MSAL réel et des transports HTTP Microsoft/Graph synthétiques : consentement limité aux choix, identité identique au compte connecté, cache chiffré par propriétaire, lecture avec le bon jeton, refus des accès non accordés, recherche de métadonnées, absence de suivi des redirections/pagination, limitation de débit, renouvellement du cache et révocation. Une panne temporaire du service de jetons conserve le consentement. Un scénario PostgreSQL bloque l’échange de code pendant qu’une déconnexion réelle via l’API intervient ; son retour ne peut pas réactiver les jetons.

L’interface dispose de sept scénarios JSDOM réussis et d’un build TypeScript/Vite réussi. Cela vérifie ses appels et son rendu DOM, pas sa présentation dans un navigateur réel ni le consentement sur le tenant du pilote.


## Runtime Hermes réel

Le test `test_hermes_turn_tools_private_memory_and_network_isolation` utilise Podman 5.4.2 sans privilèges, Python 3.13.15 dans l’image et le véritable `AIAgent` du fork. Les réponses du modèle et les données de l’outil métier sont synthétiques ; la boucle agent, les outils mémoire/terminal et les frontières Linux ne sont pas remplacés par des mocks.

Le parcours a exécuté trois conteneurs successifs : un premier tour avec mémoire et outils, une reprise de la même conversation, puis un espace d’un autre collaborateur. Le contexte système de la conversation reprise reste identique. La commande dans l’agent constate UID 1000, aucun accès au fichier témoin de l’hôte ni à celui du collègue, aucun socket Docker et aucun accès au réseau externe. Le souvenir est présent chez son propriétaire et absent des requêtes du collègue. Un verrou refuse deux ouvertures concurrentes du même état.

Un second scénario utilise un vrai sous-processus pour envoyer une opération de protocole inconnue ; le superviseur doit la refuser avant tout appel de passerelle. Les tests conteneurisés sont explicitement ignorés sous Windows. La qualité métier des réponses, les appels de modèles réels, les droits pendant le chat et la reprise opérationnelle après panne restent à valider lors du raccordement des services.

Image locale validée : `sha256:4effe246aa67dc093879815d84adba886fd9a2ec0568a9c50ac9bd7bc20de522`. La suite complète PostgreSQL et runtime a passé 18 scénarios, sans échec ni scénario ignoré, via le lanceur officiel. Les tests d’interface existants ne sont pas modifiés par cette étape.

## Passerelle de modèles — 6 septembre 2026

Après l’ajout de `ModelGateway`, la suite complète passe **23 scénarios sous Linux avec PostgreSQL et conteneurs réels**, sans échec ni scénario ignoré. Sous Windows, 19 scénarios passent et les quatre scénarios Linux sont explicitement ignorés. Ruff et la vérification des espaces Git passent également.

Les cinq nouveaux scénarios vérifient les appels de modèles sur un serveur HTTP local : destination imposée, clé serveur, refus des outils externes et contenus distants, budgets de sortie, routage OpenRouter, erreurs nettoyées, absence de suivi des redirections et de nouvelles tentatives, plafonds de réponse, consommation inconnue et conservation du raisonnement lors des appels d’outils. Le premier tour du test Hermes utilise désormais cette passerelle et vérifie les compteurs de chaque appel, y compris le titrage. Les réponses restent synthétiques ; aucune clé de fournisseur réelle n’a été utilisée. L’image du runtime est inchangée.

Les conversations durables et leur raccordement aux droits Microsoft, au navigateur et au registre de consommation restent la prochaine étape. La passerelle seule n’active pas un chat utilisable par le pilote.

## Chat personnel — 6 septembre 2026

La migration `0005`, les conversations, la file de travail et les relevés de modèle sont implémentés. La suite complète passe **27 scénarios sous Linux/PostgreSQL avec l’image finale**, sans échec ni scénario ignoré. Sous Windows, 21 scénarios passent et six scénarios Linux sont explicitement ignorés. Ruff et la vérification Git passent.

Image finale validée : `sha256:e3059ff1ccf7c8d9274e2a71fc70142fb274f2a3c989db445f2aa1b16eb54649`. Le contexte est désormais restauré directement depuis SessionDB. Le titrage secondaire Hermes est désactivé, puisque la projection AlpenData nomme la conversation à partir du premier message.

Les nouveaux scénarios vérifient la propriété et les clés étrangères composées, l’envoi idempotent, l’annulation, le profil de conversation figé, l’accès sans licence à son historique et le refus après désactivation. Deux soumissions et deux réclamations simultanées sur PostgreSQL aboutissent à une seule exécution. Un bail expiré devient une interruption, sans remise en file et sans inventer la consommation absente.

Le scénario complet remplace l’API après mise en file, puis exécute Hermes dans trois conteneurs successifs. La lecture utilise le jeton Microsoft du propriétaire et reste inaccessible à l’administrateur. Une reprise conserve le contexte ; la déconnexion interdit la nouvelle lecture. Une annulation pendant l’appel de modèle conserve sa consommation confirmée mais ne livre pas la réponse. Une désactivation avant exécution empêche tout nouvel appel de modèle. Microsoft, Graph et les réponses de modèle restent synthétiques ; l’API, PostgreSQL, MSAL, le serveur HTTP de modèle et le runtime sont réels.

Le frontend passe dix scénarios JSDOM et sa compilation TypeScript/Vite. Un aperçu séparé du build, explicitement signalé comme fictif, a été contrôlé dans le navigateur intégré : présentation de la conversation, envoi et changement français/anglais, sans erreur JavaScript observée. Ce serveur de vérification a ensuite été arrêté. L’API locale normale a été migrée et redémarrée ; ses routes de chat sont présentes et elle annonce correctement que Microsoft et SMTP ne sont pas configurés. Aucun compte pilote ou modèle commercial réel n’a été connecté.

## Propositions et essais personnels — 6 septembre 2026

La suite complète passe **29 scénarios sous Linux/PostgreSQL avec des conteneurs réels**, sans échec ni scénario ignoré. Sous Windows, 22 scénarios passent et sept scénarios Linux sont ignorés. Le frontend passe **12 scénarios JSDOM** et sa compilation TypeScript/Vite. Ruff passe également.

Image utilisée : `sha256:6f706d2d9556dfcbb4cdf8927fdfc9621cdddbbac655ec1007a75f8949fc9730`. L’extension Hermes enregistre réellement ses propositions via un outil propre à l’onboarding ; un deuxième conteneur exécute l’essai de messagerie. Le modèle et Microsoft répondent avec des données synthétiques. Les tests vérifient le profil obligatoire, la propriété des propositions et essais, les tentatives idempotentes, les recettes incompatibles avec les permissions, la déconnexion et les sources provenant du bon compte. Une affirmation du modèle sans lecture ne permet pas de vérifier un essai.

Le contrôle ajouté ensuite pour refuser un onboarding sans propositions enregistrées a été vérifié séparément sur les scénarios concernés. Les pages compilées ont été parcourues dans un aperçu local explicitement fictif : saisie du besoin, cartes, essai, références et changement anglais/français ; aucune erreur JavaScript observée. L’aperçu fictif a été fermé et arrêté. La base de prévisualisation normale a été sauvegardée, migrée en `0006`, puis son API redémarrée. Aucun service commercial réel ni compte pilote n’a été connecté.

Le [document du premier résultat](PREMIER_RESULTAT.md) décrit les limites, notamment la lecture de métadonnées de fichiers et l’absence actuelle d’activation récurrente.

## Automatisations personnelles — 6 septembre 2026

La suite complète passe **34 scénarios sous Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l’image `sha256:4031b65db47e83b5216fc4d0b882472c351221da012590006be02868a8e30fa0`. Elle couvre désormais deux activations et deux tickers concurrents, les changements d’heure suisses, les récurrences, leur suspension et les occurrences manquées. Les contrôles ajoutés pour le nouvel essai, la réactivation, l’édition et le retrait de licence ont également passé les tests concernés. Le frontend passe **14 scénarios JSDOM** et sa compilation TypeScript/Vite ; Ruff passe.

Le test complet Hermes exécute successivement la proposition, l’essai et l’occurrence planifiée dans trois conteneurs réels. L’occurrence consulte la messagerie du bon propriétaire ; l’administrateur ne peut pas voir son historique. Un vrai sous-processus avec des pipes vérifie que l’attente du broker n’empêche pas le respect du délai du contrôleur. Les appels Microsoft et modèle restent synthétiques.

Le build a été contrôlé dans le navigateur sur une démonstration locale signalée comme fictive : case de revue, activation, prochain horaire affiché, gestion des automatisations, historique, suspension et changement français/anglais. Aucune erreur JavaScript observée. Cette démonstration ne valide pas une exécution à heure réelle sur les services du client. Les exercices de production et le déploiement Infomaniak restent à réaliser.
