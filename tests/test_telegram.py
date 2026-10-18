import unittest
from unittest import mock

import httpx

from bot.telegram import TelegramClient, TelegramError

TOKEN = "123:abc"
CHAT_ID = "-10042"


class TelegramClientTest(unittest.TestCase):
    def _client(self, handler) -> TelegramClient:
        http = httpx.Client(transport=httpx.MockTransport(handler))
        self.addCleanup(http.close)
        return TelegramClient(http, TOKEN)

    def test_sends_photo_with_caption(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = request.content
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 11}})

        result = self._client(handler).send_photo(CHAT_ID, b"png-bytes", "Une légende")
        self.assertEqual(result["message_id"], 11)
        self.assertEqual(seen["url"], f"https://api.telegram.org/bot{TOKEN}/sendPhoto")
        self.assertIn(b"Une l\xc3\xa9gende", seen["body"])

    def test_raises_on_api_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                400, json={"ok": False, "description": "Bad Request: chat not found"}
            )

        with self.assertRaises(TelegramError) as ctx:
            self._client(handler).send_photo(CHAT_ID, b"png", "caption")
        self.assertIn("chat not found", str(ctx.exception))

    def test_retries_once_on_rate_limit(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] == 1:
                return httpx.Response(
                    429,
                    json={"ok": False, "parameters": {"retry_after": 1}},
                )
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 12}})

        with mock.patch("bot.telegram.time.sleep") as sleep:
            result = self._client(handler).send_photo(CHAT_ID, b"png", "caption")

        self.assertEqual(result["message_id"], 12)
        self.assertEqual(calls["count"], 2)
        sleep.assert_called_once_with(1)

    def test_get_updates_passes_offset(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(
                200,
                json={"ok": True, "result": [{"update_id": 3}]},
            )

        updates = self._client(handler).get_updates(offset=3)

        self.assertEqual(updates, [{"update_id": 3}])
        self.assertIn("offset=3", seen["url"])
        self.assertIn("timeout=0", seen["url"])

    def test_sends_message(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = request.content
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 13}})

        result = self._client(handler).send_message(CHAT_ID, "Bonjour")

        self.assertEqual(result["message_id"], 13)
        self.assertEqual(seen["url"], f"https://api.telegram.org/bot{TOKEN}/sendMessage")
        self.assertIn(b"Bonjour", seen["body"])


if __name__ == "__main__":
    unittest.main()
