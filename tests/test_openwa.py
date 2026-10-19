import json
import unittest

import httpx

from bot.openwa import (
    OpenWAError,
    OpenWAClient,
    parse_channel_invite,
)


class ChannelInviteTest(unittest.TestCase):
    def test_parses_a_share_link(self) -> None:
        self.assertEqual(
            parse_channel_invite(
                "https://whatsapp.com/channel/0029VbDVUc3H5JM2MUNqmq0J"
            ),
            "0029VbDVUc3H5JM2MUNqmq0J",
        )

    def test_parses_a_link_with_a_query_string(self) -> None:
        self.assertEqual(
            parse_channel_invite(
                "https://www.whatsapp.com/channel/0029VbDVUc3H5JM2MUNqmq0J?fbclid=abc"
            ),
            "0029VbDVUc3H5JM2MUNqmq0J",
        )

    def test_accepts_a_bare_code(self) -> None:
        self.assertEqual(
            parse_channel_invite(" 0029VbDVUc3H5JM2MUNqmq0J "),
            "0029VbDVUc3H5JM2MUNqmq0J",
        )

    def test_rejects_anything_else(self) -> None:
        with self.assertRaisesRegex(ValueError, "lien de chaîne invalide"):
            parse_channel_invite("https://example.com/hello world")


class OpenWAClientTest(unittest.TestCase):
    def _client(self, handler) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(handler))

    def test_posts_image_status_with_base64_and_caption(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["api_key"] = request.headers["X-API-Key"]
            captured["payload"] = json.loads(request.content)
            return httpx.Response(201, json={"id": "STATUS1"})

        with self._client(handler) as client:
            api = OpenWAClient(
                client,
                "http://127.0.0.1:2785/",
                "secret",
                "session-1",
                ("123@c.us",),
            )
            result = api.send_image_status(b"png-bytes", "Légende")

        self.assertEqual(result, {"id": "STATUS1"})
        self.assertEqual(
            captured["url"],
            "http://127.0.0.1:2785/api/sessions/session-1/status/send-image",
        )
        self.assertEqual(captured["api_key"], "secret")
        self.assertEqual(
            captured["payload"],
            {
                "image": {"base64": "cG5nLWJ5dGVz", "mimetype": "image/png"},
                "caption": "Légende",
                "recipients": ["123@c.us"],
            },
        )

    def test_omits_empty_caption_and_recipients(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["payload"] = json.loads(request.content)
            return httpx.Response(201, json={"id": "STATUS1"})

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "session-1")
            api.send_image_status(b"png-bytes", "")

        self.assertNotIn("caption", captured["payload"])
        self.assertNotIn("recipients", captured["payload"])

    def test_reports_gateway_errors(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(409, json={"message": "session not ready"})

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "session-1")
            with self.assertRaisesRegex(OpenWAError, "409.*session not ready"):
                api.send_image_status(b"png-bytes", "Légende")

    def test_posts_image_to_a_channel_with_chat_id(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["api_key"] = request.headers["X-API-Key"]
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                201, json={"messageId": "CHANNEL1", "timestamp": 1706868000}
            )

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "session-1")
            result = api.send_image_message(
                "120363000000000000@newsletter", b"png-bytes", "Légende"
            )

        self.assertEqual(result["messageId"], "CHANNEL1")
        self.assertEqual(
            captured["url"],
            "http://localhost:2785/api/sessions/session-1/messages/send-image",
        )
        self.assertEqual(captured["api_key"], "secret")
        self.assertEqual(
            captured["payload"],
            {
                "chatId": "120363000000000000@newsletter",
                "base64": "cG5nLWJ5dGVz",
                "mimetype": "image/png",
                "caption": "Légende",
            },
        )

    def test_channel_post_without_caption_omits_it(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["payload"] = json.loads(request.content)
            return httpx.Response(201, json={"messageId": "CHANNEL1"})

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "session-1")
            api.send_image_message("120363000000000000@newsletter", b"png-bytes", "")

        self.assertNotIn("caption", captured["payload"])

    def test_channel_post_reports_the_wwjs_refusal(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                501, json={"message": "Channel media is not supported"}
            )

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "session-1")
            with self.assertRaisesRegex(OpenWAError, "501.*not supported"):
                api.send_image_message(
                    "120363000000000000@newsletter", b"png-bytes", "Légende"
                )

    def test_subscribes_to_resolve_the_channel_id(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["api_key"] = request.headers["X-API-Key"]
            captured["payload"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": "120363000000000000@newsletter",
                    "name": "Memes News",
                },
            )

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "session-1")
            channel = api.subscribe_channel("0029VbDVUc3H5JM2MUNqmq0J")

        self.assertEqual(channel["id"], "120363000000000000@newsletter")
        self.assertEqual(
            captured["url"],
            "http://localhost:2785/api/sessions/session-1/channels/subscribe",
        )
        self.assertEqual(captured["api_key"], "secret")
        self.assertEqual(
            captured["payload"], {"inviteCode": "0029VbDVUc3H5JM2MUNqmq0J"}
        )

    def test_pages_through_all_contacts(self) -> None:
        pages = {
            "0": [
                {"id": "111@c.us", "name": "Ada", "isMyContact": True},
                {"id": "222@c.us", "name": "Zoé", "isMyContact": True},
            ],
            "2": [{"id": "333@lid", "name": "Linus", "isMyContact": True}],
        }
        seen_offsets: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/sessions/session-1/contacts")
            self.assertEqual(request.headers["X-API-Key"], "secret")
            offset = request.url.params["offset"]
            seen_offsets.append(offset)
            return httpx.Response(200, json=pages.get(offset, []))

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "session-1")
            contacts = api.list_contacts(page_size=2)

        self.assertEqual([contact["id"] for contact in contacts], [
            "111@c.us",
            "222@c.us",
            "333@lid",
        ])
        self.assertEqual(seen_offsets, ["0", "2"])

    def test_pages_through_all_chats(self) -> None:
        seen_offsets: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/api/sessions/session-1/chats")
            offset = request.url.params["offset"]
            seen_offsets.append(offset)
            page = (
                [{"id": "111@c.us", "kind": "individual", "timestamp": 10}]
                if offset == "0"
                else []
            )
            return httpx.Response(200, json=page)

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "session-1")
            chats = api.list_chats(page_size=1)

        self.assertEqual([chat["id"] for chat in chats], ["111@c.us"])
        self.assertEqual(seen_offsets, ["0", "1"])

    def test_quotes_session_id_in_path(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(201, json={})

        with self._client(handler) as client:
            api = OpenWAClient(client, "http://localhost:2785", "secret", "a/b")
            api.send_image_status(b"png-bytes", "Légende")

        self.assertIn("/api/sessions/a%2Fb/status/send-image", captured["url"])


if __name__ == "__main__":
    unittest.main()
