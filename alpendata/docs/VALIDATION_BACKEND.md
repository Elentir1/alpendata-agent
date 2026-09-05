# Vérification du premier backend

5 septembre 2026. Périmètre : `alpendata/backend`, migrations `0001` à `0003`.

## Résultats

| Environnement | Résultat du lanceur officiel |
|---|---|
| Windows, Python 3.11.15, SQLite | 11 réussites, 0 échec, 1 scénario Linux ignoré. |
| Debian 13 sous WSL, Python 3.13.5, PostgreSQL 17.11 | 12 réussites, 0 échec, aucun scénario ignoré. |
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

Les invitations exigent désormais une preuve envoyée à la boîte destinataire, liée au compte connecté et à l’invitation. Les scénarios exercent cette preuve avec des messages capturés en mémoire ; un scénario distinct utilise un véritable serveur SMTP TLS local, sans relais externe. Le certificat non approuvé est refusé, et une coupure simulée après envoi invalide la preuve. Le relais de production reste à valider. L’écran de confirmation est implémenté et vérifié séparément dans les tests JSDOM de l’interface ; le parcours navigateur avec les services réels reste à valider. Les tests ne constituent pas une preuve d’isolation des processus Hermes : ces processus ne sont pas encore intégrés au backend.

Le démon Docker Desktop local a rencontré une erreur d’accès à son socket de démarrage. Les tests PostgreSQL ont donc été réalisés dans Debian avec des serveurs temporaires accessibles par socket Unix privé, sans modifier ni réinitialiser les données Docker existantes.

La procédure reproductible est décrite dans le [README du backend](../backend/README.md). Aucun déploiement Infomaniak n’a été réalisé à ce stade.

Après ajout des lectures administrateur (noms des membres et invitations en attente) et du retour HTML après interruption de connexion, les deux fichiers de tests concernés ont de nouveau passé 7 scénarios sous Windows et PostgreSQL Linux. Les lectures restent refusées aux collaborateurs et ne renvoient pas de jetons.
