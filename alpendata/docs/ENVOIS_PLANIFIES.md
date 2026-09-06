# Briefing envoyé par e-mail

6 septembre 2026 — essai explicite puis récurrence personnelle.

## Parcours

La recette `mail_briefing_delivery` peut être proposée pendant l’onboarding lorsque la lecture des mails, l’envoi Microsoft et l’autonomie personnelle sont disponibles sous les règles communes. La proposition annonce un envoi ; le collaborateur choisit lui-même ses destinataires et l’objet. La conversation de proposition n’a aucun outil d’envoi.

Le bouton « Tester avec un envoi » ouvre un formulaire. Une case confirme les destinataires, l’objet et **un véritable envoi unique pour cet essai**. L’essai n’active aucune récurrence. Les informations modifiées retirent la confirmation ; une réponse réseau perdue conserve la même demande et ses paramètres pour retrouver l’essai.

Hermes consulte les mails récents, prépare le briefing et le soumet depuis le compte personnel. Le contenu et le reçu apparaissent dans le chat. Le propriétaire peut ensuite activer une récurrence, avec une seconde confirmation portant sur les futurs envois, leurs destinataires et l’horaire. Un reçu accepté et les lectures nécessaires sont requis côté serveur ; une simple affirmation du modèle ne permet pas l’activation.

Les tâches existantes de lecture et de préparation n’obtiennent plus l’outil d’envoi par le seul réglage personnel d’autonomie. Les conversations existantes gardent leur contexte ; le broker refuse l’envoi d’une tâche sans destination explicitement confirmée. L’autonomie du chat ordinaire garde son fonctionnement distinct, décrit dans [Autonomie personnelle](AUTONOMIE.md).

## Destination et exécution

La migration `0015` conserve dans la conversation d’essai les destinataires et l’objet validés. La nouvelle conversation de chaque occurrence reprend cette destination. L’agent ne peut pas remplacer l’objet, ajouter un destinataire, des copies, des copies cachées ou une pièce jointe. La recette actuelle produit un briefing en texte, pour vingt destinataires au maximum.

Les contrôles du broker exigent les reçus des lectures nécessaires avant la soumission. Une seule tentative d’envoi est permise par exécution pour cette recette, avec récupération idempotente de la même version. Créer un autre brouillon ne permet pas de contourner cette limite, y compris après un refus connu ou un résultat incertain. Le reçu distingue la demande acceptée par Microsoft de la livraison effective. Les droits de l’entreprise, l’autonomie personnelle, la connexion, la licence et les annulations sont revérifiés par la chaîne d’envoi existante.

L’essai ou l’occurrence n’est pas marqué comme terminé avec succès si l’envoi attendu n’a pas de reçu accepté correspondant à la destination. Le contenu du briefing et sa pertinence restent à relire : un reçu de lecture et un reçu d’envoi ne prouvent pas la qualité de la synthèse. Les lectures portent sur l’échantillon récent exposé par l’outil Microsoft, et non sur toute la messagerie.

Chaque échéance produit un briefing distinct ; la recette n’est pas une alerte limitée aux nouveautés. Elle peut reprendre des éléments du même échantillon récent. Un résultat incertain n’est pas rejoué pour la même occurrence ; les échéances suivantes restent soumises au fonctionnement de la planification et peuvent être suspendues par le propriétaire.

## Modifier ou arrêter

L’écran « Automatisations » montre la destination, l’objet, l’horaire, l’état et les résultats. La suspension et le retrait arrêtent les prochains passages. Le retrait de l’autonomie ou des accès nécessaires bloque la tâche et annule ses occurrences en file ; réautoriser ces accès ne la relance pas automatiquement.

Pour changer les destinataires ou l’objet, le propriétaire refait un essai explicitement confirmé. Il peut ensuite remplacer l’automatisation par cet essai relu. L’activation du remplacement exige la version actuelle de la planification et annule les anciennes occurrences en attente. Une autre modification intervenue pendant l’essai doit être rechargée ; elle n’est pas écrasée silencieusement.

## Vérification

Le scénario `test_routine_delivery.py` vérifie les confirmations, les propriétaires, la destination exacte, les reçus de sources, l’absence de deuxième tentative, la révocation, le remplacement versionné et les résultats incertains. Le scénario OCI utilise deux exécutions du véritable Hermes : l’essai, puis une occurrence après activation. Les transports Microsoft et modèle sont synthétiques ; les requêtes Graph portent sur la connexion du propriétaire.

Les tests d’interface couvrent les confirmations, les changements de langue, une réponse perdue et l’affichage des destinataires avant activation. Le reçu provenant du rafraîchissement du chat remplace les commandes du brouillon ; une réponse ancienne ne rétablit pas un bouton d’envoi. Une édition personnelle non enregistrée est préservée avec demande de rechargement si une autre édition arrive.

Le parcours visuel a été contrôlé sur des données fictives séparées : formulaire, reçu, activation, gestion, nouvel essai et suspension. Aucun e-mail réel n’a été envoyé. La validation avec Entra/Exchange, un modèle commercial et le client pilote reste nécessaire, de même que l’exploitation sur Infomaniak.
