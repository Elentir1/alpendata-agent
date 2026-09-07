# Un espace de travail centré sur la discussion

L’assistant regroupe désormais l’historique, la recherche, les archives et les projets dans une seule barre latérale repliable. Le menu d’entreprise donne accès au profil personnel, aux automatisations et à l’administration. Les conversations restent personnelles.

La discussion défile indépendamment du champ de saisie. Entrée envoie, Maj + Entrée insère une ligne ; la composition IME ne déclenche pas d’envoi. Les réponses affichent Markdown, tableaux et blocs de code. Le HTML reste du texte, les images distantes ne sont pas chargées et les liens de réponse acceptent uniquement HTTP/HTTPS. Les téléchargements proviennent des reçus du serveur.

Le volet de travail donne accès aux livrables de la discussion, à la mémoire personnelle, aux connexions, aux choix d’autonomie et aux premiers essais d’automatisation. Les cartes proposent des messages modifiables ; cliquer ne déclenche ni exécution, ni envoi de mail, ni programmation récurrente. Une recherche dans l’historique conserve le brouillon de la discussion ouverte.

## Capacités réellement raccordées

| Usage | Mécanisme | Accès dans l’application |
| --- | --- | --- |
| Conversations suivies | AIAgent, SessionDB, historique canonique et compression Hermes | Discussion et historique |
| Préférences et notes privées | Outil mémoire et fichiers MemoryStore personnels | Volet Mémoire |
| Méthodes réutilisables | `skills_list`, `skill_view`, `skill_manage` Hermes | Apprendre ma méthode / Retrouver mes méthodes |
| Travail en plusieurs étapes | `todo_list`, fichiers et terminal dans le conteneur personnel | Analyser et décider ; synthèse du plan par l’agent |
| Documents Word, Excel, PowerPoint, PDF | Outils locaux de génération et publication par le broker | Créer un livrable / volet Livrables |
| Lecture mails, calendrier et SharePoint | Outils Microsoft avec droits personnels vérifiés à chaque appel | Connexions ; nouvelle discussion après un nouvel accès |
| Préparation et envoi de mails | Reçus privés, confirmation ou autonomie explicitement choisie | Brouillon de mail ; volet Autonomie |
| Travail récurrent | Essai vérifié, activation utilisateur, ordonnanceur AlpenData | Volet Routines / Automatisations |
| Ressources d’entreprise | Publication et accès par destinataires | Mon espace / partage d’un document |

Les nouvelles conversations sont en révision d’outils **6**. Les conversations antérieures et les occurrences planifiées gardent leurs outils ; leur contexte n’est pas réécrit. Les compétences et le plan de travail sont activés pour les nouvelles discussions interactives. Les méthodes sont stockées sous le volume personnel `.hermes/skills` ; elles ne constituent pas une permission d’accès supplémentaire.

La création, la lecture, la persistance, la reprise du préfixe de conversation et l’isolation entre propriétaires sont exercées dans `test_personal_skills.py` avec un vrai conteneur. Les scénarios navigateur ordinateur/mobile sont dans `alpendata/frontend/e2e/chat.spec.ts` ; ils utilisent des données fictives et complètent les essais API/PostgreSQL/runtime.

## Ce qui reste à raccorder pour couvrir davantage d’Hermes

Cette version n’expose pas toutes les possibilités du produit Hermes amont. Les priorités suivantes nécessitent des parcours et des adaptateurs réels :

1. Pièces jointes directement dans le chat et bibliothèque visuelle de méthodes, avec lecture, édition et suppression explicites.
2. Recherche web et navigateur isolé : exécution distante contrôlée, reçus des actions et interruptions accessibles depuis le chat.
3. Agents délégués : budgets et annulation des sous-tâches, propagation des droits personnels et restitution de leur travail.
4. Connecteurs MCP personnels et catalogue d’intégrations : secrets côté serveur, consentement et révocation par utilisateur.
5. Voix, vision et génération d’images : modèles compatibles, stockage et restitution des fichiers.
6. Recherche sémantique de l’historique et contexte documentaire propre aux projets.

Le terminal hôte, les clés du fournisseur et les volumes d’autres utilisateurs ne deviennent jamais des fonctionnalités de l’agent. Les capacités supplémentaires doivent passer par son conteneur personnel et les adaptateurs appropriés.

## Vérification locale du navigateur

Depuis `alpendata/frontend`, construire avec `npm run build`, puis lancer `npm run test:browser`. Installer Chromium avec Playwright, ou définir `ALPENDATA_TEST_BROWSER` vers un navigateur Chromium local. Les captures sont écrites dans `test-results`, exclu de Git. Les tests unitaires restent accessibles avec `npm test`. Les tests Python doivent passer par `scripts/run_tests.sh` comme indiqué dans le guide du dépôt.
