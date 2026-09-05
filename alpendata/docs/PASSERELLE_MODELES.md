# Passerelle de modèles AlpenData

6 septembre 2026 — passerelle reliée au [chat personnel](CHAT_PERSONNEL.md) et à son processus de travail.

`backend/src/alpendata_api/model_gateway.py` relie le superviseur de l’agent aux API de modèles. Le conteneur Hermes transmet une requête sur ses pipes ; le processus serveur appelle `ModelGateway.complete()` et renvoie `completion.reply()` au conteneur. La clé du fournisseur reste dans la configuration du processus serveur. Elle ne figure ni dans le montage personnel, ni dans l’environnement du conteneur, ni dans la réponse de la passerelle.

## Configuration et limites

Le constructeur `ModelSettings` exige un fournisseur (`mistral` ou `openrouter`), un identifiant de modèle et une clé serveur. Il accepte une limite de sortie, un délai réseau et, pour OpenRouter, une liste de fournisseurs autorisés. Ces paramètres sont fournis par l’exploitant, jamais par le navigateur ou le message de l’agent. Aucun modèle commercial ni tarif n’est présélectionné. La configuration du chat et de son processus de travail est décrite dans le document lié ci-dessus.

Les destinations HTTPS sont fixes. Le modèle, le nombre de réponses et le plafond de sortie sont imposés par le serveur. Les paramètres de routage, plugins, modèles de secours, en-têtes et identifiants de suivi fournis par le conteneur ne sont pas transmis. Les outils acceptés sont des définitions de fonctions exécutées par Hermes ; les outils de recherche web ou d’exécution du fournisseur sont refusés. Les messages acceptent pour l’instant du texte et des appels/résultats de fonctions, sans images ou fichiers distants que le fournisseur pourrait télécharger.

Pour OpenRouter, la requête impose `data_collection: deny`, interdit le repli automatique et peut limiter les fournisseurs via `only`. Ces réglages ne constituent pas une garantie de traitement en Suisse. Le choix des destinations et les conditions du service restent à valider avant le pilote. Les blocs de raisonnement OpenRouter sont conservés à l’identique lors de la poursuite d’un appel d’outil. Les formats de raisonnement propres à Mistral ne sont pas encore pris en charge.

Les échanges sont non diffusés en continu et limités à 6 Mio. Les redirections ne sont pas suivies et la passerelle ne relance pas automatiquement une requête échouée. Les délais réseau et le délai vérifié pendant la lecture limitent les attentes ordinaires ; ils ne remplacent pas la limite d’exécution du superviseur. Les erreurs retournent des codes stables sans corps de diagnostic du fournisseur. Les sessions HTTP de production sont neuves à chaque appel et n’utilisent pas les proxies ou identifiants implicites de l’environnement.

## Consommation

`ModelCompletion.usage` contient les compteurs d’entrée, de sortie et de total lus dans la réponse HTTP. Les chiffres déclarés par le conteneur sont ignorés. Des compteurs absents, négatifs ou incohérents produisent une consommation inconnue (`None`), jamais une estimation gratuite. Le processus de chat enregistre maintenant ces relevés par propriétaire et par tour, y compris si le travail est annulé pendant l’appel. Leur réconciliation et la conversion en facturation CHF restent à implémenter.

## Validation

Cinq scénarios utilisent un serveur HTTP local avec des réponses de modèle synthétiques. La bibliothèque HTTP, la sérialisation et la passerelle sont réelles. Ils couvrent les destinations et clés, le routage imposé, les plafonds, les outils et contenus refusés, les erreurs et redirections, les réponses surdimensionnées, les compteurs manquants et la continuité du raisonnement.

Le scénario conteneurisé existant passe également par cette passerelle pour le premier tour Hermes : mémoire, commande locale, outil métier et réponse finale. Le test du chat ajoute les relevés durables et les contrôles d’accès pendant l’exécution. Le titrage secondaire Hermes est désormais désactivé, car les conversations sont nommées par AlpenData. Les essais n’utilisent aucune clé de fournisseur réelle et ne valident pas la qualité des réponses d’un modèle commercial.

Références : [API de chat Mistral](https://docs.mistral.ai/api/endpoint/chat), [routage OpenRouter](https://openrouter.ai/docs/guides/routing/provider-selection), [continuité du raisonnement OpenRouter](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).
