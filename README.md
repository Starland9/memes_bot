# Memegen news bot

Publie sur Telegram un meme généré à partir de l'actualité du jour : les titres
viennent de Google News (tech FR) et de Hacker News, le texte du meme est écrit
par DeepSeek, l'image est produite par l'API [memegen](https://api.memegen.link).
Optionnellement, le même meme est aussi publié en **statut WhatsApp** via une
passerelle [OpenWA](https://docs.open-wa.org/api-reference/status).

```
RSS + HN ─► filtre sécurité/dédup ─► DeepSeek (JSON) ─► memegen (PNG) ─┬─► Telegram (abonnés + canal)
                                                                        └─► statut WhatsApp (OpenWA, optionnel)
```

## Prérequis

- Une clé API DeepSeek (`DEEPSEEK_API_KEY`).
- Un bot Telegram créé avec [@BotFather](https://t.me/BotFather). Chaque abonné
  lui envoie `/start` en privé ; il peut aussi être ajouté comme
  **administrateur** d'un canal avec `TELEGRAM_CHAT_ID`.
- (Optionnel) Une passerelle OpenWA joignable, avec une session WhatsApp
  connectée, pour publier aussi le meme en statut.

## Variables d'environnement

| Variable | Obligatoire | Défaut | Rôle |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | oui | — | clé API DeepSeek |
| `TELEGRAM_BOT_TOKEN` | oui (hors dry-run) | — | token du bot |
| `TELEGRAM_CHAT_ID` | non | — | destinataire supplémentaire (canal `-100…` ou groupe) |
| `MEMEGEN_BASE_URL` | non | `https://api.memegen.link` | API memegen |
| `DATA_DIR` | non | `./data` | base SQLite + images de dry-run (en Docker : `/data`, défini par l'image) |
| `DRY_RUN` | non | `0` | `1` = génère sans publier |
| `MAX_AGE_HOURS` | non | `8` | fraîcheur maximale des actus |
| `MAX_NEWS_ITEMS` | non | `40` | taille du lot d'actus |
| `DEEPSEEK_MODEL` | non | `deepseek-flash` | modèle utilisé |
| `REQUEST_TIMEOUT` | non | `60` | délai HTTP max par requête (secondes) |
| `OPENWA_BASE_URL` | non | — | URL de la passerelle OpenWA (ex. `http://openwa:2785`) |
| `OPENWA_API_KEY` | non | — | clé API OpenWA (rôle *operator* requis) |
| `OPENWA_SESSION_ID` | non | — | UUID de la session WhatsApp connectée |
| `OPENWA_STATUS_RECIPIENTS` | non | — | JIDs destinataires du statut, séparés par des virgules (`123@c.us`) |

Le statut WhatsApp n'est publié que si les trois variables `OPENWA_*`
(`BASE_URL`, `API_KEY`, `SESSION_ID`) sont définies. Une configuration partielle
lève une erreur au démarrage.

Avec l'engine **Baileys**, `OPENWA_STATUS_RECIPIENTS` est obligatoire : OpenWA
publie le statut uniquement pour cette liste. Avec **whatsapp-web.js**, laisse-le
vide : le statut est diffusé à l'audience définie par les réglages de
confidentialité du compte.

Copie `.env.example` vers un fichier d'environnement de ton choix.

## En local

Ce dossier est un dépôt autonome : aucune dépendance au dépôt memegen parent.

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
export DEEPSEEK_API_KEY=sk-...
python -m bot --dry-run       # image écrite dans data/out/, aucune publication
python -m bot --poll-updates  # relève les /start et /stop, puis quitte
python -m bot                 # publication réelle à tous les abonnés
```

Tests :

```bash
python -m unittest discover -s tests -t .
```

## Abonnés Telegram

Chaque personne qui envoie `/start` au bot en privé est enregistrée dans la base
SQLite et reçoit chaque meme en message privé ; `/stop` (ou `/unsubscribe`) la
désinscrit. Les commandes sont relevées avec `getUpdates` et l'offset est
persisté, donc aucun update n'est perdu entre deux exécutions.

- `python -m bot --poll-updates` traite uniquement les abonnements : programme-le
  toutes les 5 minutes pour des inscriptions réactives.
- `python -m bot --once` relève aussi les updates au début du cycle, puis publie
  un meme à tous les abonnés.
- Un bot ne peut écrire qu'aux personnes qui l'ont démarré : sans `/start`, pas
  de message privé possible.
- Si un abonné bloque le bot (HTTP 403), il est retiré automatiquement.
- Si `TELEGRAM_CHAT_ID` est défini, le canal/groupe le reçoit aussi.

Délais normaux : la confirmation « Inscription enregistrée » part au prochain
`--poll-updates` (≤ 5 min avec la planification recommandée). Le premier meme
arrive au prochain `--once` (horaire, minute 5) et **seulement si `DRY_RUN=0`**.
Un `/start` envoyé juste après le passage horaire attend donc jusqu'à l'heure
suivante ; pour un test immédiat, lance `python -m bot --once` à la main.

## Statut WhatsApp (OpenWA)

Quand la passerelle OpenWA est configurée, chaque meme publié par `python -m bot`
est également posté en statut WhatsApp avec sa légende :

```http
POST {OPENWA_BASE_URL}/api/sessions/{OPENWA_SESSION_ID}/status/send-image
X-API-Key: {OPENWA_API_KEY}

{"image": {"base64": "<png>", "mimetype": "image/png"},
 "caption": "<légende>",
 "recipients": ["123@c.us"]}
```

- La session WhatsApp doit être **connectée** (`ready`) ; sinon OpenWA répond
  `409` et le statut est simplement ignoré (le canal Telegram reste publié).
- Le statut est indépendant de Telegram : sans aucun abonné Telegram, le meme est
  quand même généré et publié en statut si OpenWA est configuré.
- Les envois de statut (succès et échecs) sont enregistrés dans la table
  `deliveries` sous la cible `whatsapp-status`, et visibles dans les logs.
- En `--dry-run`, aucune requête n'est envoyée à OpenWA.

## Déploiement Dokploy

1. Pousse ce dépôt sur GitHub, puis dans Dokploy **Create Application** →
   source GitHub.
2. Build type **Dockerfile** : contexte = racine du dépôt, Dockerfile =
   `Dockerfile`.
3. Onglet **Environment** : les variables du tableau ci-dessus, avec
   `DRY_RUN=1` pour le premier déploiement. **Ne définis pas `DATA_DIR`** :
   l'image fixe déjà `/data`, et une valeur relative (`./data`, reprise de
   `.env.example`) échoue en `PermissionError` car `/app` appartient à root.
4. Onglet **Volumes** → **Volume Mount** (pas *Bind Mount*), nom
   `memes-bot-data`, mount path `/data`. Un volume nommé hérite du propriétaire
   uid 1000 de l'image, donc aucun `chown` n'est nécessaire. Si tu tiens au
   *Bind Mount*, le dossier hôte doit exister et appartenir à l'uid 1000 :
   `sudo mkdir -p /opt/memes-bot/data && sudo chown -R 1000:1000 /opt/memes-bot/data`,
   puis Host Path `/opt/memes-bot/data` et Mount Path `/data`.
5. Onglet **Schedule Jobs** :
   - `*/5 * * * *` → `python -m bot --poll-updates` (inscriptions réactives) ;
   - `5 * * * *` → `python -m bot --once` (publication horaire).
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
