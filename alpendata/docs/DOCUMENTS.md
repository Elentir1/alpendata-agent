# Documents privés dans le chat

6 septembre 2026 — première étape du lot documents : publication et téléchargement.

## Parcours implémenté

Dans une nouvelle conversation, Hermes dispose de `alpendata_publish_document`. Il crée d’abord un fichier dans `/state/workspace` avec ses outils habituels, puis demande sa publication. Le runtime ouvre chaque composant du chemin sans suivre de liens symboliques, transmet les octets au broker et reçoit un identifiant. Ce parcours ne dépend pas d’une connexion Microsoft.

Le broker revérifie le membre, sa licence, le tour en cours, son bail et son éventuelle annulation. Il attribue lui-même le propriétaire, l’entreprise et le tour. Aucun chemin hôte, identifiant de propriétaire ou URL de stockage fourni par l’agent ne sert à trouver le fichier côté serveur.

Le chat affiche les reçus conservés dans la base, indépendamment du texte de l’IA : nom, taille et bouton de téléchargement en français ou anglais. Un fichier déjà reçu reste accessible si la suite de l’exécution échoue ou est interrompue ; cela ne signifie pas que toute la demande a été terminée.

`GET /api/organizations/{organization_id}/documents/{document_id}/download` exige une session et une adhésion active du propriétaire. Un membre actif sans licence garde ses documents existants ; un membre désactivé perd l’accès. L’administrateur ne peut pas télécharger les documents personnels d’un collègue. Les réponses utilisent `attachment`, `no-store`, `nosniff` et un nom UTF-8. Aucun lien public ou jeton dans l’URL n’est créé.

## Stockage et limites actuelles

La migration `0008` ajoute les reçus et leurs octets immuables dans PostgreSQL (`bytea`) ou SQLite pour l’aperçu local. Le contenu binaire est chargé uniquement au téléchargement. Une clé étrangère composée rattache chaque document au tour et au propriétaire. Une répétition du même fichier, nom et tour renvoie le même reçu. Des octets différents créent un nouveau document sans écraser le précédent.

- 5 Mio par fichier ; PDF, DOCX, XLSX et PPTX.
- 20 documents par tour et 100 Mio conservés par utilisateur et entreprise.
- Office : 2 048 entrées ZIP au plus, 50 Mio décompressés au total, absence d’entrées dupliquées ou de traversée de chemin, cohérence du type principal, contrôle CRC.

Le contrôle de format porte sur le conteneur. Il ne valide ni la mise en page, ni le contenu métier, ni l’absence de logiciel malveillant. Pour PDF, il porte actuellement sur l’en-tête et la fin du fichier. Les documents sont téléchargés sans aperçu HTML intégré.

Suppression, conservation configurable, volumes supérieurs et éventuel stockage objet privé restent à réaliser. Ces limites techniques ne constituent pas une offre commerciale.

## Continuité des conversations

`Conversation.documents_enabled` fige la disponibilité de l’outil. La migration conserve `false` pour les conversations existantes ; les nouvelles l’activent. Un ancien contexte ne reçoit donc pas cet outil lors d’une mise à jour. Les occurrences planifiées recopient le réglage de l’essai revu. Le broker applique aussi ce réglage, indépendamment des déclarations du runtime.

## Vérification et travail restant

`test_documents_worker.py` utilise l’API réelle, PostgreSQL, un modèle HTTP synthétique et un vrai conteneur Hermes. Le scénario crée un PDF complet dans le terminal de l’agent, refuse un chemin sortant et un lien symbolique, publie deux fois sans doublon, compare les octets téléchargés et refuse l’accès administrateur. Il n’utilise aucune connexion Microsoft.

`test_documents.py` vérifie les reçus après interruption, les permissions, les types Office, les noms et tailles invalides. Ses paquets Office sont volontairement minimaux : ils ne prouvent pas l’ouverture ou la qualité dans Word, Excel ou PowerPoint. Le test d’interface vérifie l’accès expiré, la nouvelle tentative et le téléchargement du reçu. Un aperçu séparé, explicitement fictif, a été contrôlé dans le navigateur en anglais et français.

La génération métier fiable, les bibliothèques et instructions documentaires du runtime, les exemples représentatifs ouverts et rendus dans les quatre formats, la lecture du contenu SharePoint, l’édition et l’enregistrement SharePoint restent à terminer. Le lot documents reste en cours.
