# Recette des comptes Microsoft 365 et Infomaniak

Le propriétaire dispose des deux comptes de test. Ce guide s’applique après activation de la nouvelle interface pour l’entreprise pilote ; il ne constitue pas un constat de recette déjà effectuée. Utiliser des contacts et fichiers fictifs, et des destinataires de test contrôlés.

## Préparer les connexions personnelles

1. Dans le compte AlpenData de test, compléter son propre profil en français ou en anglais : coach, préparation des rendez-vous, suivi des demandes clients, synthèses courtes.
2. Ouvrir **Connexions** et connecter Microsoft 365. Autoriser les sources de test nécessaires, sélectionner le périmètre SharePoint prévu et vérifier le compte affiché. Une autorisation administrateur Microsoft peut être nécessaire selon la politique du tenant.
3. Connecter **Infomaniak Mail** avec l’adresse et le mot de passe de la boîte de test, puis l’agenda et kDrive avec les accès de synchronisation personnels indiqués par l’assistant Infomaniak. Le formulaire teste chaque service. Ne pas déposer ces mots de passe dans une discussion.
4. Commencer avec l’autonomie **Préparer uniquement**. Pour les écritures de test, autoriser les capacités nécessaires dans les règles de l’entreprise et passer à **Demander ma validation**. Garder les envois autonomes pour une recette distincte et explicite.
5. Dans les premières tâches, choisir **Choisir les outils de cet essai**, puis le fournisseur à tester. Dans une discussion, utiliser **Réglages**. Une nouvelle connexion nécessite une nouvelle discussion ou une variante compatible.

Les trois parcours ci-dessous doivent être exécutés une fois avec chaque fournisseur. Noter pour chaque essai la discussion, le reçu d’action, l’identifiant du résultat externe, le résultat attendu et observé. Ne pas enregistrer les secrets dans le compte rendu.

## Jeu de données fictif

- Client « Atelier Azur », demande de préparation d’un atelier de 90 minutes et réponse souhaitée pour une date explicite.
- Un e-mail distinct pour « Studio Ambre », qui ne doit pas être utilisé comme contexte du premier client.
- Un rendez-vous de test à une heure Europe/Zurich connue, avec un destinataire de test contrôlé.
- Un document Word de brief, un classeur avec formules et plusieurs feuilles, une présentation avec notes et images, un PDF paginé. Ajouter aussi un PDF protégé et un fichier inutilisable pour vérifier l’explication de l’échec.
- Deux utilisateurs AlpenData, chacun avec sa connexion personnelle ; un projet partagé en lecture, puis en contribution, et un projet privé.

## 1. Commencer sa journée

Demande : « Prépare ma journée à partir de mes derniers e-mails et rendez-vous. Cite tes sources, sépare les engagements confirmés des suggestions et propose trois priorités. »

Attendu : messages et rendez-vous du bon compte, heure correcte, références consultables, limites de recherche expliquées, aucune écriture externe. Le premier résultat peut être noté utile ou à corriger. Fermer la page pendant le travail, la rouvrir et retrouver le résultat dans la discussion et **À suivre**.

## 2. Traiter une demande client

Demande : « Retrouve la demande d’Atelier Azur, prépare une réponse et un programme d’atelier en Word. Utilise seulement le projet et les sources d’Atelier Azur. »

Attendu : contexte correspondant au bon client ; livrable téléchargeable ; création d’une version après correction ; original conservé. Après activation de l’éditeur licencié, corriger le document manuellement et vérifier la sauvegarde, puis tester une modification concurrente : aucune version ne doit être écrasée silencieusement.

Enregistrer la pièce jointe dans un dossier de test SharePoint ou kDrive choisi explicitement. Confirmer l’envoi vers une adresse de test. Vérifier côté fournisseur le contenu, la pièce jointe et l’absence de doublon. Une réponse réseau perdue doit laisser un reçu à vérifier, sans nouvel envoi automatique. Le suivi d’un état incertain se vérifie d’abord chez le fournisseur.

## 3. Assurer le suivi

Demande : « Prépare un rendez-vous de suivi avec mon destinataire de test, puis propose une vérification le lendemain. »

Attendu : aperçu de l’heure, du fuseau et des participants ; validation explicite ; rendez-vous présent une seule fois. Vérifier la réception réelle de l’invitation, pas seulement la présence de l’événement. Une modification du rendez-vous chez le fournisseur après préparation doit provoquer un conflit explicite.

Tester la routine une fois, examiner son contenu et sa fréquence, puis l’activer. Vérifier une occurrence dans **À suivre**, suspendre la routine et confirmer qu’aucune occurrence ultérieure n’est lancée. Le fournisseur et le projet de la routine restent ceux de l’essai.

## Contrôles bloquants

- Utilisateur B ne peut ouvrir ni discussion, fichier personnel, session d’édition ou reçu d’action de A, même avec un lien connu.
- Publier une copie ne partage ni la discussion d’origine ni la connexion personnelle. Révoquer un membre retire les prochains accès aux documents et bloque l’utilisation du projet par un agent déjà lancé.
- Une branche conserve l’historique et ses pièces jointes, sans réexécuter les actions de l’original. Deux branches peuvent travailler sans mélanger leurs fichiers ou mémoires.
- Une suppression retire les accès à la discussion, arrête les travaux et désactive les routines dépendantes ; une publication indépendante demeure accessible selon les droits du projet. La suppression actuelle est logique, pas une purge physique.
- Vérifier ces parcours sur mobile et ordinateur, en FR et EN, avec fermeture du navigateur, interruption d’un travail et indisponibilité du fournisseur.

Toute fuite, double écriture, perte de version ou accès nouveau après révocation bloque l’activation pour d’autres entreprises. Les fonctionnalités sans licence ou accès fournisseur configuré restent désactivées.
