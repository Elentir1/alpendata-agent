# Services continus et maintenance

6 septembre 2026 — contrôle des processus AlpenData sur un compte Linux dédié.

Les commandes `alpendata_api.chat_worker`, `alpendata_api.schedule_worker` et `alpendata_api.billing_worker` vérifient la connexion et la révision de la base avant leur première itération. Elles interceptent `SIGTERM` et `SIGINT` : l'itération déjà admise se termine, puis le processus quitte avec le code zéro. Le worker chat ne prend pas le travail suivant. Le planificateur termine son lot courant, qui peut examiner jusqu'à 100 échéances, puis quitte sans attendre les 30 secondes du prochain contrôle. Le service de facturation termine la lecture Stripe de l'entreprise déjà prise et ne prend pas la suivante.

Un arrêt de service n'est pas une annulation métier. Une action déjà autorisée dans le travail en cours peut encore se terminer pendant cet arrêt. Utiliser le contrôle d'annulation personnel pour demander l'arrêt d'un tour, et vérifier les reçus des actions dont le résultat reste incertain. Ni un redémarrage ni une reprise après interruption ne prouvent qu'un effet externe n'a pas eu lieu.

## Unités du compte de service

Le générateur `alpendata_api.service_units` prépare trois unités **systemd utilisateur** : API, file de travail et planificateur. L'option `--with-billing` ajoute `alpendata-billing.service` pour l'actualisation Stripe. Il ne crée pas de compte Linux, ne configure pas sa persistance après déconnexion et n'installe ni n'active les unités. Il refuse un dossier de sortie déjà présent.

Exemple depuis l'environnement backend, avec les chemins définitifs du serveur :

```sh
python -m alpendata_api.service_units \
  --python /srv/alpendata/venv/bin/python \
  --backend /srv/alpendata/backend \
  --environment /etc/alpendata/service.env \
  --api-port 8080 \
  --output /srv/alpendata/unit-candidates
```

Pour un environnement où Stripe est configuré, ajouter `--with-billing` à cette génération, puis inclure `alpendata-billing` dans les commandes de démarrage, de statut et d'arrêt ci-dessous. Le service de facturation n'a pas besoin des paramètres modèle/runtime ; sa configuration Stripe est décrite dans [Abonnements et licences](FACTURATION_STRIPE.md).

Les chemins Linux absolus acceptent les espaces ASCII. Les traversées `..`, caractères de substitution systemd et expressions de commande sont refusés. Le fichier d'environnement doit être lisible uniquement par le compte de service et les opérateurs autorisés, typiquement mode `0600`. Il contient les paramètres et secrets décrits dans le README backend ; aucune clé n'entre dans les unités générées. L'environnement Python et les migrations appartiennent à la même release, dont l'installation doit être terminée avant le démarrage.

Sous le compte Linux dédié à AlpenData, après installation et revue des candidats dans son répertoire `~/.config/systemd/user/` :

```sh
systemctl --user daemon-reload
systemctl --user start alpendata-api alpendata-chat alpendata-scheduler
curl --fail --max-time 5 http://127.0.0.1:8080/health/ready
systemctl --user status alpendata-api alpendata-chat alpendata-scheduler
```

L'activation persistante avec `systemctl --user enable ...` et le maintien du gestionnaire utilisateur sans session interactive doivent être configurés sur le futur hôte par l'opérateur. Ne pas utiliser le compte personnel d'un collaborateur. L'API et le worker partagent le compte technique de contrôle, les volumes privés et l'installation rootless Podman. Les droits des collaborateurs restent vérifiés par l'application, indépendamment de ce compte système.

L'API écoute uniquement sur `127.0.0.1` et accepte les en-têtes du proxy local. Le serveur web HTTPS utilise un compte séparé, comme décrit dans [Entrée HTTPS](ENTREE_HTTPS.md). Les unités présentes ne supervisent pas encore Nginx, PostgreSQL ni le renouvellement du certificat.

## Arrêt et redémarrage

Les unités utilisent `KillMode=mixed` : systemd envoie d'abord le signal d'arrêt au processus principal. Il laisse le temps à ce contrôleur de terminer le travail et de fermer le conteneur. Si le délai de 1 020 secondes expire, systemd peut tuer les processus restants du groupe. Cette borne laisse une marge au budget runtime maximal de 900 secondes ; elle ne rend pas toute opération de base de données infaillible. Prévoir aussi les délais PostgreSQL et la supervision externe.

Une erreur provoque un redémarrage après cinq secondes. Trois démarrages sont autorisés sur une fenêtre de 60 secondes ; une configuration toujours incorrecte finit en échec au lieu de redémarrer indéfiniment. Un arrêt explicite du service ne déclenche pas ce redémarrage. Après correction de la cause :

```sh
systemctl --user reset-failed alpendata-chat
systemctl --user start alpendata-chat
```

`Type=exec` confirme que le programme a été exécuté ; l'état systemd « active » ne garantit pas que tous ses contrôles de démarrage ont réussi. Vérifier aussi `/health/ready` pour l'API et l'événement `ready` des workers. Leurs événements de cycle de vie contiennent seulement le nom de service et un état : `ready`, `stopped`, `database_unavailable`, `configuration_failed` ou `failed`. Le service de facturation ajoute `sync_failed` après une lecture Stripe en erreur. Les exceptions de boucle donnent un code de sortie non nul sans leurs paramètres privés. Les journaux de l'API ont leur propre politique ; `--no-access-log` désactive ses journaux d'accès HTTP. Les cores des services sont désactivés et le masque de création des fichiers est `0077`.

Pour une maintenance cohérente :

1. Fermer les nouvelles admissions HTTP au niveau de l'entrée web.
2. Arrêter le planificateur et, s'il est activé, le service de facturation ; attendre la fin de leurs itérations courantes.
3. Arrêter l'API et attendre ses requêtes déjà engagées, puis arrêter le worker chat et attendre son travail courant.
4. Vérifier l'absence de contrôleur et de conteneur encore en activité avant de sauvegarder ou migrer. Les outils de sauvegarde effectuent leurs propres contrôles et refusent une source encore occupée.
5. Après mise à jour, démarrer les services, vérifier leur disponibilité et les reçus, puis rouvrir les admissions.

Les travaux encore en attente restent en base et peuvent être pris après le redémarrage. Si l'objectif est de restaurer un ancien état, suivre la [restauration suspendue](SAUVEGARDE_RESTAURATION.md), qui impose une réconciliation avant reprise. Après un arrêt forcé ou un conteneur orphelin, suivre la [récupération ciblée](RECUPERATION_RUNTIME.md) ; ne pas supprimer arbitrairement des conteneurs ou rejouer les actions.

## Exercices locaux

Les tests de signaux lancent un processus Python distinct, PostgreSQL et le vrai Hermes rootless. Un fournisseur HTTP local attend pendant le travail ; un signal d'arrêt est envoyé, puis la réponse synthétique est libérée. Le travail courant termine et le suivant reste en attente. Les commandes réelles des trois workers sont également vérifiées au repos et sur une base incompatible. Le processus de facturation est lancé avec ses seuls paramètres Stripe/base, sans modèle IA ni runtime, sur une base sans client Stripe lié : aucun appel extérieur n'est fait par cet exercice de démarrage.

L'option `--systemd-user`, avec `--postgresql-bin`, active les exercices du gestionnaire utilisateur réellement disponible. Ils chargent des unités sous des noms uniques, uniquement pour la session de test, puis les arrêtent et retirent leurs liens. Ils vérifient les quatre unités, le redémarrage après un crash au repos, l'arrêt propre et la limite de redémarrages sur une base incompatible. Les traces du journal ne contiennent que des données de test. Aucun service permanent, compte client ou serveur Infomaniak n'est créé.

Le test d'arrêt en cours de travail utilise un signal direct ; l'exercice systemd de crash concerne un worker au repos. Un arrêt forcé de l'hôte, les limites de ressources du serveur et le parcours complet avec des connexions commerciales restent à valider sur Infomaniak.

Références : [sémantique des signaux systemd 257](https://github.com/systemd/systemd/blob/v257/man/systemd.kill.xml), [cycle de vie et redémarrage des services](https://github.com/systemd/systemd/blob/v257/man/systemd.service.xml).
