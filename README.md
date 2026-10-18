# Memegen news bot

Publie sur Telegram un meme généré à partir de l'actualité du jour : les titres
viennent de Google News (tech FR) et de Hacker News, le texte du meme est écrit
par DeepSeek, l'image est produite par l'API [memegen](https://api.memegen.link).

```
RSS + HN ─► filtre sécurité/dédup ─► DeepSeek (JSON) ─► memegen (PNG) ─► Telegram sendPhoto
```

## Prérequis

- Une clé API DeepSeek (`DEEPSEEK_API_KEY`).
- Un bot Telegram créé avec [@BotFather](https://t.me/BotFather), ajouté comme
  **administrateur** du canal (ou membre du groupe) où publier.
- Le `chat_id` de la destination : `-100…` pour un canal, visible via
  `https://api.telegram.org/bot<TOKEN>/getUpdates` après un message dans le chat.

## Variables d'environnement

| Variable | Obligatoire | Défaut | Rôle |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | oui | — | clé API DeepSeek |
| `TELEGRAM_BOT_TOKEN` | oui (hors dry-run) | — | token du bot |
| `TELEGRAM_CHAT_ID` | oui (hors dry-run) | — | canal/groupe de destination |
| `MEMEGEN_BASE_URL` | non | `https://api.memegen.link` | API memegen |
| `DATA_DIR` | non | `./data` | base SQLite + images de dry-run (en Docker : `/data`, défini par l'image) |
| `DRY_RUN` | non | `0` | `1` = génère sans publier |
| `MAX_AGE_HOURS` | non | `8` | fraîcheur maximale des actus |
| `MAX_NEWS_ITEMS` | non | `40` | taille du lot d'actus |
| `DEEPSEEK_MODEL` | non | `deepseek-flash` | modèle utilisé |

Copie `.env.example` vers un fichier d'environnement de ton choix.

## En local

Ce dossier est un dépôt autonome : aucune dépendance au dépôt memegen parent.

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
export DEEPSEEK_API_KEY=sk-...
python -m bot --dry-run      # image écrite dans data/out/, aucune publication
python -m bot                # publication réelle
```

Tests :

```bash
python -m unittest discover -s tests -t .
```

## Déploiement Dokploy

1. Pousse ce dépôt sur GitHub, puis dans Dokploy **Create Application** →
   source GitHub.
2. Build type **Dockerfile** : contexte = racine du dépôt, Dockerfile =
   `Dockerfile`.
3. Onglet **Environment** : les variables du tableau ci-dessus, avec
   `DRY_RUN=1` pour le premier déploiement. **Ne définis pas `DATA_DIR`** :
   l'image fixe déjà `/data`, et une valeur relative (`./data`, reprise de
   `.env.example`) échoue en `PermissionError` car `/app` appartient à root.
4. Onglet **Volumes** : monte un volume Docker sur `/data` (la base SQLite évite
   de republier deux fois la même actu). Préfère un volume nommé : un bind mount
   doit être accessible en écriture par l'uid 1000 (`chown 1000:1000`).
5. Onglet **Schedule Jobs** : type *Application*, cron `5 * * * *`, commande
   `python -m bot --once`.
6. Vérifie les logs du premier run en `DRY_RUN=1`, puis passe `DRY_RUN=0`.

Le conteneur ne travaille pas de lui-même : son `CMD` est `sleep infinity` pour
rester disponible aux `docker exec` des Schedule Jobs. Chaque exécution est
indépendante (un seul cycle, aucune boucle interne), donc un run peut être
relancé à la main depuis Dokploy.

Pour lancer un cycle ponctuel hors Dokploy :

```bash
docker run --rm -v memes-bot-data:/data \
  -e DEEPSEEK_API_KEY=sk-... -e DRY_RUN=1 \
  memes-bot python -m bot --once
```

## Coûts

- Telegram Bot API : gratuit.
- DeepSeek : quelques centimes par mois (une génération par heure).
- memegen : gratuit (`api.memegen.link`).

## Sécurité et bon sens

- `bot/safety.py` bloque les titres violents (drames, guerres, accidents…) avant
  même l'appel au modèle.
- Le modèle peut refuser une actu (`skip`) ; ces actus sont marquées comme
  traitées en base.
- Les liens sont dé-dupliqués par hash dans SQLite, donc un même titre n'est
  jamais publié deux fois.
- Commence toujours par `DRY_RUN=1` et vérifie quelques images.
