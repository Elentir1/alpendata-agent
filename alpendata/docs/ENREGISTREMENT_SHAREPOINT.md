# Enregistrement personnel dans Microsoft 365

6 septembre 2026 — parcours local implémenté ; validation Microsoft réelle à effectuer.

## Parcours utilisateur

Depuis un document créé dans le chat, « Enregistrer dans Microsoft 365 » ouvre un parcours en français ou anglais. L’utilisateur recherche un dossier ou un document proche, parcourt ses sous-dossiers, choisit le nom de sortie et prépare l’enregistrement. La préparation affiche le nom, la destination et un lien Microsoft. Elle rappelle que les personnes ayant accès au dossier pourront consulter le document.

Si ce nom existe déjà, une case de confirmation de remplacement est obligatoire avant de pouvoir confirmer. La préparation expire après quinze minutes. Changer le nom ou la destination crée une nouvelle préparation. Le contenu est celui du document immuable déjà publié dans AlpenData ; aucun nouveau contenu fourni par le navigateur n’est accepté lors de la confirmation.

L’utilisateur active séparément « Enregistrer mes documents » dans ses connexions personnelles. Cette capacité demande `Files.ReadWrite.All` déléguée. Elle n’est jamais ajoutée aux capacités du modèle ou aux anciennes conversations : les écritures de cette étape sont exclusivement déclenchées par la confirmation dans l’interface. Les règles administrateur et l’autonomie accordée aux agents restent à implémenter avant le pilote.

## Destinations et protocole

La recherche réutilise Microsoft Search avec les droits du propriétaire. Chaque résultat est résolu vers son dossier, puis ses sous-dossiers sont consultables. La recherche prend dix résultats ; le navigateur de dossiers affiche jusqu’à deux cents entrées et signale une liste partielle. La pagination complète, les bibliothèques favorites et l’accès direct aux racines restent à améliorer. Aucun identifiant de compte voisin ni URL Graph libre n’est accepté.

Le dossier et l’éventuel fichier existant sont relus avant l’écriture. Le nom et le lien du dossier, ainsi que l’identifiant et l’ETag du fichier existant, doivent correspondre à la préparation. La création utilise une [session Microsoft avec conflit `fail`](https://learn.microsoft.com/en-us/graph/api/driveitem-createuploadsession?view=graph-rest-1.0), pour refuser un nom pris pendant le transfert. L’URL temporaire reste côté serveur ; une session HTTP distincte transmet les octets sans jeton OAuth. Les mêmes destinations HTTPS Microsoft que pour le téléchargement sont admises.

Le remplacement utilise [l’API de contenu](https://learn.microsoft.com/en-us/graph/api/driveitem-put-content?view=graph-rest-1.0), l’identifiant existant et l’en-tête `If-Match`. La prise en charge effective de cette précondition sur la bibliothèque cible doit être vérifiée contre Microsoft, notamment lorsqu’une modification intervient entre la dernière lecture et l’écriture. Les tests HTTP synthétiques contrôlent l’en-tête émis et les refus ; ils ne prouvent pas le comportement du service Microsoft. Ce contrôle fait partie des conditions d’activation du pilote.

## Reçus et interruptions

La migration `0010` conserve une préparation personnelle liée au document par une clé étrangère composée : entreprise, propriétaire et document doivent correspondre. Les droits, la session, la licence et la connexion personnelle sont revérifiés avant le transfert. L’administrateur ne peut pas lire ni confirmer le reçu d’un collègue.

La confirmation inscrit et valide un état `running` dans la base avant toute mutation Microsoft. La même confirmation ne devient jamais réexécutable : un double clic, une nouvelle requête concurrente ou une réponse HTTP perdue ne déclenche pas une seconde écriture. Les échecs explicitement refusés et les résultats inconnus sont distincts. Après une panne du processus, un reçu encore en cours depuis plus de trois minutes apparaît comme incertain ; cela ne signifie pas qu’une écriture est relancée ou annulée chez Microsoft.

L’utilisateur peut actualiser le reçu ou demander de vérifier le document enregistré. Cette vérification télécharge le fichier présent à la destination et compare son SHA-256 au document AlpenData. Une correspondance confirme le contenu actuellement présent, sans renvoyer les octets vers Microsoft. Une différence ou une absence conserve l’incertitude. Une préparation vers une destination encore incertaine est refusée ; la résolution opérateur des cas non concordants reste à définir.

## Vérification

`test_sharepoint_saves.py` utilise l’API, MSAL, le coffre et les transactions réels, avec HTTP Microsoft synthétique. Il couvre la permission supplémentaire, le choix de dossier, la préparation sans écriture, les refus entre propriétaires, le remplacement explicite, l’expiration, les fichiers modifiés, la confirmation concurrente et le résultat inconnu sans répétition. La vérification par téléchargement compare les octets attendus. Les migrations et les mêmes scénarios sont exercés sous SQLite et PostgreSQL.

Le test d’interface parcourt la sélection et la confirmation, refuse un remplacement non confirmé et simule une réponse perdue : seule une lecture du reçu suit, jamais une seconde confirmation. Le parcours visuel sur des données explicitement fictives a été contrôlé en français et anglais ; l’alignement de la case de remplacement a été corrigé et revérifié.

Les bibliothèques réelles du client, les fichiers protégés ou verrouillés, le consentement Microsoft, le contrôle conditionnel du remplacement et les interruptions du service réel restent à tester. Aucune écriture sur un compte Microsoft réel n’a été effectuée pendant cette étape.
