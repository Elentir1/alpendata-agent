# Précisions du porteur du projet — 6 septembre 2026

Ces décisions complètent le cahier des charges initial et priment sur les hypothèses antérieures de préparation du pilote.

| Sujet | Décision confirmée |
| --- | --- |
| Hébergement | Utiliser en priorité le compte Jelastic Infomaniak existant. Aucun projet Public Cloud n'est disponible. |
| Adresse publique | `https://agent.alpendata.ch`. Le choix du nom n'est pas une preuve de configuration DNS ou TLS. |
| Fournisseur IA initial | Mistral, avec un compte déjà détenu par AlpenData. Le modèle précis et le raccordement serveur restent à configurer. |
| Microsoft | Intégration facultative. Un client sans Microsoft doit pouvoir se connecter à AlpenData et utiliser les fonctions ne nécessitant pas cette intégration. |
| Invitations du pilote | Le porteur du projet gère lui-même ce travail. L'envoi automatique d'invitations ne conditionne pas le démarrage du pilote. Les appartenances, licences et parcours personnels restent nécessaires. |

## Connexion indépendante de Microsoft

L'audit du code actuel confirme que `SignIn` dans `frontend/src/App.tsx` ne propose que Microsoft et que `backend/src/alpendata_api/signin.py` ne fournit que ce parcours d'authentification. Cette dépendance est incompatible avec la précision du porteur du projet et doit être corrigée avant de lui livrer un accès utilisable sans Microsoft.

La création de documents et le chat disposent déjà de chemins ne nécessitant pas de connexion Graph. L'API `routines.py` refuse cependant les propositions initiales lorsqu'elle trouve moins de deux recettes compatibles et renvoie `microsoft_reconnect_required`. Le texte de `FirstTasks.tsx` demande également de connecter les outils avant de commencer. Le premier parcours sans intégration doit donc être corrigé, pas seulement le bouton de connexion. La connexion, les propositions initiales et le premier résultat devront être vérifiés ensemble avec un compte AlpenData indépendant, sans configurer Entra. Les tâches fondées sur des informations fournies par l'utilisateur devront être distinguées de celles qui nécessitent une source externe ; aucune lecture Microsoft ne devra être simulée pour rendre le parcours disponible.

Le choix entre e-mail/mot de passe et code reçu par e-mail est soumis au porteur du projet. La gestion manuelle des invitations ne dispense pas de vérifier l'identité du bénéficiaire. Le parcours actuel d'acceptation d'invitation utilise une preuve d'adresse envoyée par SMTP ; il ne faut donc pas le présenter comme un provisionnement manuel déjà utilisable sans messagerie. La création manuelle de comptes et leur activation devront être cohérentes avec le mode de connexion retenu. Les besoins éventuels d'e-mails de connexion ou de récupération sont distincts de l'envoi d'invitations.

## Vérification de Jelastic

La [documentation Infomaniak](https://www.infomaniak.com/fr/support/faq/2256/creer-un-vps-avec-jelastic-cloud) confirme la disponibilité de VPS et d'images Docker dans Jelastic. Elle ne prouve pas que le compte ou un nœud existant peut exécuter le runtime AlpenData actuel.

L'exécution actuelle nécessite Linux, Podman sans privilèges, les espaces de noms utilisateur, les limites de ressources et des volumes privés par propriétaire. Les services préparés utilisent PostgreSQL, Nginx et systemd utilisateur. Avant déploiement, inspecter le type de nœud, les accès disponibles et les capacités réelles de l'environnement Jelastic, puis y exécuter les vérifications d'isolation. Une simple capacité à héberger une image Docker ne suffit pas à valider l'exécution imbriquée d'agents isolés.

L'URL de console et le nom de l'environnement éventuel ont été demandés. Aucun environnement, changement DNS ou service public n'est créé par cette mise à jour. Ne pas transférer les secrets Mistral dans Git ou dans une conversation ; ils seront injectés dans la configuration serveur protégée lors du raccordement.
