import unittest

from bot.config import ConfigError, load_settings


def _load(**extra: str):
    env = {"DEEPSEEK_API_KEY": "key"}
    env.update(extra)
    return load_settings(env=env, dry_run=True)


class OpenWAConfigTest(unittest.TestCase):
    def test_disabled_by_default(self) -> None:
        settings = _load()
        self.assertFalse(settings.openwa_configured)
        self.assertEqual(settings.openwa_status_recipients, ())

    def test_requires_all_three_settings(self) -> None:
        with self.assertRaisesRegex(ConfigError, "OPENWA_API_KEY, OPENWA_SESSION_ID"):
            _load(OPENWA_BASE_URL="http://localhost:2785")

    def test_parses_use_contacts(self) -> None:
        self.assertFalse(_load().openwa_status_use_contacts)
        settings = _load(OPENWA_STATUS_USE_CONTACTS="true")
        self.assertTrue(settings.openwa_status_use_contacts)

    def test_chat_filters_imply_use_contacts(self) -> None:
        settings = _load(OPENWA_STATUS_CHATTED_ONLY="1")
        self.assertTrue(settings.openwa_status_use_contacts)
        self.assertTrue(settings.openwa_status_chatted_only)

        settings = _load(OPENWA_STATUS_CHAT_DAYS="30")
        self.assertTrue(settings.openwa_status_use_contacts)
        self.assertFalse(settings.openwa_status_chatted_only)
        self.assertEqual(settings.openwa_status_chat_days, 30)

    def test_parses_recipients_and_trims_base_url(self) -> None:
        settings = _load(
            OPENWA_BASE_URL="http://localhost:2785/",
            OPENWA_API_KEY="secret",
            OPENWA_SESSION_ID="session-1",
            OPENWA_STATUS_RECIPIENTS="123@c.us, 456@lid ,",
        )
        self.assertTrue(settings.openwa_configured)
        self.assertEqual(settings.openwa_base_url, "http://localhost:2785")
        self.assertEqual(
            settings.openwa_status_recipients, ("123@c.us", "456@lid")
        )


OPENWA = {
    "OPENWA_BASE_URL": "http://localhost:2785",
    "OPENWA_API_KEY": "secret",
    "OPENWA_SESSION_ID": "session-1",
}


class PublishTargetsConfigTest(unittest.TestCase):
    def test_default_publishes_to_telegram_only(self) -> None:
        self.assertEqual(_load().publish_targets, ("telegram",))

    def test_default_adds_status_when_openwa_is_configured(self) -> None:
        self.assertEqual(
            _load(**OPENWA).publish_targets, ("telegram", "status")
        )

    def test_explicit_targets_replace_the_default(self) -> None:
        settings = _load(
            PUBLISH_TARGETS="Channel",
            OPENWA_CHANNEL_ID="120363000000000000",
            **OPENWA,
        )
        self.assertEqual(settings.publish_targets, ("channel",))

    def test_rejects_unknown_targets(self) -> None:
        with self.assertRaisesRegex(ConfigError, "inconnues : mastodon"):
            _load(PUBLISH_TARGETS="telegram,mastodon")

    def test_channel_target_requires_a_channel_id(self) -> None:
        with self.assertRaisesRegex(ConfigError, "OPENWA_CHANNEL_ID manquant"):
            _load(PUBLISH_TARGETS="channel", **OPENWA)

    def test_channel_target_requires_openwa(self) -> None:
        with self.assertRaisesRegex(ConfigError, "OPENWA_BASE_URL.*OPENWA_SESSION_ID"):
            _load(PUBLISH_TARGETS="channel", OPENWA_CHANNEL_ID="120363000000000000")

    def test_normalizes_the_channel_id(self) -> None:
        settings = _load(
            PUBLISH_TARGETS="channel",
            OPENWA_CHANNEL_ID="120363000000000000@newsletter",
            **OPENWA,
        )
        self.assertEqual(
            settings.openwa_channel_id, "120363000000000000@newsletter"
        )

        settings = _load(
            PUBLISH_TARGETS="channel",
            OPENWA_CHANNEL_ID=" 120363000000000000 ",
            **OPENWA,
        )
        self.assertEqual(
            settings.openwa_channel_id, "120363000000000000@newsletter"
        )

    def test_rejects_a_malformed_channel_id(self) -> None:
        with self.assertRaisesRegex(ConfigError, "OPENWA_CHANNEL_ID invalide"):
            _load(OPENWA_CHANNEL_ID="memes@newsletter", **OPENWA)

    def test_invite_code_as_channel_id_points_at_the_resolver(self) -> None:
        with self.assertRaisesRegex(
            ConfigError, "un id de chaîne est numérique.*--resolve-channel"
        ):
            _load(OPENWA_CHANNEL_ID="0029VbDVUc3H5JM2MUNqmq0J", **OPENWA)

    def test_channel_mode_defaults_to_image(self) -> None:
        settings = _load(
            PUBLISH_TARGETS="channel",
            OPENWA_CHANNEL_ID="120363000000000000",
            **OPENWA,
        )
        self.assertEqual(settings.openwa_channel_mode, "image")

    def test_channel_mode_accepts_link(self) -> None:
        settings = _load(
            PUBLISH_TARGETS="channel",
            OPENWA_CHANNEL_ID="120363000000000000",
            OPENWA_CHANNEL_MODE="Link",
            **OPENWA,
        )
        self.assertEqual(settings.openwa_channel_mode, "link")

    def test_channel_mode_rejects_unknown_values(self) -> None:
        with self.assertRaisesRegex(ConfigError, "OPENWA_CHANNEL_MODE invalide"):
            _load(OPENWA_CHANNEL_MODE="video", **OPENWA)

    def test_helper_commands_tolerate_a_bad_channel_id(self) -> None:
        settings = load_settings(
            env={
                "DEEPSEEK_API_KEY": "key",
                "OPENWA_CHANNEL_ID": "0029VbDVUc3H5JM2MUNqmq0J",
                "PUBLISH_TARGETS": "channel",
                **OPENWA,
            },
            dry_run=True,
            validate_publish=False,
        )
        self.assertEqual(settings.openwa_channel_id, "")
        self.assertEqual(settings.openwa_base_url, "http://localhost:2785")

    def test_channel_only_target_needs_no_telegram_token(self) -> None:
        env = {"DEEPSEEK_API_KEY": "key", "PUBLISH_TARGETS": "channel"}
        env.update(OPENWA)
        env["OPENWA_CHANNEL_ID"] = "120363000000000000@newsletter"
        settings = load_settings(env=env, dry_run=False)
        self.assertEqual(settings.publish_targets, ("channel",))

    def test_telegram_stays_required_for_the_telegram_target(self) -> None:
        env = {"DEEPSEEK_API_KEY": "key"}
        with self.assertRaisesRegex(ConfigError, "TELEGRAM_BOT_TOKEN"):
            load_settings(env=env, dry_run=False)


if __name__ == "__main__":
    unittest.main()
