import unittest
from datetime import timezone

from bot.news import parse_rss

SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Meta lance Muse &amp; son agent IA</title>
    <link>https://example.com/muse</link>
    <pubDate>Sun, 18 Oct 2026 19:00:00 GMT</pubDate>
  </item>
  <item>
    <title>Ligne sans date</title>
    <link>https://example.com/ignoree</link>
  </item>
</channel></rss>"""


class ParseRssTest(unittest.TestCase):
    def test_parses_items_with_a_date(self) -> None:
        items = parse_rss(SAMPLE_RSS, "Test")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Meta lance Muse & son agent IA")
        self.assertEqual(items[0].url, "https://example.com/muse")
        self.assertEqual(items[0].published.tzinfo, timezone.utc)

    def test_invalid_xml_returns_empty_list(self) -> None:
        self.assertEqual(parse_rss("<rss", "Test"), [])


if __name__ == "__main__":
    unittest.main()
