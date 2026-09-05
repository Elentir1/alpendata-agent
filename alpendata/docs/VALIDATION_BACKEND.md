# Vérification du premier backend

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
