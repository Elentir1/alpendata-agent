# AlpenData Agent

Adaptation d’Hermes Agent pour une utilisation simple en entreprise, sous identité AlpenData.

## État au 5 septembre 2026

- Fork GitHub créé : [Elentir1/alpendata-agent](https://github.com/Elentir1/alpendata-agent), public, issu de NousResearch/hermes-agent.
- Base examinée : `9dd6634c5635321cf38840cc30e9b51226689128`.
- Branche de développement publiée : [alpendata/main](https://github.com/Elentir1/alpendata-agent/tree/alpendata/main).
- Audit initial et architecture proposés disponibles ci-dessous.
- Un premier [backend AlpenData](backend/README.md) est implémenté localement : entreprises, membres, invitations, propriété des ressources et connexion Microsoft par MSAL. Les vérifications de base s’exécutent sur SQLite et PostgreSQL réel.
- Une première [interface AlpenData](frontend/README.md) en français et anglais est présente : connexion, entreprise, invitations et onboarding individuel. Elle reprend les actifs publics de la marque et dialogue avec le backend.
- La connexion aux données Microsoft et l’exécution isolée d’Hermes restent à réaliser. Cette première version est publiée sur la branche de développement ; elle ne constitue pas encore une application utilisable par le pilote.

## Documents

- [Audit technique Hermes](docs/AUDIT_HERMES.md)
- [Architecture AlpenData](docs/ARCHITECTURE.md)
- [Séquence d’implémentation](docs/PLAN_IMPLEMENTATION.md)
- [Révision d’origine et référence du cahier des charges](upstream.lock.json)
- [Diagnostic reproductible des profils](audit/probe_profiles.py)
- [Résultats du diagnostic](audit/results.json)

Le cahier des charges validé 1.0 est conservé dans le dossier de travail parent, sous `CAHIER_DES_CHARGES.md`. Son empreinte est enregistrée dans `upstream.lock.json`.

## Principes du fork

Conserver le moteur d’Hermes et son historique, isoler les adaptations AlpenData dans des modules identifiables, conserver les notices de licence et reprendre les corrections amont après vérification. La copie locale initiale est superficielle (`--depth 1`) ; l’historique complet reste disponible sur le fork GitHub.

Les utilisateurs AlpenData disposent chacun de leur onboarding, de leurs connexions, de leur mémoire et de leurs tâches. Les autorisations d’administration de l’entreprise ne confèrent pas l’accès aux contenus privés d’un collaborateur.

Le dossier `alpendata/` contient les travaux propres au produit. L’interface client à développer sera une surface web adaptée au cahier des charges. Le chat terminal de `web/` reste une référence technique d’Hermes, sans déterminer l’expérience du produit AlpenData.
