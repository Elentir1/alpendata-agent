# Séquence d’implémentation AlpenData

5 septembre 2026 — séquence fondée sur les dépendances du produit, sans estimation de budget ou de délai.

## Lot 0 — Base du fork et architecture

État : fork GitHub créé, copie locale et branche AlpenData préparées ; audit initial réalisé ; architecture proposée. Les documents et le premier code AlpenData sont publiés sur la branche `alpendata/main` du fork.

Résultats : révision d’origine enregistrée, diagnostic reproductible, principaux composants à réutiliser et adaptations identifiés.

## Lot 1 — Identités et isolation

État : identités, invitations avec preuve de boîte mail, licences locales et onboarding individuel implémentés. Les conversations durables sont reliées à l’interface, à la passerelle Mistral/OpenRouter et au véritable Hermes dans des conteneurs personnels. Les tests PostgreSQL vérifient la propriété, l’envoi concurrent, les interruptions et la consommation. La reprise conserve le contexte système et les droits sont revérifiés à l’exécution. Entra, SMTP et les modèles commerciaux réels, ainsi que la récupération opérationnelle sur Infomaniak, restent à valider : ce lot reste en cours.

- Créer l’API AlpenData, les entreprises, les utilisateurs, les membres et les invitations.
- Préparer un environnement Hermes neuf par utilisateur, sans copie de connexions ou de mémoires personnelles.
- Implémenter l’autorisation des ressources et la passerelle d’accès aux agents.
- Consultation, correction et retrait de la mémoire active depuis l'interface : implémentés, sans accès administrateur aux contenus des collaborateurs. Voir [Mémoire personnelle](MEMOIRE_PERSONNELLE.md).
- Valider le flux de conversation structuré avec une instance réelle d’Hermes.
- Vérifier les accès croisés entre deux utilisateurs d’une entreprise et un utilisateur d’une autre entreprise, ainsi que le rôle administrateur.

Sortie attendue : un utilisateur authentifié parle à son agent, retrouve son historique et ne peut atteindre celui d’un autre, au niveau API et exécution Linux.

## Lot 2 — Connexion Microsoft personnelle

État : consentement, coffre, renouvellement, déconnexion et lectures implémentés, y compris le contenu des fichiers SharePoint dans l’espace privé d’Hermes. Les scénarios SQLite/PostgreSQL utilisent MSAL réel avec HTTP simulé. L’interface permet de choisir les accès et de vérifier mails, agenda ou métadonnées de fichiers. L’enregistrement Entra et les droits SharePoint réels restent à valider.

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

Les [copies partagées d’entreprise](RESSOURCES_ENTREPRISE.md) sont implémentées : publication volontaire de notes et documents par les membres, y compris depuis leurs documents créés dans le chat, destinataires explicites, versions, retrait et lecture par Hermes sous les droits actuels du propriétaire. Elles n’exposent pas les connexions personnelles. L’auteur gère ses copies et les administrateurs conservent leur contrôle sur les ressources publiées ; un simple destinataire ne peut pas modifier ces copies. Le stockage objet, la synchronisation éventuelle des sources et la conservation des copies dérivées restent des travaux d’exploitation distincts.

État : lecture du contenu SharePoint, génération des quatre formats, édition locale, recalcul Excel, publication et téléchargement privés implémentés. L’enregistrement personnel dans Microsoft 365 dispose d’un choix de dossier, d’une confirmation explicite et de reçus durables ; il est testé avec HTTP Microsoft synthétique. Un parcours Hermes réel crée et publie les fichiers, avec réouverture et rendu LibreOffice ; les exemples ont été contrôlés visuellement. La validation Microsoft réelle, les modèles du client, l’autonomie des dépôts SharePoint, les brouillons/réponses Outlook et la validation avec un modèle commercial restent à réaliser. Les brouillons privés dans le chat et leur envoi confirmé sont implémentés, avec versions et reçus durables ; une recherche personnelle des copies envoyées est également implémentée ; la résolution opérateur des cas toujours incertains reste à compléter. Le choix personnel d’envoi direct est implémenté sous les règles communes, avec révocation et héritage des capacités par les tâches ; la recette dédiée de briefing envoyé, son essai explicitement confirmé et son occurrence planifiée sont implémentés et testés avec Hermes réel et transports externes synthétiques. Voir [Envois planifiés](ENVOIS_PLANIFIES.md). Détails dans [Autonomie personnelle](AUTONOMIE.md), [E-mails](EMAILS.md), [Documents](DOCUMENTS.md) et [Enregistrement SharePoint](ENREGISTREMENT_SHAREPOINT.md).

- Produire des fichiers Word, Excel, PowerPoint et PDF avec un premier exemple représentatif de chaque format.
- Ajouter téléchargement, destination SharePoint et gestion des collisions de noms.
- Ajouter brouillons et envoi d’e-mails sous permissions et validations explicites.
- Vérifier les résultats incertains, interruptions et reprises pour prévenir les doublons.

Sortie attendue : chaque livrable est ouvert et vérifié dans le format attendu ; les écritures utilisent la connexion et les droits du propriétaire.

## Lot 5 — Automatisations et exploitation

L'entrée HTTPS et le contrôle de compatibilité de la base au démarrage sont préparés ; voir [Entrée HTTPS](ENTREE_HTTPS.md). Les services système, la supervision et la validation sur Infomaniak restent à réaliser.

État : récurrences personnelles, historique, modification d’horaire, suspension, reprise et remplacement après nouvel essai versionné implémentés. Une première recette d’envoi utilise une destination explicitement confirmée par le propriétaire. Les tests couvrent PostgreSQL concurrent et Hermes réel avec des services externes synthétiques. La récupération opérateur ciblée est implémentée avec vérification du conteneur, des baux et des verrous, sans répétition des actions. Voir [Récupération runtime](RECUPERATION_RUNTIME.md). Les notifications personnelles dans l’application sont implémentées : résultats, échecs, interruptions, échéances manquées et blocages. Voir [Notifications](NOTIFICATIONS.md). La [sauvegarde et restauration locales](SAUVEGARDE_RESTAURATION.md) réunissent PostgreSQL et les états privés, avec restauration vers des cibles neuves et suspension des tâches. Le [chiffrement des sauvegardes](CHIFFREMENT_SAUVEGARDES.md) avec clés de récupération séparées est implémenté. Stockage indépendant, exercice sur Infomaniak, collecte des reçus opérateur et éventuels canaux de notification externes restent à réaliser.

- Ajouter suivi des exécutions, reprise, suspension et notifications utiles.
- Utiliser l’autorité unique de planification PostgreSQL et la file Hermes, conformément à la décision documentée dans [Automatisations](AUTOMATISATIONS.md).
- Tester sauvegardes, restauration, désactivation d’un membre et mises à jour du fork.
- Évaluer avec le pilote les éléments utiles à un tableau de bord.

Sortie attendue : les automatisations restent compréhensibles et contrôlables, avec erreurs visibles et droits revérifiés à l’exécution.

## Lot 6 — Commercialisation

L’[administration des membres et licences](MEMBRES_LICENCES.md) est reliée à l’API : modifications versionnées, capacité disponible et réservations par invitation. La quantité de places reste celle du pilote ; elle n’est pas encore synchronisée avec Stripe.

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
