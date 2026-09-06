# Vérification du premier backend

## Comptes indépendants et onboarding sans Microsoft — 6 septembre 2026

La migration `0022` ajoute les comptes par mot de passe et la limitation persistante des tentatives. La suite complète passe **96 tests dans 51 fichiers sous Linux/PostgreSQL**, sans échec ni scénario ignoré, avec Podman, age, Nginx et systemd utilisateur réels. Le lanceur officiel a utilisé quatre workers et aucune nouvelle tentative automatique (`HERMES_TEST_FILE_RETRIES=0`), pour 298 secondes d'exécution après précompilation. Un premier passage avec 32 workers avait produit trois échecs dans les fichiers runtime, sauvegarde et mémoire, dont des délais d'attente de la commande Podman ; tous passent lors du passage complet à quatre workers, sans modifier les délais de production.

L'interface passe **44 scénarios JSDOM** et sa compilation TypeScript/Vite. Ruff et `git diff --check` passent. Cette étape ne constitue pas une recette de connexion dans un navigateur sur le domaine public.

Les nouveaux scénarios exercent le CLI réel avec fichiers temporaires privés, l'activation unique concurrente, le choix et le changement de mot de passe, la révocation des sessions, la récupération, l'invalidation après restauration, les limites persistantes et les erreurs sans secrets. Un compte indépendant connecte ensuite son propre compte Microsoft avec MSAL réel et un transport synthétique : l'administrateur ne reçoit pas ses jetons et un changement silencieux de compte source est refusé.

Un scénario complet démarre sans configuration Microsoft ni SMTP, active un compte AlpenData, crée l'entreprise et le profil personnel, fait enregistrer des propositions par Hermes, exécute un essai puis une occurrence planifiée sans sources externes. Le modèle HTTP fournit des réponses synthétiques ; les conteneurs et la boucle Hermes sont réels. Le résultat indique qu'il part des informations saisies, sans prétendre vérifier des fichiers ou des e-mails. Image inchangée : `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b`.

L'environnement Jelastic existant a été démarré et son terminal Web SSH ouvert. Le diagnostic constate un accès root, Docker, systemctl et Python 3, mais aucun Podman installé ; `docker ps` ne liste aucun conteneur actif. La limite `user.max_user_namespaces` est non nulle, sans que cela prouve encore l'exécution imbriquée sans privilèges. Aucun code AlpenData, secret Mistral, compte réel ou configuration DNS/TLS n'a été déployé à cette étape.

## Actualisation autonome de la facturation — 6 septembre 2026

La suite complète passe **90 scénarios Linux/PostgreSQL**, dans 47 fichiers, sans échec, scénario ignoré ni relance automatique. Les exercices incluent le runtime Hermes inchangé, age, Nginx et les unités systemd. Les six scénarios Stripe ciblés donnent quatre succès sur Windows/SQLite et deux exclusions Linux explicites. Le frontend passe **42 scénarios JSDOM** et son build TypeScript/Vite ; Ruff et la vérification Git passent.

Le nouveau service lit les abonnements via le SDK officiel sur un vrai serveur HTTP local, sans notification Stripe ni clic administrateur. Un renouvellement prolonge la confirmation à la nouvelle échéance, une panne conserve exactement la confirmation précédente, puis une résiliation retire l'accès au contrôle suivant. Les échéances de reprise survivent au remplacement de l'objet worker et empêchent une boucle immédiate de nouvelles tentatives.

Un scénario PostgreSQL retient la réponse d'une première entreprise pendant qu'une seconde instance vérifie la suivante. Les deux clients ne sont lus qu'une fois, le client en erreur conserve sa confirmation antérieure et un client d'un autre environnement Stripe n'est jamais appelé. Les scénarios de services lancent aussi la commande de facturation sans configuration de modèle ou runtime, contrôlent ses signaux d'arrêt et son refus d'une base incompatible. L'unité facultative est réellement chargée puis arrêtée et retirée du gestionnaire systemd utilisateur avec les trois autres unités temporaires. Aucun appel commercial n'est fait par cet exercice système, dont la base ne contient aucun client Stripe lié.

L'interface vérifie en JSDOM l'affichage de l'erreur d'actualisation puis sa disparition après confirmation côté serveur. La base locale dispose de `preview.before-0021.db`, est migrée en `0021` et son API redémarrée répond à `/health/ready`. Microsoft, SMTP et Stripe restent non configurés dans l'aperçu réel. Le service de facturation permanent, sa surveillance externe et ses appels Stripe réels restent à déployer et valider ; voir [Facturation Stripe](FACTURATION_STRIPE.md) et [Services continus](SERVICES_CONTINUS.md).

## Abonnements et licences Stripe — 6 septembre 2026

La suite complète passe **88 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, dans 46 fichiers. Elle inclut les exercices Hermes conteneurisés, age, Nginx et systemd, avec l'image runtime inchangée `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b`. Les nouveaux scénarios Stripe passent également sous Windows/SQLite, sauf le contrôle du worker marqué Linux. Le frontend passe **42 scénarios JSDOM** ; son build TypeScript/Vite final et Ruff passent. Le verrou uv est cohérent et conserve les versions précédentes des autres paquets.

Le SDK Stripe officiel `15.6.1` effectue les appels HTTP vers un serveur local. Les tests vérifient les demandes avec réponses perdues, le remplacement de l'application, les clés durables, deux reprises concurrentes PostgreSQL, la reprise d'une session expirée et les frontières administrateur/entreprise. Les signatures réelles sont vérifiées par le SDK. Une facture non payée retire les droits, puis le même événement rejoué relit l'état payé ; sa réutilisation après résiliation ne réactive pas l'abonnement. Le véritable worker refuse l'autorisation du travail et la livraison d'une réponse après révocation. La réduction de capacité conserve l'administration, et le retrait d'une licence excédentaire rétablit l'accès. Une restauration impose une nouvelle confirmation Stripe.

Les scénarios de navigateur simulé vérifient la conservation de la quantité, de la langue et de la référence après rechargement, l'absence de navigation en cas de réponse perdue, le contrôle des destinations Stripe et la suspension jusqu'à confirmation côté serveur. Le build est également vérifié visuellement en français et anglais sur un aperçu affichant explicitement des données et prix fictifs ; l'espacement des boutons a été corrigé. Cette vérification n'accède pas aux pages de paiement réelles de Stripe.

La base locale a été sauvegardée dans `preview.before-0020.db`, migrée vers `0020`, puis l'API redémarrée. `/health/ready` répond, les cinq routes de facturation sont présentes, l'accès non authentifié est refusé et le webhook répond `billing_not_configured`. Aucun compte ou paiement Stripe réel n'a été utilisé. Le prix commercial, les conditions d'impayés, Stripe Tax, la consommation et la recette Stripe publique restent à finaliser. Voir [Abonnements et licences Stripe](FACTURATION_STRIPE.md).

## Invitations directes par e-mail — 6 septembre 2026

La suite complète finale passe **84 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique. Les services systemd temporaires, Nginx, age et l'image Hermes inchangée `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b` sont inclus. Le frontend passe **40 scénarios JSDOM** ; TypeScript, Vite, Ruff et la vérification Git passent. Les quatre scénarios ciblés migration/invitation/propriété passent également sur Windows/SQLite.

Le parcours utilise un vrai serveur SMTP TLS local avec authentification. Deux appels concurrents PostgreSQL portant le même UUID produisent une invitation et un seul e-mail initial. Une relecture ne renvoie aucun jeton brut. Le destinataire doit encore obtenir une preuve d'adresse liée à son compte ; un autre compte ne peut pas l'utiliser. L'acceptation ne provoque aucun nouvel envoi. Un accusé perdu après réception par le serveur SMTP laisse un reçu incertain, sans répétition du message. Les invitations annulées, les demandes restées en cours et la limite d'envoi sont vérifiées.

Le test de migration a d'abord reproduit un refus SQLite : la recréation de la table aurait supprimé une table encore référencée par une preuve existante. La migration ajoute désormais ses colonnes et son index sans cette recréation. Une base `0018` contenant une invitation et sa preuve conserve leur association et leurs empreintes, sur SQLite et PostgreSQL. Le contrôle de propriété existant a été adapté pour autoriser uniquement les nouveaux champs publics de suivi ; il continue d'exclure les jetons et les contenus privés.

L'interface est vérifiée dans le navigateur avec un bandeau explicite de données fictives : formulaire français, choix de langue de l'e-mail, présentation anglaise, état transmis et invitations incertaines. Le statut est placé sous l'adresse pour éviter la juxtaposition des textes. Les tests JSDOM vérifient également le maintien du même UUID après une réponse perdue et l'affichage d'une annulation.

La base locale dispose d'une copie `preview.before-0019.db` et est migrée vers `0019`. L'ancienne API a été remplacée par la version courante ; `/health/ready` répond et la nouvelle route est présente. Microsoft et SMTP restent non configurés dans cette API locale. Le serveur de vérification visuelle utilise uniquement des réponses fictives, sans accès au backend ni envoi externe. La réception dans les messageries du client et son parcours Entra restent à valider. Voir [Invitations par e-mail](INVITATIONS_EMAIL.md).

## Services continus et arrêts de maintenance — 6 septembre 2026

La suite complète finale passe **81 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec le gestionnaire utilisateur **systemd 257 (257.7-1)**. L'image runtime reste `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b`. Les exercices HTTPS et age sont aussi inclus. Ruff, le format des fichiers concernés et la vérification Git passent. Aucun changement de schéma, d'image runtime ni d'interface ; la compilation et les tests frontend précédents n'ont pas été répétés.

Un véritable processus worker exécute Hermes dans son conteneur personnel et attend une réponse HTTP synthétique. SIGTERM arrive pendant cette attente ; le résultat courant est ensuite enregistré, le processus quitte avec le code zéro et le travail d'un autre propriétaire reste en attente. Les commandes réelles chat et scheduler s'arrêtent aussi au repos sur SIGTERM/SIGINT. Une base incompatible est refusée avant traitement, avec code non nul et événement expurgé. Le gestionnaire de signal ne prend aucun verrou Python : il enregistre la demande et le descripteur de réveil interrompt l'attente de la boucle.

Les unités sont produites par la commande opérateur, liées au gestionnaire systemd utilisateur sous des noms uniques, puis réellement démarrées. L'API répond sur son port local, le worker au repos redémarre après SIGKILL, et l'arrêt explicite laisse les processus inactifs avec un code zéro. Une base incompatible provoque exactement trois démarrages refusés puis un état d'échec ; la correction de la base et la remise à zéro de cet échec permettent un nouveau démarrage. Les chemins de travail et du fichier d'environnement contiennent des espaces dans ces exercices. Les candidats existants ne sont pas remplacés.

Les premiers essais ont permis de corriger la syntaxe des chemins `WorkingDirectory` et `EnvironmentFile`, dont systemd conservait les guillemets, et de raccorder explicitement le test au répertoire du gestionnaire utilisateur réel. L'environnement des services de test désactive les connexions commerciales, indépendamment de celui du gestionnaire. Tous les liens et services temporaires sont retirés ; aucun service permanent n'est activé. Les journaux laissés par ces exercices contiennent uniquement leurs paramètres et données synthétiques.

L'option `--systemd-user` s'ajoute à `--postgresql-bin`, `--runtime-image`, `--age-bin`, `--nginx-bin` et `--frontend-dist` pour inclure tous les exercices. Sans cette option, les deux tests systemd sont explicitement ignorés. Le crash systemd est testé au repos ; le signal pendant un travail est testé sur un processus distinct hors systemd. L'installation persistante, l'arrêt de l'hôte, les limites du serveur et les connexions commerciales restent à valider sur Infomaniak. La prévisualisation locale n'a pas été redémarrée. Voir [Services continus et maintenance](SERVICES_CONTINUS.md).

## Entrée HTTPS et compatibilité au démarrage — 6 septembre 2026

La suite complète finale passe **77 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec l'image runtime inchangée `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b`, age 1.2.1 et Nginx **1.26.3**, paquet Debian `1.26.3-3+deb13u7`. La compilation TypeScript/Vite, Ruff, le format des fichiers concernés et la vérification Git passent. Le frontend est recompilé sans modification de ses sources ; ses 38 tests JSDOM du lot précédent n'ont pas été relancés.

Les deux scénarios HTTPS lancent le vrai Nginx avec une configuration produite par la commande opérateur, Uvicorn et PostgreSQL temporaires. Le client valide le certificat éphémère. La page, le lien d'invitation, les scripts, styles et polices compilés retrouvent leurs octets. Les chemins privés, cartes de sources, liens symboliques et hôtes étrangers sont refusés ; une erreur API conserve son contenu JSON. Les requêtes dépassant 8 Mio sont refusées. Les sessions personnelles passent par HTTPS, les mutations par cookie exigent l'origine exacte et les en-têtes de proxy fournis par le client ne contrôlent pas les redirections. Une configuration existante n'est pas écrasée.

Les deux scénarios de santé vérifient la version réelle de la base, sa dégradation puis son rétablissement, une erreur SQL expurgée et le refus de démarrer sur une base vide sans la modifier. La suite complète couvre aussi le démarrage après restauration et les parcours Hermes existants.

Le premier essai Nginx a échoué parce que le binaire Debian cherchait encore son répertoire FastCGI système, même sans route FastCGI. Tous les répertoires temporaires sont désormais explicitement rattachés au répertoire privé de l'instance. Le binaire a été extrait du paquet Debian dans un dossier d'outils local, sans installation ni démarrage d'un service système. Les essais finaux passent sous le compte Linux non privilégié.

Les options `--nginx-bin` et `--frontend-dist` activent les deux exercices HTTPS ; elles s'ajoutent à `--postgresql-bin`, `--runtime-image` et `--age-bin` pour la suite complète. Les tests utilisent des données et sessions synthétiques. Ils vérifient le transport HTTP et les fichiers compilés, sans nouveau parcours visuel dans le navigateur ni compte Entra réel. Aucun domaine public, certificat de production, service Infomaniak ou compte client n'a été configuré. L'API de prévisualisation Windows n'a pas été redémarrée pendant ces essais. Voir [Entrée HTTPS et démarrage](ENTREE_HTTPS.md).

## Chiffrement des sauvegardes — 6 septembre 2026

La suite complète finale passe **73 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec l’image runtime inchangée `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b` et le programme age **1.2.1** du paquet Debian `1.2.1-1+b5`. Ruff, le format des nouveaux fichiers et la vérification Git passent. Aucune migration, route cliente ou modification d’interface n’est ajoutée.

Le nouveau parcours chiffre un ensemble réel PostgreSQL + états personnels pour deux clés de récupération indépendantes. La commande de déchiffrement retourne un ensemble vérifié, puis une nouvelle base PostgreSQL et de nouveaux fichiers sont restaurés. Les données privées retrouvent leurs octets ; les sessions sont révoquées et les caches Microsoft sont retirés dans la cible. Les clés sont éphémères et les données synthétiques.

Les refus couvrent une mauvaise clé, une identité lisible par d’autres utilisateurs, un fichier tronqué après plusieurs blocs, une altération du contenu, un reçu qui ne correspond pas, une cible existante, une enveloppe contenant un chemin extérieur et un ensemble source incomplet. La troncature est aussi testée avec une empreinte recalculée, pour exercer réellement l’authentification finale de age. Aucun dossier final en clair n’est publié dans ces cas. Les fichiers temporaires en clair sont séparés du répertoire de sortie chiffrée ; le manifeste et les octets effectivement empaquetés sont vérifiés avant chiffrement.

La première suite complète a révélé un ancien scénario de planification dépendant de l’horloge réelle : `now() - 20 - offset` pouvait donner le même horaire deux fois. Ce scénario utilise désormais un instant fixe et des échéances distinctes, transmis au véritable ticker. La suite complète finale passe après cette correction, sans modifier le comportement du scheduler en production.

L’option `--age-bin /usr/bin/age` est nécessaire pour inclure les exercices de chiffrement. Le paquet age a été installé dans l’environnement Debian local depuis le dépôt signé ; la source Redis déjà mal formée n’a pas été modifiée. Aucun stockage Infomaniak ni clé de production n’a été configuré. L’API locale et sa base `0018` sont inchangées. Voir [Chiffrement et clés de récupération](CHIFFREMENT_SAUVEGARDES.md) pour la procédure, le reçu indépendant et les limites du stockage temporaire.

## Sauvegarde et restauration locales — 6 septembre 2026

La suite complète passe **71 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec l’image runtime inchangée `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b`. Ruff, le format des fichiers concernés et la vérification Git passent. Ce lot ajoute uniquement un outil opérateur et sa documentation : aucune migration, route client ou modification d’interface.

Le premier exercice crée un PDF privé via le broker, une mémoire avec le vrai magasin Hermes exécuté en OCI, une récurrence revue et un tour en attente. Il sauvegarde PostgreSQL et les fichiers sous verrous, modifie ensuite un fichier source, puis restaure vers une nouvelle base PostgreSQL et un nouveau dossier. Le PDF récupéré garde les octets sauvegardés ; Hermes relit la mémoire restaurée. Les anciennes sessions sont refusées, les connexions Microsoft sont déconnectées, la tâche reste suspendue et le tour devient interrompu. Un administrateur ne peut pas lire le document ou le chat du collègue. Les états de la source restent inchangés.

Le second exercice vérifie les refus pendant une écriture PostgreSQL, une prise du verrou propriétaire ou la présence d’un vrai conteneur orphelin. Il exécute également la commande de sauvegarde dans un sous-processus. Un lien sortant empêche la création du manifeste final ; une altération de l’archive est détectée avant création des cibles. Même avec un manifeste recalculé, une archive qui tente de sortir de l’espace propriétaire est refusée avant restauration de la base. Les cibles existantes ne sont pas écrasées.

La première exécution a révélé que les arguments de connexion du pilote SQLAlchemy contenaient aussi son contexte Python d’adaptation. Les outils PostgreSQL utilisent désormais les paramètres de connexion de l’URL avec une liste explicite de variables libpq ; aucun contexte Python ni secret de service tiers n’est transmis. Les exercices ciblés puis la suite complète finale passent après correction.

Les bases, comptes, fichiers et services externes sont synthétiques. Les processus PostgreSQL, pg_dump, pg_restore, les verrous Linux et les conteneurs sont réels. L’API de prévisualisation normale n’a pas été modifiée et sa base reste en `0018`. L’outil produit pour l’instant un ensemble local non chiffré ; copie indépendante, chiffrement et reprise sur Infomaniak restent à réaliser. Voir [Procédure de sauvegarde et restauration](SAUVEGARDE_RESTAURATION.md).

## Partage volontaire par les collaborateurs — 6 septembre 2026

La suite complète passe **69 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec l’image runtime inchangée `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b`. Le frontend passe **38 scénarios JSDOM** ; TypeScript, Vite, Ruff et la vérification Git passent.

Les deux nouveaux scénarios API exercent la publication par un membre, l’annuaire limité de destinataires, le contrôle de l’auteur et de l’administrateur, le refus des mutations par un lecteur, les versions et la désactivation. Ils vérifient aussi qu’un document créé dans le chat est copié exactement depuis son propriétaire : un administrateur ou un collègue ne peut pas publier l’original privé, et retirer la copie laisse cet original inchangé. Les demandes rejouées restent idempotentes, y compris les anciens corps sans identifiant de document source.

Le parcours OCI utilise un collaborateur pour publier les ressources puis révoquer l’accès : Hermes réel lit la note, télécharge et ouvre le PDF sous les droits du destinataire, puis constate la révocation sans modifier le contexte système de la conversation. Les services de modèle restent synthétiques.

Les nouveaux tests d’interface couvrent la publication par un membre, la reconfirmation après modification des destinataires et le partage depuis le chat sans téléchargement préalable. Une réponse perdue conserve le même identifiant de publication et fige le formulaire. Le build a été contrôlé visuellement en français, en anglais et à une largeur mobile de 360 pixels avec des données fictives ; l’aperçu séparé a ensuite été fermé et arrêté.

L’API normale a été redémarrée et ses nouvelles routes vérifiées ; la base reste en `0018`, sans migration pour ce lot. Microsoft et les invitations par e-mail restent annoncés comme non configurés. Aucun compte client, service commercial ou paiement réel n’a été utilisé. Voir [Ressources d’entreprise](RESSOURCES_ENTREPRISE.md).

## Administration des membres et licences — 6 septembre 2026

La suite complète passe **67 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec l’image runtime inchangée `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b`. Le frontend passe **36 scénarios JSDOM** ; ses deux nouveaux scénarios passent également après le traitement des erreurs de relecture. TypeScript, Vite, Ruff et la cohérence des migrations passent.

Les tests vérifient le compteur des places, les invitations réservées, les attributions, la gestion sans licence et le maintien du dernier administrateur. Des mutations PostgreSQL simultanées ne peuvent ni utiliser deux fois la dernière place, ni écraser les changements d’un autre administrateur avec une version dépassée. Les parcours de chat, mémoire, notifications et automatisations continuent à refuser les opérations après retrait de licence ou désactivation. Le PATCH exige désormais la version de l’adhésion, y compris dans ces tests existants.

L’interface exige de confirmer les choix actuels et de relire après une réponse perdue. Elle actualise le compte connecté après une mutation et efface les données administratives lors d’un refus d’accès à la relecture. La liste, les compteurs et la modification d’accès ont été contrôlés visuellement en français, en anglais et dans un viewport mobile de 360 × 780 avec des données fictives.

La base normale a été sauvegardée dans `preview.before-0018.db`, migrée en `0018` avec conservation des adhésions, puis l’API redémarrée. La capacité reste configurée côté serveur pour le pilote. Aucun achat, paiement, appel de compte Stripe ou changement tarifaire n’a été exécuté ; la documentation Stripe a seulement été consultée pour préparer la suite. Voir [Membres et licences](MEMBRES_LICENCES.md).

## Ressources partagées d’entreprise — 6 septembre 2026

La suite complète passe **65 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec l’image `sha256:d8a703885b3e38285234eed459af064f74c895fcb157c1def9c3f9c234e44e4b`. Le frontend passe **34 scénarios JSDOM** ; les deux scénarios du partage passent à nouveau après ajout du dépôt de fichier et de la protection contre les réponses après changement d’utilisateur. TypeScript, Vite, Ruff et la cohérence des migrations passent.

Les tests API couvrent les copies publiées, les accès croisés, les confirmations, l’idempotence, les versions, la validation du fichier et le retrait. PostgreSQL confirme par `pg_blocking_pids` que la révocation attend la transaction de lecture courante. Le parcours OCI utilise Hermes réel pour lire une note, télécharger un PDF, l’ouvrir avec `pypdf`, puis constater le refus après retrait du partage. Les sources portent le titre et la version, et le contexte système de la conversation reprise demeure inchangé. Les réponses de modèle restent synthétiques ; aucun appel Microsoft n’est nécessaire à ce parcours.

L’interface a été contrôlée en français, anglais et sur une largeur mobile de 360 pixels avec un aperçu fictif distinct, ensuite fermé et arrêté. Le test de sélection de fichier vérifie les octets envoyés ; JSDOM exige un événement de soumission explicite car sa validation native de champ fichier ignore le `FileList` fourni par userEvent. Ce test ne remplace pas un dépôt via navigateur avec les services du pilote.

La base normale a été sauvegardée dans `preview.before-0017.db`, migrée en `0017`, puis l’API redémarrée. Sa santé et les quatre chemins de ressources sont vérifiés. Les connexions personnelles et les données client n’ont pas été utilisées. L’hébergement Infomaniak, les services externes réels et le pilote restent à valider. Voir [Ressources d’entreprise](RESSOURCES_ENTREPRISE.md).

## Notifications personnelles — 6 septembre 2026

La suite complète passe **62 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec l'image runtime inchangée `sha256:9379c3016cafa5d1fdb8152a6135200d108e42f0c4b31a782559c274e5fc46a6`. Les contrôles supplémentaires sur les notifications d'échec et d'interruption ont ensuite passé les deux scénarios concernés sur PostgreSQL. Le frontend passe **32 scénarios JSDOM**, TypeScript et le build Vite. Ruff et la cohérence des migrations passent.

Les nouveaux parcours vérifient la création transactionnelle depuis le scheduler et le worker, l'absence de doublons, la séparation des propriétaires, la lecture concurrente et idempotente, le retrait de licence et la désactivation. La pagination couvre 27 notifications de même horaire avec insertion d'un nouveau blocage entre deux pages. Aucun contenu de réponse, de mail ou de fichier n'est copié dans l'événement.

Les tests frontend contrôlent le compteur obsolète reçu après une lecture, la pagination sans doublons, la navigation vers le résultat sans nouvelle exécution, le changement de langue, la réponse de lecture perdue et la disparition des contenus après révocation. Le panneau a été contrôlé visuellement en français, anglais et dans un viewport mobile de 360 × 780 ; l'en-tête a été adapté aux petits écrans. Les aperçus fictifs ont ensuite été fermés et arrêtés.

La base locale normale a été sauvegardée dans `preview.before-0016.db`, migrée en `0016`, puis l'API redémarrée. Santé, configuration et nouvelles routes sont vérifiées. Cette étape ajoute des notifications dans l'application ; elle n'envoie aucun mail et ne modifie pas les autorisations des actions. Les transports externes restent synthétiques ; pilote et exploitation Infomaniak restent à valider. Voir [Notifications](NOTIFICATIONS.md).

## Récupération opérateur — 6 septembre 2026

La suite complète passe **60 scénarios Linux/PostgreSQL**, sans échec, scénario ignoré ou relance automatique, avec l'image runtime inchangée `sha256:9379c3016cafa5d1fdb8152a6135200d108e42f0c4b31a782559c274e5fc46a6`. Le changement porte sur le contrôleur hôte et son outil opérateur ; aucune migration ni modification frontend n'est ajoutée. Ruff et le contrôle de format passent.

Les nouveaux tests créent de véritables conteneurs rootless temporaires. Ils vérifient le refus d'un bail valide, le verrou du volume, le refus d'une inspection périmée, deux récupérations concurrentes, un montage étranger, la file d'attente et le point d'entrée CLI. Une seule récupération aboutit, les fichiers personnels et le reçu d'e-mail incertain restent inchangés, puis une opération du véritable runtime accède de nouveau au volume. Un scénario simule également la suppression du conteneur suivie d'un rollback en base ; la clôture explicitement confirmée avec `absent` interrompt le tour sans le rejouer.

Les premières exécutions ciblées ont révélé le nom exact du champ de format Podman (`.ID`) et un cas d'attente du verrou PostgreSQL lors de demandes simultanées. Le champ a été corrigé et la contention du propriétaire dispose d'un refus dédié `recovery_owner_busy`. La suite complète finale passe après ces corrections.

La procédure documente le diagnostic, la récupération, la collecte du reçu opérateur et les résultats incertains. L'API locale normale a été redémarrée et ses routes de santé et de configuration répondent ; la base reste en `0015`. Les services externes restent synthétiques, et les exercices Infomaniak, la collecte centralisée des reçus et les restaurations restent à réaliser. Voir [Récupération runtime](RECUPERATION_RUNTIME.md).

## Mémoire personnelle — 6 septembre 2026

La suite complète passe **58 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l'image `sha256:9379c3016cafa5d1fdb8152a6135200d108e42f0c4b31a782559c274e5fc46a6`. Le frontend passe **30 scénarios JSDOM**, puis TypeScript et le build Vite. Ruff passe. Aucune migration n'est ajoutée.

Le parcours mémoire utilise l'API authentifiée, PostgreSQL et le véritable outil mémoire Hermes. Une préférence apprise par Hermes est corrigée depuis l'API et reprise dans une nouvelle conversation ; le contexte d'une conversation existante reste inchangé. Les scénarios vérifient les accès croisés, l'absence de contournement administrateur, les versions, l'exécution concurrente, la licence retirée, la désactivation du membre et les fichiers invalides. Le premier lancement ciblé a révélé une requête de test incomplète pour modifier une adhésion ; après fourniture des trois champs requis, la suite complète passe sans relance automatique.

L'interface conserve les éditions non enregistrées de l'autre liste et oblige à relire après une réponse perdue. Le rendu, la modification, le retrait des préférences et leur relecture ont été contrôlés en français et anglais sur un aperçu fictif séparé, ensuite arrêté et fermé. L'API normale a été redémarrée : santé et routes mémoire vérifiées, base inchangée en `0015`. Les fournisseurs externes restent synthétiques. L'effacement concerne la mémoire active, pas les conversations ni les sauvegardes ; détails dans [Mémoire personnelle](MEMOIRE_PERSONNELLE.md).

## Briefing envoyé et récurrence — 6 septembre 2026

La suite complète passe **56 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec le runtime inchangé `sha256:4b433a33ee62fc1cc3bc260f6d98716fc7a3d046ec70a855a91ff67ee6aca0a7`. Le frontend passe **28 scénarios JSDOM**, puis TypeScript et le build Vite. Ruff et la cohérence des migrations passent.

Le nouveau parcours exécute le véritable Hermes pour un essai d’envoi puis pour une occurrence planifiée, avec la même destination confirmée. Les contrôles couvrent les destinataires et l’objet fixes, la lecture préalable des sources, l’absence de deuxième tentative, les refus par défaut, les reçus et la révocation. Les cas supplémentaires de remplacement versionné et d’incertitude ont ensuite été vérifiés sur SQLite et PostgreSQL. Le test de remplacement a d’abord réutilisé la même seconde pour deux échéances forcées : après correction vers deux horaires synthétiques distincts, le scénario PostgreSQL passe sans nouvelle tentative du runner.

Les scénarios d’interface vérifient la confirmation de l’essai, la conservation de la demande après une réponse perdue, la confirmation des futurs envois et la version du remplacement. Ils vérifient aussi qu’un reçu arrivé par le rafraîchissement du chat remplace le brouillon, qu’un ancien résultat ne rétablit pas l’envoi et qu’une édition locale est préservée lors d’un conflit.

Le formulaire et le parcours ont été contrôlés visuellement en anglais et français sur un aperçu fictif séparé, ensuite fermé et arrêté. La base normale a été sauvegardée puis migrée en `0015` et l’API redémarrée. Aucun message réel n’a été envoyé : Entra/Exchange, le modèle commercial, l’hébergement Infomaniak et le pilote restent à valider. Détails dans [Envois planifiés](ENVOIS_PLANIFIES.md).


## Autonomie personnelle des e-mails — 6 septembre 2026

La suite complète passe **54 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l’image runtime `sha256:4b433a33ee62fc1cc3bc260f6d98716fc7a3d046ec70a855a91ff67ee6aca0a7`. Le frontend passe **24 scénarios JSDOM** et le build TypeScript/Vite. Ruff et la cohérence des migrations passent également.

Les nouveaux scénarios exercent les règles communes, le choix individuel explicite et versionné, la séparation des propriétaires, la stabilité des anciennes conversations et la soumission par le véritable Hermes isolé. Ils contrôlent la révocation pendant un appel Microsoft, la conservation du reçu, le refus de recréer un message après une réponse incertaine, ainsi que l’héritage et la révocation de la capacité dans les tâches. Le scénario d’envoi Hermes concerne le chat ; un envoi planifié complet reste à vérifier.

Le réglage a été contrôlé visuellement en français et anglais sur un aperçu fictif séparé. La taille des boutons radio a été corrigée, le build repassé et le rendu revérifié. L’aperçu fictif a ensuite été fermé et arrêté. La base normale a été sauvegardée avant migration `0014`, puis l’API redémarrée. Les transports Microsoft et modèle restent synthétiques ; aucun message réel n’a été envoyé. Détails et limites dans [Autonomie personnelle](AUTONOMIE.md).


## Vérification des copies envoyées — 6 septembre 2026

La suite complète passe **50 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré. Le runtime reste `sha256:c2cc47b857dc65752cd0f74c67b115bbf37ef82b8cbeaef052a280e1eb96f566` : cette étape ajoute le suivi côté API et interface. Le frontend passe **22 scénarios JSDOM** et le build TypeScript/Vite. Ruff et la cohérence des migrations passent également.

Les scénarios vérifient la recherche avec le consentement de lecture personnel, les règles communes, l’absence de correspondance, les en-têtes ou destinataires incorrects, les erreurs Microsoft et les anciennes tentatives sans marqueur. Une copie trouvée est conservée comme observation indépendante du statut d’envoi ; aucun résultat ne déverrouille une répétition. Les tests de navigateur couvrent une réponse de vérification perdue, puis la récupération du reçu sans nouvelle recherche ni envoi.

L’aperçu fictif a été contrôlé en anglais pour la sélection sans correspondance et en français pour la copie trouvée avec lien Outlook. Il a ensuite été fermé et arrêté. La base normale a été sauvegardée avant migration `0013`. Les requêtes Microsoft sont synthétiques : la conservation des en-têtes et la sélection réelle dans Exchange restent à valider avant le pilote. Détails dans [E-mails](EMAILS.md).


## Brouillons et envoi confirmé — 6 septembre 2026

La suite complète passe **48 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l’image runtime `sha256:c2cc47b857dc65752cd0f74c67b115bbf37ef82b8cbeaef052a280e1eb96f566`. Le frontend passe **20 scénarios JSDOM** et le build TypeScript/Vite. Ruff et la cohérence des migrations passent également.

Le nouveau parcours vérifie préparation privée par le vrai Hermes isolé, relecture versionnée, confirmation personnelle, consentement `Mail.Send`, refus par défaut des règles d’entreprise, pièces jointes exactes et absence de deuxième requête Microsoft après double confirmation concurrente ou résultat réseau incertain. Un résultat HTTP 202 est présenté comme une demande acceptée, sans prétendre à la livraison. Les transports Microsoft et modèle restent synthétiques ; aucune boîte réelle n’a été contactée.

Le formulaire, sa modification, sa confirmation et le reçu ont été contrôlés dans le navigateur en français et anglais sur un aperçu local explicitement fictif, ensuite fermé et arrêté. La prévisualisation normale a été sauvegardée avant migration `0012`. Les limites et les étapes restantes sont précisées dans [E-mails](EMAILS.md).


## Règles d’entreprise — 6 septembre 2026

La suite complète passe **45 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré. Le runtime reste `sha256:3d58b390f8943cdb18fed899ab9d79f4dc8238290134ea7f12a2dc4934e525d2` ; cette étape modifie l’API et l’interface. Le frontend passe **18 scénarios JSDOM** et le build TypeScript/Vite. Un cas supplémentaire de consentement commencé avant une restriction est ajouté puis vérifié sous Windows/SQLite ; le scénario de concurrence PostgreSQL est volontairement ignoré sur Windows.

Les tests contrôlent l’administration, les versions concurrentes, les confirmations SharePoint déjà préparées, les capacités des nouvelles conversations, la stabilité des anciennes et l’absence d’accès administrateur aux contenus personnels. Le scénario PostgreSQL garde un appel Microsoft en cours : la politique attend, puis les appels suivants sont refusés et l’automatisation concernée est bloquée. Réautoriser les capacités ne la relance pas automatiquement.

L’écran administrateur a été contrôlé visuellement en français et anglais, sur des données fictives séparées. Les limites actuelles et le fonctionnement des verrous sont décrits dans [Règles de l’entreprise](REGLES_ENTREPRISE.md). Les autorisations personnelles d’action autonome et les services réels restent à raccorder.

## Enregistrement Microsoft 365 — 6 septembre 2026

La suite complète passe **43 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec le runtime documentaire inchangé `sha256:3d58b390f8943cdb18fed899ab9d79f4dc8238290134ea7f12a2dc4934e525d2`. Après ajout de la vérification des octets présents à la destination et distinction de l’expiration d’une URL d’envoi, les deux scénarios d’enregistrement sont repassés avec succès sur PostgreSQL. Le frontend passe **16 scénarios JSDOM** et le build TypeScript/Vite.

La migration `0010`, le consentement personnel supplémentaire, la préparation sans effet externe, le choix de dossier, la confirmation de remplacement, les accès propriétaires et l’idempotence sont vérifiés avec Microsoft synthétique au niveau HTTP. Une confirmation concurrente et une réponse perdue ne provoquent pas de seconde écriture. La récupération compare le SHA-256 téléchargé au document immuable attendu. Le parcours français/anglais a été contrôlé visuellement sur un aperçu fictif séparé ; la case de remplacement a été corrigée puis revérifiée.

Les règles administrateur et les services réels restent à raccorder. En particulier, les tests synthétiques ne prouvent pas que la bibliothèque cible applique l’en-tête conditionnel de remplacement. Ce point doit être validé sur Microsoft avant le pilote. Les limites et le parcours sont décrits dans [Enregistrement SharePoint](ENREGISTREMENT_SHAREPOINT.md).

## Lecture du contenu SharePoint — 6 septembre 2026

La suite complète passe **41 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l’image `sha256:3d58b390f8943cdb18fed899ab9d79f4dc8238290134ea7f12a2dc4934e525d2`. Le frontend passe ses **15 scénarios JSDOM** et son build TypeScript/Vite. Ruff et le contrôle des espaces passent.

Le nouveau scénario utilise MSAL, l’API et Hermes réels, avec Microsoft Graph et le modèle simulés au niveau HTTP. Hermes recherche un fichier, le télécharge via la connexion de son propriétaire, ouvre réellement le PDF avec pypdf puis le publie sous son nom d’origine. Les octets téléchargés par l’API correspondent à la source ; l’administrateur reçoit un refus. Les requêtes du modèle ne contiennent ni jeton Microsoft ni URL de téléchargement préauthentifiée.

Les tests du broker couvrent les connexions personnelles, la déconnexion, les capacités absentes, les anciennes conversations, les destinations refusées, l’expiration du lien temporaire, le changement d’ETag et les dépassements de taille avant ou pendant le transfert. La migration `0009` est exercée sur les bases temporaires ; elle conserve les anciens outils et fige la nouvelle révision pour les nouvelles conversations. Les essais avec Entra et les fichiers réels du pilote restent à réaliser. Voir [Documents](DOCUMENTS.md).

## Génération documentaire — 6 septembre 2026

La suite complète passe **38 scénarios Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l’image `sha256:32b95a02d526073ae49c8ca414c99dd454d51f3fd2fb716a9d7d275c6ff7aa85`. Après correction visuelle des styles Word, le parcours documentaire complet est retesté avec succès sur l’image finale `sha256:349e453517fcbbe3fb69cf4fe3804024a1fb74e062dc723a07e534de74f55ad5`.

Le vrai Hermes lit le guide interne puis utilise son terminal pour créer DOCX, PDF, XLSX et PPTX. Les contrôles rouvrent les fichiers avec leurs bibliothèques, modifient du contenu Word et PowerPoint, recalculent une modification Excel avec LibreOffice et vérifient les valeurs/formules conservées. Les rendus comportent une page Word, une page PDF, une page Excel et deux diapositives PowerPoint ; les textes attendus sont extraits. Les quatre fichiers sont ensuite publiés par l’outil et récupérés via l’API avec contrôle de propriété. Aucun fournisseur commercial ou compte Microsoft réel n’intervient dans ce scénario.

Les cinq PNG du dernier rendu ont été inspectés : titres, accents, tableaux et corps de texte lisibles, sans chevauchement constaté. Ces fichiers de contrôle restent hors de Git dans l’espace local de prévisualisation. Le calcul Excel contient aussi une cellule de test commençant par `=` pour vérifier qu’un libellé reste du texte. Les sorties de contrôle ne sont pas des documents du client pilote.

Le premier essai a détecté le choix du Python système par le terminal ; le guide utilise désormais explicitement `/opt/venv/bin/python`. Le guide et les bibliothèques sont embarqués, sans dépendance au poste utilisateur. Ruff et la vérification des espaces passent. Voir [Documents](DOCUMENTS.md) pour la portée et les limites.

## Documents privés — 6 septembre 2026

Après la migration `0008`, la suite complète passe **36 scénarios sous Linux/PostgreSQL avec l’image `sha256:acbd8d15b9c59a97425671e677fcae5714ac05ddc0b93f48e853eb2cf22158e8`**, sans échec ni scénario ignoré. Un contrôle supplémentaire des conteneurs Office et des tailles a ensuite été ajouté ; les deux tests du fichier documents passent sous Windows/SQLite. Le frontend passe **15 scénarios JSDOM** et son build TypeScript/Vite.

Le nouveau parcours exécute le vrai Hermes sans connexion Microsoft : création d’un PDF de test dans le terminal, refus des chemins sortants et liens symboliques, publication idempotente, conservation des octets et téléchargement réservé au propriétaire. Les autres tests vérifient la continuité après interruption, les refus d’accès, les noms, les types et les plafonds. Les réponses de modèle restent synthétiques. Les paquets Office du test vérifient uniquement le contrôle de format ; les exemples métier et leur rendu restent à produire.

Le build a été contrôlé dans un navigateur sur un aperçu séparé explicitement fictif : bloc du document, nom, taille, téléchargement indisponible et changement anglais/français. Aucune erreur JavaScript observée. Cet aperçu a été fermé et arrêté. La base de prévisualisation normale a été sauvegardée et migrée en `0008`, puis l’API redémarrée. La route de téléchargement est présente ; Microsoft et SMTP restent correctement annoncés comme non configurés.

Le périmètre et les limites sont décrits dans [Documents](DOCUMENTS.md). L’historique des vérifications précédentes suit ci-dessous.

5 septembre 2026. Périmètre : `alpendata/backend`, migrations `0001` à `0004`.

## Résultats

| Environnement | Résultat du lanceur officiel |
|---|---|
| Windows, Python 3.11.15, SQLite | 14 réussites, 0 échec, 4 scénarios Linux ignorés. |
| Debian 13 sous WSL, Python 3.13.5, PostgreSQL 17.11 | 18 réussites, 0 échec, aucun scénario ignoré, avec l’image runtime fournie. |
| Ruff | Aucun problème de lint restant. |

Les dépendances des deux environnements sont issues du même `uv.lock`. Les tests passent par `scripts/run_tests.sh`, qui crée les processus de test avec un environnement nettoyé. Chaque scénario reconstruit une base temporaire à partir des migrations et vérifie leur cohérence avec les modèles SQLAlchemy.

Le premier passage PostgreSQL a détecté un problème de comparaison des contraintes sans nom explicite. Les contraintes ont reçu des noms stables dans les modèles et la migration initiale ; les passages suivants sont réussis. La migration initiale n’avait pas été publiée ni appliquée à une base client.

## Comportements exercés

- Un membre ne peut pas lire les ressources d’une autre entreprise.
- Un administrateur ne peut ni lire, ni lister, ni supprimer les contenus privés d’un collègue.
- L’invitation crée un onboarding neuf, sans copie des réponses de l’administrateur.
- Les invitations expirent et se révoquent ; leur acceptation est liée à une adresse vérifiée et ne se répète pas.
- Deux demandes simultanées pour la dernière place ne créent qu’une invitation ; deux acceptations simultanées du même lien ne créent qu’un membre.
- Les changements de licence, la désactivation d’un membre et la révocation d’une session sont appliqués aux appels suivants.
- Le navigateur qui commence la connexion Microsoft est le seul à pouvoir la terminer ; une tentative consommée ne peut être rejouée.
- L’échange MSAL emploie PKCE et nonce. Les erreurs de nonce, audience, émetteur ou expiration ne créent ni utilisateur ni session.
- Un changement d’adresse ne change pas l’identité ; un compte portant la même adresse dans un autre annuaire ne fusionne pas avec elle.
- Les mutations par cookie demandent l’origine attendue. La déconnexion invalide aussi une copie du jeton opaque.

## Limites de cette preuve

Microsoft est simulé au niveau HTTP dans les tests. La bibliothèque MSAL, le chiffrement, l’API et les bases sont réels. Aucun compte client, consentement Entra ou jeton Microsoft réel n’a été utilisé.

Les invitations exigent désormais une preuve envoyée à la boîte destinataire, liée au compte connecté et à l’invitation. Les scénarios exercent cette preuve avec des messages capturés en mémoire ; un scénario distinct utilise un véritable serveur SMTP TLS local, sans relais externe. Le certificat non approuvé est refusé, et une coupure simulée après envoi invalide la preuve. Le relais de production reste à valider. L’écran de confirmation est implémenté et vérifié séparément dans les tests JSDOM de l’interface ; le parcours navigateur avec les services réels reste à valider. Ces scénarios d’API ne constituent pas à eux seuls une preuve d’isolation des processus Hermes. Le scénario conteneurisé ajouté ensuite est décrit ci-dessous ; son raccordement au chat web reste à réaliser.

Le démon Docker Desktop local a rencontré une erreur d’accès à son socket de démarrage. Les tests PostgreSQL ont donc été réalisés dans Debian avec des serveurs temporaires accessibles par socket Unix privé, sans modifier ni réinitialiser les données Docker existantes.

La procédure reproductible est décrite dans le [README du backend](../backend/README.md). Aucun déploiement Infomaniak n’a été réalisé à ce stade.

Après ajout des lectures administrateur (noms des membres et invitations en attente) et du retour HTML après interruption de connexion, les deux fichiers de tests concernés ont de nouveau passé 7 scénarios sous Windows et PostgreSQL Linux. Les lectures restent refusées aux collaborateurs et ne renvoient pas de jetons.


Les connexions Microsoft 365 sont exercées avec MSAL réel et des transports HTTP Microsoft/Graph synthétiques : consentement limité aux choix, identité identique au compte connecté, cache chiffré par propriétaire, lecture avec le bon jeton, refus des accès non accordés, recherche de métadonnées, absence de suivi des redirections/pagination, limitation de débit, renouvellement du cache et révocation. Une panne temporaire du service de jetons conserve le consentement. Un scénario PostgreSQL bloque l’échange de code pendant qu’une déconnexion réelle via l’API intervient ; son retour ne peut pas réactiver les jetons.

L’interface dispose de sept scénarios JSDOM réussis et d’un build TypeScript/Vite réussi. Cela vérifie ses appels et son rendu DOM, pas sa présentation dans un navigateur réel ni le consentement sur le tenant du pilote.


## Runtime Hermes réel

Le test `test_hermes_turn_tools_private_memory_and_network_isolation` utilise Podman 5.4.2 sans privilèges, Python 3.13.15 dans l’image et le véritable `AIAgent` du fork. Les réponses du modèle et les données de l’outil métier sont synthétiques ; la boucle agent, les outils mémoire/terminal et les frontières Linux ne sont pas remplacés par des mocks.

Le parcours a exécuté trois conteneurs successifs : un premier tour avec mémoire et outils, une reprise de la même conversation, puis un espace d’un autre collaborateur. Le contexte système de la conversation reprise reste identique. La commande dans l’agent constate UID 1000, aucun accès au fichier témoin de l’hôte ni à celui du collègue, aucun socket Docker et aucun accès au réseau externe. Le souvenir est présent chez son propriétaire et absent des requêtes du collègue. Un verrou refuse deux ouvertures concurrentes du même état.

Un second scénario utilise un vrai sous-processus pour envoyer une opération de protocole inconnue ; le superviseur doit la refuser avant tout appel de passerelle. Les tests conteneurisés sont explicitement ignorés sous Windows. La qualité métier des réponses, les appels de modèles réels, les droits pendant le chat et la reprise opérationnelle après panne restent à valider lors du raccordement des services.

Image locale validée : `sha256:4effe246aa67dc093879815d84adba886fd9a2ec0568a9c50ac9bd7bc20de522`. La suite complète PostgreSQL et runtime a passé 18 scénarios, sans échec ni scénario ignoré, via le lanceur officiel. Les tests d’interface existants ne sont pas modifiés par cette étape.

## Passerelle de modèles — 6 septembre 2026

Après l’ajout de `ModelGateway`, la suite complète passe **23 scénarios sous Linux avec PostgreSQL et conteneurs réels**, sans échec ni scénario ignoré. Sous Windows, 19 scénarios passent et les quatre scénarios Linux sont explicitement ignorés. Ruff et la vérification des espaces Git passent également.

Les cinq nouveaux scénarios vérifient les appels de modèles sur un serveur HTTP local : destination imposée, clé serveur, refus des outils externes et contenus distants, budgets de sortie, routage OpenRouter, erreurs nettoyées, absence de suivi des redirections et de nouvelles tentatives, plafonds de réponse, consommation inconnue et conservation du raisonnement lors des appels d’outils. Le premier tour du test Hermes utilise désormais cette passerelle et vérifie les compteurs de chaque appel, y compris le titrage. Les réponses restent synthétiques ; aucune clé de fournisseur réelle n’a été utilisée. L’image du runtime est inchangée.

Les conversations durables et leur raccordement aux droits Microsoft, au navigateur et au registre de consommation restent la prochaine étape. La passerelle seule n’active pas un chat utilisable par le pilote.

## Chat personnel — 6 septembre 2026

La migration `0005`, les conversations, la file de travail et les relevés de modèle sont implémentés. La suite complète passe **27 scénarios sous Linux/PostgreSQL avec l’image finale**, sans échec ni scénario ignoré. Sous Windows, 21 scénarios passent et six scénarios Linux sont explicitement ignorés. Ruff et la vérification Git passent.

Image finale validée : `sha256:e3059ff1ccf7c8d9274e2a71fc70142fb274f2a3c989db445f2aa1b16eb54649`. Le contexte est désormais restauré directement depuis SessionDB. Le titrage secondaire Hermes est désactivé, puisque la projection AlpenData nomme la conversation à partir du premier message.

Les nouveaux scénarios vérifient la propriété et les clés étrangères composées, l’envoi idempotent, l’annulation, le profil de conversation figé, l’accès sans licence à son historique et le refus après désactivation. Deux soumissions et deux réclamations simultanées sur PostgreSQL aboutissent à une seule exécution. Un bail expiré devient une interruption, sans remise en file et sans inventer la consommation absente.

Le scénario complet remplace l’API après mise en file, puis exécute Hermes dans trois conteneurs successifs. La lecture utilise le jeton Microsoft du propriétaire et reste inaccessible à l’administrateur. Une reprise conserve le contexte ; la déconnexion interdit la nouvelle lecture. Une annulation pendant l’appel de modèle conserve sa consommation confirmée mais ne livre pas la réponse. Une désactivation avant exécution empêche tout nouvel appel de modèle. Microsoft, Graph et les réponses de modèle restent synthétiques ; l’API, PostgreSQL, MSAL, le serveur HTTP de modèle et le runtime sont réels.

Le frontend passe dix scénarios JSDOM et sa compilation TypeScript/Vite. Un aperçu séparé du build, explicitement signalé comme fictif, a été contrôlé dans le navigateur intégré : présentation de la conversation, envoi et changement français/anglais, sans erreur JavaScript observée. Ce serveur de vérification a ensuite été arrêté. L’API locale normale a été migrée et redémarrée ; ses routes de chat sont présentes et elle annonce correctement que Microsoft et SMTP ne sont pas configurés. Aucun compte pilote ou modèle commercial réel n’a été connecté.

## Propositions et essais personnels — 6 septembre 2026

La suite complète passe **29 scénarios sous Linux/PostgreSQL avec des conteneurs réels**, sans échec ni scénario ignoré. Sous Windows, 22 scénarios passent et sept scénarios Linux sont ignorés. Le frontend passe **12 scénarios JSDOM** et sa compilation TypeScript/Vite. Ruff passe également.

Image utilisée : `sha256:6f706d2d9556dfcbb4cdf8927fdfc9621cdddbbac655ec1007a75f8949fc9730`. L’extension Hermes enregistre réellement ses propositions via un outil propre à l’onboarding ; un deuxième conteneur exécute l’essai de messagerie. Le modèle et Microsoft répondent avec des données synthétiques. Les tests vérifient le profil obligatoire, la propriété des propositions et essais, les tentatives idempotentes, les recettes incompatibles avec les permissions, la déconnexion et les sources provenant du bon compte. Une affirmation du modèle sans lecture ne permet pas de vérifier un essai.

Le contrôle ajouté ensuite pour refuser un onboarding sans propositions enregistrées a été vérifié séparément sur les scénarios concernés. Les pages compilées ont été parcourues dans un aperçu local explicitement fictif : saisie du besoin, cartes, essai, références et changement anglais/français ; aucune erreur JavaScript observée. L’aperçu fictif a été fermé et arrêté. La base de prévisualisation normale a été sauvegardée, migrée en `0006`, puis son API redémarrée. Aucun service commercial réel ni compte pilote n’a été connecté.

Le [document du premier résultat](PREMIER_RESULTAT.md) décrit les limites, notamment la lecture de métadonnées de fichiers et l’absence actuelle d’activation récurrente.

## Automatisations personnelles — 6 septembre 2026

La suite complète passe **34 scénarios sous Linux/PostgreSQL**, sans échec ni scénario ignoré, avec l’image `sha256:4031b65db47e83b5216fc4d0b882472c351221da012590006be02868a8e30fa0`. Elle couvre désormais deux activations et deux tickers concurrents, les changements d’heure suisses, les récurrences, leur suspension et les occurrences manquées. Les contrôles ajoutés pour le nouvel essai, la réactivation, l’édition et le retrait de licence ont également passé les tests concernés. Le frontend passe **14 scénarios JSDOM** et sa compilation TypeScript/Vite ; Ruff passe.

Le test complet Hermes exécute successivement la proposition, l’essai et l’occurrence planifiée dans trois conteneurs réels. L’occurrence consulte la messagerie du bon propriétaire ; l’administrateur ne peut pas voir son historique. Un vrai sous-processus avec des pipes vérifie que l’attente du broker n’empêche pas le respect du délai du contrôleur. Les appels Microsoft et modèle restent synthétiques.

Le build a été contrôlé dans le navigateur sur une démonstration locale signalée comme fictive : case de revue, activation, prochain horaire affiché, gestion des automatisations, historique, suspension et changement français/anglais. Aucune erreur JavaScript observée. Cette démonstration ne valide pas une exécution à heure réelle sur les services du client. Les exercices de production et le déploiement Infomaniak restent à réaliser.

## Contrôle qualité et reprise des essais — 6 septembre 2026

La suite complète du backend a passé **96 tests dans 51 fichiers**, sous Linux avec PostgreSQL, Podman rootless, le véritable runtime Hermes, systemd utilisateur, Nginx et age, sans échec ni test ignoré. Le lanceur officiel utilise quatre workers et aucune relance automatique de fichier. Après ajout de la récupération des essais par lecture, les deux fichiers concernés (`test_routines.py` et `test_routine_delivery.py`) ont de nouveau passé leurs **3 tests**, dont l’envoi puis la récurrence avec Hermes réel. Les fournisseurs de modèle, Microsoft et Stripe restent synthétiques ; ces passages ne valident pas les comptes commerciaux.

Le frontend passe **46 tests dans 21 fichiers** et la compilation TypeScript/Vite. Les deux nouveaux scénarios de récupération après rechargement échouent avec le composant précédent, puis passent avec la correction : réception perdue, conservation du seul UUID, lecture du reçu, panne de lecture sans nouvel envoi, absence de reçu puis reprise avec le même identifiant. L’API refuse la récupération par un autre propriétaire, même administrateur, et les références utilisées pour une autre proposition. L’onboarding réutilise le besoin enregistré et conserve son édition au changement de langue.

Les fichiers PDF, Word, Excel et PowerPoint produits par le scénario documentaire ont été rendus puis inspectés visuellement : cinq pages, sans chevauchement observé. Ils constituent des exemples de test et non des modèles métier validés par le client.

Le build a été inspecté dans un navigateur avec des données explicitement fictives, en français et en anglais, sur ordinateur et à 390 pixels de largeur. Le contrôle mobile a reproduit un débordement des boutons de documents : largeur de page de 598 pixels avant correction. Après adaptation des boutons et du reçu de téléchargement, la page reste dans la largeur disponible et les noms longs sont lisibles. Le passage du premier résultat au chat fonctionne dans cet aperçu ; aucune erreur JavaScript observée. Cette vérification du rendu ne remplace pas une session avec les intégrations réelles.
