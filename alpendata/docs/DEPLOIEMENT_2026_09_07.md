# Production pilote — 7 septembre 2026

Déploiement demandé et autorisé par le propriétaire. Release applicative `d1ad4e176d89f866ce2ed5c4c6bfdf998fca0fc5`, publiée sur https://agent.alpendata.ch, avec migration PostgreSQL `0023` → `0040`. L’interface de travail est activée uniquement pour l’entreprise AlpenData. Les préfixes et propriétaires des discussions existantes sont conservés.

## Services activés

- React, API FastAPI, worker de discussion et planificateur de cette release ; état de disponibilité `ready` et unités actives.
- Modèle principal Mistral `zai-glm-5-2`, image Hermes `sha256:37995e02f951e2dc42c0fe52c41a0d1a83632876b9435f9bfed02d5116d7a176`. Chaque fichier Python embarqué du runtime a été comparé au commit déployé.
- Lecture d’images `mistral-small-2603` et transcription `voxtral-mini-2602`, via le compte Mistral existant. Ces modèles ont été vérifiés par les sondes synthétiques précédentes.
- Connexions Infomaniak disponibles avec chiffrement des identifiants ; chaque personne doit connecter ses propres services.
- Collabora CODE 26.04.3.2 sur https://office.agent.alpendata.ch. Image officielle épinglée `sha256:efa5a5d1f2ab25d4361535478cdd3a75bd2c91daadf5b2ee389230ba5b5bf93b`. Aucun achat ONLYOFFICE.

## Isolation de l’éditeur

Le service `alpendata-office` utilise un réseau Podman interne dédié, sans route par défaut ni DNS externe. Le processus du conteneur fonctionne en UID 1001, sans capacités, avec `no-new-privileges`, 2 CPU, 2 Gio et 256 processus maximum. Aucun volume client, secret de modèle ou socket Podman n’est monté. Les fichiers temporaires du conteneur sont supprimés lors de son remplacement.

Le pare-feu dédié autorise uniquement le HTTPS vers l’entrée WOPI de l’hôte. Nginx refuse les autres chemins de l’API depuis ce réseau et ne transmet pas de cookies à Collabora. Les certificats WOPI sont vérifiés ; l’éditeur accepte uniquement l’origine AlpenData. Macros, console administrateur, IA propre à Collabora et Zotero sont désactivés. Les journaux d’accès HTTP sont désactivés ; les diagnostics de service restent réservés à l’exploitation.

Contrôles réels : chemin WOPI joignable, autre API refusée en 403, connexions vers les métadonnées cloud, le port API interne et Internet bloquées. Le service a été redémarré avec succès après la recette. Les unités Office et pare-feu sont activées au démarrage.

Le certificat Office expire le 6 décembre 2026 ; renouvellement automatique et hook de rechargement Nginx testés avec `certbot renew --dry-run --run-deploy-hooks`. Domaine A ajouté chez Infomaniak ; aucune modification des enregistrements des autres services.

## Sauvegarde et reprise

La bascule a interrompu temporairement les écritures publiques, arrêté les workers, puis sauvegardé PostgreSQL et le répertoire d’état personnel avant migration. Dump et archive ont été relus. Sauvegarde protégée sur l’hôte : `/root/alpendata-before-d1ad4e176d89f866ce2ed5c4c6bfdf998fca0fc5/`. Elle contient aussi l’environnement protégé, les anciennes unités, Nginx et la référence du runtime. Aucun secret ni contenu de sauvegarde n’est rapatrié dans le dépôt.

Release et procédures exécutées : `/srv/alpendata/releases/d1ad4e176d89f866ce2ed5c4c6bfdf998fca0fc5/`, sous-répertoire `operations` réservé à l’opérateur. La première sonde publique immédiatement après rechargement a rencontré la transition de maintenance ; le contrôle suivant a confirmé HTTP 200 et la correspondance exacte du fichier d’entrée avec le build déployé.

Le retour visuel à l’ancienne interface passe par le retrait de l’entreprise de `ALPENDATA_WORKSPACE_ORGANIZATIONS`, puis le redémarrage de l’API. Les données et la nouvelle base restent conservées. Ne pas restaurer automatiquement le dump antérieur une fois le trafic réouvert : cela ferait perdre les écritures ultérieures. Un retour complet du backend exige une sauvegarde récente et une procédure de compatibilité validée.

## Recette de production

Trois contrôles réussis via le lanceur officiel `scripts/run_tests.sh`, dans une entreprise technique distincte et avec uniquement des données fictives :

1. Ordinateur anglais : ouverture et sauvegarde DOCX, XLSX et PPTX, relecture des octets enregistrés, sélection Word vers le brouillon, édition concurrente conservée dans une copie.
2. Mobile français avec interactions tactiles : mêmes vérifications sur les trois formats. Captures examinées.
3. GLM 5.2 réel : création et publication d’un Word, soumission idempotente d’un même message et reprise des événements SSE avec curseur après fermeture du flux.

Les deux contrôles Office ont passé en 21,5 secondes ; le contrôle chat en 45,5 secondes. Les certificats publics sont vérifiés, sans exception navigateur. Tous les comptes techniques sont désactivés et toutes leurs sessions révoquées ; l’activation temporaire de leur entreprise a été retirée. Les recettes de production sont archivées hors des tests courants pour éviter un lancement accidentel.

Le JavaScript public `index-Box3VK-B.js` a l’empreinte SHA-256 `acc6ba3776f6f131c0240d2b0c83f6e94d960ed88b655e9368e177c72c1b8f83`. Après les contrôles : environ 54 Gio de disque libres et 6,3 Gio de mémoire disponibles.

## Limites et suite

Microsoft 365 requiert encore la configuration OAuth de l’application et les comptes de recette ; Infomaniak requiert la connexion personnelle des comptes de test. La recherche Brave n’est pas activée sans son accès fournisseur. Le stockage documentaire utilise actuellement le stockage privé du serveur Infomaniak ; la migration vers le stockage objet Swift et son renouvellement d’identifiants restent à effectuer. La facturation est inchangée.

La recette administrative métier, les documents Office complexes, l’endurance, la montée en charge, la sauvegarde hors hôte et la politique de purge restent à valider. CODE reste l’édition gratuite de développement, sans SLA fournisseur. Ce déploiement rend le pilote utilisable ; il ne constitue pas la recette complète des quatre lots du cahier des charges.
