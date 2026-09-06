# Documents privés dans le chat

6 septembre 2026 — lecture SharePoint, génération locale, publication et téléchargement.

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

## Génération et édition locales

Le runtime contient désormais python-docx, openpyxl, python-pptx, ReportLab et pypdf, ainsi que LibreOffice Writer/Calc/Impress, Poppler et les polices DejaVu. Les versions Python sont verrouillées avec empreintes, en conservant les dépendances communes au verrou Hermes. Les nouvelles conversations reçoivent le chemin d’un [guide interne](../runtime/DOCUMENT_GUIDE.md). Le terminal doit utiliser `/opt/venv/bin/python`, car son shell peut sélectionner le Python système.

Le programme facultatif `document_builder.py` crée des mises en page de départ à partir d’une spécification JSON : sections et tableaux pour Word/PDF, feuilles et cellules typées pour Excel, diapositives avec texte modifiable pour PowerPoint. Il refuse d’écraser un fichier existant, les contenus destinés à un autre format et les textes qui débordent de sa disposition PowerPoint. Les chaînes Excel restent du texte, même lorsqu’elles commencent par `=` ; les formules sont déclarées explicitement et doivent être recalculées et vérifiées avant livraison.

Le guide conserve l’accès direct aux bibliothèques pour les modèles, graphiques, tableaux PowerPoint et mises en page qui dépassent ce programme de départ. Les originaux Office restent modifiables ; les rendus PDF sont des sorties distinctes. Les modèles de documents propres au client restent à recueillir et à valider. Aucune application bureautique ni compétence technique n’est nécessaire sur son poste pour demander la création depuis le chat.

## Lecture du contenu SharePoint

Les nouvelles conversations autorisées à lire les fichiers disposent de `alpendata_download_file`. Après une recherche, Hermes transmet les identifiants de lecteur et de fichier au broker, qui utilise exclusivement la connexion Microsoft personnelle du propriétaire. Les droits, la licence et le bail du tour sont revérifiés. Le fichier rejoint un sous-dossier privé unique dans `sources/`, en conservant son nom lorsque celui-ci est utilisable. Hermes peut alors le lire ou l’éditer avec les bibliothèques locales et publier le résultat dans le chat.

Le [protocole Microsoft de téléchargement](https://learn.microsoft.com/en-us/graph/api/driveitem-get-content?view=graph-rest-1.0) fournit une redirection vers une URL temporaire préauthentifiée. Le broker conserve cette URL côté serveur et la télécharge dans une session distincte sans jeton OAuth ni suivi de redirections supplémentaires. Les destinations HTTPS sont limitées aux sous-domaines de `sharepoint.com`, `sharepointonline.com` et `1drv.com`. Ce raccordement vise le service Microsoft global ; les clouds nationaux et destinations différentes restent à valider avant de les prendre en charge.

La taille annoncée et les octets reçus sont plafonnés à 5 Mio. L’identifiant et l’ETag sont vérifiés avant et après le transfert ; un changement ou une taille différente provoque un refus, sans remettre un résultat présenté comme stable. Les sources visibles dans le chat contiennent le nom et le lien de consultation Microsoft, jamais le lien temporaire ou le contenu binaire. Un téléchargement réussi prouve la récupération des octets ; l’agent doit encore ouvrir le fichier avant de prétendre l’avoir analysé.

La migration `0009` fige une révision d’outils par conversation. Les conversations existantes restent en révision 1 ; les nouvelles utilisent la révision 2. Les occurrences planifiées recopient la révision de l’essai revu. Cela préserve les outils et le contexte des conversations antérieures. Cette opération de lecture ne modifie aucun fichier SharePoint et ne demande pas de permission d’écriture.

## Vérification et travail restant

`test_documents_worker.py` utilise l’API réelle, PostgreSQL, un modèle HTTP synthétique et un vrai conteneur Hermes. Le scénario crée un PDF complet dans le terminal de l’agent, refuse un chemin sortant et un lien symbolique, publie deux fois sans doublon, compare les octets téléchargés et refuse l’accès administrateur. Il n’utilise aucune connexion Microsoft.

`test_documents.py` vérifie les reçus après interruption, les permissions, les types Office, les noms et tailles invalides. Ses paquets Office sont volontairement minimaux : ils ne prouvent pas l’ouverture ou la qualité dans Word, Excel ou PowerPoint. Le test d’interface vérifie l’accès expiré, la nouvelle tentative et le téléchargement du reçu. Un aperçu séparé, explicitement fictif, a été contrôlé dans le navigateur en anglais et français.

`test_document_generation.py` ajoute un parcours complet avec Hermes réel : lecture du guide, création des quatre formats, édition du Word et du PowerPoint, modification d’une valeur Excel et recalcul du total par LibreOffice. Il vérifie les contenus après réouverture, les pages rendues, l’absence d’écrasement, le refus d’un texte PowerPoint trop long et les téléchargements personnels. Les quatre documents publiés sont récupérés par l’API. Les cinq pages/diapositives rendues ont été examinées visuellement ; le thème Word hérité a été corrigé puis le parcours et les rendus revérifiés.

L’image finale de cette étape est `sha256:349e453517fcbbe3fb69cf4fe3804024a1fb74e062dc723a07e534de74f55ad5`. Les exemples sont synthétiques, et les décisions du modèle de test sont scriptées. Cette vérification prouve le parcours technique et les exemples contrôlés ; elle ne mesure pas encore la qualité d’un modèle commercial sur les documents du client.

`test_sharepoint_documents.py` vérifie la connexion personnelle, les refus d’accès, la déconnexion, les liens temporaires invalides ou expirés, les fichiers modifiés et les plafonds annoncés ou dépassés pendant le transfert. `test_sharepoint_worker.py` fait rechercher, télécharger et lire un PDF par le vrai Hermes, puis compare son téléchargement privé aux octets source. Microsoft et le modèle restent synthétiques dans ces tests.

L’[enregistrement personnel dans Microsoft 365](ENREGISTREMENT_SHAREPOINT.md) est désormais relié à une préparation et une confirmation dans l’interface, avec permission supplémentaire, conflit explicite et reçus durables. La validation sur Microsoft réel, les modèles du client, les règles administrateur, la conservation configurable et la validation métier avec le pilote restent à terminer. Le lot documents reste en cours.
