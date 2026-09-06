# Exécution Hermes AlpenData

Ce runtime exécute le véritable `AIAgent` du fork dans un conteneur Linux sans réseau externe. Il est relié au [chat personnel](../docs/CHAT_PERSONNEL.md), à sa file PostgreSQL et à la passerelle Mistral/OpenRouter. Les services externes sont encore synthétiques dans les essais locaux.

## Frontière d’exécution

- Podman sans privilèges, utilisateur 1000 dans le conteneur, racine en lecture seule, capacités Linux retirées et élévation de privilèges interdite.
- Un seul volume `/state`, sélectionné par le serveur avec les UUID d’entreprise et de propriétaire. Aucun volume voisin ni socket d’administration n’est monté.
- État, mémoire et fichiers Hermes sous `/state/.hermes` et `/state/workspace`. Le verrou de l’utilisateur est placé hors du volume de l’agent pour qu’un outil ne puisse pas le supprimer.
- Un nom de conteneur stable par propriétaire empêche un second démarrage après une panne du superviseur. Si un ancien conteneur subsiste, l’exécution demande une récupération explicite ; elle ne supprime pas silencieusement un travail dont l’état est inconnu. La file de chat marque les baux expirés comme interrompus ; la récupération opérateur des conteneurs orphelins reste à compléter.
- Réseau `none`. Le modèle et les outils métier utilisent une passerelle sur les pipes hérités du processus. La configuration de l’image ne contient aucune clé Microsoft ou IA.
- Limites actuelles : 1 Gio de mémoire, un CPU, 128 processus, 128 Mio temporaires ; un tour Hermes jusqu’à 20 itérations et 240 secondes. Le superviseur impose aussi un délai global et supprime son conteneur en cas d’échec.

Le noyau reste partagé avec l’hôte. Cette vérification locale ne certifie pas un déploiement Infomaniak ni une résistance à toutes les vulnérabilités du noyau. Le service de gestion des conteneurs doit rester séparé de l’exposition web et inaccessible aux agents.

## Construction locale

Prévoir Linux, Podman, une configuration de sous-UID/sous-GID et cgroup v2 permettant les limites de ressources. Sur l’environnement Debian WSL de développement, `slirp4netns` sert uniquement au réseau de construction :

```sh
podman --cgroup-manager=cgroupfs build --network=slirp4netns \
  --ignorefile alpendata/runtime/.containerignore \
  -f alpendata/runtime/Containerfile -t localhost/alpendata-runtime:dev .
```

L’image Python de base est épinglée par digest. Les dépendances Hermes sont installées depuis le `uv.lock` du fork, sans les extras facultatifs. La licence et les notices amont sont conservées. Aucun service Docker Desktop n’est utilisé.

Les bibliothèques documentaires supplémentaires sont installées depuis `documents.lock`, avec vérification des empreintes. Ce verrou conserve les versions communes au verrou Hermes (notamment Pillow et les dépendances partagées). Pour le régénérer depuis la racine, avec `uv` et Python 3.13 : `sh alpendata/runtime/lock-documents.sh`. Le mode `uv --no-config` sert uniquement à installer ce verrou autonome ; l’installation Hermes conserve ses contraintes amont.

L’image inclut aussi LibreOffice Writer/Calc/Impress, Poppler et DejaVu Sans depuis les dépôts Debian signés. Le digest final de l’image identifie l’environnement d’exécution testé. Les profils de rendu sont temporaires et personnels ; aucun LibreOffice installé sur le poste de l’utilisateur n’est utilisé. Le [guide interne](DOCUMENT_GUIDE.md) et le programme `document_builder.py` complètent les outils terminal/fichier existants sans ajouter d’outil au noyau Hermes. Les nouvelles conversations reçoivent le chemin du guide dans leur contexte initial ; le contexte des conversations déjà créées reste inchangé.

`RuntimeSettings.image` attend l’identifiant local complet `sha256:…`, jamais une étiquette mutable. La résolution de `:dev` est réservée au script de test ; une exécution ne télécharge jamais une image manquante.

## Contrat du superviseur

`alpendata_api.runtime.ContainerRuntime.run(organization_id, owner_id, payload, exchange)` attend des identités déjà établies par le backend. Ces arguments ne doivent jamais être copiés d’un appel d’outil du modèle.

Le message initial contient l’identifiant serveur de conversation, le modèle configuré, le message utilisateur, le contexte système et les capacités métier disponibles. L’historique actif est restauré depuis SessionDB dans le volume personnel, jamais depuis le navigateur. Le processus démarre un endpoint de modèle local à adresse stable, applique l’identité AlpenData et réutilise la mémoire privée Hermes. Les outils de fichiers, terminal et mémoire restent ceux d’Hermes ; les outils Microsoft appellent la passerelle. Le titrage secondaire Hermes est désactivé : AlpenData nomme déjà la conversation à partir du premier message, et aucun thread de titrage ne doit survivre au tour.

Le superviseur reçoit des requêtes structurées `model` ou `tool`. La fonction `exchange` doit être liée à l’exécution autorisée et revérifier les droits courants avant chaque action. Elle retourne un statut et un corps JSON ; elle choisit les véritables destinations et secrets côté serveur. Le contenu du conteneur est une entrée non fiable, y compris lorsqu’il ressemble à un identifiant ou à une demande administrative. Aucun endpoint HTTP public n’expose directement ce protocole.

Les frames sont plafonnées à 8 Mio et les demandes par tour à 80. L’écriture sur les pipes ne bloque pas le contrôle du délai. Le runtime ne conserve ni stderr ni corps d’échange dans les journaux d’exploitation. Le résultat contient la réponse et les messages Hermes ; le processus de chat vérifie l’état et les droits avant d’enregistrer la réponse finale. Les règles de conservation restent à configurer avant exploitation.

## Vérification

Le parcours `test_document_generation.py` crée, édite, recalcule et rend les quatre formats dans le vrai Hermes, puis vérifie leurs téléchargements privés. L’option de test `--document-qa-output DIRECTORY` conserve les originaux et rendus dans un nouveau sous-dossier pour inspection visuelle. Image finale de génération documentaire vérifiée : `sha256:349e453517fcbbe3fb69cf4fe3804024a1fb74e062dc723a07e534de74f55ad5`.

L’extension [documents](../docs/DOCUMENTS.md) publie des fichiers privés depuis les nouvelles conversations, même sans connexion Microsoft. Les octets traversent le broker ; aucun fichier n’est lu par un chemin hôte choisi par le modèle. Image vérifiée pour cette étape : `sha256:acbd8d15b9c59a97425671e677fcae5714ac05ddc0b93f48e853eb2cf22158e8`.

Installer les dépendances de développement du backend et définir `HERMES_PYTHON` vers cet environnement, puis :

```sh
sh alpendata/runtime/test-runtime.sh
```

Le script résout l’image locale puis utilise obligatoirement `scripts/run_tests.sh`. Le scénario crée des conteneurs réels et un stockage temporaire Linux. Seuls le fournisseur de modèle et les données métier sont synthétiques. Il exerce les outils Hermes, la mémoire, la reprise de conversation, le refus des fichiers d’hôte et voisins, l’absence de réseau externe et l’absence de mémoire d’un collègue.

Le scénario `test_chat_worker.py` vérifie également le parcours API/file/agent et les droits Microsoft pendant le chat. Un test de qualité avec Mistral/OpenRouter et des identités Microsoft réelles reste nécessaire avant le pilote. Le scénario `test_routines_worker.py` exerce maintenant une occurrence planifiée issue d’un essai approuvé. La planification est décrite dans [Automatisations](../docs/AUTOMATISATIONS.md).

Les occurrences planifiées ont un budget maximal de 180 secondes et n’activent pas les fournisseurs de mémoire. Le contrôleur reste réactif aux délais et annulations pendant l’attente du broker ; les reçus tardifs restent liés au tour initial. Image validée pour cette étape : `sha256:4031b65db47e83b5216fc4d0b882472c351221da012590006be02868a8e30fa0`.
