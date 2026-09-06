# Récupération d'un assistant interrompu

Cette procédure est réservée à l'exploitation AlpenData sur l'hôte Linux. Les collaborateurs et administrateurs clients continuent d'utiliser l'interface web. Aucun endpoint HTTP de récupération, accès au terminal ou accès aux contenus des autres utilisateurs n'est ajouté.

## Diagnostic

Un superviseur interrompu peut laisser son conteneur actif. Le prochain lancement est refusé avec `agent_recovery_required` afin de ne pas créer deux processus écrivant dans la même mémoire. Le worker marque les baux expirés comme interrompus ; il ne rejoue pas le travail.

Sous le même compte Linux que le worker rootless, utiliser l'environnement Python du backend et les trois paramètres de service `ALPENDATA_DATABASE_URL`, `ALPENDATA_RUNTIME_STATE_ROOT` et `ALPENDATA_RUNTIME_IMAGE`. La base doit être PostgreSQL. Les secrets Microsoft, SMTP et modèle ne sont pas nécessaires. Les identifiants entreprise et utilisateur proviennent du dossier d'incident, pas d'un texte produit par le modèle.

```sh
python -m alpendata_api.runtime_recovery inspect \
  --organization "$ORGANIZATION_ID" --owner "$OWNER_ID"
```

Le résultat JSON ne contient que les identifiants, horaires, état du conteneur et tours en attente. Il ne contient ni messages, ni mémoire, ni environnement, ni journaux du conteneur. L'inspection contrôle le montage du volume personnel et prend les verrous d'exploitation ; un superviseur vivant peut donc provoquer un refus `agent_already_running`. Elle ne modifie pas les tours et ne supprime aucun conteneur.

## Récupération ciblée

Conserver le diagnostic dans le dossier d'incident, puis fournir l'identifiant complet du conteneur observé :

```sh
python -m alpendata_api.runtime_recovery recover \
  --organization "$ORGANIZATION_ID" --owner "$OWNER_ID" \
  --expected-container "$CONTAINER_ID"
```

L'outil reprend le verrou PostgreSQL du membre et des tours concernés, puis le verrou de son volume. Il refuse un travail en file, un bail encore valide, un superviseur tenant le volume, un montage étranger ou un conteneur différent de celui inspecté. Il ne contourne pas un refus en arrêtant un autre service.

La récupération supprime uniquement ce conteneur par son identifiant complet, vérifie sa disparition, puis marque les tours expirés comme interrompus en réutilisant le traitement du worker. Les fichiers personnels et les volumes sont conservés. Les lectures ou appels de modèle interrompus restent de résultat inconnu ; leur consommation n'est pas inventée. Le compteur d'échecs des occurrences suit la règle existante, sans double traitement d'un tour déjà terminé.

Si le diagnostic indique l'absence de conteneur mais qu'un bail expiré doit être clôturé, utiliser `--expected-container absent`. Cette valeur n'autorise jamais la suppression d'un conteneur apparu entre-temps.

Le résultat de succès contient un `recovery_id`, les horaires, le conteneur observé avant l'action et les identifiants des tours interrompus. Conserver cette sortie avec l'identité de l'opérateur dans le journal d'exploitation et le dossier d'incident. Ce reçu CLI n'est pas un journal d'audit centralisé ; sa collecte et sa conservation doivent être configurées lors du déploiement.

## Refus et résultats incertains

| Code | Suite à donner |
| --- | --- |
| `agent_already_running` | Un processus détient le volume. Contrôler le worker ; utiliser l'arrêt normal du chat si nécessaire. |
| `recovery_owner_busy` | Une autre opération tient le verrou du propriétaire en base. Attendre sa fin, puis refaire le diagnostic. |
| `recovery_execution_pending` | Attendre la fin du bail ou annuler le travail en file par les contrôles existants, puis refaire le diagnostic. |
| `recovery_inspection_changed` | Refaire une inspection. L'identifiant précédent n'autorise pas l'arrêt d'un remplaçant. |
| `recovery_container_mismatch` | Contrôler le compte de service, la configuration et le montage. Aucune suppression n'a été autorisée. |
| `recovery_engine_unavailable`, `recovery_removal_uncertain`, `recovery_database_unavailable` | Vérifier l'état de Podman et PostgreSQL, puis inspecter à nouveau. Une suppression peut avoir abouti avant une erreur ou un rollback en base. |

Après une coupure entre la suppression du conteneur et le commit PostgreSQL, une nouvelle inspection peut montrer `container: null` et un tour toujours expiré. La récupération explicitement confirmée avec `absent` permet alors sa clôture. Aucun appel Microsoft ni modèle n'est effectué par cette procédure. Elle ne transforme pas un envoi incertain en échec, ne modifie pas ses reçus et n'autorise pas sa répétition ; utiliser la vérification de copie envoyée ou d'enregistrement SharePoint disponible dans l'interface.

Les tâches futures gardent leur définition et leurs permissions. Une tâche bloquée par sa politique d'échecs n'est pas réactivée par la récupération. Après contrôle des reçus et des fichiers, le propriétaire peut ouvrir une nouvelle conversation ; l'ancien travail n'est pas rejoué.

## Validation et limites

`test_runtime_recovery.py` utilise des conteneurs rootless réellement démarrés, PostgreSQL temporaire et le véritable point d'entrée CLI. Il vérifie les baux, verrous, demandes concurrentes, changement d'identité de conteneur, montage étranger, file d'attente, conservation des données et reprise du runtime. Les conteneurs d'incident exécutent un processus inoffensif ; aucune donnée client ni service externe n'est utilisé.

Les exercices de restauration complète, alertes d'exploitation et validation sur Infomaniak restent distincts. Le compte de service ayant accès à la base et aux volumes reste un rôle d'exploitation privilégié, séparé du rôle administrateur client.

Références : [inspection ciblée Podman](https://docs.podman.io/en/latest/markdown/podman-container-inspect.1.html), [suppression d'un conteneur Podman](https://docs.podman.io/en/latest/markdown/podman-rm.1.html).
