# API AlpenData

Premier socle de gestion des entreprises et des espaces personnels, indépendant des services de gestion d’Hermes. Il ne s’agit pas encore d’une application accessible aux clients.

## Fonctions présentes

- Entreprises, membres administrateurs/collaborateurs et licences du pilote.
- Invitations nominatives, révocables, expirantes et utilisables une fois ; les invitations en attente réservent une place.
- Sessions opaques stockées sous forme d’empreinte, révocation et vérification de l’état du compte.
- Connexion Microsoft organisationnelle par MSAL, avec retour `form_post`, PKCE, nonce, tentative liée au navigateur et consommation unique.
- Onboarding propre à chaque membre, y compris l’administrateur.
- Ressources personnelles accessibles uniquement à leur propriétaire dans son entreprise ; aucun contournement lié au rôle administrateur.
- Connexion Microsoft 365 personnelle avec choix des accès, cache MSAL chiffré, renouvellement et déconnexion.
- Lecture des dix derniers mails, des rendez-vous des sept prochains jours et recherche de fichiers OneDrive/SharePoint sous les droits du compte connecté.
- Migration Alembic et contraintes de propriété en base.

Les sessions sont émises uniquement par le serveur après le parcours Microsoft. Aucun endpoint ne permet de déclarer librement son identité ou son rôle ; aucun compte de démonstration n’est intégré. Les tests emploient des identités synthétiques et un transport Microsoft simulé en conservant la véritable bibliothèque MSAL. Aucune connexion à un compte Microsoft réel n’a encore été validée.

Les premiers accès de lecture Microsoft 365 sont implémentés ; leur validation avec Entra/Graph réels reste à réaliser. Le runtime isolé du moteur Hermes est implémenté et décrit dans `../runtime/README.md` ; son raccordement aux conversations, les automatisations et Stripe restent à intégrer. La connexion à AlpenData n’accorde aucun accès aux e-mails ou aux fichiers.

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

Configurer une application web confidentielle Entra acceptant les comptes organisationnels. Enregistrer exactement `https://DOMAINE/api/auth/microsoft/callback` et `https://DOMAINE/api/integrations/microsoft/callback` comme URI de redirection web, puis fournir au serveur :

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

Ces tests portent sur l’API et sa base. La séparation des processus Hermes et de leurs fichiers est vérifiée séparément par `test_runtime.py`, avec une image réelle et `--runtime-image`. Ce scénario ne valide pas encore le chat web ni le fournisseur IA réel.

## Connexions Microsoft 365 personnelles

Après son onboarding, chaque utilisateur choisit les accès de lecture à activer. Le consentement est séparé de la connexion à AlpenData et utilise le même compte, dans le même annuaire Microsoft. Les permissions déléguées sont `Mail.Read`, `Calendars.Read` et `Files.Read.All` selon le choix ; MSAL ajoute les scopes OIDC et `offline_access`. Les politiques de l’organisation Microsoft peuvent exiger un consentement administrateur. Aucune permission d’application ni permission d’envoi ou de modification n’est demandée.

| Route sous `/api/organizations/{organization_id}/microsoft` | Fonction |
|---|---|
| `GET` | État et accès du seul utilisateur authentifié. |
| `POST /connect` | Démarrer son consentement ; corps `capabilities` parmi `mail`, `calendar`, `files`. |
| `DELETE` | Effacer son cache de jetons et invalider ses consentements en cours. |
| `GET /mail` | Lire jusqu’à dix mails de sa boîte. |
| `GET /calendar` | Lire jusqu’à vingt rendez-vous sur sept jours. |
| `POST /files/search` | Rechercher jusqu’à dix fichiers ; corps `query`, entre 1 et 256 caractères. |

Le cache MSAL est chiffré et lié à l’entreprise, au propriétaire et à la connexion. L’API ne permet pas de choisir un propriétaire, une boîte mail ou une URL Microsoft. L’administrateur ne dispose d’aucun contournement. Une déconnexion pendant le retour OAuth empêche la réactivation des jetons ; un compte ou un membre désactivé ne peut pas terminer son consentement. Le serveur conserve un cache renouvelé, demande une reconnexion en cas de révocation et conserve le consentement pendant une indisponibilité temporaire du fournisseur.

La déconnexion retire l’accès d’AlpenData pour cette entreprise ; elle ne supprime pas le consentement global de l’application dans Microsoft et ne déconnecte pas les autres applications de l’utilisateur. Les cookies et l’état HTTP ne sont pas partagés entre les lectures des collaborateurs. Les réponses Graph sont limitées à 2 Mio ; les redirections et liens de pagination ne sont pas suivis. Une limitation Microsoft revient avec `Retry-After`, sans boucle automatique de nouvelles lectures. Aucun contenu de mail ou fichier n’est conservé par ces routes de lecture.

La recherche retourne les métadonnées et liens web des fichiers accessibles. Elle ne télécharge pas encore leur contenu et ne remplace pas une validation des droits SharePoint sur un tenant réel. Les liens de téléchargement préautorisés ne sont pas transmis au navigateur. Le chat utilise désormais le même service de lecture avec les droits de son propriétaire ; les tâches planifiées restent à relier.

Références : [mails Graph](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0), [calendrier Graph](https://learn.microsoft.com/en-us/graph/api/calendar-list-calendarview?view=graph-rest-1.0), [recherche Microsoft](https://learn.microsoft.com/en-us/graph/api/search-query?view=graph-rest-1.0), [permissions](https://learn.microsoft.com/en-us/graph/permissions-reference).

## Passerelle Mistral/OpenRouter

La [passerelle de modèles](../docs/PASSERELLE_MODELES.md) est implémentée et exercée avec Hermes réel et un fournisseur HTTP local synthétique. Les clés et le routage sont contrôlés par le serveur ; la consommation vient de la réponse du fournisseur.

## Chat et processus de travail

Le [chat personnel](../docs/CHAT_PERSONNEL.md) ajoute la migration `0005`, les conversations, les tours idempotents et les relevés de modèle par propriétaire. Ses routes se trouvent sous `/api/organizations/{organization_id}/chat`. L’API enregistre le travail ; le processus séparé `uv run python -m alpendata_api.chat_worker` l’exécute sur Linux. Le document lié décrit la configuration complète, les droits, les interruptions et les limites restantes. Les modèles commerciaux et services Microsoft réels restent à valider.

## Onboarding et essais personnels

La migration `0006` ajoute les propositions personnalisées, les essais et les reçus de lecture. Le [parcours du premier résultat](../docs/PREMIER_RESULTAT.md) documente les routes, la validation par le broker et les limites. La création d’une conversation exige maintenant un rôle et un besoin enregistrés dans le profil personnel. Les répétitions ne sont pas encore activables.
