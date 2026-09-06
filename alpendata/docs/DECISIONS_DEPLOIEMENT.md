# Précisions du porteur du projet — 6 septembre 2026

Ces décisions complètent le cahier des charges initial et priment sur les hypothèses antérieures de préparation du pilote.

| Sujet | Décision confirmée |
| --- | --- |
| Hébergement | Utiliser en priorité le compte Jelastic Infomaniak existant. Aucun projet Public Cloud n'est disponible. |
| Adresse publique | `https://agent.alpendata.ch`. Le choix du nom n'est pas une preuve de configuration DNS ou TLS. |
| Fournisseur IA initial | Mistral, avec un compte déjà détenu par AlpenData. Le modèle précis et le raccordement serveur restent à configurer. |
| Microsoft | Intégration facultative. Un client sans Microsoft doit pouvoir se connecter à AlpenData et utiliser les fonctions ne nécessitant pas cette intégration. |
| Connexion | E-mail et mot de passe, confirmés par le porteur du projet. Activation manuelle du pilote. |
| Invitations du pilote | Le porteur du projet gère lui-même ce travail. L'envoi automatique d'invitations ne conditionne pas le démarrage du pilote. Les appartenances, licences et parcours personnels restent nécessaires. |

## Connexion indépendante de Microsoft

La connexion par e-mail et mot de passe est désormais implémentée, avec activation et récupération manuelles, changement de mot de passe et interface français/anglais. Le parcours ne requiert ni Microsoft ni SMTP. Voir [Comptes AlpenData](COMPTES_ALPENDATA.md).

Le premier parcours peut proposer des processus, listes de travail et trames de documents à partir du profil et du besoin saisis. Ces résultats sont des brouillons dans le chat ; ils ne prétendent pas consulter une messagerie ou des fichiers. Leur essai et leur planification utilisent le véritable runtime Hermes dans les tests locaux, avec réponses de modèle synthétiques. Un compte AlpenData peut connecter ultérieurement son propre compte Microsoft, indépendamment de son identité de connexion à l'application.

L'opérateur transmet un lien d'activation personnel à usage unique après vérification du bénéficiaire. Celui-ci choisit son mot de passe. Cette remise manuelle n'est pas assimilée à une preuve de possession de l'adresse e-mail et ne fusionne jamais automatiquement un compte Microsoft portant la même adresse. Les invitations automatiques existantes restent un parcours distinct nécessitant SMTP.

## Vérification de Jelastic

La [documentation Infomaniak](https://www.infomaniak.com/fr/support/faq/2256/creer-un-vps-avec-jelastic-cloud) confirme la disponibilité de VPS et d'images Docker dans Jelastic. Elle ne prouve pas que le compte ou un nœud existant peut exécuter le runtime AlpenData actuel.

L'exécution actuelle nécessite Linux, Podman sans privilèges, les espaces de noms utilisateur, les limites de ressources et des volumes privés par propriétaire. Les services préparés utilisent PostgreSQL, Nginx et systemd utilisateur. Avant déploiement, inspecter le type de nœud, les accès disponibles et les capacités réelles de l'environnement Jelastic, puis y exécuter les vérifications d'isolation. Une simple capacité à héberger une image Docker ne suffit pas à valider l'exécution imbriquée d'agents isolés.

Console fournie : `https://app.jpc.infomaniak.com/`. Environnement existant : **Agentbox - Pilote 01**, `agentbox-pilot.jcloud-ver-jpc.ik-server.com`, nœud **215892**, Docker Engine CE 27.5.1 sur AlmaLinux 9. L'environnement était interrompu ; il a été démarré et son état « En cours d'exécution » a été constaté dans la console. Le terminal Web SSH est accessible. Cela ne valide pas encore l'isolation du runtime AlpenData. Aucun déploiement applicatif ni changement DNS/TLS n'a été réalisé à cette étape. Ne pas transférer les secrets Mistral dans Git ou dans une conversation ; ils seront injectés dans la configuration serveur protégée lors du raccordement.
