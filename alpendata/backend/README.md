# API AlpenData

Premier socle de gestion des entreprises et des espaces personnels, indépendant des services de gestion d’Hermes. Il ne s’agit pas encore d’une application accessible aux clients.

## Fonctions présentes

- Entreprises, membres administrateurs/collaborateurs et licences du pilote.
- Attribution des licences et modifications d’adhésion versionnées ; compteur des places attribuées, réservées et libres. Le PATCH d’un membre exige la version lue depuis la migration `0018`. Voir [Membres et licences](../docs/MEMBRES_LICENCES.md).
- Invitations nominatives, révocables, expirantes et utilisables une fois ; les invitations en attente réservent une place.
- Sessions opaques stockées sous forme d’empreinte, révocation et vérification de l’état du compte.
- Connexion e-mail/mot de passe indépendante de Microsoft, activation et récupération manuelles du pilote ; voir [Comptes AlpenData](../docs/COMPTES_ALPENDATA.md).
- Connexion Microsoft organisationnelle par MSAL, avec retour `form_post`, PKCE, nonce, tentative liée au navigateur et consommation unique.
- Onboarding propre à chaque membre, y compris l’administrateur.
- Ressources personnelles accessibles uniquement à leur propriétaire dans son entreprise ; aucun contournement lié au rôle administrateur.
- Connexion Microsoft 365 personnelle avec choix des accès, cache MSAL chiffré, renouvellement et déconnexion.
- Lecture des dix derniers mails, des rendez-vous des sept prochains jours et recherche de fichiers OneDrive/SharePoint sous les droits du compte connecté.
- Migration Alembic et contraintes de propriété en base.

Les sessions sont émises uniquement par le serveur après authentification Microsoft, authentification par mot de passe ou activation d'un compte préalablement provisionné. Aucun endpoint ne permet de déclarer librement son identité ou son rôle ; aucun compte de démonstration n’est intégré. Les tests emploient des identités synthétiques et un transport Microsoft simulé en conservant la véritable bibliothèque MSAL. Aucune connexion à un compte Microsoft réel n’a encore été validée.

Les premiers accès de lecture Microsoft 365 sont implémentés ; leur validation avec Entra/Graph réels reste à réaliser. Le runtime isolé du moteur Hermes est raccordé aux conversations et aux récurrences personnelles, et décrit dans `../runtime/README.md`. Stripe reste à intégrer. La connexion à AlpenData n’accorde aucun accès aux e-mails ou aux fichiers.

La migration `0008` ajoute la publication et le téléchargement de documents personnels depuis le chat. Le contenu reste privé, immuable et rattaché au tour. Les limites et la génération des quatre formats sont décrites dans [Documents](../docs/DOCUMENTS.md).

**Invitations :** après connexion, le collaborateur demande une vérification avec `POST /api/invitations/verify`. Le serveur envoie un lien à la seule adresse enregistrée par l’administrateur. La preuve expire après 15 minutes et ne fonctionne que pour le compte demandeur et cette invitation. `POST /api/invitations/accept` demande le jeton d’invitation et `verification_token`. Une adresse précédemment vérifiée ou déclarée par Microsoft ne contourne jamais cette preuve. Le formulaire administrateur utilise maintenant l'envoi direct par SMTP, avec reçus et protection contre les doublons. L'ancienne route de création de lien reste disponible pour les clients API ; voir [Invitations par e-mail](../docs/INVITATIONS_EMAIL.md). L’écran `/join` est maintenant présent dans `alpendata/frontend`.

`personal-resources` sert à vérifier le contrat de propriété du stockage AlpenData. Ces données sont distinctes des conversations et de la mémoire du moteur Hermes. Le véritable magasin mémoire est accessible au seul propriétaire via les routes `memory`, décrites dans [Mémoire personnelle](../docs/MEMOIRE_PERSONNELLE.md). Le champ `step` de l’onboarding reste à `connect_tools` après les premières réponses : cette sauvegarde ne simule pas une connexion Microsoft réussie.

## Installation et démarrage local

Python 3.11 à 3.13, `uv` et PostgreSQL sont requis pour un environnement représentatif. Depuis ce dossier :

```sh
uv sync --locked --group dev
export ALPENDATA_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@HOST/DATABASE'
uv run alembic upgrade head
uv run uvicorn alpendata_api.app:from_environment --factory --host 127.0.0.1 --port 8080
```

Sous PowerShell, définir la variable avec `$env:ALPENDATA_DATABASE_URL`. Utiliser un compte PostgreSQL dédié et des secrets locaux, jamais des identifiants enregistrés dans Git. Les migrations sont exécutées explicitement avant le démarrage, pas à chaque démarrage de l’API.

`GET /health/live` vérifie que le processus répond. `GET /health/ready` vérifie la connexion et la révision Alembic attendue ; une incompatibilité empêche aussi le démarrage de l'API. Voir [Entrée HTTPS et démarrage](../docs/ENTREE_HTTPS.md) pour servir la compilation frontend et l'API sous une même origine. Les routes métier acceptent une session opaque par cookie `HttpOnly; Secure; SameSite=Lax`, ou par `Authorization: Bearer …` pour un client serveur. Toute mutation utilisant le cookie doit fournir l’en-tête `Origin` exact du produit. La capacité initiale du pilote est de trois places ; ce paramètre serveur n’est pas encore piloté par un abonnement payant.

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

Pour inclure les exercices de chiffrement, installer `age` et `age-keygen` dans l’hôte Linux, puis ajouter `--age-bin /usr/bin/age` et l’option `--runtime-image` déjà utilisée pour les conteneurs Hermes. Sans `--age-bin`, les deux scénarios de chiffrement sont explicitement ignorés ; cela ne valide pas ce parcours.

Cette seconde commande crée des serveurs PostgreSQL temporaires, accessibles exclusivement par des sockets Unix dans des dossiers privés. Elle ne se connecte pas à une base existante. Ne pas l’exécuter en tant que root. La création depuis les migrations et la cohérence entre schéma et modèles sont vérifiées avant chaque scénario.

Les scénarios couvrent les accès croisés entre entreprises, la confidentialité vis-à-vis de l’administrateur, la révocation de session, la désactivation d’un membre, les licences et invitations. Ils exercent également MSAL avec un serveur Microsoft simulé : liaison au navigateur, PKCE, usage unique, identité stable, refus des réponses invalides et protection des cookies. Le scénario Linux supplémentaire exerce simultanément deux invitations pour la dernière place et deux acceptations du même lien.

Ces tests portent sur l’API et sa base. La séparation des processus Hermes et de leurs fichiers est vérifiée séparément par `test_runtime.py`, avec une image réelle et `--runtime-image`. Ce scénario ne valide pas encore le chat web ni le fournisseur IA réel.

## Connexions Microsoft 365 personnelles

Après son onboarding, chaque utilisateur choisit les accès de lecture à activer. Le consentement est séparé de la connexion à AlpenData et utilise le même compte, dans le même annuaire Microsoft. Les permissions déléguées sont `Mail.Read`, `Calendars.Read` et `Files.Read.All` selon le choix ; MSAL ajoute les scopes OIDC et `offline_access`. Les politiques de l’organisation Microsoft peuvent exiger un consentement administrateur. Les enregistrements SharePoint confirmés demandent séparément `Files.ReadWrite.All` ; les envois demandent `Mail.Send`, avec confirmation par défaut ou autonomie personnelle explicitement autorisée. Les règles de l’entreprise doivent aussi les permettre. Aucune permission d’application n’est demandée. Voir [E-mails](../docs/EMAILS.md), [Autonomie personnelle](../docs/AUTONOMIE.md) et [Enregistrement SharePoint](../docs/ENREGISTREMENT_SHAREPOINT.md).

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

## Sauvegarde et restauration

La commande locale `python -m alpendata_api.backup` crée un ensemble PostgreSQL + états privés et restaure uniquement vers une base vide et un dossier neuf. Les tâches restaurées sont suspendues et les connexions doivent être rétablies. Aucun service n’est démarré automatiquement. La commande distincte `python -m alpendata_api.backup_encryption` [chiffre ces ensembles avec age](../docs/CHIFFREMENT_SAUVEGARDES.md) avant leur conservation hors hôte. Aucun transfert distant n’est encore intégré ; voir la [procédure et ses limites](../docs/SAUVEGARDE_RESTAURATION.md).

## Abonnements et licences

La migration `0020` et les routes `/api/organizations/{organization_id}/billing` relient les licences à Stripe Checkout et au portail. Les notifications signées relisent l'abonnement actuel avant de modifier les droits ; voir [Abonnements et licences Stripe](../docs/FACTURATION_STRIPE.md) pour les secrets serveur, la configuration du Price CHF et du portail, les reprises et les validations externes restantes.

## Services continus

Les workers terminent leur itération courante sur SIGTERM/SIGINT, puis quittent sans prendre le travail suivant. Le générateur `python -m alpendata_api.service_units` prépare les unités utilisateur de l'API, du worker et du planificateur ; `--with-billing` ajoute l'actualisation automatique des abonnements Stripe. Voir [Services continus et maintenance](../docs/SERVICES_CONTINUS.md) pour le démarrage, les arrêts, la limite de redémarrages et les vérifications avant sauvegarde.

## Récupération opérateur

L'outil local `python -m alpendata_api.runtime_recovery` permet le diagnostic et la récupération ciblée des conteneurs orphelins, sous verrous PostgreSQL et du volume personnel. Il ne demande aucune clé modèle ou Microsoft. Voir la [procédure opérateur](../docs/RECUPERATION_RUNTIME.md).

## Onboarding et essais personnels

La migration `0016` ajoute les [notifications personnelles](../docs/NOTIFICATIONS.md), écrites avec les résultats et blocages des automatisations. Les routes de liste, compteur et lecture conservent les mêmes frontières de propriétaire, y compris face à l'administrateur de l'entreprise.

La migration `0006` ajoute les propositions personnalisées, les essais et les reçus de lecture. Le [parcours du premier résultat](../docs/PREMIER_RESULTAT.md) documente les routes, la validation par le broker et les limites. La création d’une conversation exige maintenant un rôle et un besoin enregistrés dans le profil personnel. Les répétitions sont activables après revue d’un essai depuis la migration `0007`. Le processus `uv run python -m alpendata_api.schedule_worker` alimente la file du chat ; voir [Automatisations](../docs/AUTOMATISATIONS.md).
