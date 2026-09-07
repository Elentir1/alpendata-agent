# Édition Office avec Collabora CODE

Choix validé le 7 septembre 2026 : Collabora CODE remplace ONLYOFFICE Developer dans la refonte. Aucun achat ni contact fournisseur n’a été effectué. Cette intégration est validée sur QA ; elle n’est pas activée sur la production existante.

## Comportement

L’utilisateur ouvre un DOCX, XLSX ou PPTX depuis ses fichiers ou une publication de projet dont il est contributeur. Sur téléphone, il passe de la lecture à la modification avec le bouton natif de l’éditeur. Le panneau donne la place au document, avec les commandes de sauvegarde, de reprise d’une sélection et de retour aux versions. La sélection est prévisualisée puis ajoutée explicitement au brouillon ; elle n’envoie pas de message et ne remplace pas automatiquement le document.

AlpenData garde les objets privés et leurs versions. Collabora reçoit un jeton WOPI signé, limité à une session de douze heures et à un document. Le navigateur transmet ce jeton par formulaire POST vers l’iframe, sans le placer dans l’URL de l’éditeur. Le secret de signature reste exclusivement dans l’API AlpenData. Il ne s’agit pas d’un secret partagé à configurer dans Collabora.

Chaque ouverture correspond à une ressource WOPI distincte et à une version précise, ce qui évite de mettre en coédition des utilisateurs ou conversations. Les verrous WOPI sont persistés en PostgreSQL et expirent après trente minutes sans renouvellement. Les lectures et sauvegardes revérifient la personne, l’appartenance et les droits du projet. Un retrait d’accès bloque les prochaines requêtes ; il ne peut effacer les octets déjà ouverts dans un navigateur.

Une sauvegarde crée une version immuable. Si le fichier a changé ailleurs, elle crée une copie accessible aux mêmes personnes que le document publié, sans partager son original personnel. Le même contrôle s’applique si cette copie change ensuite ailleurs. Une répétition du dernier contenu enregistré ne crée pas de version supplémentaire. Les formats sont validés avant stockage, avec les limites actuelles de 5 Mo par fichier et 500 Mo de versions par propriétaire.

## Configuration et activation

- `ALPENDATA_OFFICE_ORIGIN` : origine HTTPS exacte de Collabora, sans chemin. Elle doit être distincte de l’origine de l’application.
- `ALPENDATA_OFFICE_SECRET` : secret aléatoire d’au moins 32 caractères, uniquement dans l’API. Sa rotation invalide les anciens jetons.
- Générer l’entrée HTTPS AlpenData avec `--office-origin` égal à cette origine : la CSP autorise l’iframe et le formulaire POST, sans autoriser le chargement de scripts Collabora dans la page principale.
- Collabora autorise uniquement l’origine WOPI AlpenData dans `storage.wopi.alias_groups` ; ne pas utiliser de motif global. `PostMessageOrigin` est fourni par l’API. Le frontend vérifie également l’origine et la fenêtre émettrice des messages.
- Garder `ssl.ssl_verification=true` et configurer la chaîne de confiance TLS de l’hôte WOPI. Derrière une terminaison TLS, utiliser le mode `ssl.termination=true`, un port local non exposé, et relayer les WebSockets `/cool/`, les ressources `/browser/` et `/hosting/`. Déclarer `server_name` avec le nom externe de l’éditeur.
- Isoler le service et ses fichiers temporaires, limiter CPU/mémoire/processus, conserver les protections de processus du conteneur et ne monter ni stockage client, ni clés de modèles, ni socket Podman dans Collabora. La recette utilise un conteneur non privilégié, sans capacités ajoutées, limité à 2 CPU, 2 Go et 256 processus.
- Désactiver l’IA propre à Collabora et sa configuration utilisateur (`ai.enabled=false`, `ai.allow_user_settings=false`), les macros et les services linguistiques externes. Les actions de l’assistant continuent de passer par AlpenData et ses permissions.
- Sur une infrastructure partagée, isoler aussi le réseau : limiter les sorties de l’éditeur à l’hôte WOPI autorisé, bloquer les métadonnées cloud et les autres services internes, et contrôler les sources externes des documents. Le réseau hôte de la recette locale n’est pas une configuration de production pour des documents clients.
- Les jetons WOPI apparaissent dans les requêtes serveur : désactiver les journaux d’accès qui conservent les arguments et ne pas publier les journaux bruts de l’éditeur. Aucune connexion tierce d’utilisateur n’est transmise à Collabora.
- Appliquer la migration `0040`, qui ajoute les verrous et invalide les anciennes sessions ONLYOFFICE sans toucher aux documents. Un retour de migration invalide aussi les sessions actives. Garder l’activation de la nouvelle interface limitée aux entreprises du pilote.

L’ancien réglage `ALPENDATA_OFFICE_AUTOMATION_ENABLED` est retiré : la sélection utilise l’API PostMessage gratuite de Collabora (`Action_Copy`), sans option commerciale.

## Version et recette reproductible

Image officielle testée : **CODE 26.04.3.2**, identifiant local `sha256:efa5a5d1f2ab25d4361535478cdd3a75bd2c91daadf5b2ee389230ba5b5bf93b` ; référence registre `docker.io/collabora/code@sha256:379b8f1fc955dd6d01ba24adf61d1b177048ddaae179ae8c1e6a6342daccb282`. Épingler l’image et refaire la recette avant une mise à jour.

`test_collabora_live.py` utilise le véritable conteneur, Chromium, le build React, HTTPS et PostgreSQL. Le serveur et Collabora vérifient le certificat de test ; seul le navigateur de recette accepte ce certificat local. Aucun appel modèle ou compte client n’est nécessaire. Les dépendances supplémentaires de cette recette sont Playwright 1.62.0, python-docx 1.2.0, openpyxl 3.1.5 et python-pptx 1.0.2 ; elles sont installées uniquement dans l’environnement QA. Chromium validé : 152.0.7977.82.

Depuis la racine du dépôt Linux, avec `HERMES_PYTHON` désignant ce Python QA :

```bash
bash scripts/run_tests.sh alpendata/backend/tests/test_collabora_live.py -j 1 -- \
  -c alpendata/backend/pyproject.toml \
  --postgresql-bin=/usr/lib/postgresql/17/bin \
  --collabora-image=sha256:efa5a5d1f2ab25d4361535478cdd3a75bd2c91daadf5b2ee389230ba5b5bf93b \
  --chromium-bin=/usr/bin/chromium \
  --frontend-dist=/chemin/absolu/alpendata/frontend/dist \
  --document-qa-output=/chemin/prive/recette-collabora
```

La recette couvre ordinateur anglais et mobile français : ouverture et sauvegarde des trois formats, relecture des contenus enregistrés, capture de sélection Word, modification concurrente et conservation de la copie. Les tests WOPI complémentaires couvrent refus des jetons invalides, substitution de session, verrous périmés et remplacés, répétitions de sauvegarde, conflits successifs et révocation personnelle/de projet. La découverte rejette les origines étrangères, les redirections, les XML dangereux ou malformés et les réponses trop grandes.

## Limites retenues

CODE est gratuit ; l’hébergement, l’exploitation et les mises à jour restent à la charge d’AlpenData. L’éditeur et ses attributions Collabora ne sont pas présentés comme un moteur écrit par AlpenData. Le fournisseur décrit CODE comme une édition de développement, sans la garantie de stabilité et le support de son offre commerciale ; ne pas lui attribuer un SLA de production. [Présentation CODE](https://www.collaboraonline.com/code/), [FAQ](https://www.collaboraonline.com/faqs/).

La licence MPL 2.0 permet l’intégration dans un produit plus large, avec ses obligations sur les fichiers couverts et modifiés. Cette intégration ne modifie pas le code Collabora. [Licence du projet](https://github.com/CollaboraOnline/online/blob/main/COPYING), [FAQ MPL](https://www.mozilla.org/en-US/MPL/2.0/FAQ/).

La recette technique utilise des fichiers synthétiques simples. Restent à valider les documents métier complexes, polices, formules avancées, présentations riches, endurance et montée en charge. L’application automatique d’une révision IA dans une sélection, la coédition simultanée et la fidélité parfaite d’une conversion PDF ne sont pas promises par cette livraison. L’activation publique du pilote requiert encore le service durable, son origine HTTPS et la recette opérationnelle de la refonte.
