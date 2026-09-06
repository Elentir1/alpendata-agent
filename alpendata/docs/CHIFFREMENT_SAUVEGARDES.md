# Chiffrer une sauvegarde avant sa conservation hors hôte

6 septembre 2026 — chiffrement local avec age, sans transfert réseau intégré.

## Clés distinctes du serveur applicatif

L’outil `python -m alpendata_api.backup_encryption` chiffre les trois fichiers d’un [ensemble de sauvegarde terminé](SAUVEGARDE_RESTAURATION.md) dans un fichier `.age`. Il utilise le programme age installé sur l’hôte, avec des clés natives X25519. Il n’implémente pas de primitive cryptographique propre à AlpenData. Le parcours est testé sous Debian avec age `1.2.1` ; son exécutable peut être sélectionné par `--age-bin` avec un chemin absolu.

Générer les clés sur la machine de restauration ou dans l’environnement de gestion des secrets, **pas sur le serveur applicatif**. Seules les clés publiques nécessaires au chiffrement sont fournies à celui-ci. Exemple sur la machine de restauration :

```sh
umask 077
age-keygen -o /CHEMIN_PRIVE/alpendata-recovery.txt
age-keygen -y /CHEMIN_PRIVE/alpendata-recovery.txt
```

La deuxième commande retourne la clé publique `age1…`, à transférer dans la configuration de sauvegarde. Le fichier privé `AGE-SECRET-KEY-1…` reste dans le dispositif de récupération et son accès est restreint. Aucune clé de production n’a été générée pendant le développement ; les tests créent puis retirent leurs clés éphémères.

Plusieurs destinataires peuvent être déclarés, par exemple une clé opérationnelle et une clé de secours conservée séparément. Chacun peut déchiffrer l’ensemble à lui seul ; il ne s’agit pas d’un quorum. Retirer une clé des futurs chiffrements ne révoque pas sa capacité à ouvrir les anciens fichiers. La conservation et la rotation doivent donc rester cohérentes avec la durée de vie des sauvegardes.

Les clés SSH, les identités à mot de passe et les plugins age ne sont pas acceptés par ce premier parcours. Le fichier d’identité doit contenir des clés natives, être un fichier ordinaire non symbolique, et n’être accessible ni au groupe ni aux autres utilisateurs. Les secrets ne sont pas inscrits dans les arguments de processus ou les résultats JSON ; age ne reçoit pas les variables de connexion, modèle, SMTP ou Microsoft du serveur.

## Chiffrer l’ensemble terminé

```sh
python -m alpendata_api.backup_encryption \
  --age-bin /usr/bin/age --scratch /var/tmp \
  seal \
  --bundle /srv/alpendata-backups/2026-09-06-initial \
  --output /srv/alpendata-encrypted/2026-09-06-initial.age \
  --recipient CLE_PUBLIQUE_AGE_OPERATIONNELLE \
  --recipient CLE_PUBLIQUE_AGE_DE_SECOURS
```

Les parents des chemins doivent exister. Le fichier cible doit être neuf, hors du dossier source. L’outil vérifie le manifeste, prépare une archive des trois fichiers, puis vérifie les octets effectivement copiés avant chiffrement. Il ne publie le fichier final qu’après succès de age et synchronisation des octets. La publication refuse un nom déjà utilisé, sans l’écraser ; le résultat est en mode `0600`.

Le résultat JSON contient `backup_id`, `sha256`, `bytes` et `status: encrypted`. Conserver ce reçu dans un canal opérateur de confiance. L’empreinte attendue est obligatoire lors du déchiffrement ; ne pas simplement la recalculer depuis un fichier reçu d’une source inconnue.

Seul le `.age` est destiné au futur stockage indépendant. Cette commande ne supprime pas l’ensemble source en clair, ne charge aucun fichier vers Infomaniak et ne modifie aucune règle de rétention. Ces opérations seront reliées à la procédure d’exploitation après définition du stockage retenu.

## Déchiffrer, puis restaurer

Sur la machine de restauration, utiliser la clé privée et le SHA-256 conservé dans le reçu de confiance :

```sh
python -m alpendata_api.backup_encryption \
  --age-bin /usr/bin/age --scratch /var/tmp \
  unseal \
  --input /srv/alpendata-encrypted/2026-09-06-initial.age \
  --destination /srv/alpendata-restores/verified-bundle \
  --identity /CHEMIN_PRIVE/alpendata-recovery.txt \
  --expected-sha256 EMPREINTE_DU_RECU_CONSERVE
```

Le dossier final doit être neuf. L’outil vérifie d’abord le reçu, puis attend la validation du fichier entier par age. Des blocs temporaires peuvent être déchiffrés pendant cette vérification ; ils ne sont ni extraits ni publiés comme une sauvegarde utilisable avant la réussite complète. Une mauvaise clé, une altération ou une troncature empêche la création du dossier final.

L’enveloppe ne peut contenir que les trois fichiers ordinaires attendus, sans doublon, chemin extérieur ni lien. Leur manifeste, leurs empreintes et la compatibilité de migration sont revérifiés avant publication ; le manifeste final est copié en dernier. Une erreur d’écriture à ce dernier stade peut laisser un dossier partiel à examiner, sans résultat de succès et sans nettoyage destructeur de la cible.

Un résultat `decrypted_verified` permet ensuite d’appliquer la commande `backup restore` de la [procédure de restauration](SAUVEGARDE_RESTAURATION.md) vers une nouvelle base et de nouveaux états. Cette seconde étape suspend les tâches, révoque les sessions et exige une nouvelle connexion Microsoft. Ni le déchiffrement ni la restauration ne démarrent les services.

## Espace temporaire et confiance

`--scratch` désigne un espace **local** de la machine opératrice ; il vaut `/var/tmp` par défaut. Ne pas le placer sur un stockage partagé ou distant. Les données en clair temporaires y restent dans un répertoire `0700` séparé du répertoire de sortie chiffrée. Prévoir environ une fois la taille de l’ensemble pendant le chiffrement et deux fois pendant le déchiffrement, en plus des fichiers source et de la destination finale. La mémoire Python est utilisée par blocs, sans charger le dump entier.

Les répertoires temporaires sont retirés à la fin et lors des erreurs traitées. Un arrêt brutal de la machine ou du processus peut en laisser : les examiner dans la procédure de maintenance. Ce retrait logique n’est pas une garantie d’effacement physique sur disque, SSD, swap ou snapshot ; le chiffrement des volumes hôtes et leur rétention restent des mesures d’exploitation distinctes.

Le chiffrement protège la confidentialité et l’intégrité du contenu. Il n’identifie pas à lui seul l’expéditeur : toute personne connaissant une clé publique peut produire un nouveau fichier pour son détenteur. La provenance du reçu, les droits sur le futur stockage distant et la confiance dans le dump restent indispensables avant d’exécuter son SQL. La clé privée et le reçu doivent être récupérables indépendamment du serveur applicatif.

## Validation et références

Les exercices utilisent réellement age et PostgreSQL : deux clés de récupération, déchiffrement par la commande CLI, restauration du contenu privé, refus des mauvaises clés, refus d’une troncature après plusieurs blocs, altération du contenu et enveloppe contenant un chemin extérieur. Aucun compte ni donnée client réelle n’est utilisé.

- [Documentation officielle age — clés, destinataires et commandes](https://github.com/FiloSottile/age)
- [Manuel age 1.2.1 — fin de fichier, authentification et codes de sortie](https://raw.githubusercontent.com/FiloSottile/age/v1.2.1/doc/age.1)
- [Résultats des exercices AlpenData](VALIDATION_BACKEND.md)

La copie indépendante, le contrôle d’intégrité après téléchargement, la rotation opérationnelle et la reprise depuis Infomaniak restent à mettre en place et à exercer.

Pour cette étape distante, la documentation Infomaniak distingue son stockage Swift et sa compatibilité S3 partielle. L’intégration devra tester le protocole et les droits effectivement disponibles, sans assimiler ce service à toutes les fonctionnalités Amazon S3. Les objets chiffrés devront porter des noms uniques, et le téléchargement devra être contrôlé avec le reçu indépendant avant déchiffrement. Références : [Stockage objet Infomaniak](https://docs.infomaniak.cloud/object_storage/swift_object_storage/) et [compatibilité S3](https://docs.infomaniak.cloud/object_storage/s3/).
