import unittest

from bot.memegen import build_image_url


class BuildImageUrlTest(unittest.TestCase):
    def test_encodes_spaces_accents_and_reserved_characters(self) -> None:
        url = build_image_url(
            "https://api.memegen.link/",
            "drake",
            ["Ça marche", "100% prêt"],
        )
        self.assertEqual(
            url,
            "https://api.memegen.link/images/drake/%C3%87a_marche/100%25_pr%C3%AAt.png",
        )

    def test_supports_single_line_templates(self) -> None:
        url = build_image_url("http://localhost:5000", "cmm", ["Un seul texte"])
        self.assertEqual(
            url, "http://localhost:5000/images/cmm/Un_seul_texte.png"
        )


if __name__ == "__main__":
    unittest.main()
