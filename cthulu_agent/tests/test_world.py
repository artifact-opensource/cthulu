import json
import os
import time
import unittest
import urllib.error
from types import SimpleNamespace
from unittest.mock import patch

from cthulu_agent.agent import AgentRuntime
from cthulu_agent.journal import Journal
from cthulu_agent import llm as llmmod
from cthulu_agent.world import NATIVE_FEEDS, WorldIntel, normalize_world_brief, world_brief_validation_error


class NativeWorldFeedTests(unittest.TestCase):
    def test_world_brief_validation_rejects_prompt_template_but_accepts_analysis(self):
        template = {
            "summary": "3-5 sentences",
            "themes": [{
                "theme": "",
                "assets": ["SYMBOL or asset class"],
                "bias": "risk_on|risk_off|bullish|bearish|volatile|neutral",
                "urgency": "low|medium|high",
                "why": "",
            }],
            "event_risk": [{"what": "", "when": "", "assets": [""]}],
            "stand_down": False,
        }
        self.assertIn("placeholder", world_brief_validation_error(template))

        valid = {
            "summary": "Treasury yields rose while the dollar strengthened, creating macro headwinds for gold.",
            "themes": [{
                "theme": "Stronger dollar pressures gold",
                "assets": ["XAUUSD"],
                "bias": "bearish",
                "urgency": "medium",
                "why": "The feed shows a stronger dollar and higher yields.",
            }],
            "event_risk": [],
            "stand_down": False,
        }
        self.assertEqual(world_brief_validation_error(valid), "")

    def test_world_brief_normalizes_singleton_and_json_encoded_lists(self):
        brief = {
            "summary": "Treasury yields rose while the dollar strengthened, creating macro headwinds for gold.",
            "themes": {
                "theme": "Stronger dollar pressures gold",
                "assets": ["XAUUSD"],
                "bias": "bearish",
                "urgency": "medium",
                "why": "The feed shows a stronger dollar and higher yields.",
            },
            "event_risk": '{"what":"US data release","when":"today","assets":["XAUUSD"]}',
            "stand_down": False,
        }

        normalized = normalize_world_brief(brief)

        self.assertIsInstance(normalized["themes"], list)
        self.assertIsInstance(normalized["event_risk"], list)
        self.assertEqual(len(normalized["themes"]), 1)
        self.assertEqual(len(normalized["event_risk"]), 1)
        self.assertEqual(world_brief_validation_error(normalized), "")

    def test_world_brief_uses_empty_arrays_for_missing_or_null_lists(self):
        brief = {
            "summary": "Treasury yields rose while the dollar strengthened, creating macro headwinds for gold.",
            "event_risk": None,
            "stand_down": False,
        }

        normalized = normalize_world_brief(brief)

        self.assertEqual(normalized["themes"], [])
        self.assertEqual(normalized["event_risk"], [])
        self.assertEqual(world_brief_validation_error(normalized), "")

    def test_world_brief_normalizes_explicit_boolean_encodings(self):
        for value in ("false", "TRUE", "no", "off", "1", "0", 1, 0, 1.0, 0.0):
            with self.subTest(value=value):
                normalized = normalize_world_brief({"stand_down": value})
                self.assertIsInstance(normalized["stand_down"], bool)
                self.assertEqual(normalized["stand_down"], value not in ("false", "no", "off", "0", 0, 0.0))

        for value in ("true", "yes", "on"):
            with self.subTest(value=value):
                self.assertIs(normalize_world_brief({"stand_down": value})["stand_down"], True)

        self.assertEqual(normalize_world_brief({"stand_down": "unknown"})["stand_down"], "unknown")
        self.assertIs(normalize_world_brief({"stand_down": None})["stand_down"], False)
        self.assertIs(normalize_world_brief({})["stand_down"], False)

    def test_native_feeds_are_parsed_and_cached_in_the_agent_database(self):
        journal = Journal(":memory:")
        world = WorldIntel(journal)

        def response(url):
            if "coingecko" in url:
                return b'{"bitcoin":{"usd":68000,"usd_24h_change":1.25}}'
            if "feeds.bbci.co.uk" in url:
                return b"""<?xml version="1.0"?>
                <rss version="2.0"><channel><title>BBC Test</title><lastBuildDate>Today</lastBuildDate>
                <item><title>Oil supply risk rises</title><description><![CDATA[Markets <b>watch</b> supply.]]></description>
                <link>https://example.com/story</link><pubDate>Today</pubDate></item>
                </channel></rss>"""
            series = url.rsplit("id=", 1)[1]
            return f"observation_date,{series}\n2026-11-03,4.25\n".encode()

        with patch.dict(os.environ, {"WORLD_NATIVE_ENABLED": "true", "WORLD_API_URL": ""}), \
                patch.object(WorldIntel, "_read_url", side_effect=response):
            self.assertTrue(world.fetch())

        payload = json.loads(world.payload_for_prompt())
        self.assertEqual(payload["source"], "cthulu_native_public_feeds")
        self.assertEqual(payload["sources"]["coingecko_bitcoin"]["data"]["usd"], 68000.0)
        self.assertEqual(payload["sources"]["fred_dgs10"]["data"], {"date": "2026-11-03", "value": 4.25})
        self.assertEqual(payload["sources"]["bbc_world"]["data"]["items"][0]["title"], "Oil supply risk rises")
        self.assertEqual(payload["sources"]["bbc_business"]["data"]["items"][0]["summary"], "Markets watch supply.")
        self.assertEqual(set(payload["sources"]), set(NATIVE_FEEDS))

        restored = WorldIntel(journal)
        self.assertIn("coingecko_bitcoin", restored.payload_for_prompt())
        self.assertEqual(restored.native_feed_status()["fred_dcoilwtico"]["status"], "ok")

    def test_world_prompt_explicitly_reviews_geopolitical_sources(self):
        from cthulu_agent.prompts import world_prompt

        prompt = world_prompt('{"sources":{"bbc_world":{"items":[]}}}', ["BTCUSD", "GOLD", "WTI"])

        self.assertIn("geopolitics", prompt[-1]["content"].lower())
        self.assertIn("energy supply", prompt[-1]["content"].lower())
        self.assertIn("headlines are context", prompt[-1]["content"].lower())

    def test_failed_refresh_keeps_last_good_value_and_reports_stale(self):
        journal = Journal(":memory:")
        world = WorldIntel(journal)
        world.native_feeds["fred_dcoilwtico"] = {
            "status": "ok",
            "fetched_at": 123.0,
            "data": {"date": "2026-11-03", "value": 60.0},
            "error": "",
        }

        def response(url):
            if "DCOILWTICO" in url:
                raise urllib.error.URLError("offline")
            if "coingecko" in url:
                return b'{"bitcoin":{"usd":68000}}'
            if "feeds.bbci.co.uk" in url:
                return b"""<?xml version="1.0"?>
                <rss version="2.0"><channel><title>BBC Test</title>
                <item><title>World headline</title><description>Summary</description>
                <link>https://example.com/story</link></item></channel></rss>"""
            series = url.rsplit("id=", 1)[1]
            return f"observation_date,{series}\n2026-11-03,4.25\n".encode()

        with patch.dict(os.environ, {"WORLD_NATIVE_ENABLED": "true", "WORLD_API_URL": ""}), \
                patch.object(WorldIntel, "_read_url", side_effect=response):
            self.assertTrue(world.fetch())

        stale = world.native_feed_status()["fred_dcoilwtico"]
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(world.native_feeds["fred_dcoilwtico"]["data"]["value"], 60.0)
        self.assertIn("offline", stale["error"])

    def test_public_feed_status_hides_error_details(self):
        world = WorldIntel()
        world.native_feeds["fred_dcoilwtico"] = {
            "status": "error",
            "fetched_at": 0,
            "data": None,
            "error": "private transport diagnostic",
        }

        public_feed = world.public_config()["native_feeds"]["fred_dcoilwtico"]

        self.assertEqual(public_feed["status"], "unavailable")
        self.assertNotIn("error", public_feed)
        self.assertNotIn("private transport diagnostic", str(world.public_config()))

    def test_bitcoin_parser_rejects_non_finite_prices(self):
        with self.assertRaisesRegex(ValueError, "Bitcoin USD price"):
            WorldIntel._parse_feed("coingecko_bitcoin", b'{"bitcoin":{"usd":NaN}}')

    def test_digest_failure_has_bounded_retry_and_success_clears_error(self):
        world = WorldIntel()
        world.ingest({"headline": "market update"})
        world.last_fetch = time.time()
        self.assertTrue(world.due())

        world.mark_digest_failed("model unavailable")

        self.assertEqual(world.digest_error, "model unavailable")
        self.assertEqual(world.digest_attempts, 1)
        self.assertGreaterEqual(world.digest_retry_at - time.time(), 29)
        self.assertLessEqual(world.digest_retry_at - time.time(), 30)
        self.assertFalse(world.due())

        world.digest_retry_at = time.time() - 1
        self.assertTrue(world.due())
        world.set_brief({"summary": "Recovered"})
        self.assertFalse(world.due())
        self.assertEqual(world.digest_attempts, 0)
        self.assertEqual(world.digest_error, "")

    def test_runtime_surfaces_digest_errors_without_marking_payload_as_digested(self):
        world = WorldIntel()
        world.ingest({"headline": "market update"})
        world.last_fetch = time.time()
        runtime = object.__new__(AgentRuntime)
        runtime.world = world
        runtime.s = SimpleNamespace(symbols=["EURUSD"])
        runtime.llm = SimpleNamespace(chat_json=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
        runtime._phase = lambda *args: None
        runtime._sys = lambda *args: None
        runtime.bus = SimpleNamespace(emit=lambda *args, **kwargs: None)

        with patch("cthulu_agent.agent.log.warning") as log_warning:
            runtime._maybe_world()

        log_warning.assert_called_once()
        self.assertIn("provider unavailable", world.digest_error)
        self.assertEqual(world.digested_ts, 0.0)
        self.assertFalse(world.due())

    def test_runtime_normalizes_single_theme_object_before_digest_validation(self):
        world = WorldIntel()
        world.ingest({"headline": "market update"})
        world.refresh_due = lambda: False
        theme = {
            "theme": "Stronger dollar pressures gold",
            "assets": ["XAUUSD"],
            "bias": "bearish",
            "urgency": "medium",
            "why": "The feed shows a stronger dollar and higher yields.",
        }
        runtime = object.__new__(AgentRuntime)
        runtime.world = world
        runtime.s = SimpleNamespace(symbols=["XAUUSD"])
        runtime.llm = SimpleNamespace(chat_json=lambda *args, **kwargs: {
            "summary": "Treasury yields rose while the dollar strengthened, creating macro headwinds for gold.",
            "themes": theme,
            "event_risk": None,
            "stand_down": "false",
        })
        runtime._phase = lambda *args: None
        runtime._sys = lambda *args: self.fail("valid normalized brief should not trigger an error notification")
        runtime.bus = SimpleNamespace(emit=lambda *args, **kwargs: None)
        runtime.note = lambda *args, **kwargs: None
        runtime.stand_down_until = 0.0

        runtime._maybe_world()

        self.assertEqual(world.brief["themes"], [theme])
        self.assertEqual(world.brief["event_risk"], [])
        self.assertIs(world.brief["stand_down"], False)
        self.assertEqual(world.digest_error, "")

    def test_runtime_repairs_invalid_stand_down_schema_before_reporting_failure(self):
        world = WorldIntel()
        world.ingest({"headline": "market update"})
        world.refresh_due = lambda: False
        malformed = {
            "summary": "Treasury yields rose while the dollar strengthened, creating macro headwinds for gold.",
            "themes": [],
            "event_risk": [],
            "stand_down": "No immediate shock is evident.",
        }
        repaired = dict(malformed, stand_down=False)
        calls = []

        def chat_json(messages, **kwargs):
            calls.append(messages)
            return malformed if len(calls) == 1 else repaired

        runtime = object.__new__(AgentRuntime)
        runtime.world = world
        runtime.s = SimpleNamespace(symbols=["XAUUSD"])
        runtime.llm = SimpleNamespace(chat_json=chat_json)
        runtime._phase = lambda *args: None
        runtime._sys = lambda *args: self.fail("repaired brief should not trigger an error notification")
        runtime.bus = SimpleNamespace(emit=lambda *args, **kwargs: None)
        runtime.note = lambda *args, **kwargs: None
        runtime.stand_down_until = 0.0

        runtime._maybe_world()

        self.assertEqual(len(calls), 2)
        self.assertIn("stand_down", calls[1][-1]["content"])
        self.assertIs(world.brief["stand_down"], False)
        self.assertEqual(world.digest_error, "")

    def test_world_llm_failure_sets_agent_backoff_and_skips_follow_on_llm_calls(self):
        world = WorldIntel()
        world.ingest({"headline": "market update"})
        world.last_fetch = time.time()
        runtime = object.__new__(AgentRuntime)
        runtime.world = world
        runtime.s = SimpleNamespace(symbols=["EURUSD"], int=lambda _key: 30)
        runtime.llm = SimpleNamespace(
            configured=True,
            active_provider=lambda: "openrouter",
            chat_json=lambda *args, **kwargs: (_ for _ in ()).throw(
                llmmod.LLMError("model returned an empty reply", status=502)
            ),
        )
        runtime._phase = lambda *args: None
        runtime._sys = lambda *args: None
        runtime.bus = SimpleNamespace(emit=lambda *args, **kwargs: None)
        runtime._review_one_trade = lambda _obs: self.fail("review should be skipped after LLM failure")
        runtime._maybe_meta_review = lambda: self.fail("meta review should be skipped after LLM failure")
        runtime._locked = lambda fn, *args: {"positions": [], "pending": [], "snaps": {}}
        runtime._expire_proposals = lambda: None
        runtime.last_obs = None
        runtime.backoff_until = 0.0
        runtime.cycle = 0
        runtime.paused = False
        runtime.broker = SimpleNamespace(name="paper", advance=lambda _speed: None)
        runtime.j = SimpleNamespace(equity_add=lambda *args: None)

        runtime.run_cycle()

        self.assertGreater(runtime.backoff_until, time.time())
        self.assertIn("empty reply", world.digest_error)

    def test_runtime_rejects_schema_template_as_failed_digest(self):
        world = WorldIntel()
        world.ingest({"headline": "market update"})
        world.last_fetch = time.time()
        template = {
            "summary": "3-5 sentences",
            "themes": [{
                "theme": "",
                "assets": ["SYMBOL or asset class"],
                "bias": "risk_on|risk_off|bullish|bearish|volatile|neutral",
                "urgency": "low|medium|high",
                "why": "",
            }],
            "event_risk": [{"what": "", "when": "", "assets": [""]}],
            "stand_down": False,
        }
        runtime = object.__new__(AgentRuntime)
        runtime.world = world
        runtime.s = SimpleNamespace(symbols=["EURUSD"])
        runtime.llm = SimpleNamespace(chat_json=lambda *args, **kwargs: template)
        runtime._phase = lambda *args: None
        runtime._sys = lambda *args: None
        runtime.bus = SimpleNamespace(emit=lambda *args, **kwargs: None)

        runtime._maybe_world()

        self.assertIn("placeholder", world.digest_error)
        self.assertEqual(world.digested_ts, 0.0)
        self.assertIsNone(world.brief)
        self.assertFalse(world.due())


if __name__ == "__main__":
    unittest.main()
