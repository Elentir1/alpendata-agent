# Entrée HTTPS et contrôle de démarrage

6 septembre 2026 — préparation locale de l'hébergement AlpenData.

L'interface compilée et les routes `/api/` sont servies sous une origine HTTPS commune. Le générateur `alpendata_api.ingress` produit une configuration Nginx autonome à partir de l'origine, du répertoire de compilation, du certificat et du port local de l'API. Il ne crée aucun serveur Infomaniak, DNS, certificat ou service système.

## Démarrage de l'API

L'application vérifie au démarrage que la base est accessible et que sa révision Alembic correspond exactement à celle du code déployé. Une base vide, une migration manquante ou une version incompatible empêche le démarrage avec `application_database_not_ready`. Les migrations restent une opération explicite pendant une fenêtre de maintenance ; le démarrage ne modifie pas la base.

- `GET /health/live` indique que le processus HTTP répond.
- `GET /health/ready` retourne `200 {"status":"ready"}` si la révision est compatible, sinon `503 {"status":"unavailable"}`. Les erreurs SQL et informations de connexion ne sont pas retournées.
- Ces routes restent accessibles directement sur le port local de l'API. Elles ne sont pas publiées par Nginx.

Le contrôle de disponibilité ne vérifie pas les comptes Microsoft, le fournisseur de modèle, SMTP, les workers, le stockage privé ni la conformité de toutes les colonnes d'une base modifiée manuellement. Il ne remplace pas la validation Alembic et les exercices métier. Une dégradation après démarrage ne ferme pas automatiquement Nginx : la supervision devra retirer le service de la circulation. Suspendre les admissions et les workers avant les migrations.

Déployer le dossier backend complet, y compris `alembic.ini` et `migrations/`, puis installer son environnement depuis le verrou existant. L'installation du seul wheel Python n'embarque pas encore les migrations et ne constitue pas un déploiement pris en charge.

Depuis `alpendata/backend`, avec les secrets déjà chargés par l'opérateur :

```sh
uv run alembic upgrade head
uv run uvicorn alpendata_api.app:from_environment --factory \
  --host 127.0.0.1 --port 8080 --proxy-headers \
  --forwarded-allow-ips 127.0.0.1 --no-access-log
curl --fail --max-time 5 http://127.0.0.1:8080/health/ready
```

Prévoir un délai de connexion PostgreSQL dans la configuration serveur, par exemple `connect_timeout=5` dans l'URL PostgreSQL, et une échéance de supervision indépendante. Ne pas publier le port 8080 ni faire confiance à toutes les adresses pour les en-têtes de proxy.

## Préparer une configuration candidate

Compiler l'interface avec `npm ci` puis `npm run build` dans `alpendata/frontend`. Copier uniquement `dist/` vers un répertoire de release concret et en lecture seule pour le compte du serveur web. Aucun lien symbolique ne doit être utilisé dans le chemin des fichiers publics. Les états Hermes, sauvegardes, secrets et fichiers privés restent dans d'autres répertoires.

Exemple à adapter à l'origine et aux chemins du futur serveur, depuis l'environnement Python backend :

```sh
python -m alpendata_api.ingress \
  --origin https://assistant.example.ch \
  --frontend /srv/alpendata/releases/REVISION/frontend \
  --certificate /etc/alpendata/tls/fullchain.pem \
  --private-key /etc/alpendata/tls/private.key \
  --run-directory /run/alpendata-web \
  --api-port 8080 \
  --output /etc/alpendata/nginx.candidate.conf
nginx -t -e stderr -c /etc/alpendata/nginx.candidate.conf
```

Le répertoire de travail doit exister et être privé au compte Nginx. La commande refuse d'écraser une configuration existante. Les chemins absolus ASCII acceptent les espaces, mais refusent les expressions de configuration, variables et traversées `..`. L'origine doit être canonique, en minuscules et sans chemin ; omettre le port HTTPS standard 443. La première version accepte un nom DNS ou une adresse IPv4 et écoute en IPv4.

Le fichier produit est un `nginx.conf` complet, pas un fragment `sites-enabled`. Le processus reste au premier plan. Lancer Nginx sous un compte dédié avec uniquement la capacité d'écouter sur le port 443, gérée par le futur service système ; ne pas lancer les workers avec les privilèges root. Le certificat doit être reconnu par les navigateurs et son renouvellement supervisé. Aucun certificat de test ne doit être utilisé pour le pilote.

La valeur `ALPENDATA_PUBLIC_ORIGIN` et les deux URL de retour Entra doivent correspondre à l'origine choisie. Les formulaires de retour Microsoft sont transmis à l'API ; l'entrée HTTPS n'accorde aucun accès aux connexions personnelles.

## Comportement public

La page `/` et le lien d'invitation `/join` servent l'interface. Seuls les JavaScript/CSS de `assets/` et les formats publics de `brand/` sont exposés. Les chemins inconnus, les cartes de sources, fichiers cachés, documentation API et liens symboliques ne deviennent pas des pages publiques. Une erreur API reste une erreur API, avec son statut et son contenu.

Nginx conserve l'en-tête `Origin` du navigateur pour le contrôle des mutations par cookie. Il impose l'hôte configuré et reconstruit les informations de proxy depuis la connexion entrante. Un hôte étranger est refusé. Le certificat et TLS 1.2/1.3 protègent cette entrée ; HTTP sur le port 80 n'est pas configuré. Prévoir le renouvellement du certificat en conséquence.

Les requêtes sont limitées à 8 Mio, ce qui permet un document de 5 Mio encodé en base64 avec ses métadonnées. Les transferts API sont transmis sans stockage intermédiaire volontaire sur disque et sans cache. Les réponses et en-têtes privés conservent `no-store`. Nginx ne rejoue pas une requête vers l'API en cas d'échec ; les opérations métier restent responsables de leur idempotence. Le délai d'inactivité du proxy est de 120 secondes, distinct de la durée d'un travail Hermes exécuté en arrière-plan.

Les accès HTTP et erreurs Nginx de requêtes ne sont pas journalisés, pour éviter d'enregistrer des URL ou paramètres privés. Les diagnostics de configuration et de démarrage sont contrôlés avec `nginx -t -e stderr`. La supervision des processus, des statuts et des reçus métier reste à raccorder sans inclure les contenus des clients. La politique de navigateur interdit l'intégration en iframe et limite scripts, connexions et polices à la même origine.

## Validation et suite

Les exercices utilisent Nginx Debian, Uvicorn, PostgreSQL, l'interface réellement compilée et un certificat éphémère dont la chaîne est vérifiée par le client de test. L'authentification du test est une session synthétique du serveur, pas un parcours Entra réel. Les options `--nginx-bin` et `--frontend-dist` du lanceur de tests activent ces exercices ; sans elles, les deux scénarios HTTPS sont explicitement ignorés.

Les unités de service, le renouvellement du certificat, la supervision, la protection de l'hôte, les accès Infomaniak et le parcours réel Microsoft restent à préparer ou valider avant le pilote. Aucun service système ni adresse publique n'est créé par ces tests.

Références : [proxy HTTP Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html), [fichiers et limites HTTP](https://nginx.org/en/docs/http/ngx_http_core_module.html), [TLS Nginx](https://nginx.org/en/docs/http/ngx_http_ssl_module.html).
