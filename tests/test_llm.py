import json
import unittest
from datetime import datetime, timezone

import httpx

from bot.llm import (
    MAX_TOKENS,
    DeepSeekClient,
    GenerationError,
    MemePlan,
    parse_plan,
)
from bot.news import NewsItem
from bot.templates import Template

ITEM = NewsItem(
    title="Une puce graphique bat des records",
    url="https://example.com/a",
    source="Test",
    published=datetime.now(timezone.utc),
)
TEMPLATES = [Template("drake", "Drakeposting", 2), Template("cmm", "Change My Mind", 1)]


def completion(payload: object) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": json.dumps(payload)}}]},
    )


class ParsePlanTest(unittest.TestCase):
    def test_accepts_valid_plan(self) -> None:
        plan, error = parse_plan(
            {
                "skip": False,
                "template_id": "drake",
                "lines": ["Ancien monde", "Nouveau monde"],
                "caption": "Une légende",
            },
            {t.id: t for t in TEMPLATES},
        )
        self.assertIsNone(error)
        self.assertEqual(plan, MemePlan("drake", ("Ancien monde", "Nouveau monde"), "Une légende"))

    def test_rejects_wrong_line_count(self) -> None:
        _, error = parse_plan(
            {"template_id": "drake", "lines": ["seule"], "caption": "ok"},
            {t.id: t for t in TEMPLATES},
        )
        self.assertIn("attend 2 lignes", error or "")

    def test_rejects_link_in_caption(self) -> None:
        _, error = parse_plan(
            {
                "template_id": "cmm",
                "lines": ["texte"],
                "caption": "voir https://example.com",
            },
            {t.id: t for t in TEMPLATES},
        )
        self.assertIn("lien", error or "")

    def test_skip_returns_none_without_error(self) -> None:
        plan, error = parse_plan({"skip": True, "skip_reason": "pas drôle"}, {})
        self.assertIsNone(plan)
        self.assertIsNone(error)


class DeepSeekClientTest(unittest.TestCase):
    def test_sends_json_mode_request_and_parses_plan(self) -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            body = json.loads(request.content)
            self.assertEqual(body["response_format"], {"type": "json_object"})
            self.assertEqual(body["model"], "deepseek-flash")
            self.assertEqual(body["max_tokens"], MAX_TOKENS)
            return completion(
                {
                    "template_id": "drake",
                    "lines": ["Avant", "Après"],
                    "caption": "Légende",
                }
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            plan = DeepSeekClient(client, "key").generate(ITEM, TEMPLATES)

        self.assertEqual(plan, MemePlan("drake", ("Avant", "Après"), "Légende"))
        self.assertEqual(len(requests), 1)
        self.assertTrue(str(requests[0].url).endswith("/chat/completions"))

    def test_retries_once_on_invalid_payload(self) -> None:
        responses = [
            {"template_id": "drake", "lines": ["une seule"], "caption": "ok"},
            {"template_id": "drake", "lines": ["une", "deux"], "caption": "ok"},
        ]
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            payload = responses[calls["count"]]
            calls["count"] += 1
            return completion(payload)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            plan = DeepSeekClient(client, "key").generate(ITEM, TEMPLATES)

        self.assertEqual(plan, MemePlan("drake", ("une", "deux"), "ok"))
        self.assertEqual(calls["count"], 2)

    def test_raises_after_two_invalid_payloads(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return completion({"template_id": "inconnu", "lines": [], "caption": ""})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(GenerationError):
                DeepSeekClient(client, "key").generate(ITEM, TEMPLATES)

    def test_retries_when_content_is_empty(self) -> None:
        bodies = [
            {"choices": [{"finish_reason": "length", "message": {"content": ""}}]},
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {
                                    "template_id": "drake",
                                    "lines": ["une", "deux"],
                                    "caption": "ok",
                                }
                            )
                        },
                    }
                ]
            },
        ]
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            body = bodies[calls["count"]]
            calls["count"] += 1
            return httpx.Response(200, json=body)

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            plan = DeepSeekClient(client, "key").generate(ITEM, TEMPLATES)

        self.assertEqual(plan, MemePlan("drake", ("une", "deux"), "ok"))
        self.assertEqual(calls["count"], 2)

    def test_raises_generation_error_when_content_stays_empty(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"choices": [{"finish_reason": "length", "message": {"content": ""}}]},
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(GenerationError) as ctx:
                DeepSeekClient(client, "key").generate(ITEM, TEMPLATES)

        self.assertIn("finish_reason=length", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
