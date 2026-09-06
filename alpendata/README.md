# AlpenData Agent

Adaptation d’Hermes Agent pour une utilisation simple en entreprise, sous identité AlpenData.

## État au 6 septembre 2026

- Fork GitHub créé : [Elentir1/alpendata-agent](https://github.com/Elentir1/alpendata-agent), public, issu de NousResearch/hermes-agent.
- Base examinée : `9dd6634c5635321cf38840cc30e9b51226689128`.
- Branche de développement publiée : [alpendata/main](https://github.com/Elentir1/alpendata-agent/tree/alpendata/main).
- Audit initial et architecture proposés disponibles ci-dessous.
- Un premier [backend AlpenData](backend/README.md) est implémenté localement : entreprises, membres, invitations, propriété des ressources et connexion Microsoft par MSAL. Les vérifications de base s’exécutent sur SQLite et PostgreSQL réel.
- Une première [interface AlpenData](frontend/README.md) en français et anglais est présente : connexion, entreprise, invitations et onboarding individuel. Elle reprend les actifs publics de la marque et dialogue avec le backend.
- Le [chat personnel](docs/CHAT_PERSONNEL.md) relie maintenant l’interface, les conversations durables, le [runtime Hermes isolé](runtime/README.md), les droits Microsoft et la passerelle Mistral/OpenRouter. Les tests utilisent PostgreSQL et des conteneurs réels, avec réponses externes synthétiques. L’interface a aussi été contrôlée dans un navigateur avec des données fictives. Les connexions réelles, les documents, la facturation et le déploiement restent à terminer avant le pilote.

- Le [premier résultat personnel](docs/PREMIER_RESULTAT.md) relie désormais le besoin exprimé à deux ou trois propositions Hermes, puis à un essai explicite avec références aux sources consultées. Les accès restent propres à chaque utilisateur. Les [récurrences personnelles](docs/AUTOMATISATIONS.md) sont activables après revue d’un essai et disposent d’un historique, de la modification d’horaire et de la suspension. Les tests utilisent Hermes réel et des services externes synthétiques.

## Documents

- [Publication et téléchargement de documents privés](docs/DOCUMENTS.md)

- [Audit technique Hermes](docs/AUDIT_HERMES.md)
- [Architecture AlpenData](docs/ARCHITECTURE.md)
- [Entrée HTTPS et contrôle de démarrage](docs/ENTREE_HTTPS.md)
- [Services continus et maintenance](docs/SERVICES_CONTINUS.md)
- [Séquence d’implémentation](docs/PLAN_IMPLEMENTATION.md)
- [Passerelle Mistral/OpenRouter](docs/PASSERELLE_MODELES.md)
- [Chat personnel et exécutions durables](docs/CHAT_PERSONNEL.md)
- [Consultation et correction de la mémoire personnelle](docs/MEMOIRE_PERSONNELLE.md)
- [Chiffrement et clés de récupération](docs/CHIFFREMENT_SAUVEGARDES.md)
- [Sauvegarde et restauration locales](docs/SAUVEGARDE_RESTAURATION.md)
- [Récupération opérateur d'un assistant interrompu](docs/RECUPERATION_RUNTIME.md)
- [Notifications personnelles des automatisations](docs/NOTIFICATIONS.md)
- [Ressources d’entreprise et partages explicites](docs/RESSOURCES_ENTREPRISE.md)
- [Administration des membres et des licences](docs/MEMBRES_LICENCES.md)
- [Onboarding et premier résultat](docs/PREMIER_RESULTAT.md)
- [Automatisations et autorité de planification](docs/AUTOMATISATIONS.md)
- [Révision d’origine et référence du cahier des charges](upstream.lock.json)
- [Diagnostic reproductible des profils](audit/probe_profiles.py)
- [Résultats du diagnostic](audit/results.json)

Le cahier des charges validé 1.0 est conservé dans le dossier de travail parent, sous `CAHIER_DES_CHARGES.md`. Son empreinte est enregistrée dans `upstream.lock.json`.

## Principes du fork

Conserver le moteur d’Hermes et son historique, isoler les adaptations AlpenData dans des modules identifiables, conserver les notices de licence et reprendre les corrections amont après vérification. La copie locale initiale est superficielle (`--depth 1`) ; l’historique complet reste disponible sur le fork GitHub.

Les utilisateurs AlpenData disposent chacun de leur onboarding, de leurs connexions, de leur mémoire et de leurs tâches. Les autorisations d’administration de l’entreprise ne confèrent pas l’accès aux contenus privés d’un collaborateur.

Le dossier `alpendata/` contient les travaux propres au produit. L’interface client à développer sera une surface web adaptée au cahier des charges. Le chat terminal de `web/` reste une référence technique d’Hermes, sans déterminer l’expérience du produit AlpenData.
