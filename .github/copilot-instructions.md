# Copilot instructions — memes_bot

One-shot Python 3.12 bot: fetch FR-tech/HN headlines, filter unsafe topics, ask
DeepSeek for a meme plan (JSON), render it via the memegen API, and publish the
PNG to Telegram. There is no scheduler in the code: every invocation performs
exactly one cycle.

## Commands

Setup (standard library `unittest` only — no pytest, no pyproject, no lint/type config):

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

Tests (must run from the repo root; `-t .` makes the `bot` package importable):

```bash
.venv/bin/python -m unittest discover -s tests -t .
.venv/bin/python -m unittest tests.test_pipeline.PipelineTest.test_publishes_when_not_in_dry_run
```

Run:

```bash
.venv/bin/python -m bot --dry-run          # writes DATA_DIR/out/<hash>.png, never calls Telegram
.venv/bin/python -m bot                    # real publication
.venv/bin/python -m bot --log-level DEBUG
```

Docker (build context = repo root; only `requirements.txt` and `bot/` are copied):

```bash
docker build -t memes-bot .
docker run --rm -e DEEPSEEK_API_KEY=... -e DRY_RUN=1 -v "$PWD/data:/data" memes-bot
```

## Architecture

Flow (all in `bot/pipeline.py::run_once`):

```
news.collect_news (RSS + HN) -> safety.blocked_term -> store dedupe
  -> llm.DeepSeekClient.generate (JSON plan) -> memegen.build_image_url/fetch_image
  -> store.record + TelegramClient.send_photo   (or PNG write when dry_run)
```

- `cli.py` parses args and maps the result to an exit code (`0` posted/dry_run, `1` nothing, `2` config error or exception). `--once` is accepted but unused — it exists for the Dokploy cron command.
- `pipeline.run_once` owns the only `httpx.Client` (User-Agent `memegen-news-bot/0.1`, timeout from `REQUEST_TIMEOUT`) and passes it into every HTTP consumer. Modules never create clients themselves; keep that signature style (`fn(client, ...)`) for anything network-related.
- Dependency injection is the test seam: `run_once` accepts `store`, `news_fetcher`, `template_fetcher`, `generator`, `image_fetcher`, `publisher`. Tests never touch the network and use `httpx.MockTransport` for clients. Preserve these keyword parameters when refactoring.
- Import direction: `cli -> pipeline -> {news, llm, memegen, telegram, templates, safety, store}`. `llm` may import `news`/`templates`; nothing imports `pipeline`.
- One item per run: after the first item is published (or dry-run written) the function returns; skipped items just advance to the next candidate. An LLM (`GenerationError`) or image fetch failure aborts the whole run with exit code 2 and leaves the item unrecorded, so it is retried on the next run. Only per-source news fetches are individually tolerated.
- Adding a module means adding it under `bot/`; the Dockerfile copies only that directory.

## Configuration

- `config.load_settings(env=..., dry_run=...)` accepts an injected env mapping — tests never mutate `os.environ`. New settings must be added to the `Settings` dataclass, read in `load_settings`, and documented in both `.env.example` and the README table (defaults are duplicated in those three places).
- `DEEPSEEK_API_KEY` is always required; `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` are required only when not in dry-run mode.
- Dry-run is resolved as `--dry-run` flag OR `DRY_RUN` env var. It only skips Telegram: news, memegen and DeepSeek calls still happen.

## State and dedupe

- `store.Store` is a SQLite DB at `DATA_DIR/bot.db` (default `./data`) with a single `posts` table keyed by `url_hash` = first 32 hex chars of SHA-256 of the URL without its query string (`pipeline.url_hash`).
- Every processed item is recorded, including rejections: `posted`, `dry_run`, `skipped_unsafe`, `skipped_model`. `is_seen` therefore means "already attempted", not "already published" — a dry-run record prevents later real publication of that URL. Keep this in mind when testing or replaying.
- `recent_templates()` feeds the last 10 used template IDs into the prompt so the model varies its choices.
- `.vscode/mcp.json` exposes a SQLite MCP server over `data/bot.db` for inspecting `posts`. It pins `mcp<2` because `mcp-server-sqlite` (2025.4.25) still uses the pre-2.x decorator API. The DB file only exists after a first run (`Store` creates it), so the server errors on its tools until then.

## LLM / meme contract

- The model must return a JSON object (`response_format: json_object`) matching `PLAN_SCHEMA`. `parse_plan` enforces: known `template_id`, a `lines` list whose length equals `Template.lines` reported by the memegen API, non-empty lines, `MAX_LINE_LENGTH` (45 chars) per line, and a caption that is non-empty, ≤ `MAX_CAPTION_LENGTH` (200) and free of URLs.
- `skip: true` returns `(None, None)` (recorded as `skipped_model`); an invalid payload returns an error string. `generate` retries exactly once by appending the bad answer plus a correction message, then raises `GenerationError`.
- The 45-char limit is duplicated in `MAX_LINE_LENGTH` and in the `SYSTEM_PROMPT` text — change both together.
- Templates come from the intersection of `templates.CURATED_TEMPLATE_IDS` and the live `/templates/` endpoint; unknown IDs are dropped and an empty result raises. When adding a curated ID, also describe its joke structure in `SYSTEM_PROMPT`, otherwise the model has no guidance for it.
- `memegen.build_image_url` is the canonical encoding (spaces → `_`, each line percent-encoded, lines joined by `/`); assert URL shapes in `tests/test_memegen.py` when touching it.
- `TelegramClient` retries once on HTTP 429, honoring `retry_after` clamped to 1–60 s, and raises `TelegramError` otherwise.

## Conventions

- All user-facing text — log messages, error strings, prompt content, CLI help, README — is French. Code identifiers and docstrings are English. Keep new messages French.
- `safety.BLOCKED_TERMS` is a flat FR+EN tuple; `_pattern` makes short ASCII terms (≤ 4 chars) match only the whole word or plural so `software`/`deadline` are not flagged. Add tests in `tests/test_safety.py` for new terms, including false-positive cases.
- Tests use `unittest` + `tempfile.TemporaryDirectory` (for `Store`) and `httpx.MockTransport` (for HTTP). They assert on fake bytes/callables, never on real services.
