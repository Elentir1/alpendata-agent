# Interface AlpenData

Première interface web du produit, construite avec React, TypeScript et Vite, dans la continuité de la pile web du fork. Elle utilise l’API d’`alpendata/backend` et conserve l’architecture Infomaniak prévue ; aucun service d’authentification, stockage ou hébergement Sites/Cloudflare n’a été ajouté.

## Parcours implémentés

- Écran de connexion Microsoft et retour compréhensible après interruption de connexion.
- Création d’une entreprise après authentification.
- Invitation : demande de preuve de boîte mail, confirmation avec le compte demandeur, puis accès à un onboarding neuf.
- Onboarding individuel en français/anglais ; les réponses non enregistrées sont conservées lors d’un changement de langue.
- Espace administrateur : membres, invitations en attente, création et annulation d’invitations ; aucune lecture des contenus privés des collaborateurs.
- Déconnexion, y compris si la session a déjà expiré.

L’interface ne simule ni un dialogue IA ni une connexion aux documents. Après sauvegarde des réponses, elle indique clairement que la connexion aux outils est en préparation. Le chat, le consentement Graph, les propositions d’automatisations, la gestion complète des licences et la facturation restent à implémenter.

## Développement

```sh
npm ci
npm run dev
```

Le serveur local écoute sur `http://127.0.0.1:5178` et transfère `/api` à `http://127.0.0.1:8180`. Démarrer l’API sur ce dernier port après migration, selon son README. L’interface consulte les capacités réellement configurées : aucune connexion Microsoft n’est présentée comme utilisable lorsque l’API ne dispose pas de sa configuration.

Pour tester Microsoft réellement, fournir un certificat HTTPS local approuvé via les chemins `ALPENDATA_DEV_TLS_CERT` et `ALPENDATA_DEV_TLS_KEY`, régler l’origine HTTPS exacte dans `ALPENDATA_PUBLIC_ORIGIN` côté API et enregistrer son URL de retour dans Entra. Aucune clé Microsoft, SMTP ou de chiffrement ne doit entrer dans le bundle navigateur ou dans une variable `VITE_*`.

Le déploiement prévu sert `dist/` par HTTPS et transfère `/api` vers le backend sous la même origine. Le serveur statique doit retourner `index.html` pour `/join`. La configuration du proxy et le déploiement Infomaniak restent à réaliser.

## Données du navigateur

L’authentification utilise exclusivement le cookie HttpOnly émis par l’API. La préférence de langue est conservée localement. Les jetons d’une invitation en cours sont temporairement placés dans `sessionStorage` pour survivre au détour par Microsoft ; le fragment est immédiatement retiré de l’URL. Ils restent soumis aux contrôles et expirations serveur et sont supprimés après acceptation. Aucun jeton Microsoft ou de session n’est stocké par JavaScript.

## Vérification

```sh
npm test
npm run build
```

Cinq scénarios d’interface passent dans JSDOM avec une API simulée : disponibilité de connexion, conservation et sauvegarde des réponses, invitation suivie de l’onboarding, gestion des invitations par l’administrateur et sortie d’une session expirée. Le build vérifie les types et produit le bundle statique. Ces tests ne sont pas une validation visuelle dans un navigateur ni une connexion Entra réelle.

L’aperçu local a été démarré et a répondu HTTP 200 ; son ouverture dans Codex a été mise en attente pour cette tâche. Les actifs de marque publics sont référencés dans `public/brand/README.md`, avec la licence de la police Inter.
