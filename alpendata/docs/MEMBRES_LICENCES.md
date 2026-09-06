# Gestion des membres et des licences

6 septembre 2026 — interface d’administration et migration `0018`.

## Parcours disponible

Dans « Mon entreprise », un administrateur voit le nombre de places de l’offre, les licences attribuées, les places réservées par des invitations et les places encore disponibles. Une invitation active réserve une place jusqu’à son acceptation, son expiration ou son annulation. Le nombre de places reste celui configuré côté serveur pour le pilote ; aucun achat ni renouvellement Stripe n’est déclenché par cet écran.

« Gérer les accès » permet de modifier le rôle, l’adhésion active et l’attribution de licence d’un membre. Le formulaire explique les conséquences et demande confirmation des choix affichés. Toute modification de ces choix décoche la confirmation. Le rôle d’administrateur reste indépendant de la licence : un administrateur actif peut gérer l’entreprise sans utiliser un assistant payant.

Le retrait de licence libère une place et bloque l’exécution de l’assistant et ses automatisations. Un membre actif conserve l’accès à son historique et le contrôle de sa mémoire. La désactivation de l’adhésion bloque l’accès à cette entreprise. Les autres adhésions de ce compte ne sont pas modifiées. Aucune connexion, mémoire ou conversation n’est transférée à l’administrateur.

Rétablir un accès ne relance pas automatiquement les routines bloquées. Le propriétaire doit les reprendre selon leurs règles de validation. Une action externe déjà acceptée ne peut pas être annulée par une modification de licence ; les reçus et règles d’incertitude des parcours concernés continuent à s’appliquer.

## Contrat API

`GET /api/organizations/{organization_id}/members` reste réservé aux administrateurs actifs. Il renvoie `members`, avec une `version` par adhésion, et `seats` : `capacity`, `assigned`, `reserved`, `available`. La lecture tient le verrou d’entreprise utilisé par les attributions et invitations. Ces compteurs ne constituent pas encore une facture ou une mesure de consommation.

`PATCH /api/organizations/{organization_id}/members/{user_id}` exige maintenant les quatre champs `version`, `role`, `active`, `licensed`. L’absence de version est refusée. Une version dépassée renvoie `409 member_state_changed`. Chaque mutation acceptée incrémente la version ; l’interface relit après une réponse perdue au lieu de rejouer aveuglément une ancienne modification.

Les mutations conservent le verrou d’entreprise, la limite de places et le maintien d’au moins un administrateur actif. Deux administrateurs qui tentent d’utiliser la dernière place ne peuvent pas tous deux réussir. Le changement de rôle du compte connecté entraîne une actualisation de sa navigation ; un ancien écran ne confère pas de permission supplémentaire côté serveur.

La migration ajoute une version initiale aux adhésions existantes. Le déploiement doit appliquer `0018` avant de servir la nouvelle API et le nouveau frontend. Les scripts appelant directement le PATCH doivent lire la version actuelle. La capacité d’abonnement elle-même n’est pas modifiable par cette route.

## Validation et suite Stripe

Deux scénarios API couvrent réservations, attribution, refus croisés, administrateur sans licence, dernier administrateur, versions et concurrence PostgreSQL. Les parcours existants de chat, mémoire, notifications et tâches vérifient également les effets des retraits de licence et désactivations. Deux scénarios d’interface couvrent confirmation, capacité épuisée, réponse perdue et relecture.

La facturation reste à intégrer après définition de l’offre : tarif CHF, unité d’usage, inclusions, plafonds, proratisation, impayés et résiliation. L’achat d’une capacité supplémentaire et son attribution à une personne seront deux opérations distinctes. Le retour navigateur après paiement ne devra pas suffire à accorder des places ; l’état confirmé côté Stripe et sa synchronisation durable porteront cette autorité.

L’orientation documentée par Stripe associe Billing à Checkout pour l’abonnement, et un portail client pour sa gestion. Les changements de quantité devront respecter les places déjà attribuées et réservées. Le choix du traitement du surusage reste ouvert avec les règles commerciales. Le paramétrage TVA et les inscriptions applicables devront être vérifiés avant activation fiscale ; aucune collecte automatique n’est activée ici. Référence consultée : [intégration des abonnements Stripe](https://docs.stripe.com/billing/quickstart).
