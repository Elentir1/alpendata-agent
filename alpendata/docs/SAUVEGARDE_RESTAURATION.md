# Sauvegarde et restauration locales

6 septembre 2026 — outil opérateur Linux/PostgreSQL, sans endpoint client.

## Ensemble sauvegardé

`python -m alpendata_api.backup create` produit un dossier privé contenant un dump PostgreSQL au format custom, une archive des états Hermes par entreprise et propriétaire, et un manifeste final avec leurs tailles et empreintes SHA-256. Le manifeste conserve également la version des migrations, la révision logicielle déclarée et l’image OCI configurée. La révision doit être le SHA complet du code effectivement installé ; l’outil ne copie pas le dépôt ni l’image.

Le dossier contient des données personnelles. Cette première commande produit un ensemble **local non chiffré**, avec un dossier en mode `0700` et des fichiers en `0600`. Elle n’effectue aucun transfert distant. Le [chiffrement avec age](CHIFFREMENT_SAUVEGARDES.md) est implémenté comme une étape distincte à appliquer avant la conservation hors hôte. La copie indépendante, la rétention et les tests depuis le stockage Infomaniak restent à intégrer avant exploitation. Les empreintes détectent une altération accidentelle ; elles ne prouvent pas l’authenticité face à quelqu’un capable de modifier aussi le manifeste.

Les clés de chiffrement des connexions, clés modèles, secrets Microsoft/SMTP, configuration PostgreSQL, rôles du cluster, certificats et secrets d’exploitation ne sont pas exportés. Ils doivent disposer d’une conservation et d’une procédure de récupération séparées. Les caches Microsoft déjà chiffrés en base sont présents dans le dump ; la restauration décrite ci-dessous les efface dans la base cible et exige une nouvelle connexion.

## Préparer une fenêtre de maintenance

Arrêter les admissions au point d’entrée, puis arrêter le scheduler, laisser finir les exécutions et les écritures Microsoft engagées, arrêter les workers et l’API. Conserver PostgreSQL et le moteur Podman disponibles. Ne pas lancer de migration ou modifier les volumes pendant cette opération. Le compte opérateur doit être celui qui contrôle les conteneurs rootless et les états locaux.

La commande vérifie elle-même plusieurs frontières : elle prend un verrou `SHARE NOWAIT` sur toutes les tables métier et Alembic, puis tous les verrous des propriétaires. Elle refuse un schéma inattendu, une transaction d’écriture concurrente, un tour en cours, un envoi en cours, un dépôt Microsoft en cours ou un conteneur personnel encore présent, même arrêté. Utiliser la [récupération ciblée](RECUPERATION_RUNTIME.md) pour examiner les orphelins, puis recommencer vers un nouveau dossier. Aucun conteneur n’est supprimé par la sauvegarde.

Le dump utilise un snapshot PostgreSQL exporté pendant que les écritures restent bloquées et que les états personnels sont verrouillés. Ces verrous concernent les processus AlpenData et les conteneurs connus du moteur configuré ; ils ne protègent pas contre un opérateur hôte qui écrirait directement dans les fichiers. L’arrêt préalable des services évite aussi de faire attendre les requêtes des utilisateurs pendant la copie.

Les chemins d’état doivent correspondre aux membres présents en base. Les fichiers ordinaires, dossiers et liens symboliques relatifs restant dans le même espace propriétaire sont pris en charge. Un lien absolu, une sortie de cet espace, un lien dur ou un fichier spécial fait échouer la sauvegarde, sans manifeste final. L’outil ne suit jamais ces liens pour copier une cible extérieure.

## Créer l’ensemble

Depuis l’environnement Python AlpenData de la version installée, fournir par le gestionnaire de secrets la connexion de base et par la configuration de maintenance les chemins absolus :

```sh
export ALPENDATA_RUNTIME_STATE_ROOT='/srv/alpendata/states'
export ALPENDATA_RUNTIME_IMAGE='sha256:REMPLACER_PAR_ID_LOCAL_VERIFIE'
# ALPENDATA_DATABASE_URL est injectée par le gestionnaire de secrets.
python -m alpendata_api.backup create \
  --bundle /srv/alpendata-backups/2026-09-06-initial \
  --postgresql-bin /usr/lib/postgresql/17/bin \
  --revision SHA_COMPLET_DE_LA_VERSION_INSTALLEE
```

Le parent du dossier de sauvegarde doit déjà exister et le dossier demandé doit être neuf, hors des états Hermes. Ne considérer l’ensemble comme créé que si la commande réussit et que le manifeste final existe. Une interruption laisse un dossier partiel pour diagnostic ; la commande ne le nettoie pas et ne l’écrase pas lors d’une nouvelle tentative. Le résultat JSON n’affiche ni URL de base ni contenu privé. Les avertissements des outils PostgreSQL font échouer la certification de l’ensemble ; les erreurs sont nettoyées pour ne pas exposer des secrets dans les sorties.

La connexion accepte hôte/socket Unix, port, utilisateur, mot de passe et les paramètres TLS courants explicitement reconnus. Les variables `PG*` héritées et les secrets des autres services ne sont pas transmis aux outils. La connexion serveur SQLAlchemy et la connexion de `pg_dump` désignent la même base.

## Restaurer dans un environnement isolé

L’ensemble doit provenir d’une source opérateur de confiance : un dump PostgreSQL peut contenir du code SQL exécuté lors de sa restauration. Créer une base vide dédiée et un chemin d’états neuf. Aucun service AlpenData ne doit utiliser cette cible pendant l’opération ; ne pas la substituer directement à la production.

```sh
# ALPENDATA_DATABASE_URL désigne maintenant la NOUVELLE base vide.
export ALPENDATA_RUNTIME_STATE_ROOT='/srv/alpendata-restores/initial-states'
python -m alpendata_api.backup restore \
  --bundle /srv/alpendata-backups/2026-09-06-initial \
  --postgresql-bin /usr/lib/postgresql/17/bin
```

La commande contrôle les empreintes et exige la même version de migration que le code de restauration. Elle refuse toute base contenant déjà des relations utilisateur et tout dossier cible existant. Elle vérifie les chemins de l’archive et restaure PostgreSQL dans une transaction, sans `--clean`, sans reprise des propriétaires ni des ACL du cluster source. Les droits métier AlpenData, eux, sont conservés dans les données restaurées.

Ensuite, dans la base cible seulement :

- Les sessions sont révoquées ; les parcours OAuth, preuves d’invitation et anciennes invitations sont invalidés.
- Les connexions Microsoft sont déconnectées et leurs caches supprimés ; le mode personnel d’envoi revient à la confirmation.
- Les récurrences non archivées sont suspendues et leurs versions avancent.
- Les tours en attente ou en cours deviennent interrompus ; les appels sans résultat deviennent inconnus/échoués selon leur registre. Les envois et dépôts dont l’issue était incertaine ne sont pas rejoués.
- Les documents, conversations, mémoires, membres, droits de partage et résultats déjà connus sont conservés.

Une réussite renvoie `restored_suspended` et produit un reçu voisin du dossier d’états. Aucun service, modèle ou envoi n’est démarré. Un échec laisse des cibles partielles et un marqueur `RESTORE_INCOMPLETE` : les conserver pour examen, sans les mettre en service. La commande ne promet pas une transaction atomique entre PostgreSQL et le système de fichiers ; une nouvelle tentative utilise de nouvelles cibles.

Une sauvegarde est un état passé : elle ne connaît pas les messages envoyés, retraits d’accès ou changements de consentement survenus ensuite. Avant une bascule, rapprocher les reçus externes, réexaminer les adhésions et partages, reconnecter les outils et faire revoir les tâches concernées. Ne pas relancer aveuglément un ancien brouillon ou une ancienne tâche. Vérifier les exemples privés et partagés avec plusieurs comptes, puis seulement configurer le point d’entrée et les services vers les cibles validées.

## Références

- [PostgreSQL 17 — pg_dump et snapshots](https://www.postgresql.org/docs/17/app-pgdump.html)
- [PostgreSQL 17 — pg_restore et restauration transactionnelle](https://www.postgresql.org/docs/17/app-pgrestore.html)
- [PostgreSQL 17 — compatibilité des verrous](https://www.postgresql.org/docs/17/explicit-locking.html)

Les résultats des exercices locaux sont consignés dans [Validation backend](VALIDATION_BACKEND.md). Ils ne remplacent pas une restauration depuis une sauvegarde chiffrée indépendante sur l’infrastructure Infomaniak retenue.
