# Séquence d’implémentation AlpenData

5 septembre 2026 — séquence fondée sur les dépendances du produit, sans estimation de budget ou de délai.

## Lot 0 — Base du fork et architecture

État : fork GitHub créé, copie locale et branche AlpenData préparées ; audit initial réalisé ; architecture proposée. Les documents et le premier code AlpenData sont publiés sur la branche `alpendata/main` du fork.

Résultats : révision d’origine enregistrée, diagnostic reproductible, principaux composants à réutiliser et adaptations identifiés.

## Lot 1 — Identités et isolation

État : identités, invitations avec preuve de boîte mail, licences locales et onboarding individuel implémentés. Les conversations durables sont reliées à l’interface, à la passerelle Mistral/OpenRouter et au véritable Hermes dans des conteneurs personnels. Les tests PostgreSQL vérifient la propriété, l’envoi concurrent, les interruptions et la consommation. La reprise conserve le contexte système et les droits sont revérifiés à l’exécution. Entra, SMTP et les modèles commerciaux réels, ainsi que la récupération opérationnelle des conteneurs orphelins, restent à valider : ce lot reste en cours.

- Créer l’API AlpenData, les entreprises, les utilisateurs, les membres et les invitations.
- Préparer un environnement Hermes neuf par utilisateur, sans copie de connexions ou de mémoires personnelles.
- Implémenter l’autorisation des ressources et la passerelle d’accès aux agents.
- Valider le flux de conversation structuré avec une instance réelle d’Hermes.
- Vérifier les accès croisés entre deux utilisateurs d’une entreprise et un utilisateur d’une autre entreprise, ainsi que le rôle administrateur.

Sortie attendue : un utilisateur authentifié parle à son agent, retrouve son historique et ne peut atteindre celui d’un autre, au niveau API et exécution Linux.

## Lot 2 — Connexion Microsoft personnelle

État : consentement, coffre, renouvellement, déconnexion et premières lectures implémentés. Les scénarios SQLite/PostgreSQL utilisent MSAL réel avec HTTP simulé. L’interface permet de choisir les accès et de vérifier mails, agenda ou métadonnées de fichiers. L’enregistrement Entra, les droits SharePoint réels et la lecture du contenu des fichiers restent à terminer.

- Enregistrer l’application Microsoft et ses URL de retour sur les environnements de développement puis de test.
- Implémenter le consentement individuel, le coffre de jetons, le renouvellement et la déconnexion.
- Ajouter lecture d’e-mails, agenda et recherche/lecture SharePoint avec les permissions nécessaires.
- Vérifier les droits divergents sur SharePoint et les cas de consentement administrateur requis.

Sortie attendue : deux collaborateurs utilisent leurs propres connexions ; la déconnexion de l’un n’affecte pas celle de l’autre.

## Lot 3 — Première expérience AlpenData

État : interface React/Vite compilée avec quatorze scénarios JSDOM réussis. Connexion, invitations, onboarding, outils personnels et chat sont reliés à l’API. Le chat dispose de l’historique, de l’envoi idempotent et de l’arrêt ; son rendu a été contrôlé dans un navigateur sur des données fictives. Aucun résultat IA n’est simulé dans l’application. Les propositions personnalisées et les essais explicites avec sources sont implémentés et testés avec Hermes réel et des réponses externes synthétiques. La planification après essai est implémentée. Le parcours complet avec Entra, Graph et un modèle commercial reste à valider.

- Extraire et appliquer les éléments visuels de la marque.
- Créer les écrans en français et anglais et l’onboarding combinant questions et conversation.
- Produire deux ou trois propositions réalisables à partir des permissions réellement disponibles.
- Lancer un premier usage de lecture et montrer ses sources ; proposer sa planification.

Sortie attendue : parcours complet depuis l’invitation jusqu’à un premier briefing personnalisé, sans terminal ni clé API pour l’utilisateur.

## Lot 4 — Documents et actions

- Produire des fichiers Word, Excel, PowerPoint et PDF avec un premier exemple représentatif de chaque format.
- Ajouter téléchargement, destination SharePoint et gestion des collisions de noms.
- Ajouter brouillons et envoi d’e-mails sous permissions et validations explicites.
- Vérifier les résultats incertains, interruptions et reprises pour prévenir les doublons.

Sortie attendue : chaque livrable est ouvert et vérifié dans le format attendu ; les écritures utilisent la connexion et les droits du propriétaire.

## Lot 5 — Automatisations et exploitation

État : récurrences personnelles, historique, modification d’horaire, suspension et reprise implémentés. Les tests couvrent PostgreSQL concurrent et Hermes réel avec des services externes synthétiques. Notifications, restauration, récupération opérateur et exploitation Infomaniak restent à réaliser.

- Ajouter suivi des exécutions, reprise, suspension et notifications utiles.
- Utiliser l’autorité unique de planification PostgreSQL et la file Hermes, conformément à la décision documentée dans [Automatisations](AUTOMATISATIONS.md).
- Tester sauvegardes, restauration, désactivation d’un membre et mises à jour du fork.
- Évaluer avec le pilote les éléments utiles à un tableau de bord.

Sortie attendue : les automatisations restent compréhensibles et contrôlables, avec erreurs visibles et droits revérifiés à l’exécution.

## Lot 6 — Commercialisation

- Définir licence en CHF, consommation incluse, surusage, plafonds et règles de cycle de vie.
- Implémenter Stripe et le provisionnement correspondant ; tester les paiements sans facturation réelle.
- Finaliser le traitement des données, leur conservation et les modalités d’accès exceptionnel du support.
- Exécuter les critères d’acceptation du cahier des charges avec le client pilote.

Sortie attendue : activation des utilisateurs et facturation cohérentes, et parcours métier validés avant ouverture commerciale.

## Décisions encore nécessaires au moment approprié

- Environnements Infomaniak et nom de domaine de l’application.
- Enregistrement Microsoft et comptes de test ; éventuels consentements de l’organisation.
- Fournisseurs/modèles IA et destinations de traitement retenus.
- Tarifs et règles de conservation.

Ces éléments ne bloquent pas le travail local sur le lot 1. Aucun identifiant secret ne doit être inscrit dans ces documents ou dans Git.
