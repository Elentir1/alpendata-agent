# Comptes AlpenData du pilote

La connexion e-mail/mot de passe, l'activation et le changement de mot de passe sont disponibles en français et anglais. Microsoft et SMTP sont facultatifs. Il n'y a pas encore d'inscription publique : AlpenData prépare les comptes du pilote et remet les liens manuellement.

## Préparation par l'opérateur

Exécuter avec la configuration serveur protégée et une base migrée en `0022`. Les commandes ci-dessous sont des exemples ; aucun compte réel n'est créé par ce document.

```bash
python -m alpendata_api.accounts create \
  --email personne@example.com --name 'Prénom Nom' \
  --activation-file /chemin/protege/activation-personne.txt
```

Sans organisation, le bénéficiaire peut créer son entreprise après activation. Pour rattacher un collaborateur à une entreprise existante, ajouter `--organization-id UUID` et éventuellement `--role admin` ; le rôle par défaut est `member`. La commande vérifie la capacité de licences et crée un onboarding propre au collaborateur.

Le fichier de sortie doit avoir un chemin absolu et un dossier parent existant, privé, hors Git et synchronisation cloud. La création exclusive refuse un fichier existant ; les droits Unix sont `0600`. La commande n'affiche jamais le lien ni le mot de passe. Vérifier sa sortie `activation_prepared` avant de remettre le lien au bénéficiaire vérifié. Un échec peut laisser un fichier vide ou inutilisable : ne pas le distribuer et utiliser un nouveau chemin lors de la reprise.

Le lien expire après 24 heures et ne sert qu'une fois. L'utilisateur choisit une phrase de passe de 15 à 128 caractères. Le navigateur retire le jeton de l'adresse et le garde temporairement dans le stockage de session, puis l'efface après activation ou abandon. Les mots de passe ne sont pas stockés dans ce stockage navigateur. Une remise manuelle n'établit pas une preuve SMTP et ne fusionne pas les identités par adresse e-mail.

## Changement et récupération

Le propriétaire connecté peut changer son mot de passe en confirmant l'actuel. Les autres sessions sont révoquées. En cas de perte, l'opérateur vérifie le demandeur avant de préparer un nouveau lien :

```bash
python -m alpendata_api.accounts reset \
  --email personne@example.com \
  --activation-file /chemin/protege/recuperation-personne.txt
```

Cette opération invalide immédiatement l'ancien mot de passe, les sessions et le lien d'activation précédent. Elle conserve les appartenances et données de travail. Une restauration de sauvegarde invalide également tous les mots de passe restaurés ; les bénéficiaires doivent être revérifiés avant récupération.

## Protections et limites

Argon2id utilise 64 Mio, trois passes et un sel aléatoire propre à chaque empreinte. Deux calculs simultanés au maximum sont admis par processus. Une limitation persistante en base contrôle les tentatives par adresse réseau et identité, y compris après redémarrage. La configuration du proxy doit transmettre l'adresse cliente à travers la frontière de confiance prévue.

Les sessions utilisent un cookie opaque Secure/HttpOnly/SameSite et les écritures contrôlent l'origine. Les erreurs de connexion restent génériques, les erreurs de validation n'incluent pas les secrets soumis, et l'activation concurrente n'aboutit qu'une fois. HTTPS est requis pour le déploiement. MFA et récupération autonome par e-mail ne sont pas implémentées dans ce parcours pilote.

Les nouveaux comptes peuvent travailler à partir de leurs propres indications sans intégration. Les connexions externes, mémoires et onboarding restent propres à chaque personne. Le rôle administrateur n'ouvre pas les intégrations privées des collègues.
