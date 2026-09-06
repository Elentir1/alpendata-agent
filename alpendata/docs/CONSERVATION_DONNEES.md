# Conservation et suppression des données

État vérifié dans le code le 6 septembre 2026. La durée de conservation reste une décision ouverte du cahier des charges (§ 5 et § 12). Ce document décrit les données effectivement conservées et les dépendances à traiter ; il ne constitue pas une politique de suppression déjà implémentée.

## Contrôles disponibles

Le propriétaire peut consulter, corriger et vider sa [mémoire active](MEMOIRE_PERSONNELLE.md). L'opération conserve le contexte des conversations existantes. Il peut aussi déconnecter Microsoft, suspendre ses automatisations et retirer les copies d'entreprise qu'il gère. La désactivation d'un membre bloque ses accès et ses exécutions futures, sans effacer ses contenus. L'administrateur n'acquiert aucun accès à ses données privées.

L'API de chat permet actuellement de consulter les conversations, d'envoyer un message et d'arrêter un tour. Elle ne possède pas de route de suppression de conversation. L'interface ne doit donc pas annoncer un effacement complet.

## Emplacements à traiter ensemble

| Données | Emplacement actuel | Conséquence pour une suppression |
| --- | --- | --- |
| Profil d'onboarding et ressources personnelles | Tables `alpendata_onboardings` et `alpendata_personal_resources` | Les valeurs peuvent également être reprises dans les contextes de conversations déjà créées. |
| Conversations et réponses | `Conversation`, `ChatTurn` et leurs contextes dans la base AlpenData ; historique canonique `SessionDB` dans le volume Hermes du propriétaire | Retirer une conversation de la seule liste du navigateur ne supprime pas ces contenus et ne suffit pas à empêcher leur reprise. |
| Mémoire active | `/state/.hermes/memories/MEMORY.md` et `USER.md` dans le volume personnel | Vider les fichiers n'efface ni les anciens contextes ni les sources susceptibles de faire mémoriser à nouveau une information. |
| Fichiers lus ou créés par Hermes | `/state/workspace` dans le volume personnel | L'espace de travail est commun aux conversations de ce propriétaire ; le purger pour une seule conversation affecterait potentiellement d'autres travaux. |
| Documents publiés et références aux sources | `Artifact.content`, `ToolRead.sources` dans la base AlpenData | Les octets publiés sont distincts des fichiers du workspace. Les références peuvent aussi apparaître dans une réponse ou l'historique Hermes. |
| Brouillons, envois et dépôts SharePoint | `EmailDraft`, `EmailAttempt`, `SharePointSave` | Les reçus et références empêchent des répétitions après une réponse incertaine. Une suppression doit définir le traitement des actions en cours et conserver le minimum nécessaire à leur résolution. |
| Automatisations, essais et résultats | `RoutineProposal`, `RoutineTrial`, `RoutineSchedule`, `RoutineOccurrence`, `PersonalNotification` | Des clés étrangères relient ces objets aux conversations et tours. Leur sort doit être explicite ; une suppression ne doit pas laisser de tâche exécutable sans sa configuration revue. |
| Copies partagées volontairement | `CompanyResource` et ses droits d'accès | Elles sont distinctes de l'original personnel. Leur retrait suit les droits de publication ; supprimer un original n'est pas actuellement une révocation de ses copies. |
| Consommation et facturation | `ModelCall`, `BillingAccount`, `BillingCheckout` | Les relevés de consommation dépendent des tours. Il faut séparer les contenus à effacer des données nécessaires au suivi d'utilisation et de facturation. |
| Connexion Microsoft | Cache chiffré de `MicrosoftConnection` | La déconnexion efface le cache actif ; elle n'efface pas les contenus précédemment importés. |
| Connexion AlpenData | `PasswordAccount` : adresse, empreinte Argon2id, empreinte du lien d'activation et expiration ; `SignInLimit` : clés hachées et compteurs | Aucun mot de passe ou lien brut en base. Les compteurs expirés depuis plus d'une heure sont nettoyés lors des tentatives suivantes. Les fichiers de remise manuelle restent à gérer séparément par l'opérateur. La restauration invalide les mots de passe et activations restaurés. |
| Sauvegardes | Ensemble PostgreSQL et états Hermes, puis archive chiffrée | Une sauvegarde antérieure peut contenir les données retirées depuis. La restauration actuelle suspend les accès et travaux mais n'applique pas de registre des suppressions postérieures. |
| Copies chez Microsoft et données transmises aux services externes | Compte Microsoft du propriétaire, fournisseur de modèle, Stripe | Une suppression locale n'efface pas un e-mail déjà envoyé ou un fichier enregistré dans Microsoft. Leurs règles et mécanismes doivent être décrits séparément. |

Le conteneur monte uniquement le volume de son propriétaire. Il utilise `/state/.hermes` comme `HERMES_HOME`, reprend les historiques via `SessionDB` et désactive les trajectoires facultatives. Cela ne constitue pas une garantie d'absence de tout autre fichier produit par Hermes ou ses outils : une fonction d'effacement devra vérifier le contenu réel du volume, y compris ses journaux et fichiers dérivés.

## Décisions attendues avant le parcours d'effacement complet

La question suivante est soumise au porteur du projet : suppression uniquement à la demande de l'utilisateur, suppression automatique après une durée définie, ou durée configurable par entreprise. Aucune échéance automatique n'est retenue à ce stade.

La conception devra ensuite préciser le périmètre proposé au propriétaire, le sort des copies partagées et des automatisations, les données conservées après son départ et la durée des sauvegardes. Le traitement des reçus d'actions externes et des données de facturation doit rester distinct de l'effacement des contenus de travail. Les modalités d'accès exceptionnel du support restent également à définir ; aucun accès aux contenus d'un collègue n'est accordé par le rôle administrateur actuel.

L'effacement devra être durable et reprenable entre la base et le volume privé, bloquer les exécutions concurrentes, ne pas supprimer les données d'un autre propriétaire et ne pas réintroduire les contenus lors d'une restauration. Un statut de demande ou un masquage dans l'interface ne devra pas être présenté comme une suppression terminée. Les preuves de validation devront examiner les données et fichiers restants, pas seulement l'absence dans la liste des conversations.

## Sources de l'inventaire

- [Modèles de données](../backend/src/alpendata_api/models.py) et [routes du chat](../backend/src/alpendata_api/chat.py).
- [Montage des volumes et verrou du propriétaire](../backend/src/alpendata_api/runtime.py).
- [Exécution Hermes et reprise de l'historique](../runtime/worker.py), [configuration du conteneur](../runtime/Containerfile) et [maintenance mémoire](../runtime/memory_access.py).
- [Copies d'entreprise](RESSOURCES_ENTREPRISE.md), [envois d'e-mails](EMAILS.md) et [sauvegarde/restauration](SAUVEGARDE_RESTAURATION.md).
