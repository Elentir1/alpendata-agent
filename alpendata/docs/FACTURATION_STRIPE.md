# Abonnements et licences Stripe

6 septembre 2026 — migrations `0020` et `0021`, SDK Python officiel `15.6.1`, API `2026-08-26.dahlia`.

L'administrateur retrouve « Abonnement et factures » dans « Mon entreprise ». Il choisit un nombre de places puis confirme son paiement sur Stripe Checkout. Le portail Stripe permet ensuite de gérer la quantité, le moyen de paiement, les factures et la résiliation. Le retour ouvre l'entreprise concernée et relit l'état côté serveur. Chaque collaborateur garde ses connexions, sa mémoire et ses contenus personnels.

Le prix mensuel par place vient d'un **Price Stripe en CHF configuré par l'opérateur**. Aucun tarif commercial n'est fixé dans le code. Les montants des tests et de l'aperçu sont fictifs. Le parcours ne facture pour l'instant ni consommation IA ni prestations : le tarif, la consommation incluse, les plafonds et le surusage restent à définir. Les entreprises sans abonnement conservent leur régime pilote actuel ; l'inscription commerciale publique et la durée de ce pilote restent à finaliser.

## Activation des places

Une création de Checkout, une URL de succès ou la quantité envoyée dans une notification ne donnent aucun droit supplémentaire. L'API vérifie la signature du corps brut des notifications Stripe, puis relit les abonnements du client Stripe déjà associé à cette entreprise en base. Les lectures sont sérialisées par entreprise. Les doublons et événements dans le désordre relisent ainsi l'état actuel ; aucun ancien événement payé ne réactive directement un abonnement résilié.

Le raccordement accepte un abonnement comportant une seule ligne du Price configuré, de 1 à 1 000 places, avec le client, l'environnement et la référence d'entreprise attendus. Plusieurs abonnements non terminés ou une structure différente conduisent à un état à vérifier. L'accès exige un abonnement `active`, sa dernière facture `paid` et une échéance future. Une annulation planifiée borne également cette échéance. La capacité affichée suit la quantité de l'abonnement ; la disponibilité de l'assistant dépend séparément de son paiement.

Cette première politique suspend les exécutions pendant un impayé, une activation incomplète ou un état à vérifier. Elle n'accorde pas de délai de grâce supplémentaire. Les règles commerciales d'essai et d'impayés doivent être finalisées avant ouverture. En cas de notification manquante, un accès déjà confirmé ne dépasse pas son échéance ; l'administrateur peut demander une actualisation. Un service indépendant relit aussi périodiquement les abonnements. La surveillance externe de ce service et de la réception des webhooks reste à installer pour l'exploitation.

## Actualisation automatique

`python -m alpendata_api.billing_worker` vérifie les clients Stripe déjà associés en base, dans le même environnement test ou live que sa configuration. Il ne crée ni client, ni paiement, ni abonnement. Il exige la configuration Stripe et la base, sans avoir besoin d'un modèle IA ou d'un runtime Hermes.

Chaque lecture réussie, qu'elle vienne d'une notification, d'un administrateur ou du service, fixe la prochaine vérification cinq minutes plus tard. Les échéances sont en base et survivent aux redémarrages. Le worker traite une entreprise par itération, dans l'ordre des échéances, et attend cinq secondes quand aucune n'est due. Cette cadence dépend de sa disponibilité et de la charge ; elle ne garantit pas un délai maximum de cinq minutes sur un hôte indisponible ou saturé.

Les instances concurrentes utilisent les verrous PostgreSQL des entreprises. Une entreprise déjà prise est ignorée temporairement pour laisser une autre instance travailler sur la suivante. Les notifications et les actualisations administrateur utilisent le même verrou. Une erreur Stripe ne bloque donc pas les autres entreprises : son échéance est repoussée de cinq minutes et son code d'erreur nettoyé est conservé. La dernière confirmation d'accès et son échéance restent inchangées, sans prolongation. Une réponse invalide ne doit pas laisser de mise à jour partielle ; la lecture est appliquée dans une transaction annulable.

L'écran de facturation affiche la dernière vérification réussie et, après un échec automatique, la prochaine tentative prévue. Le journal du service reçoit `sync_failed`, sans identifiant client, contenu de facture ou détail privé du fournisseur. Les erreurs de base font échouer le processus pour que son superviseur puisse le relancer. Un arrêt demandé termine la lecture déjà admise puis quitte sans prendre la suivante.

Après une restauration, les abonnements connus sont à vérifier immédiatement, mais les autres suspensions de restauration continuent de s'appliquer : une confirmation de facturation ne relance pas les anciennes tâches. Générer et installer l'unité facultative avec `--with-billing`, puis démarrer `alpendata-billing` comme décrit dans [Services continus](SERVICES_CONTINUS.md). Il ne faut pas l'activer dans un environnement sans configuration Stripe.

Si une diminution du nombre de places passe sous le nombre de membres licenciés, les exécutions sont suspendues jusqu'à régularisation. L'administrateur conserve l'accès à la facturation et choisit les licences à retirer, ou augmente la quantité. Aucun collaborateur n'est sélectionné automatiquement. Les invitations excédentaires doivent être annulées avant leur acceptation. Une diminution ne supprime aucun historique.

Le contrôle s'applique aux routes nécessitant une licence, aux nouveaux appels du worker, à son contrôle périodique et à la livraison de sa réponse. Le planificateur utilise le même contrôle et bloque les tâches concernées. Les opérations externes déjà engagées peuvent se terminer. Les historiques et l'administration restent accessibles aux membres actifs selon leurs droits habituels. Une régularisation ne relance pas automatiquement une tâche bloquée.

## Reprises après une interruption

La base conserve les clés de création du client Stripe et de Checkout avant les appels distants. Un même UUID et les mêmes paramètres reprennent la demande ; une autre langue ou quantité avec cet UUID est refusée. Un autre UUID ne permet pas de créer une deuxième demande tant qu'un Checkout demeure ouvert ou incertain. Le formulaire retrouve la référence en base après rechargement, sans stockage de clé Stripe dans le navigateur.

Les écritures ne sont pas relancées automatiquement par le SDK. Pendant la première demi-heure, une reprise explicite utilise les mêmes paramètres et la même clé. Ensuite, l'API recherche la session parmi celles du client, à partir de la référence immuable de la demande. Après son expiration fixe d'une heure, une recherche exhaustive sans résultat clôt la demande : un nouvel essai devient possible sans prolonger la session initiale. Une recherche tronquée ou ambiguë demande une vérification opérateur.

La création d'un client Stripe dont l'issue demeure inconnue après 23 heures n'est pas répétée : il faut retrouver et vérifier le client dans Stripe avant de rétablir son association. Aucun rapprochement automatique sur l'adresse e-mail n'est réalisé. Cette récupération exceptionnelle doit encore disposer d'un outil opérateur dédié ; elle ne doit pas être contournée par la suppression de la ligne en base.

Une restauration conserve les références de facturation mais retire l'accès précédemment confirmé des entreprises ayant un abonnement. Une lecture Stripe fraîche est nécessaire pour le rétablir. Les sessions utilisateur et les automatisations suivent en plus la suspension habituelle de restauration.

## Configuration de l'environnement de test

Quatre valeurs serveur activent le raccordement ensemble :

| Variable | Valeur attendue |
| --- | --- |
| `ALPENDATA_STRIPE_API_KEY` | Clé restreinte de l'environnement Stripe retenu, avec les droits nécessaires. |
| `ALPENDATA_STRIPE_WEBHOOK_SECRET` | Secret de signature du point d'entrée, distinct de la clé API. |
| `ALPENDATA_STRIPE_PRICE_ID` | Price actif, CHF, mensuel, par unité, `licensed`, montant entier positif, sans transformation de quantité. |
| `ALPENDATA_STRIPE_PORTAL_CONFIGURATION_ID` | Configuration du portail correspondant au même environnement. |

Les secrets restent dans le stockage de secrets de l'hébergement et la configuration serveur protégée, jamais dans Git ou le frontend. Le mode test/live est dérivé du préfixe de la clé et vérifié sur les notifications et objets concernés. Prévoir les permissions de lecture Prices/Subscriptions/Portal configurations/Checkout sessions et de création Customers/Checkout sessions/Portal sessions. L'identification publicitaire et la télémétrie facultative du SDK sont désactivées. Ne pas activer la journalisation détaillée du SDK sur les données du pilote.

Configurer le portail pour autoriser uniquement la modification de `quantity` sur le Price retenu, avec `proration_behavior=always_invoice`, et une résiliation `at_period_end`. Activer également l'historique des factures et la modification du moyen de paiement ; borner les quantités entre 1 et 1 000. Le serveur vérifie la configuration de quantité, de prorata, de produit et de résiliation avant de créer une session de portail. La configuration du portail peut changer dans Stripe : la validation en environnement de test fait partie de la recette à réaliser.

Le point d'entrée public est `POST /api/billing/stripe/webhook`. Configurer les événements `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`, `checkout.session.completed`, `checkout.session.async_payment_succeeded` et `checkout.session.async_payment_failed`. Le corps est limité à 1 Mio et sa signature est vérifiée avec la tolérance du SDK. Cette route ne dépend pas d'une session navigateur ; les routes d'administration utilisent les contrôles habituels de session et d'origine.

`automatic_tax` n'est pas activé par ce code. Le paramétrage fiscal, notamment l'éventuelle activation de Stripe Tax après vérification des enregistrements, reste une étape préalable à la facturation réelle. Les prix, taxes, proratas et conditions doivent être contrôlés dans Checkout et le portail avant ouverture.

## Recette et limites

Les tests utilisent le vrai SDK Stripe sur un serveur HTTP local, PostgreSQL, des signatures HMAC vérifiées par Stripe et les véritables contrôles du worker. Ils couvrent les réponses perdues, le redémarrage de l'API, la concurrence, les accès administrateur, les quantités, les factures non payées, les événements répétés ou périmés, l'expiration de Checkout, les configurations incompatibles et la restauration. Les appels Stripe réels, le rendu des pages Stripe, les paiements de test et les notifications publiques ne sont pas encore validés. Aucun abonnement ou paiement commercial n'a été créé.

Références primaires : [SDK Python officiel](https://github.com/stripe/stripe-python), [cycle de vie des abonnements](https://docs.stripe.com/billing/subscriptions/overview), [notifications d'abonnement](https://docs.stripe.com/billing/subscriptions/webhooks), [portail client](https://docs.stripe.com/customer-management/integrate-customer-portal), [configuration du portail](https://docs.stripe.com/api/customer_portal/configurations/create). Pour la consommation IA à venir, l'intégration devra être choisie après définition des unités et plafonds ; la documentation Stripe oriente les nouvelles intégrations vers [Metronome](https://docs.stripe.com/billing/usage-based).
