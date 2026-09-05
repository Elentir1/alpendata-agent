# Audit initial d’Hermes pour AlpenData

5 septembre 2026 — révision `9dd6634c5635321cf38840cc30e9b51226689128`.

## Conclusion

Le fork est une base pertinente pour le moteur de l’assistant. Les adaptations structurantes concernent l’expérience web, les comptes entreprise, l’autorisation par utilisateur, les connexions Microsoft déléguées et l’exécution isolée. La configuration native des profils ne suffit pas à satisfaire à elle seule le cahier des charges AlpenData.

Ce constat porte sur les composants et chemins examinés, et ne constitue ni un audit exhaustif de sécurité d’Hermes ni un constat de vulnérabilité dans son usage personnel prévu.

## Méthode et limites

- Lecture du code cloné et des instructions de développement.
- Examen des chemins de profils, des routes de gestion, des secrets, de la mémoire, de la planification et du client Microsoft Graph.
- Diagnostic local sur deux profils fictifs, dans deux processus Python, avec des contextes asynchrones entrelacés.
- Vérification documentaire des permissions Microsoft et de l’offre Public Cloud Infomaniak.
- Aucun lancement du serveur HTTP, appel à un modèle ou accès à des données client. Aucun test du déploiement Linux ou des conteneurs.
- La suite de régression Hermes n’a pas été exécutée ; aucun code du moteur n’a été modifié.

Les références ci-dessous sont relatives à la racine du dépôt, sur la révision indiquée. Les numéros de lignes se rapportent à cette révision et non à une version future de `main`.

## Constats et décisions

| Sujet | Éléments examinés | Conséquence pour AlpenData |
| --- | --- | --- |
| Chat web | `web/src/pages/ChatPage.tsx:2` et imports xterm à partir de la ligne 19 ; `web/AGENTS.md` | Le chat du dashboard embarque le terminal Hermes. Développer une surface client adaptée ; évaluer les composants Desktop et le transport partagé avant toute réécriture de logique. |
| Transport réutilisable | `apps/shared/src/json-rpc-gateway.ts` ; `hermes_cli/web_routers/chat_ws.py` | Réutilisation possible des contrats JSON-RPC et événements, derrière une API AlpenData qui contrôle les méthodes autorisées. Ce transport n’est pas encore validé de bout en bout pour AlpenData. |
| Profils | `hermes_constants.py:25`, `:80`, `:149` ; `hermes_cli/profiles.py:130` | Les chemins peuvent être sélectionnés par contexte ; les opérations de gestion retrouvent une racine commune. Prévoir une frontière d’exécution indépendante du nom de profil. |
| Gestion de tous les profils | `hermes_cli/web_routers/profiles.py:366`, `:635` ; `hermes_cli/web_server_profiles.py:145` | Les routes examinées agrègent les profils ou résolvent un nom sans contrôle d’appartenance salarié dans ces fonctions. Ne pas exposer ces routes telles quelles aux clients. |
| Authentification existante | `hermes_cli/dashboard_auth/base.py:10` ; `middleware.py:148` ; `hermes_cli/web_server.py:613` | Hermes possède déjà une authentification. Il faut ajouter une autorisation métier reliant chaque ressource à l’entreprise et au propriétaire ; une session authentifiée seule ne satisfait pas ce besoin. |
| Secrets | `agent/secret_scope.py:26`, `:47`, `:110` | Le mode multiplex dispose d’un contexte de secrets et refuse une lecture sans contexte. Préserver ces protections, tout en gardant les jetons Microsoft durables hors des environnements accessibles à l’agent. |
| Création par copie | `hermes_cli/profiles.py:34` ; `hermes_cli/web_routers/profiles.py:646` | Une copie de profil peut reprendre `.env` et la mémoire. Le provisionnement AlpenData doit créer un espace neuf à partir d’un modèle sans secrets ; jamais depuis le profil d’un salarié. La copie n’est pas activée par défaut dans `ProfileCreate` examiné. |
| Mémoire et tâches | `tools/memory_tool.py:38` ; `cron/jobs.py:59` et `:118` | Les magasins sont déjà attachés au profil. Les conserver par utilisateur, avec des contrôles AlpenData pour toute consultation et exécution. |
| Microsoft Graph | `tools/microsoft_graph_auth.py:1`, `:18`, `:128` | Le fournisseur examiné utilise `client_credentials`. Il faut un parcours OAuth délégué par utilisateur pour respecter le produit. |
| Client Graph | `tools/microsoft_graph_client.py:120` et `:154` | Le client accepte des URL absolues et réessaie les requêtes, y compris les mutations. Avant réutilisation : borner les destinations autorisées, contrôler la pagination et les en-têtes, distinguer les reprises de lecture des actions à effet externe. |

Les routes de dashboard existantes peuvent rester internes à un environnement ne contenant qu’un utilisateur. Le portail public doit exposer des fonctions métier autorisées et ne doit pas permettre au navigateur de choisir librement un profil serveur, un chemin ou une méthode RPC.

## Résultat du diagnostic des profils

Commande depuis la racine du dépôt :

```powershell
python -I -B alpendata/audit/probe_profiles.py
```

Le diagnostic importe les modules réels `hermes_constants.py` et `agent/secret_scope.py`. Il utilise uniquement des fichiers et valeurs fictifs, créés dans un dossier temporaire.

- Chaque processus retrouve son propre répertoire et sa propre mémoire fictive.
- Les deux contextes asynchrones entrelacés conservent leurs chemins et valeurs de secret respectifs.
- La lecture d’un secret sans contexte en mode multiplex est refusée.
- Le contexte initial est restauré après l’opération.
- Un processus exécuté sous le même compte système peut lire le fichier fictif voisin par son chemin explicite.

Le dernier résultat démontre la limite d’une séparation par répertoires dans cette configuration. Il ne démontre pas un contournement d’un conteneur ou d’une autorisation HTTP. L’architecture devra être testée sous Linux avec des montages et des permissions effectivement séparés.

Le résultat enregistré est disponible dans [results.json](../audit/results.json).

## Microsoft 365 : choix d’accès

Les permissions déléguées permettent d’agir au nom de l’utilisateur, dans la limite de ses droits et des permissions accordées à l’application. L’accès applicatif utilise une identité propre à l’application. Pour le pilote, retenir le premier mécanisme. [Microsoft — permissions Graph](https://learn.microsoft.com/en-us/graph/permissions-overview)

Prévoir le flux de code d’autorisation, une bibliothèque d’authentification Microsoft et la gestion de renouvellement pour les tâches planifiées. Une politique de l’organisation peut exiger un consentement administrateur ou une reconnexion : ces situations feront partie du parcours produit. [Microsoft — accès au nom d’un utilisateur](https://learn.microsoft.com/en-us/graph/auth-v2-user)

## Préparation du fork

Le fork public [Elentir1/alpendata-agent](https://github.com/Elentir1/alpendata-agent) a été créé et vérifié dans GitHub. Le dépôt local conserve `upstream` vers Nous Research et `origin` vers Elentir1 ; sa branche de travail est `alpendata/main`.

La licence MIT et son attribution sont conservées. Les dépendances, actifs visuels et composants de marque repris devront être vérifiés lors de leur intégration. La création du fork n’implique pas que les adaptations locales soient déjà publiées.

## Travaux prioritaires issus de l’audit

1. Définir et vérifier les contrôles d’appartenance aux ressources et l’isolation Linux.
2. Valider le transport de conversation entre l’API AlpenData et un agent isolé.
3. Construire la connexion Microsoft personnelle et sa révocation.
4. Réaliser le parcours onboarding → premier résultat → automatisation.
5. Ajouter les quatre formats documentaires puis les licences et la facturation.
