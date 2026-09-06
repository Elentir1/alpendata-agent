# Règles d’accès de l’entreprise

6 septembre 2026 — limites communes reliées aux connexions personnelles et aux automatisations.

## Parcours

L’administrateur retrouve quatre choix dans « Mon entreprise » : lecture des mails, consultation des agendas, recherche/lecture des documents et enregistrement Microsoft 365. Interdire l’accès documentaire interdit aussi l’enregistrement. Les règles s’appliquent à tous les membres, administrateurs compris. Elles limitent les possibilités du collaborateur sans lui fournir de connexion ni remplacer son consentement personnel.

En l’absence de règle enregistrée, les quatre capacités peuvent être autorisées personnellement. Aucune connexion n’est créée et aucun consentement Microsoft n’est obtenu par défaut. Un administrateur actif sans licence peut gérer les règles, comme il peut déjà gérer les membres.

Les choix restreints sont désactivés dans les outils personnels, avec une explication en français ou anglais. Les erreurs d’accès du chat, de la planification et de l’enregistrement renvoient également vers les règles de l’entreprise. Les autorisations d’action autonome de l’agent et les règles propres aux envois d’e-mails restent à réaliser ; les dépôts documentaires exigent encore la confirmation du propriétaire.

## Application côté serveur

La migration `0011` ajoute une politique par entreprise : capacités permises, version, auteur et date de la dernière modification. `GET /api/organizations/{id}/policy` est accessible aux membres actifs ; `PUT` exige un administrateur. Le numéro de version empêche deux administrateurs d’écraser silencieusement leurs modifications. Une réponse perdue ou un conflit conduit l’interface à demander de recharger l’état actuel avant de modifier à nouveau les règles.

La passerelle Microsoft vérifie les règles à l’intérieur de la transaction qui verrouille le membre et utilise son coffre personnel. Cette vérification couvre les lectures, les téléchargements SharePoint, le choix des dossiers, l’écriture confirmée et la vérification d’un résultat incertain. Les connexions nouvelles sont contrôlées au départ du consentement et à son retour : un parcours commencé avant une restriction ne peut pas la contourner en se terminant après.

La modification administrative verrouille l’entreprise puis les membres dans un ordre stable. Les opérations Microsoft déjà en cours peuvent terminer sous leurs autorisations initiales ; la modification attend ces verrous avant de valider les nouvelles règles. Les appels suivants observent les nouvelles limites. Les identifiants Microsoft ne sont pas transférés, exposés à l’administrateur ou supprimés par ce réglage.

## Conversations et planification

Les nouvelles conversations reçoivent uniquement les capacités personnelles encore permises. Les conversations existantes gardent leur contexte et leurs schémas d’outils ; le broker refuse un appel devenu interdit. Les propositions d’onboarding sont aussi confrontées aux droits courants avant d’être conservées.

Les automatisations actives qui dépendent d’un accès retiré passent à l’état bloqué, sans prochaine exécution. Les occurrences en file sont annulées ; celles en cours reçoivent une demande d’arrêt. Réautoriser un accès ne réactive pas ces tâches. Le propriétaire peut demander leur reprise, qui revérifie les règles, sa connexion et les autres conditions existantes.

Ces règles contrôlent les nouveaux accès externes. Elles ne suppriment pas les conversations, mémoires et documents déjà conservés dans l’espace personnel. L’administrateur n’obtient aucun droit supplémentaire sur ces contenus. La conservation et la suppression restent des fonctions distinctes à compléter.

## Vérification

`test_company_policy.py` exerce l’application réelle, les migrations, MSAL, le coffre et les transactions. Il vérifie le rôle administrateur, la version concurrente, le refus des confirmations déjà préparées, les nouvelles connexions et les retours de consentement tardifs, les capacités des nouvelles conversations et la stabilité des anciennes. Un contrôle PostgreSQL maintient une lecture Microsoft en cours pendant la modification des règles, vérifie l’attente de cette modification puis le refus des lectures suivantes et l’arrêt de la planification concernée.

Le frontend vérifie la cohérence lecture/écriture, le changement de langue, le conflit entre administrateurs et l’impossibilité de réautoriser un accès depuis les choix personnels. L’écran a été contrôlé visuellement en français et anglais sur un aperçu séparé, explicitement fictif. Les services Microsoft et le modèle restent synthétiques dans les tests locaux ; l’essai de l’ensemble sur l’environnement Infomaniak et avec le pilote reste à réaliser.
