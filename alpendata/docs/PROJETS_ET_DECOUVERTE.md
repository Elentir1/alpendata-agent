# Projets personnels et découverte des usages

Les projets regroupent les discussions d'un utilisateur dans son entreprise. Ils ont un nom et des consignes communes : objectif, public, style ou points à respecter. Les consignes sont copiées à la création d'une nouvelle discussion. Modifier un projet ou y déplacer une discussion ne réécrit jamais l'historique ni le contexte initial de cette discussion.

L'utilisateur peut rechercher les titres, renommer une discussion, la classer dans un projet, l'archiver et la restaurer. L'archivage est un classement réversible, pas une suppression ni une annulation d'exécution. Les administrateurs n'ont pas accès aux projets privés des autres membres. Une clé étrangère composée empêche aussi l'association d'une discussion au projet d'un autre propriétaire ou d'une autre entreprise.

Le modèle des nouvelles discussions est affiché par l'application à partir de la configuration serveur. Les anciennes discussions conservent leur modèle enregistré ; un changement de configuration nécessite une nouvelle discussion. L'identité distingue l'application développée par AlpenData, le moteur open source Hermes de Nous Research et le fournisseur du modèle. Les notices de licence d'origine restent conservées.

L'onboarding individuel ajoute une priorité professionnelle, une question adaptée au domaine choisi et un format préféré. Six pistes aident à formuler un premier besoin : relation client, commercial, RH, organisation, gestion et conseil/coaching. Choisir une carte remplit le besoin éditable ; cette action ne déclenche ni connexion, ni exécution, ni planification. Les réponses enregistrées alimentent la génération des propositions personnalisées, toujours limitée aux outils réellement accessibles.

API sous `/api/organizations/{organization_id}/chat` : `GET/POST /projects`, `PUT /projects/{id}`, `PUT /conversations/{id}`. La liste des discussions accepte `project` (identifiant ou `unfiled`), `q` (recherche littérale du titre) et `archived`. Migration additive : `0023`.

Les projets ne partagent pas automatiquement les documents, la mémoire ni les conversations entre collègues. Les ressources d'entreprise explicitement autorisées continuent d'utiliser leur propre mécanisme de partage.
