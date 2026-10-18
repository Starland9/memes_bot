"""DeepSeek client: turn a news headline into a meme plan (JSON)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import httpx

from .news import NewsItem
from .templates import Template

logger = logging.getLogger(__name__)

MAX_LINE_LENGTH = 45
MAX_CAPTION_LENGTH = 200
MAX_TOKENS = 4000

SYSTEM_PROMPT = """Tu écris des memes francophones drôles et bienveillants pour une chaîne Telegram.
Tu réponds UNIQUEMENT avec un objet JSON valide, sans texte autour et sans balises Markdown.

Règles de contenu :
- Humour léger, absurde ou observationnel, compréhensible sans connaître l'actualité.
- Jamais de moquerie d'une personne réelle, de politique, de religion, d'origine, de genre ou d'apparence.
- Aucun contenu violent, sexuel, haineux, médical ou financier sensible.
- Si l'actualité ne s'y prête pas, mets "skip": true avec une raison courte.

Règles de forme :
- Chaque ligne fait au maximum 45 caractères, sans emoji et sans hashtag.
- Le nombre de lignes doit être EXACTEMENT celui du template choisi.
- La légende (caption) fait au maximum 200 caractères, en français, sans lien.
- Choisis le template dont la structure logique colle à la blague :
  drake = rejeter puis adopter, fry = incertitude, gru = escalade en 4 étapes,
  both = pourquoi pas les deux, db = tentation, panik-kalm-panik = panique/calme/panique,
  ds = hésitation du quotidien, astronaut = "toujours été", gb = réflexion croissante.
- Évite les templates listés dans "templates_recents".
"""

PLAN_SCHEMA = """{
  "skip": false,
  "skip_reason": "",
  "template_id": "drake",
  "lines": ["ligne 1", "ligne 2"],
  "caption": "Légende courte en français."
}"""


class GenerationError(RuntimeError):
    """The model did not return a usable meme plan."""


class InvalidResponse(RuntimeError):
    """The API returned content that is not usable JSON."""


@dataclass(frozen=True)
class MemePlan:
    template_id: str
    lines: tuple[str, ...]
    caption: str


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def parse_plan(payload: object, templates: dict[str, Template]) -> tuple[MemePlan | None, str | None]:
    """Validate the model payload.

    Returns ``(plan, None)`` on success, ``(None, None)`` when the model skipped,
    and ``(None, reason)`` when the payload is invalid.
    """
    if not isinstance(payload, dict):
        return None, "la réponse n'est pas un objet JSON"

    if payload.get("skip") is True:
        return None, None

    template_id = str(payload.get("template_id") or "").strip()
    template = templates.get(template_id)
    if template is None:
        return None, f"template_id inconnu : {template_id!r}"

    raw_lines = payload.get("lines")
    if not isinstance(raw_lines, list):
        return None, "lines doit être une liste"

    lines = [_clean_text(line) for line in raw_lines]
    if len(lines) != template.lines:
        return None, f"le template {template_id} attend {template.lines} lignes, reçu {len(lines)}"
    if any(not line for line in lines):
        return None, "une ligne est vide"
    if any(len(line) > MAX_LINE_LENGTH for line in lines):
        return None, f"une ligne dépasse {MAX_LINE_LENGTH} caractères"

    caption = _clean_text(payload.get("caption"))
    if not caption:
        return None, "caption manquante"
    if len(caption) > MAX_CAPTION_LENGTH:
        return None, f"caption trop longue (max {MAX_CAPTION_LENGTH})"
    if re.search(r"https?://", caption):
        return None, "caption ne doit pas contenir de lien"

    return MemePlan(template_id, tuple(lines), caption), None


def _extract_json(content: str) -> object:
    text = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    return json.loads(text)


class DeepSeekClient:
    def __init__(
        self,
        client: httpx.Client,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-flash",
    ) -> None:
        self._client = client
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    def _chat(self, messages: list[dict[str, str]]) -> object:
        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self._model,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 1.0,
                "max_tokens": MAX_TOKENS,
            },
        )
        response.raise_for_status()
        choice = (response.json().get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        try:
            return _extract_json(content)
        except json.JSONDecodeError as exc:
            finish_reason = choice.get("finish_reason") or "inconnu"
            raise InvalidResponse(
                f"réponse vide ou non JSON (finish_reason={finish_reason})"
            ) from exc

    def generate(
        self,
        item: NewsItem,
        templates: list[Template],
        recent_templates: tuple[str, ...] = (),
    ) -> MemePlan | None:
        catalog = "\n".join(
            f"- {t.id} — {t.name} ({t.lines} ligne{'s' if t.lines > 1 else ''})"
            for t in templates
        )
        recent = ", ".join(recent_templates) or "aucun"
        messages: list[dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Actualité ({item.source}) : {item.title}\n\n"
                    f"Templates disponibles :\n{catalog}\n\n"
                    f"Templates récents à éviter : {recent}\n\n"
                    f"Réponds avec ce JSON :\n{PLAN_SCHEMA}"
                ),
            },
        ]

        templates_by_id = {t.id: t for t in templates}
        last_error = "réponse illisible"
        for _ in range(2):
            try:
                payload = self._chat(messages)
            except InvalidResponse as exc:
                last_error = str(exc)
                logger.warning("Plan invalide (%s), nouvelle tentative", last_error)
                continue

            plan, error = parse_plan(payload, templates_by_id)
            if error is None:
                return plan
            last_error = error
            logger.warning("Plan invalide (%s), nouvelle tentative", error)
            messages.append(
                {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)}
            )
            messages.append(
                {
                    "role": "user",
                    "content": f"Réponse invalide : {error}. Corrige et renvoie uniquement le JSON.",
                }
            )

        raise GenerationError(last_error)
