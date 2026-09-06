# Mémoire personnelle

Dans « Mon espace », chaque collaborateur peut ouvrir « Ma mémoire », consulter ses notes de travail et ses préférences, puis ajouter, corriger ou retirer des éléments. « Tout retirer » prépare une modification ; seul « Enregistrer » la rend effective. Le parcours existe en français et en anglais.

## Propriété et exécution

Les routes `GET /api/organizations/{organization_id}/memory` et `PUT /api/organizations/{organization_id}/memory/{target}` utilisent exclusivement l'identité authentifiée. Aucun paramètre ne permet de choisir un autre propriétaire. Un administrateur ne consulte que sa propre mémoire. Un membre actif conserve cet accès après retrait de sa licence ; un membre désactivé n'y accède plus.

Le backend lance une opération de maintenance dans le même conteneur isolé et le même volume personnel que le chat. Elle réutilise `MemoryStore` d'Hermes et ses fichiers `MEMORY.md` et `USER.md`, sans instancier un agent ni appeler un modèle. Les opérations de broker sont refusées. Le verrou du propriétaire empêche une modification pendant une exécution de chat ou une tâche ; les tours en attente empêchent également la maintenance.

La version est l'empreinte SHA-256 des octets lus. Une écriture sur une version dépassée impose un rechargement. L'écriture atomique et le verrou de fichier sont ceux d'Hermes ; l'adaptateur remplace la liste explicitement revue, au lieu d'utiliser une suppression par recherche de sous-chaîne. Les limites de caractères et les contrôles de contenu d'Hermes restent appliqués. Les liens, fichiers irréguliers, contenu UTF-8 invalide et lectures dépassant 64 Kio sont refusés, sans réécriture partielle.

## Effet des modifications

Les nouvelles conversations reprennent la mémoire corrigée. Les conversations déjà ouvertes conservent leur contexte système, conformément au fonctionnement d'Hermes. Une réponse réseau perdue impose de relire l'état avant une nouvelle édition ; aucune écriture n'est répétée automatiquement. Enregistrer une liste ne remplace pas les corrections non enregistrées de l'autre liste.

Cette fonction gère la mémoire active. Elle ne supprime pas les conversations passées, leurs contextes déjà enregistrés, les fichiers produits ou les sauvegardes. Une information encore présente dans une source ou une conversation peut être mémorisée à nouveau. Un effacement complet avec règles de conservation et traitement des sauvegardes reste un chantier distinct ; les emplacements et dépendances vérifiés sont décrits dans [Conservation et suppression des données](CONSERVATION_DONNEES.md).

## Vérification

`test_personal_memory.py` exerce l'API, PostgreSQL, le conteneur Linux et le véritable outil mémoire d'Hermes. Il vérifie la séparation des propriétaires, la correction reprise au nouveau dialogue, la stabilité d'un dialogue existant, le conflit de version, le verrou d'exécution, le retrait de licence et la désactivation du membre. Un second scénario vérifie la capacité, le contenu refusé et les fichiers invalides. Les réponses du fournisseur de modèle sont synthétiques.

Les tests de l'interface couvrent les corrections locales, la concurrence et la récupération après perte de réponse. La maintenance exige une nouvelle image runtime contenant `memory_access.py` ; aucune migration de base de données n'est nécessaire.
