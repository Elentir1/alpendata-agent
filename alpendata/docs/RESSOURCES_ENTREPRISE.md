# Ressources publiées pour l’entreprise

6 septembre 2026 — notes et copies de documents, migration `0017`.

## Parcours

Dans « Mon espace », chaque collaborateur peut consulter les ressources partagées avec lui et publier volontairement ses propres copies. Un administrateur dispose aussi de cette rubrique dans « Mon entreprise ». Chaque membre actif peut publier une note ou un fichier PDF, DOCX, XLSX ou PPTX, choisir les destinataires et confirmer la publication. Les fichiers sont copiés dans AlpenData ; ils ne sont pas synchronisés avec leur original SharePoint. La connexion Microsoft du déposant n’est jamais partagée.

L’audience peut être toute l’équipe, y compris les futurs membres actifs, ou une sélection de collaborateurs actifs. L’auteur et les administrateurs peuvent toujours consulter et gérer ces copies explicitement publiées. Une sélection vide réserve la copie à son auteur et aux administrateurs. Ces droits ne donnent aucun accès aux conversations, à la mémoire, aux documents privés ou aux intégrations d’un collaborateur.

La recherche porte sur le titre. Une note s’affiche en texte simple ; un document se télécharge après un nouveau contrôle des accès et de sa version. L’auteur ou un administrateur peut remplacer le contenu, modifier seulement les accès sans renvoyer le fichier, ou retirer la copie. L’interface indique les personnes concernées et demande confirmation avant ces mutations.

Le bouton « Partager dans l’entreprise » d’un document créé dans le chat ouvre le même choix de destinataires. Après confirmation, le serveur copie les octets du document personnel appartenant au compte connecté dans cette entreprise. Un identifiant de document privé d’un collègue est refusé, même pour un administrateur. Le document original reste privé et inchangé ; retirer sa copie partagée ne l’efface pas. Le modèle peut lire les copies autorisées, mais ne dispose pas d’un outil de publication ou de modification des accès.

Le sélecteur utilise un annuaire limité aux identifiants, noms et rôles des membres actifs de l’entreprise (`/company-resources/recipients`). Les données administratives des licences, invitations et connexions ne sont pas exposées. L’auteur n’est pas présenté comme un destinataire révocable. Toute modification du contenu ou des destinataires annule la confirmation précédente.

## Frontières et concurrence

Les tables `CompanyResource` et `CompanyResourceGrant` portent l’entreprise et des clés étrangères composées vers ses membres. Chaque lecture exige une session et une adhésion actives. Les API de consultation et de partage restent accessibles à un membre actif sans licence ; exécuter l’assistant exige toujours une licence. L’interface personnelle actuelle demande une licence pour ouvrir le parcours « Mon espace ».

Une publication possède un identifiant de demande propre au déposant et une empreinte du corps. Rejouer la même demande ne crée pas une deuxième copie. Après une réponse perdue, l’interface conserve la demande et fige le formulaire pour permettre cette reprise. Après fermeture du formulaire ou rechargement du navigateur, consulter la liste avant de soumettre une nouvelle publication si la réponse précédente était incertaine.

Les modifications utilisent la version lue. Un conflit ou une réponse incertaine exige une actualisation avant une nouvelle modification. Sur PostgreSQL, les mutations verrouillent l’entreprise puis ses adhésions dans un ordre stable. Une révocation attend la lecture déjà autorisée ; toute lecture suivante recontrôle l’audience actuelle. SQLite sert au développement, pas à la preuve de concurrence en production.

Le retrait efface le texte ou les octets de la copie active et ses grants. Une ligne inactive conserve les métadonnées et la demande d’origine, sans possibilité de réactivation. Il n’efface pas les téléchargements, historiques, souvenirs dérivés ou sauvegardes déjà créés. Le suivi de ces copies dérivées et les règles de conservation restent à définir pour l’exploitation.

Limites actuelles : 200 ressources actives, 20 000 caractères par note, 5 Mio par document et 100 Mio de fichiers par entreprise. Les octets sont conservés en base pour cette première version. La validation du conteneur PDF/Office et du nom de fichier reprend celle des documents privés ; elle ne constitue pas une analyse antivirus. Un stockage objet avec la même frontière d’autorisation pourra remplacer cette persistance lors du dimensionnement Infomaniak.

## Utilisation par Hermes

Les nouvelles conversations utilisent la révision d’outils `5`. L’outil AlpenData `alpendata_company_resources` propose recherche, lecture d’une note et téléchargement d’un fichier avec identifiant et version exacts. L’identité vient du job authentifié, pas des arguments du modèle. Les conversations et routines antérieures conservent leurs outils ; démarrer une nouvelle conversation ou un nouvel essai pour bénéficier de cette capacité.

Les lectures réussies produisent un reçu `ToolRead` avec le titre et la version. Un téléchargement écrit le fichier dans un répertoire aléatoire de `sources/` dans l’espace privé du propriétaire. Hermes doit ouvrir ce fichier avant d’en résumer le contenu. Le contenu partagé n’est jamais une autorisation de modifier les droits ou d’envoyer un message. Le modèle ne reçoit ni jeton Microsoft ni accès direct à la base. Le contexte système d’une conversation reste identique après un changement de partage.

## Validation

Deux scénarios API vérifient publication explicite, rejeu, refus croisés, grants, versions, retrait, formats et refus par le broker. Le scénario concurrent observe directement le verrou PostgreSQL qui bloque la révocation pendant une lecture. Un troisième scénario exécute Hermes dans de vrais conteneurs : recherche autorisée, lecture de note, téléchargement et ouverture PDF avec `pypdf`, sources du résultat, puis refus après révocation dans la même conversation. Aucun appel Microsoft n’est nécessaire ; le modèle de test répond sur un serveur HTTP local.

Deux scénarios API supplémentaires vérifient la publication par un collaborateur, sa révocation, le contrôle conservé par l’administrateur et la copie exacte d’un document privé du propriétaire. Le parcours OCI utilise désormais un collaborateur comme auteur et comme acteur de la révocation.

Quatre scénarios d’interface vérifient la confirmation, la reprise après une réponse perdue, le conflit de version et l’isolement des réponses tardives lors d’un changement d’utilisateur, ainsi que la publication par un membre et le partage direct depuis le chat sans téléchargement préalable. Voir [Validation globale](VALIDATION_BACKEND.md) pour les résultats et les limites des services externes synthétiques.
