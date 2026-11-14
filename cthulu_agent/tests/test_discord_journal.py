import json
import os
import sys
import time
import urllib.parse
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.error import HTTPError
from email.message import Message
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cthulu_agent.discord_journal import (  # noqa: E402
    DiscordJournalDelivery,
    WEBHOOK_ENV,
    _message,
    _post,
    _webhook_url,
)
from cthulu_agent.journal import Journal  # noqa: E402


class DiscordJournalTests(unittest.TestCase):
    def setUp(self):
        self.previous_url = os.environ.get(WEBHOOK_ENV)
        os.environ[WEBHOOK_ENV] = "https://discord.com/api/webhooks/123456/test-secret"
        self.journal = Journal()
        self.delivery = DiscordJournalDelivery(self.journal)

    def tearDown(self):
        self.delivery.stop()
        self.journal._db.close()
        if self.previous_url is None:
            os.environ.pop(WEBHOOK_ENV, None)
        else:
            os.environ[WEBHOOK_ENV] = self.previous_url

    def test_live_journal_entries_are_not_sent_immediately_to_discord(self):
        for kind in ("reason", "world", "system"):
            self.delivery.enqueue(self.journal.add(kind, f"{kind} title", "entry body"))

        self.assertEqual(len(self.journal.entries(kind="reason,world")), 2)
        self.assertEqual(self.journal.discord_pending(), [])

    def test_hourly_world_update_is_scheduled_only_to_discord(self):
        hour = 1_793_883_600  # 2026-11-05 13:00 UTC
        world = SimpleNamespace(brief={
            "summary": "The dollar strengthened as yields rose.",
            "themes": [{
                "theme": "Gold faces macro pressure",
                "bias": "bearish",
                "assets": ["GOLD"],
                "why": "Higher yields and a firmer dollar are headwinds.",
            }],
            "event_risk": [{"what": "US data", "when": "today"}],
            "stand_down": False,
            "ts": hour - 300,
        })
        delivery = DiscordJournalDelivery(self.journal, world, ("BTCUSD",))

        delivery.schedule_due(now=hour + 30)
        first = self.journal.discord_pending()
        delivery.schedule_due(now=hour + 60)

        self.assertEqual(len(first), 1)
        self.assertEqual(len(self.journal.discord_pending()), 1)
        payload = json.loads(first[0]["content"])
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "🌍 Hourly World Brief")
        self.assertIn("Gold faces macro pressure", embed["description"])
        self.assertIn("US data", embed["description"])
        self.assertIn("BTCUSD", embed["fields"][0]["value"])
        self.assertEqual(self.journal.entries(), [])

    def test_world_brief_contains_all_material_themes_and_events(self):
        hour = datetime(2026, 11, 5, 13, 0, tzinfo=timezone.utc).timestamp()
        world = SimpleNamespace(brief={
            "summary": "Global risk sentiment is mixed amid shifting commodity and currency conditions.",
            "themes": [
                {"theme": f"Theme {index}", "bias": "neutral", "assets": [], "why": "Source data supports this observation."}
                for index in range(1, 8)
            ],
            "event_risk": [
                {"what": f"Event {index}", "when": "today"}
                for index in range(1, 7)
            ],
            "stand_down": False,
            "ts": hour,
        })
        delivery = DiscordJournalDelivery(self.journal, world)

        delivery.schedule_due(now=hour + 30)

        description = json.loads(self.journal.discord_pending()[0]["content"])["embeds"][0]["description"]
        self.assertIn("Theme 7", description)
        self.assertIn("Event 6", description)

    def test_world_and_session_updates_target_their_dedicated_threads(self):
        world = SimpleNamespace(brief={
            "summary": "Markets are reacting to global trade and macro data developments.",
            "themes": [],
            "event_risk": [],
            "stand_down": False,
        })
        delivery = DiscordJournalDelivery(self.journal, world)
        world_hour = datetime(2026, 11, 5, 13, 0, tzinfo=timezone.utc).timestamp()
        session_prep = datetime(2026, 11, 5, 11, 55, 30, tzinfo=timezone.utc).timestamp()

        with patch.dict(os.environ, {
            "DISCORD_WORLD_BRIEF_THREAD_ID": "1568029828777517197",
            "DISCORD_TRADING_JOURNAL_THREAD_ID": "1568029693876109363",
        }):
            delivery.schedule_due(now=world_hour + 30)
            delivery.schedule_due(now=session_prep)

        payloads = [json.loads(item["content"]) for item in self.journal.discord_pending()]
        by_title = {item["embeds"][0]["title"]: item for item in payloads}
        self.assertEqual(by_title["🌍 Hourly World Brief"]["_discord_thread_id"], "1568029828777517197")
        self.assertEqual(by_title["📓 New York · Pre-session journal"]["_discord_thread_id"], "1568029693876109363")

    def test_session_preparation_and_close_updates_use_utc_session_windows(self):
        delivery = DiscordJournalDelivery(self.journal, symbols=("BTCUSD", "GOLD", "WTI"))
        event_times = (
            (23, 55, 30),  # Asia prep
            (7, 0, 30),    # Asia close
            (6, 55, 30),   # London prep
            (12, 0, 30),   # London close
            (11, 55, 30),  # New York prep
            (21, 0, 30),   # New York close
        )
        for hour, minute, second in event_times:
            now = datetime(2026, 11, 5, hour, minute, second, tzinfo=timezone.utc).timestamp()
            delivery.schedule_due(now=now)

        payloads = [json.loads(item["content"]) for item in self.journal.discord_pending()]
        titles = {payload["embeds"][0]["title"] for payload in payloads}
        self.assertIn("📓 Asia · Pre-session journal", titles)
        self.assertIn("📓 London · Pre-session journal", titles)
        self.assertIn("📓 Asia · Session close journal", titles)
        self.assertIn("📓 London · Session close journal", titles)
        self.assertIn("📓 New York · Pre-session journal", titles)
        self.assertIn("📓 New York · Session close journal", titles)
        self.assertTrue(all("BTCUSD" in payload["embeds"][0]["fields"][0]["value"] for payload in payloads))
        self.assertEqual(self.journal.entries(), [])


    def test_message_includes_clickable_chart_for_known_instrument(self):
        message = _message({
            "kind": "reason", "title": "Sweep setup", "body": "Wait for a reclaim.",
            "symbol": "BTCUSD#", "cycle": 7, "ts": 1_798_900_000,
        })
        embed = message["embeds"][0]
        self.assertEqual(embed["fields"][0]["value"], "BTCUSD#")
        self.assertIn("COINBASE%3ABTCUSD", embed["fields"][1]["value"])
        self.assertEqual(embed["url"], "https://www.tradingview.com/chart/?symbol=COINBASE%3ABTCUSD")
        self.assertIn("not execution confirmations", embed["footer"]["text"])

    def test_unconfigured_webhook_does_not_accumulate_messages(self):
        os.environ.pop(WEBHOOK_ENV, None)
        self.delivery.enqueue(self.journal.add("reason", "reason title", "entry body"))
        self.assertEqual(self.journal.discord_pending(), [])

    def test_message_respects_discord_limit(self):
        message = _message({"kind": "reason", "title": "test", "body": "x" * 5000})
        self.assertEqual(len(message["embeds"][0]["description"]), 3500)
        self.assertTrue(message["embeds"][0]["description"].endswith("..."))

    def test_delivery_marks_outbox_item_done(self):
        payload = {"embeds": [{"title": "Hourly World Brief"}], "allowed_mentions": {"parse": []}}
        self.delivery._enqueue_scheduled(1, 1_798_900_800, payload)
        with patch("cthulu_agent.discord_journal._post", return_value=(True, 0.0, "")) as post:
            self.delivery.start()
            deadline = time.time() + 2
            while self.journal.discord_pending() and time.time() < deadline:
                time.sleep(0.01)
            self.delivery.stop()

        post.assert_called_once()
        self.assertIn("embeds", post.call_args.args[1])
        self.assertEqual(self.journal.discord_pending(), [])

    def test_permanent_delivery_failure_is_retained_without_retry(self):
        payload = {"embeds": [{"title": "Hourly World Brief"}], "allowed_mentions": {"parse": []}}
        self.delivery._enqueue_scheduled(1, 1_798_900_800, payload)
        item = self.journal.discord_pending()[0]

        self.journal.discord_mark_permanent_failure(
            item["journal_id"], 1, "http_400 (code 50035: Invalid Form Body)"
        )

        self.assertEqual(self.journal.discord_pending(), [])
        row = self.journal._q(
            "SELECT failed_at, last_error FROM discord_outbox WHERE journal_id=?",
            (item["journal_id"],),
        )[0]
        self.assertIsNotNone(row["failed_at"])
        self.assertIn("50035", row["last_error"])

    def test_http_error_includes_only_discord_error_details(self):
        error_body = json.dumps({
            "code": 50035,
            "message": "Invalid Form Body",
            "errors": {"embeds": {"_errors": [{"message": "Invalid embed"}]}},
        }).encode()
        headers = Message()
        http_error = HTTPError("https://discord.com/api/webhooks/secret", 400, "Bad Request", headers, None)
        http_error.read = lambda _size=-1: error_body

        with patch("cthulu_agent.discord_journal.urllib.request.urlopen", side_effect=http_error):
            delivered, delay, error = _post(
                "https://discord.com/api/webhooks/123456/secret",
                {"embeds": [{"title": "test"}]},
            )

        self.assertFalse(delivered)
        self.assertEqual(delay, 0.0)
        self.assertIn("50035", error)
        self.assertIn("Invalid embed", error)
        self.assertNotIn("secret", error)

    def test_forum_mode_posts_each_entry_as_a_named_thread(self):
        response = MagicMock(status=204)
        response.__enter__.return_value = response
        entry = {
            "embeds": [{
                "title": "🧠 Agent Journal · BTCUSD setup",
                "timestamp": "2026-11-05T17:00:00Z",
            }],
            "allowed_mentions": {"parse": []},
        }

        with patch.dict(os.environ, {"DISCORD_TRADING_JOURNAL_FORUM_MODE": "true"}), \
                patch("cthulu_agent.discord_journal.urllib.request.urlopen", return_value=response) as post:
            delivered, _delay, error = _post(
                "https://discord.com/api/webhooks/123456/test-secret", entry
            )

        request = post.call_args.args[0]
        sent_payload = json.loads(request.data)
        thread_name = sent_payload["thread_name"]
        self.assertTrue(delivered)
        self.assertEqual(error, "")
        self.assertNotIn("thread_name", request.full_url)
        self.assertIn("2026-11-05 17:00 UTC", thread_name)
        self.assertIn("BTCUSD setup", thread_name)
        self.assertLessEqual(len(thread_name), 100)

    def test_existing_thread_route_takes_precedence_over_forum_thread_creation(self):
        response = MagicMock(status=204)
        response.__enter__.return_value = response
        payload = {
            "embeds": [{"title": "🌍 Hourly World Brief"}],
            "_discord_thread_id": "1568029828777517197",
        }

        with patch.dict(os.environ, {"DISCORD_TRADING_JOURNAL_FORUM_MODE": "true"}), \
                patch("cthulu_agent.discord_journal.urllib.request.urlopen", return_value=response) as post:
            delivered, _delay, error = _post(
                "https://discord.com/api/webhooks/123456/test-secret", payload
            )

        request = post.call_args.args[0]
        self.assertTrue(delivered)
        self.assertEqual(error, "")
        self.assertEqual(
            urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)["thread_id"],
            ["1568029828777517197"],
        )
        sent_payload = json.loads(request.data)
        self.assertNotIn("_discord_thread_id", sent_payload)
        self.assertNotIn("thread_name", sent_payload)

    def test_invalid_thread_id_is_not_sent(self):
        with patch("cthulu_agent.discord_journal.urllib.request.urlopen") as post:
            delivered, delay, error = _post(
                "https://discord.com/api/webhooks/123456/test-secret",
                {"_discord_thread_id": "not-a-thread"},
            )

        self.assertFalse(delivered)
        self.assertEqual(delay, 0.0)
        self.assertEqual(error, "invalid_thread_id")
        post.assert_not_called()

    def test_start_does_not_backfill_local_journal_entries(self):
        for index in range(12):
            self.journal.add("reason", f"reason {index}", "entry body")

        with patch.object(self.delivery, "schedule_due"), \
                patch("cthulu_agent.discord_journal._post", return_value=(True, 0.0, "")):
            self.delivery.start()
            self.delivery.stop()

        self.assertEqual(self.journal.discord_pending(), [])

    def test_invalid_webhook_url_is_not_used(self):
        os.environ[WEBHOOK_ENV] = "https://example.com/api/webhooks/123456/test-secret"
        self.assertEqual(_webhook_url(), "")


if __name__ == "__main__":
    unittest.main()
