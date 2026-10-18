import unittest

from bot.safety import blocked_term


class SafetyTest(unittest.TestCase):
    def test_blocks_violent_french_headline(self) -> None:
        self.assertIsNotNone(blocked_term("Un homme tué dans un accident de la route"))

    def test_blocks_english_disaster_headline(self) -> None:
        self.assertEqual(blocked_term("Why war never changes"), "war")

    def test_allows_harmless_tech_headline(self) -> None:
        self.assertIsNone(
            blocked_term("Une puce graphique bat des records de vitesse")
        )

    def test_does_not_match_inside_a_word(self) -> None:
        self.assertIsNone(blocked_term("Someone behind the software"))


if __name__ == "__main__":
    unittest.main()
