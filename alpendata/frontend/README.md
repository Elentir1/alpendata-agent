# Interface AlpenData

Première interface web du produit, construite avec React, TypeScript et Vite, dans la continuité de la pile web du fork. Elle utilise l’API d’`alpendata/backend` et conserve l’architecture Infomaniak prévue ; aucun service d’authentification, stockage ou hébergement Sites/Cloudflare n’a été ajouté.

## Parcours implémentés

- Cloche et panneau de notifications personnelles : résultats et problèmes des automatisations, compteur non lu, historique paginé et ouverture du résultat. Voir [Notifications](../docs/NOTIFICATIONS.md).

- Consultation, correction et retrait de la mémoire personnelle réelle d'Hermes, avec versions et récupération après réponse perdue. Voir [Mémoire personnelle](../docs/MEMOIRE_PERSONNELLE.md).

- Écran de connexion Microsoft et retour compréhensible après interruption de connexion.
- Création d’une entreprise après authentification.
- Invitation : demande de preuve de boîte mail, confirmation avec le compte demandeur, puis accès à un onboarding neuf.
- Onboarding individuel en français/anglais ; les réponses non enregistrées sont conservées lors d’un changement de langue.
- Espace administrateur : membres, rôles, activation/désactivation, attribution/retrait de licence, compteur des places et invitations. Les changements exigent une confirmation et la version lue ; aucune lecture des contenus privés des collaborateurs. Voir [Membres et licences](../docs/MEMBRES_LICENCES.md).
- Déconnexion, y compris si la session a déjà expiré.
- Chat personnel : conversations, envoi idempotent, suivi de l’exécution, historique et arrêt d’une demande.

Après sauvegarde des réponses, chacun choisit ses accès Microsoft 365 et suit le consentement personnel. Une fois connecté, il peut afficher ses derniers mails, ses rendez-vous ou rechercher un document. L’entrée « Assistant » ouvre le chat relié au processus Hermes et à la passerelle de modèles du backend. Le chat annonce son indisponibilité tant que le serveur n’est pas configuré ; aucune réponse IA n’est simulée dans l’application. Les propositions personnalisées, leurs essais et leur planification sont implémentés. L’achat de places, la facturation et la validation des services réels restent à réaliser.

## Développement

```sh
npm ci
npm run dev
```

Le serveur local écoute sur `http://127.0.0.1:5178` et transfère `/api` à `http://127.0.0.1:8180`. Démarrer l’API sur ce dernier port après migration, selon son README. L’interface consulte les capacités réellement configurées : aucune connexion Microsoft n’est présentée comme utilisable lorsque l’API ne dispose pas de sa configuration.

Pour tester Microsoft réellement, fournir un certificat HTTPS local approuvé via les chemins `ALPENDATA_DEV_TLS_CERT` et `ALPENDATA_DEV_TLS_KEY`, régler l’origine HTTPS exacte dans `ALPENDATA_PUBLIC_ORIGIN` côté API et enregistrer les deux URL de retour du backend dans Entra. Aucune clé Microsoft, SMTP ou de chiffrement ne doit entrer dans le bundle navigateur ou dans une variable `VITE_*`.

Le déploiement prévu sert `dist/` par HTTPS et transfère `/api` vers le backend sous la même origine. Le serveur statique doit retourner `index.html` pour `/join`. La configuration du proxy et le déploiement Infomaniak restent à réaliser.

## Données du navigateur

L’authentification utilise exclusivement le cookie HttpOnly émis par l’API. La préférence de langue est conservée localement. Les jetons d’une invitation en cours sont temporairement placés dans `sessionStorage` pour survivre au détour par Microsoft ; le fragment est immédiatement retiré de l’URL. Ils restent soumis aux contrôles et expirations serveur et sont supprimés après acceptation. L’identifiant de l’entreprise choisie est aussi conservé pendant le détour de consentement, puis vérifié contre les adhésions du compte connecté avant d’ouvrir son espace. Aucun jeton Microsoft ou de session n’est stocké par JavaScript. Les résultats Microsoft sont gardés uniquement en mémoire du composant et retirés après déconnexion ou demande de reconnexion. Les extraits de mails sont rendus comme du texte, jamais comme du HTML.

## Vérification

Le chat présente aussi les [documents reçus](../docs/DOCUMENTS.md) : nom, taille et téléchargement authentifié. Il gère un accès expiré et conserve l’affichage des fichiers réellement reçus quand la suite du tour échoue. Les quinze scénarios JSDOM et le build TypeScript/Vite passent après cet ajout.

```sh
npm test
npm run build
```

Dix scénarios d’interface passent dans JSDOM avec une API simulée : les parcours existants de connexion, onboarding, invitations et Microsoft, plus création/envoi de conversation, rendu texte sans HTML, maintien du brouillon lors d’un changement de langue, nouvelle tentative avec la même clé et arrêt sans licence. Le build vérifie les types et produit le bundle statique. Un contrôle visuel distinct dans le navigateur intégré utilise le build et des données fictives explicitement signalées ; il vérifie la présentation, l’envoi et le changement de langue. Il ne constitue pas une connexion Entra ou une validation métier avec un modèle réel.

L’aperçu local a été démarré et a répondu HTTP 200. Les actifs de marque publics sont référencés dans `public/brand/README.md`, avec la licence de la police Inter.

## Premier résultat

Après son profil et ses connexions, l’utilisateur précise son besoin dans `FirstTasks`. Le formulaire ouvre une conversation qui reçoit les propositions enregistrées par Hermes. Chaque carte lance un essai explicite et ouvre son résultat personnel. Le chat affiche les références retournées par le broker et distingue un essai avec sources vérifiées d’un résultat sans lectures confirmées. Les essais ne programment aucune répétition. Quatorze scénarios JSDOM passent, ainsi que le build TypeScript/Vite ; les réponses externes des tests sont synthétiques.

L’utilisateur peut ensuite confirmer la revue de l’essai et choisir son horaire. L’écran Automatisations permet de consulter les résultats, modifier l’horaire, suspendre, reprendre, refaire un essai et retirer une tâche. Les données restent celles de l’utilisateur connecté.
