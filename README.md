# Memegen news bot

Publie sur Telegram un meme généré à partir de l'actualité du jour : les titres
viennent de Google News (tech FR) et de Hacker News, le texte du meme est écrit
par DeepSeek, l'image est produite par l'API [memegen](https://api.memegen.link).
Optionnellement, le même meme est aussi publié en **statut WhatsApp** ou sur une
**chaîne WhatsApp** via une passerelle
[OpenWA](https://docs.open-wa.org/api-reference/status).

```
RSS + HN ─► filtre sécurité/dédup ─► DeepSeek (JSON) ─► memegen (PNG) ─┬─► Telegram (abonnés + canal)
                                                                        ├─► statut WhatsApp (OpenWA, optionnel)
                                                                        └─► chaîne WhatsApp (OpenWA, optionnel)
```

## Prérequis

- Une clé API DeepSeek (`DEEPSEEK_API_KEY`).
- Un bot Telegram créé avec [@BotFather](https://t.me/BotFather). Chaque abonné
  lui envoie `/start` en privé ; il peut aussi être ajouté comme
  **administrateur** d'un canal avec `TELEGRAM_CHAT_ID`.
- (Optionnel) Une passerelle OpenWA joignable, avec une session WhatsApp
  connectée, pour publier aussi le meme en statut ou sur une chaîne.

## Variables d'environnement

| Variable | Obligatoire | Défaut | Rôle |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | oui | — | clé API DeepSeek |
| `TELEGRAM_BOT_TOKEN` | oui (hors dry-run, cible `telegram`) | — | token du bot |
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
| `OPENWA_STATUS_RECIPIENTS` | non | — | JIDs destinataires manuels, séparés par des virgules (`123@c.us`) |
| `OPENWA_STATUS_USE_CONTACTS` | non | `0` | `1` = ajoute les contacts synchronisés comme destinataires du statut |
| `OPENWA_STATUS_CHATTED_ONLY` | non | `0` | `1` = seulement les contacts avec qui une discussion existe |
| `OPENWA_STATUS_CHAT_DAYS` | non | `0` | ne garde que les discussions actives depuis N jours (`0` = pas de limite) |
| `OPENWA_CHANNEL_ID` | non | — | chaîne de destination du meme (`<id>@newsletter`) |
| `OPENWA_CHANNEL_MODE` | non | `image` | `image` = upload du PNG ; `link` = texte + lien memegen (repli quand Baileys n'affiche pas les médias) |
| `PUBLISH_TARGETS` | non | `telegram` (+ `status` si OpenWA configuré) | cibles séparées par des virgules : `telegram`, `status`, `channel` |

Le statut et la chaîne WhatsApp ne sont publiés que si les trois variables
`OPENWA_*` (`BASE_URL`, `API_KEY`, `SESSION_ID`) sont définies. Une
configuration partielle lève une erreur au démarrage.

Les destinataires du statut sont la concaténation de `OPENWA_STATUS_RECIPIENTS`
(manuel) et, si `OPENWA_STATUS_USE_CONTACTS=1`, des contacts du carnet d'adresses
mis en cache par `--sync-contacts` (hors contacts bloqués). Les doublons sont
retirés et la liste est plafonnée à **256 JIDs**, la limite d'OpenWA.

`OPENWA_STATUS_CHATTED_ONLY=1` restreint le cache aux contacts avec qui une
discussion individuelle existe, et `OPENWA_STATUS_CHAT_DAYS=N` ne garde que les
discussions actives depuis N jours. Ces deux filtres impliquent
`OPENWA_STATUS_USE_CONTACTS=1`. Quand `CHATTED_ONLY` est actif, les destinataires
sont triés du contact le plus récemment contacté au plus ancien, donc le plafond
de 256 garde les conversations les plus fraîches.

Avec l'engine **Baileys**, au moins une source de destinataires est obligatoire :
OpenWA publie le statut uniquement pour cette liste. Avec **whatsapp-web.js**,
laisse les deux vides : le statut est diffusé à l'audience définie par les
réglages de confidentialité du compte.

`PUBLISH_TARGETS` choisit où part chaque meme : `telegram`, `status` (statut
WhatsApp) et `channel` (chaîne WhatsApp), séparés par des virgules. Laissé vide,
il vaut `telegram` plus `status` si OpenWA est configuré. L'écrire explicitement
permet donc de désactiver le statut (`PUBLISH_TARGETS=telegram`) ou de ne
publier que sur la chaîne (`PUBLISH_TARGETS=channel`). Les cibles `status` et
`channel` exigent la configuration OpenWA, et `channel` exige en plus
`OPENWA_CHANNEL_ID`. Sans cible `telegram`, `TELEGRAM_BOT_TOKEN` n'est pas
requis.

Copie `.env.example` vers un fichier d'environnement de ton choix.

## En local

Ce dossier est un dépôt autonome : aucune dépendance au dépôt memegen parent.

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
export DEEPSEEK_API_KEY=sk-...
python -m bot --dry-run       # image écrite dans data/out/, aucune publication
python -m bot --poll-updates  # relève les /start et /stop, puis quitte
python -m bot --sync-contacts # met en cache les contacts WhatsApp, puis quitte
python -m bot --resolve-channel "https://whatsapp.com/channel/0029..."  # affiche l'id de la chaîne
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

Quand la cible `status` est active (par défaut dès qu'OpenWA est configuré),
chaque meme publié par `python -m bot` est également posté en statut WhatsApp
avec sa légende :

```http
POST {OPENWA_BASE_URL}/api/sessions/{OPENWA_SESSION_ID}/status/send-image
X-API-Key: {OPENWA_API_KEY}

{"image": {"base64": "<png>", "mimetype": "image/png"},
 "caption": "<légende>",
 "recipients": ["123@c.us"]}
```

### Précharger les contacts (`--sync-contacts`)

Plutôt que de maintenir `OPENWA_STATUS_RECIPIENTS` à la main, le bot peut mettre
en cache le carnet d'adresses OpenWA :

```bash
OPENWA_STATUS_USE_CONTACTS=1 python -m bot --sync-contacts
# ou, pour ne cibler que les gens avec qui tu discutes :
OPENWA_STATUS_CHATTED_ONLY=1 python -m bot --sync-contacts
```

- `GET /api/sessions/{id}/contacts` est paginé (1000 contacts par page) et les
  JIDs invalides (groupes, ids vides) sont ignorés.
- Seuls les JIDs `@c.us` / `@lid`, non bloqués et présents dans le carnet
  d'adresses (`isMyContact`) sont utilisés comme destinataires.
- Avec `OPENWA_STATUS_CHATTED_ONLY=1`, `GET /api/sessions/{id}/chats` est aussi
  lu (paginé) : seules les discussions `individual` comptent, les groupes,
  canaux et statuts sont écartés. La date de dernière activité de chaque
  discussion est stockée dans `whatsapp_contacts.last_chat_at`.
- `OPENWA_STATUS_CHAT_DAYS=N` restreint en plus aux discussions vues depuis N
  jours (utile pour ignorer les vieux fils de discussion).
- Si l'appel `/chats` échoue (session non `ready`, timeout), un avertissement est
  loggé et le carnet d'adresses est quand même rafraîchi : le filtre est ignoré
  pour ce cycle plutôt que de bloquer le sync.
- Le snapshot remplace le précédent dans la table SQLite `whatsapp_contacts` :
  un contact supprimé côté WhatsApp disparaît au sync suivant.
- Aucun appel OpenWA supplémentaire n'est fait à la publication : le statut lit
  le cache local.
- Le statut accepte au maximum 256 destinataires ; le cache peut en contenir plus.
  Sans `CHATTED_ONLY`, les 256 premiers du carnet (ordre alphabétique) partent ;
  avec, les 256 conversations les plus récentes.
- Si le cache est vide, un avertissement est loggé et, sur Baileys, le statut
  échouera faute de destinataires.

Ajoute `OPENWA_STATUS_USE_CONTACTS=1` à l'environnement du bot pour activer
l'utilisation du cache lors des publications.

- La session WhatsApp doit être **connectée** (`ready`) ; sinon OpenWA répond
  `409` et le statut est simplement ignoré (le canal Telegram reste publié).
- Le statut est indépendant de Telegram : sans aucun abonné Telegram, le meme est
  quand même généré et publié en statut si OpenWA est configuré.
- Les envois de statut (succès et échecs) sont enregistrés dans la table
  `deliveries` sous la cible `whatsapp-status`, et visibles dans les logs.
- En `--dry-run`, aucune requête n'est envoyée à OpenWA.

## Chaîne WhatsApp (OpenWA)

Pour publier chaque meme sur une **chaîne** WhatsApp (newsletter) au lieu — ou en
plus — du statut :

```bash
OPENWA_BASE_URL=http://openwa:2785
OPENWA_API_KEY=owa_k1_...
OPENWA_SESSION_ID=00000000-0000-0000-0000-000000000000
OPENWA_CHANNEL_ID=120363000000000000@newsletter
OPENWA_CHANNEL_MODE=link
PUBLISH_TARGETS=channel
```

L'id d'une chaîne se termine toujours par `@newsletter` ; un id numérique nu est
accepté et complété automatiquement. Pour l'obtenir depuis un lien de partage
(`https://whatsapp.com/channel/<code>`), le bot sait le résoudre :

```bash
python -m bot --resolve-channel "https://whatsapp.com/channel/0029VbDVUc3H5JM2MUNqmq0J"
# → resolved : OPENWA_CHANNEL_ID=120363000000000000@newsletter (Memes News)
```

`--resolve-channel` accepte aussi le code seul (`0029VbDVUc3H5JM2MUNqmq0J`). Il
appelle `POST /api/sessions/{id}/channels/subscribe` : c'est la seule route
OpenWA qui résout un code d'invitation, et elle **abonne la session** à la chaîne
au passage (sans effet sur les droits de publication : il faut être
propriétaire/administrateur pour poster). Si l'appel est refusé (`501` sur
whatsapp-web.js, ou un refus de WhatsApp), la commande liste les chaînes déjà
visibles dans `GET /chats` avec leur id, à récupérer à la main.

Dans le conteneur (pas de `.venv`, les dépendances sont globales) :

```bash
docker exec <conteneur> python -m bot --resolve-channel "https://whatsapp.com/channel/0029..."
```

Remplis ensuite `OPENWA_CHANNEL_ID` avec l'id renvoyé, jamais avec le code du
lien. Les commandes utilitaires (`--resolve-channel`, `--sync-contacts`,
`--poll-updates`) ignorent `OPENWA_CHANNEL_ID` : un id erroné ne les bloque pas,
alors qu'un cycle de publication échoue immédiatement avec un message qui
rappelle la commande à lancer.

Une fois l'id configuré, le bot poste l'image du meme avec sa légende :

```http
POST {OPENWA_BASE_URL}/api/sessions/{OPENWA_SESSION_ID}/messages/send-image
X-API-Key: {OPENWA_API_KEY}

{"chatId": "120363000000000000@newsletter",
 "base64": "<png>", "mimetype": "image/png",
 "caption": "<légende>"}
```

- L'engine doit être **Baileys** (`ENGINE_TYPE=baileys`). Avec l'engine par
  défaut *whatsapp-web.js*, OpenWA refuse toute image vers un JID `@newsletter`
  par un `501` (whatsapp-web.js n'arrive plus à construire un média vers une
  chaîne) : le log l'explique et le meme n'est pas publié sur la chaîne.
- **Bug Baileys : les médias postés sur une chaîne n'apparaissent pas.** L'upload
  réussit (donc OpenWA répond `201`) mais WhatsApp dépose l'image sur le mauvais
  CDN (`/o1/` au lieu de `/m1/`) et renvoie `ack error 479` : le média reste
  invisible. Baileys 7.0.0-rc14, la version utilisée par OpenWA, n'a pas le
  correctif (PR WhiskeySockets/Baileys#2434, encore ouverte ; issues #2199,
  #2322, #2345, #2687). Le texte, lui, passe. D'où `OPENWA_CHANNEL_MODE` :
  - `image` (défaut) — upload du PNG, correct une fois le correctif Baileys
    disponible ;
  - `link` — poste un message texte composé de la légende puis de l'URL du PNG
    sur memegen. WhatsApp génère l'aperçu, rien n'est uploadé, donc le meme
    s'affiche toujours. **C'est le mode à utiliser aujourd'hui.**
- Le bot ne crée pas la chaîne. `POST /api/sessions/{id}/channels` existe, mais
  la création n'est pas idempotente (un échec peut laisser une chaîne orpheline)
  et exige une clé *operator* : crée la chaîne une fois, puis colle son id dans
  `OPENWA_CHANNEL_ID`.
- `GET /channels` répond `501` sur Baileys : l'id est donc configuré à la main,
  jamais découvert par le bot.
- Un `201` signifie que WhatsApp a **accepté le message dans la session**, pas
  qu'il est visible sur la chaîne : Baileys n'attend pas l'accusé du serveur. Si
  le meme n'apparaît pas, vérifie que le numéro de la session OpenWA est
  **administrateur** de la chaîne (WhatsApp → infos de la chaîne →
  Administrateurs) et que l'id configuré est bien le tien
  (`GET /channels/{id}` doit renvoyer son nom). Le statut enregistré par le
  gateway se lit avec
  `GET /messages?chatId=<id>@newsletter&messageId=<id>` (`pending`, `sent` ou
  `failed`).
- La chaîne est une cible indépendante : un échec est loggé et enregistré dans
  `deliveries` sous la cible `whatsapp-channel`, sans annuler l'envoi Telegram ni
  le statut. Si aucune cible ne réussit, l'actu n'est pas enregistrée et sera
  retentée au cycle suivant.
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
   - `5 * * * *` → `python -m bot --once` (publication horaire) ;
   - `0 */6 * * *` → `python -m bot --sync-contacts` (cache des contacts WhatsApp,
     uniquement si `OPENWA_STATUS_USE_CONTACTS=1`).
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
