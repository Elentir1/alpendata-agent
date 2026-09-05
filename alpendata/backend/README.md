# API AlpenData

Premier socle de gestion des entreprises et des espaces personnels, indépendant des services de gestion d’Hermes. Il ne s’agit pas encore d’une application accessible aux clients.

## Fonctions présentes

- Entreprises, membres administrateurs/collaborateurs et licences du pilote.
- Invitations nominatives, révocables, expirantes et utilisables une fois ; les invitations en attente réservent une place.
- Sessions opaques stockées sous forme d’empreinte, révocation et vérification de l’état du compte.
- Connexion Microsoft organisationnelle par MSAL, avec retour `form_post`, PKCE, nonce, tentative liée au navigateur et consommation unique.
- Onboarding propre à chaque membre, y compris l’administrateur.
- Ressources personnelles accessibles uniquement à leur propriétaire dans son entreprise ; aucun contournement lié au rôle administrateur.
- Migration Alembic et contraintes de propriété en base.

Les sessions sont émises uniquement par le serveur après le parcours Microsoft. Aucun endpoint ne permet de déclarer librement son identité ou son rôle ; aucun compte de démonstration n’est intégré. Les tests emploient des identités synthétiques et un transport Microsoft simulé en conservant la véritable bibliothèque MSAL. Aucune connexion à un compte Microsoft réel n’a encore été validée.

La connexion aux données Microsoft 365, le moteur Hermes, les automatisations et Stripe restent à intégrer. La connexion à AlpenData n’accorde aucun accès aux e-mails ou aux fichiers.

**Invitations :** après connexion, le collaborateur demande une vérification avec `POST /api/invitations/verify`. Le serveur envoie un lien à la seule adresse enregistrée par l’administrateur. La preuve expire après 15 minutes et ne fonctionne que pour le compte demandeur et cette invitation. `POST /api/invitations/accept` demande le jeton d’invitation et `verification_token`. Une adresse précédemment vérifiée ou déclarée par Microsoft ne contourne jamais cette preuve. Le lien initial est encore retourné à l’administrateur pour partage manuel ; son envoi automatique reste à intégrer. L’écran `/join` est maintenant présent dans `alpendata/frontend`.

`personal-resources` sert à vérifier le contrat de propriété du stockage AlpenData. Ces données ne sont pas encore les conversations ou la mémoire du moteur Hermes. Le champ `step` de l’onboarding reste à `connect_tools` après les premières réponses : cette sauvegarde ne simule pas une connexion Microsoft réussie.

## Installation et démarrage local

Python 3.11 à 3.13, `uv` et PostgreSQL sont requis pour un environnement représentatif. Depuis ce dossier :

```sh
uv sync --locked --group dev
export ALPENDATA_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST/DATABASE'
uv run alembic upgrade head
uv run uvicorn alpendata_api.app:from_environment --factory --host 127.0.0.1 --port 8080
```

Sous PowerShell, définir la variable avec `$env:ALPENDATA_DATABASE_URL`. Utiliser un compte PostgreSQL dédié et des secrets locaux, jamais des identifiants enregistrés dans Git. Les migrations sont exécutées explicitement avant le démarrage, pas à chaque démarrage de l’API.

`GET /health/live` vérifie que le processus répond. Les routes métier acceptent une session opaque par cookie `HttpOnly; Secure; SameSite=Lax`, ou par `Authorization: Bearer …` pour un client serveur. Toute mutation utilisant le cookie doit fournir l’en-tête `Origin` exact du produit. La capacité initiale du pilote est de trois places ; ce paramètre serveur n’est pas encore piloté par un abonnement payant.

## Configuration Microsoft

Configurer une application web confidentielle Entra acceptant les comptes organisationnels. Enregistrer exactement `https://DOMAINE/api/auth/microsoft/callback` comme URI de redirection web, puis fournir au serveur :

| Variable | Contenu |
|---|---|
| `ALPENDATA_PUBLIC_ORIGIN` | Origine HTTPS, sans chemin ni barre oblique finale. |
| `ALPENDATA_MICROSOFT_CLIENT_ID` | Identifiant de l’application Entra. |
| `ALPENDATA_MICROSOFT_CLIENT_SECRET` | Secret client, conservé uniquement côté serveur. |
| `ALPENDATA_CREDENTIAL_KEYS` | Clés Fernet séparées par des virgules ; la première chiffre, les suivantes permettent la rotation. |

Créer la clé Fernet avec `Fernet.generate_key()` depuis un environnement de confiance et la conserver dans le gestionnaire de secrets de l’environnement, séparément de PostgreSQL. Elle chiffre notamment les vérificateurs PKCE stockés pendant une tentative de connexion. Aucune valeur par défaut ne permet d’activer le parcours sans secrets.

Le navigateur consulte `GET /api/auth/options`, puis appelle `POST /api/auth/microsoft/start` avec son origine. Microsoft renvoie le résultat par formulaire POST : aucun code d’autorisation n’est placé dans l’URL de retour. Le cookie temporaire de tentative est `SameSite=None` pour ce retour entre sites ; seul le cookie de session durable est `SameSite=Lax`. Le retour final vise exclusivement l’origine configurée.

L’identité est définie par le couple organisation Microsoft (`tid`) et objet utilisateur (`oid`). Les champs e-mail/UPN ne fusionnent jamais des comptes et ne vérifient pas l’adresse d’une invitation. Références : [claims Microsoft](https://learn.microsoft.com/en-us/entra/identity-platform/id-token-claims-reference), [MSAL Python](https://msal-python.readthedocs.io/en/latest/index.html).

Avant exposition publique : tester Entra et le relais SMTP réels, fournir HTTPS et des limites de débit au point d’entrée, et interdire la journalisation des en-têtes d’authentification, cookies et corps OAuth. Le code filtre les avertissements OIDC susceptibles de contenir des claims ; il ne remplace pas la configuration des journaux du proxy ou de l’hébergeur.

SQLite est utilisable pour les tests rapides avec une URL `sqlite:///…`. Il ne valide pas les verrous de concurrence PostgreSQL et ne constitue pas la configuration de production.

## Messages de vérification

Configurer `ALPENDATA_SMTP_HOST`, `ALPENDATA_SMTP_PORT` (465 par défaut), `ALPENDATA_SMTP_SENDER`, `ALPENDATA_SMTP_USERNAME` et `ALPENDATA_SMTP_PASSWORD`. Le transport exige TLS dès la connexion, la validation du certificat et une authentification SMTP ; il n’utilise aucune messagerie personnelle de collaborateur.

Le message est disponible en français et anglais. Le jeton de preuve ne revient jamais dans la réponse API et n’est conservé qu’en empreinte en base. Les demandes sont limitées à une par minute et cinq par heure pour une invitation. Un échec SMTP invalide la preuve dans la transaction : un éventuel message arrivé malgré une coupure ne peut pas accorder d’accès. Une nouvelle tentative doit être demandée explicitement.

Aucun mail réel n’a été envoyé pendant le développement. Le transport a été vérifié avec un serveur SMTP local utilisant un certificat de test, et le refus d’un certificat non approuvé a été exercé.

## Vérifications

Depuis la racine du fork, avec `HERMES_PYTHON` pointant vers le Python de l’environnement dédié :

```sh
scripts/run_tests.sh alpendata/backend/tests -- -c alpendata/backend/pyproject.toml
```

Sur un hôte Linux disposant des binaires PostgreSQL :

```sh
scripts/run_tests.sh alpendata/backend/tests -- \
  -c alpendata/backend/pyproject.toml \
  --postgresql-bin /usr/lib/postgresql/17/bin
```

Cette seconde commande crée des serveurs PostgreSQL temporaires, accessibles exclusivement par des sockets Unix dans des dossiers privés. Elle ne se connecte pas à une base existante. Ne pas l’exécuter en tant que root. La création depuis les migrations et la cohérence entre schéma et modèles sont vérifiées avant chaque scénario.

Les scénarios couvrent les accès croisés entre entreprises, la confidentialité vis-à-vis de l’administrateur, la révocation de session, la désactivation d’un membre, les licences et invitations. Ils exercent également MSAL avec un serveur Microsoft simulé : liaison au navigateur, PKCE, usage unique, identité stable, refus des réponses invalides et protection des cookies. Le scénario Linux supplémentaire exerce simultanément deux invitations pour la dernière place et deux acceptations du même lien.

Ces tests portent sur l’API et sa base. La séparation des processus Hermes et de leurs fichiers devra être vérifiée séparément lors de leur intégration.
