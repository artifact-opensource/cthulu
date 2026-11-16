import json
import os
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from cthulu_agent import envfile, llm as llmmod                      # noqa: E402
from cthulu_agent.app import App                                      # noqa: E402
from cthulu_agent.broker import MT5Broker, PaperBroker                # noqa: E402
from cthulu_agent.events import EventBus                               # noqa: E402
from cthulu_agent.journal import Journal                              # noqa: E402
from cthulu_agent.server import serve                                 # noqa: E402
from cthulu_agent.tests.fake_llm import FakeLLM                       # noqa: E402
from network_access import NetworkAccessError, resolve_bind_target    # noqa: E402

TMP = tempfile.mkdtemp()
ENV = os.path.join(TMP, ".env")
os.environ["CTHULU_ENV_FILE"] = ENV
os.environ["CTHULU_EXECUTION_MODE_FILE"] = ENV
os.environ["DASHBOARD_ACCESS_MODE"] = "loopback"
os.environ.pop("DASHBOARD_TOKEN", None)
Path(ENV).write_text("")
for k in list(os.environ):
    if k.endswith("_API_KEY") or k in ("LLM_PROVIDER", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_AI_GATEWAY_ID"):
        os.environ.pop(k)


def http(method, url, body=None, headers=None):
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


class LLMTests(unittest.TestCase):
    def setUp(self):
        self.f = FakeLLM()
        self.m = llmmod.LLMManager()

    def tearDown(self):
        self.f.close()

    def test_default_provider_is_cloudflare_agentic_model(self):
        saved = {
            k: os.environ.pop(k, None)
            for k in (
                "LLM_PROVIDER", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_BASE_URL",
                "CLOUDFLARE_MODEL", "CLOUDFLARE_AI_GATEWAY_ID",
            )
        }
        try:
            self.assertEqual(self.m.active_provider(), "cloudflare")
            c = self.m.provider_config("cloudflare")
            self.assertEqual(c["base_url"], "")
            self.assertEqual(c["model"], "@cf/ibm-granite/granite-4.0-h-micro")
        finally:
            os.environ.update({k: v for k, v in saved.items() if v is not None})

    def test_openai_style_chat_json_and_discovery_and_env_write(self):
        self.m.apply("openrouter", base_url=self.f.url, api_key="sk-or-test-1234", model="vendor/model-a:free", activate=True)
        env = envfile.read_env(Path(ENV))
        self.assertEqual(env["OPENROUTER_API_KEY"], "sk-or-test-1234")
        self.assertEqual(env["OPENROUTER_BASE_URL"], self.f.url)
        pub = self.m.public_config()
        self.assertTrue(pub["providers"]["openrouter"]["has_key"])
        self.assertNotIn("sk-or-test-1234", json.dumps(pub))
        models = self.m.discover("openrouter")
        ids = [x["id"] for x in models]
        self.assertIn("openrouter/free", ids)
        self.assertTrue(next(x for x in models if x["id"] == "vendor/model-a:free")["free"])
        out = self.m.chat_json([{"role": "user", "content": "PHASE: WORLD BRIEF"}])
        self.assertIn("summary", out)
        post = [c for c in self.f.calls if c[0] == "POST"][-1]
        self.assertEqual(post[3]["response_format"], {"type": "json_object"})
        self.assertEqual(post[3]["reasoning"], {"effort": "low"})
        self.assertEqual(post[2]["authorization"], "Bearer sk-or-test-1234")

    def test_anthropic_compat_and_hot_swap(self):
        self.m.apply("openrouter", base_url=self.f.url, api_key="k1", activate=True)
        self.m.apply("anthropic", base_url=self.f.url, api_key="sk-ant-xyz", model="claude-test-1")
        self.assertEqual(self.m.active_provider(), "openrouter")
        self.m.apply("anthropic", activate=True)                      # hot swap, no restart
        self.assertEqual(self.m.active_provider(), "anthropic")
        self.assertEqual([x["id"] for x in self.m.discover("anthropic")], ["claude-test-1"])
        out = self.m.chat_json([{"role": "system", "content": "s"}, {"role": "user", "content": "PHASE: WORLD BRIEF"}])
        self.assertIn("themes", out)
        post = [c for c in self.f.calls if c[0] == "POST"][-1]
        self.assertEqual(post[1], "/v1/messages")
        self.assertEqual(post[2]["x-api-key"], "sk-ant-xyz")
        self.assertEqual(post[2]["anthropic-version"], "2023-06-01")
        self.assertNotIn("response_format", post[3])
        self.m.apply("openrouter", activate=True)                     # and back

    def test_retry_on_429_then_success(self):
        f = FakeLLM(fail_first=1)
        try:
            c = llmmod.LLMClient("grok", f.url, "k", "grok-4")
            r = c.chat([{"role": "user", "content": "hi"}], retries=2)
            self.assertTrue(r.text)
        finally:
            f.close()

    def test_json_extraction(self):
        self.assertEqual(llmmod.extract_json('Sure!\n```json\n{"a": [1,2,],}\n```'), {"a": [1, 2]})
        self.assertEqual(llmmod.extract_json('x {"a": "}{"} y'), {"a": "}{"})
        with self.assertRaises(ValueError):
            llmmod.extract_json("no json here")

    def test_truncated_json_repair_uses_larger_budget_and_keeps_json_mode(self):
        client = llmmod.LLMClient("openrouter", self.f.url, "key", "test-model")
        first = llmmod.LLMResponse("{\"summary\":", "openrouter", "test-model", 0, finish_reason="length")
        repaired = llmmod.LLMResponse('{"summary":"ok"}', "openrouter", "test-model", 0)
        messages = [{"role": "user", "content": "summarize"}]

        with patch.object(client, "chat", side_effect=[first, repaired]) as chat:
            result, _ = client.chat_json(messages, max_tokens=1400)

        self.assertEqual(result, {"summary": "ok"})
        self.assertEqual(chat.call_args_list[0].kwargs["max_tokens"], 1400)
        self.assertEqual(chat.call_args_list[1].kwargs["max_tokens"], 2800)
        self.assertTrue(chat.call_args_list[1].kwargs["json_mode"])
        self.assertIn("truncated", chat.call_args_list[1].args[0][-1]["content"])

    def test_empty_json_reply_gets_one_larger_repair_attempt(self):
        client = llmmod.LLMClient("openrouter", self.f.url, "key", "test-model")
        empty = llmmod.LLMResponse("", "openrouter", "test-model", 0, tokens_out=1400, finish_reason="length")
        repaired = llmmod.LLMResponse('{"summary":"ok"}', "openrouter", "test-model", 0)
        messages = [{"role": "user", "content": "summarize"}]

        with patch.object(client, "chat", side_effect=[empty, repaired]) as chat:
            result, _ = client.chat_json(messages, max_tokens=1400)

        self.assertEqual(result, {"summary": "ok"})
        self.assertEqual(len(chat.call_args_list), 2)
        self.assertTrue(chat.call_args_list[0].kwargs["allow_empty"])
        self.assertEqual(chat.call_args_list[1].kwargs["max_tokens"], 2800)
        self.assertIn("used its token budget for reasoning", chat.call_args_list[1].args[0][-1]["content"])

    def test_empty_json_retry_error_includes_resolved_model_and_token_usage(self):
        client = llmmod.LLMClient("openrouter", self.f.url, "key", "openrouter/free")
        responses = [
            llmmod.LLMResponse("", "openrouter", "openrouter/free", 0, tokens_in=1800,
                               tokens_out=1400, finish_reason="length"),
            llmmod.LLMResponse("", "openrouter", "vendor/actual-free-model", 0, tokens_in=1900,
                               tokens_out=2800, finish_reason="length"),
            llmmod.LLMResponse("", "openrouter", "vendor/actual-free-model", 0, tokens_in=1900,
                               tokens_out=5600, finish_reason="length"),
            llmmod.LLMResponse("", "openrouter", "vendor/actual-free-model", 0, tokens_in=1900,
                               tokens_out=11200, finish_reason="length"),
        ]

        with patch.object(client, "chat", side_effect=responses) as chat:
            with self.assertRaises(llmmod.LLMError) as raised:
                client.chat_json([{"role": "user", "content": "summarize"}], max_tokens=1400)
        self.assertIn("model=vendor/actual-free-model", str(raised.exception))
        self.assertIn("input_tokens=1900, output_tokens=11200", str(raised.exception))
        self.assertEqual(
            [call.kwargs["max_tokens"] for call in chat.call_args_list],
            [1400, 2800, 5600, 11200],
        )

    def test_truncated_json_retries_with_a_larger_generation_budget(self):
        client = llmmod.LLMClient("openrouter", self.f.url, "key", "test-model")
        responses = [
            llmmod.LLMResponse('{"assessment":', "openrouter", "test-model", 0, finish_reason="length"),
            llmmod.LLMResponse("", "openrouter", "test-model", 0, tokens_out=2800, finish_reason="length"),
            llmmod.LLMResponse('{"assessment":"ok"}', "openrouter", "test-model", 0),
        ]

        with patch.object(client, "chat", side_effect=responses) as chat:
            result, _ = client.chat_json([{"role": "user", "content": "reason"}], max_tokens=1600)

        self.assertEqual(result, {"assessment": "ok"})
        self.assertEqual(
            [call.kwargs["max_tokens"] for call in chat.call_args_list],
            [1600, 3200, 6400],
        )

    def test_unsupported_openrouter_reasoning_effort_retries_without_parameter(self):
        client = llmmod.LLMClient("openrouter", self.f.url, "key", "test-model")
        success = {
            "model": "test-model",
            "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        with patch(
            "cthulu_agent.llm._http",
            side_effect=[
                (400, {"error": {"message": "reasoning.effort is not supported"}}, {}),
                (200, success, {}),
            ],
        ) as request:
            response = client._chat_once(
                [{"role": "user", "content": "Return JSON"}], 0.2, 100, 0, json_mode=True
            )

        self.assertEqual(response.text, '{"ok":true}')
        self.assertEqual(request.call_count, 2)
        first_body = request.call_args_list[0].args[3]
        retry_body = request.call_args_list[1].args[3]
        self.assertEqual(first_body["reasoning"], {"effort": "low"})
        self.assertNotIn("reasoning", retry_body)

    def test_empty_non_json_reply_is_not_retried_with_identical_request(self):
        client = llmmod.LLMClient("openrouter", self.f.url, "key", "test-model")
        empty = llmmod.LLMResponse("", "openrouter", "test-model", 0, finish_reason="content_filter")
        with patch.object(client, "_chat_once", return_value=empty) as request:
            with self.assertRaisesRegex(llmmod.LLMError, "empty reply"):
                client.chat([{"role": "user", "content": "hello"}])
        request.assert_called_once()

    def test_openrouter_reasoning_without_content_is_empty_but_keeps_finish_metadata(self):
        client = llmmod.LLMClient("openrouter", self.f.url, "key", "test-model")
        response_body = {
            "model": "test-model",
            "choices": [{
                "message": {"content": None, "reasoning": "internal reasoning only"},
                "finish_reason": "length",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1400},
        }
        with patch("cthulu_agent.llm._http", return_value=(200, response_body, {})):
            response = client._chat_once([], 0.2, 1400, 0)

        self.assertEqual(response.text, "")
        self.assertEqual(response.finish_reason, "length")
        self.assertEqual(response.tokens_out, 1400)

    def test_env_injection_rejected(self):
        with self.assertRaises(ValueError):
            self.m.apply("openai", api_key="abc\nLLM_PROVIDER=evil")


class DashboardNetworkTests(unittest.TestCase):
    def test_loopback_target(self):
        target = resolve_bind_target("loopback", 8765)
        self.assertEqual(target.host, "127.0.0.1")
        self.assertEqual(target.urls, ["http://127.0.0.1:8765/"])
        self.assertFalse(target.allowed_hosts)

    def test_lan_target_lists_only_private_ipv4_hosts(self):
        records = [
            (2, 1, 6, "", ("127.0.0.1", 0)),
            (2, 1, 6, "", ("169.254.1.2", 0)),
            (2, 1, 6, "", ("192.168.10.5", 0)),
        ]
        with patch("network_access.socket.getaddrinfo", return_value=records):
            target = resolve_bind_target("lan", 9000)
        self.assertEqual(target.host, "0.0.0.0")
        self.assertEqual(target.urls, ["http://192.168.10.5:9000/"])
        self.assertEqual(target.allowed_hosts, {"192.168.10.5"})

    def test_tailscale_target_uses_cli_address(self):
        with patch("network_access.shutil.which", return_value="tailscale"), \
                patch("network_access.subprocess.run", return_value=SimpleNamespace(stdout="100.64.0.12\n")) as run:
            target = resolve_bind_target("tailscale", 8765)
        self.assertEqual(target.host, "100.64.0.12")
        self.assertEqual(target.urls, ["http://100.64.0.12:8765/"])
        run.assert_called_once()

    def test_tailscale_target_fails_explicitly_when_cli_missing(self):
        with patch("network_access.shutil.which", return_value=None), patch("network_access.os.name", "posix"):
            with self.assertRaisesRegex(NetworkAccessError, "Tailscale CLI not found"):
                resolve_bind_target("tailscale", 8765)


class BrokerTests(unittest.TestCase):
    def test_mt5_stop_limit_orders_are_included_in_pending_exposure(self):
        broker = MT5Broker()
        broker.mt5 = SimpleNamespace(orders_get=lambda: [
            SimpleNamespace(ticket=1, symbol="BTCUSD", type=6, volume_current=0.1, price_open=65000,
                            sl=64000, tp=67000, time_setup=1, comment="", magic=1),
            SimpleNamespace(ticket=2, symbol="GOLD", type=7, volume_current=0.2, price_open=2600,
                            sl=2700, tp=2500, time_setup=1, comment="", magic=1),
        ])

        pending = broker.pending()

        self.assertEqual([order.kind for order in pending], ["buy_stop_limit", "sell_stop_limit"])


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = FakeLLM()
        cls.env = {"AGENT_SYMBOLS": "EURUSD", "AGENT_MANAGE_INTERVAL": "0", "AGENT_IDLE_THINK_MINUTES": "1", "AGENT_MAX_THINKS_PER_HOUR": "100000",
                   "AGENT_PLAN_EVERY": "3", "PAPER_SPEED": "6", "OPENROUTER_BASE_URL": cls.f.url, "OPENROUTER_API_KEY": "test", "LLM_PROVIDER": "openrouter",
                   "AGENT_AUTONOMY": "autonomous", "CTHULU_EXECUTION_MODE": "agentic",
                   "RISK_DRAWDOWN_HALT_PCT": "60", "RISK_DAILY_LOSS_PCT": "20",
                   "WORLD_NATIVE_ENABLED": "false"}
        os.environ.update(cls.env)
        cls.app = App(db_path=":memory:", env_path=ENV)
        cls.app.start_runtime(broker=PaperBroker(1000, seed=3), autostart=False)
        cls.rt = cls.app.runtime

    @classmethod
    def tearDownClass(cls):
        cls.f.close()

    def test_existing_system_journal_rows_are_purged_when_database_opens(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent.db"
            journal = Journal(path)
            system = journal.add("system", "Old error", "internal diagnostic")
            journal.discord_enqueue(system["id"], "internal diagnostic")
            journal.add("reason", "Keep this", "decision history")
            journal._db.close()

            cleaned = Journal(path)
            try:
                self.assertEqual(
                    cleaned._q("SELECT COUNT(*) AS count FROM journal WHERE lower(kind)='system'")[0]["count"],
                    0,
                )
                self.assertEqual(cleaned.entries(kind="system"), [])
                self.assertEqual(cleaned.entries(q="internal diagnostic"), [])
                self.assertEqual(cleaned.discord_pending(), [])
                self.assertEqual(cleaned.entries(kind="reason")[0]["title"], "Keep this")
            finally:
                cleaned._db.close()

    def test_system_notes_and_errors_are_notifications_only(self):
        runtime, journal, bus = self.rt, self.app.journal, self.app.bus
        before = journal._q("SELECT COUNT(*) AS count FROM journal")[0]["count"]
        isolated_bus = EventBus()
        runtime.bus = isolated_bus
        runtime.note("system", "Operational update", "details")
        runtime._sys("test-notification-only", "A test error")
        received = isolated_bus.recent()
        runtime.bus = bus

        self.assertEqual(
            journal._q("SELECT COUNT(*) AS count FROM journal")[0]["count"],
            before,
        )
        self.assertEqual([event["type"] for event in received], ["alert", "alert"])
        self.assertEqual(journal.entries(kind="system"), [])

    def test_full_loop_places_limit_fills_closes_and_learns(self):
        rt, j = self.rt, self.app.journal
        placed = filled = closed = False
        for i in range(600):
            rt.run_cycle()
            kinds = {e["kind"] for e in j.entries(limit=300)}
            if i == 0:
                self.assertIn("plan", kinds)
                self.assertIn("reason", kinds)
            t = j.trades(limit=50)
            placed = placed or any(x["kind"] == "buy_limit" for x in t)
            closed = any(x["status"] == "closed" for x in t)
            if closed and "reflection" in kinds:
                break
        self.assertTrue(placed, "agent should have rested a real limit order")
        self.assertTrue(closed, "a trade should have run to SL/TP on the paper broker")
        tr = j.trades(status="closed", limit=5)[0]
        self.assertIsNotNone(tr["pnl"])
        self.assertIsNotNone(tr["r_multiple"])
        sk = j.skill("liquidity_sweep_reversal")
        self.assertGreaterEqual(sk["uses"], 1)                       # outcome attributed to the cited skill
        for _ in range(4):                                           # let the review run
            rt.run_cycle()
        self.assertGreaterEqual(sk and j.skill("liquidity_sweep_reversal")["version"], 2)   # LLM edited the skill after review
        self.assertTrue(j.entries(kind="lesson", limit=5))
        self.assertTrue(j.todos("open"))
        self.assertGreater(len(j.equity_series()), 3)

    def test_legacy_execution_mode_blocks_agent_trade_actions(self):
        rt = self.rt
        obs = rt._locked(rt.observe)
        with patch("cthulu_agent.agent.get_execution_mode", return_value="legacy"):
            results, rejected = rt.execute(
                [{"type": "place_market", "symbol": "EURUSD", "side": "buy", "sl": 1.0, "tp": 2.0}],
                obs,
                source="agent",
            )
        self.assertFalse(results[0]["ok"])
        self.assertIn("execution mode is legacy", results[0]["detail"])
        self.assertFalse(rt.broker.positions())
        self.assertEqual(rejected[0]["fixable"], False)

    def test_agent_entry_mode_is_enforced_by_risk_engine(self):
        rt = self.rt
        obs = rt._locked(rt.observe)
        info = obs["infos"]["EURUSD"]
        action = {
            "type": "place_limit",
            "symbol": "EURUSD",
            "side": "buy",
            "entry": info.ask - 0.002,
            "sl": info.ask - 0.006,
            "tp": info.ask + 0.006,
        }
        with patch.dict(os.environ, {"AGENT_ENTRY_MODE": "market_only"}):
            results, rejected = rt.execute(rt._clean_actions([action]), obs, "agent")
        self.assertFalse(results[0]["ok"])
        self.assertIn("market_only", results[0]["detail"])
        self.assertFalse(rt.broker.pending())
        self.assertEqual(rejected[0]["fixable"], True)

    def test_context_contains_world_health_and_strategy_controls(self):
        rt = self.rt
        context = rt.context(rt._locked(rt.observe))
        self.assertIn("native_feeds", context["world_status"])
        self.assertIn("agent_strategy_profiles", context["strategy_controls"])
        self.assertIn("legacy_strategies", context["strategy_controls"])
        self.assertIn("legacy_mindsets", context["strategy_controls"])

    def test_configured_risk_caps_tighten_tier_limits(self):
        rt = self.rt
        obs = rt._locked(rt.observe)
        with patch.dict(os.environ, {
            "RISK_MAX_POSITIONS": "1",
            "RISK_MAX_POSITIONS_PER_SYMBOL": "1",
            "RISK_MAX_PENDING": "0",
            "RISK_MAX_OPEN_RISK_PCT": "0.5",
        }):
            summary = rt.risk.summary(obs["acct"], obs["positions"], obs["pending"], rt.broker)
        self.assertEqual(summary["max_positions"], 1)
        self.assertEqual(summary["max_positions_per_symbol"], 1)
        self.assertEqual(summary["max_pending"], 0)
        self.assertEqual(summary["max_open_risk_pct"], 0.5)

    def test_dynamic_universe_rotates_markets_but_keeps_account_exposure_complete(self):
        rt = self.rt
        ticket = rt.broker.place_market("BTCUSD", "buy", 0.01, 64000, 68000)["ticket"]
        try:
            with patch.dict(os.environ, {
                "AGENT_SYMBOLS": "*",
                "AGENT_SYMBOL_SCAN_LIMIT": "1",
                "AGENT_SYMBOL_MAX_SPREAD_PCT": "0.0025",
                "AGENT_PROFILE": "hft",
                "RISK_MAX_ACTIVE_ORDERS": "10",
            }), patch.object(rt.broker, "tradeable_symbols", return_value=["EURUSD", "BTCUSD"]):
                first = rt.observe()
                second = rt.observe()
                symbols = rt.s.symbols

            self.assertEqual(list(first["snaps"]), ["EURUSD"])
            self.assertEqual(list(second["snaps"]), ["BTCUSD"])
            self.assertEqual(symbols, ["EURUSD", "BTCUSD"])
            self.assertIn(ticket, [position.ticket for position in first["positions"]])
            self.assertEqual(first["risk"]["max_active_orders"], 10)
        finally:
            rt.broker.close_position(ticket)

    def test_daily_loss_halt_is_not_overwritten_by_drawdown_state(self):
        rt = self.rt
        drawdown_state = {
            "peak": 1000,
            "start": 1000,
            "drawdown_pct": 0,
            "dd_mult": 1,
            "halted": False,
            "growth_pct": 0,
        }
        with patch.object(rt.risk, "track_equity", return_value=drawdown_state), \
                patch.object(rt.risk, "daily_pnl", return_value=-100000):
            summary = rt.risk.summary(rt.broker.account(), [], [], rt.broker)

        self.assertTrue(summary["halted"])
        self.assertEqual(summary["halt_reason"], "daily loss limit reached")

    def test_daily_loss_baseline_excludes_older_closed_pnl_without_deleting_trades(self):
        rt = self.rt
        day_start = time.time() - (time.time() % 86400)
        reset_at = day_start + 100
        trades = [
            {"id": 1, "pnl": -50, "ts_close": day_start + 500},
            {"id": 2, "pnl": -7, "ts_close": day_start + 50},
        ]
        with patch("cthulu_agent.risk.time.time", return_value=day_start + 300), \
                patch.object(rt.risk.j, "kv_get", side_effect={
                    "risk_daily_loss_baseline_ts": reset_at,
                    "risk_daily_loss_baseline_trade_id": 1,
                    "risk_daily_loss_baseline_open_trade_ids": [],
                }.get), \
                patch.object(rt.risk.j, "trades", return_value=trades) as trade_query:
            daily_pnl = rt.risk.daily_pnl(None, [])

        self.assertEqual(daily_pnl, -7)
        trade_query.assert_called_once_with(status="closed", limit=300)

    def test_daily_loss_baseline_counts_new_and_previously_open_trades_by_id(self):
        rt = self.rt
        day_start = time.time() - (time.time() % 86400)
        reset_at = day_start + 100
        trades = [
            {"id": 1, "pnl": -100, "ts_close": day_start + 500},
            {"id": 2, "pnl": -50, "ts_close": day_start + 500},
            {"id": 3, "pnl": -7, "ts_close": day_start + 50},
        ]
        with patch("cthulu_agent.risk.time.time", return_value=day_start + 300), \
                patch.object(rt.risk.j, "kv_get", side_effect={
                    "risk_daily_loss_baseline_ts": reset_at,
                    "risk_daily_loss_baseline_trade_id": 2,
                    "risk_daily_loss_baseline_open_trade_ids": [2],
                }.get), \
                patch.object(rt.risk.j, "trades", return_value=trades):
            daily_pnl = rt.risk.daily_pnl(None, [])

        self.assertEqual(daily_pnl, -57)

    def test_reset_daily_loss_baseline_persists_timestamp(self):
        rt = self.rt
        with patch.object(rt.risk.j, "trade_baseline", return_value=(42, [40])), \
                patch("cthulu_agent.risk.time.time", return_value=12345.0), \
                patch.object(rt.risk.j, "kv_set") as kv_set:
            reset_at = rt.risk.reset_daily_loss_baseline()

        self.assertEqual(reset_at, 12345.0)
        self.assertEqual(kv_set.call_args_list, [
            call("risk_daily_loss_baseline_trade_id", 42),
            call("risk_daily_loss_baseline_open_trade_ids", [40]),
            call("risk_daily_loss_baseline_ts", 12345.0),
        ])

    def test_risk_engine_clamps_and_rejects(self):
        rt = self.rt
        obs = rt._locked(rt.observe)
        info = obs["infos"]["EURUSD"]
        bad = rt._clean_actions([{"type": "place_limit", "symbol": "EURUSD", "side": "buy", "entry": info.ask + 0.002, "sl": info.ask - 0.002, "tp": info.ask + 0.01}])
        res, rej = rt.execute(bad, obs, "agent")
        self.assertFalse(res[0]["ok"])
        self.assertIn("limit must sit below", res[0]["detail"])
        nosl = rt._clean_actions([{"type": "place_limit", "symbol": "EURUSD", "side": "buy", "entry": info.ask - 0.001}])
        res, _ = rt.execute(nosl, obs, "agent")
        self.assertIn("stop loss is required", res[0]["detail"])
        wrong = rt._clean_actions([{"type": "place_limit", "symbol": "XAUUSD", "side": "buy", "entry": 1, "sl": 0.5}])
        res, _ = rt.execute(wrong, obs, "agent")
        self.assertIn("not in the watchlist", res[0]["detail"])

    def test_risk_review_uses_submitted_tick_prices_and_gives_tp_boundary(self):
        rt = self.rt
        obs = rt._locked(rt.observe)
        info = obs["infos"]["EURUSD"]
        tick = info.tick_size
        entry = info.ask
        action = {
            "type": "place_market",
            "symbol": "EURUSD",
            "side": "buy",
            "sl": entry - 10.6 * tick,
            "tp": entry + 15.91 * tick,
        }

        result, rejected = rt.execute(rt._clean_actions([action]), obs, "agent")

        self.assertFalse(result[0]["ok"])
        self.assertIn("after broker tick-size rounding", result[0]["detail"])
        self.assertIn("TP must be at least", result[0]["detail"])
        self.assertIn("drop the trade", result[0]["detail"])
        self.assertTrue(rejected[0]["fixable"])
        self.assertFalse(rt.broker.positions())

    def test_cannot_widen_stops(self):
        rt = self.rt
        obs = rt._locked(rt.observe)
        info = obs["infos"]["EURUSD"]
        r = rt.broker.place_market("EURUSD", "buy", 0.01, info.ask - 0.003, info.ask + 0.006)
        obs = rt._locked(rt.observe)
        res, _ = rt.execute(rt._clean_actions([{"type": "modify_position", "ticket": r["ticket"], "sl": info.ask - 0.006}]), obs, "agent")
        self.assertFalse(res[0]["ok"])
        self.assertIn("tightened", res[0]["detail"])
        res, _ = rt.execute(rt._clean_actions([{"type": "modify_position", "ticket": r["ticket"], "sl": info.ask - 0.001}]), obs, "agent")
        self.assertTrue(res[0]["ok"])
        rt.broker.close_position(r["ticket"])

    def test_dynamic_sltp_protects_untracked_positions(self):
        rt = self.rt
        order = rt.broker.place_market("EURUSD", "buy", 0.01, 0.0, 0.0, comment="manual orphan")
        ticket = order["ticket"]
        try:
            self.assertFalse(any(t["ticket"] == ticket for t in rt.j.trades(status="open", limit=100)))
            obs = rt._locked(rt.observe)
            rt.housekeeping(obs)
            position = next(p for p in rt.broker.positions() if p.ticket == ticket)

            self.assertGreater(position.sl, 0.0)
            self.assertLess(position.sl, position.price_current)
            self.assertGreater(position.tp, position.price_current)
            self.assertFalse(any(t["ticket"] == ticket for t in rt.j.trades(status="open", limit=100)))
        finally:
            rt.broker.close_position(ticket)

    def test_observe_and_approval_modes(self):
        rt = self.rt
        obs = rt._locked(rt.observe)
        info = obs["infos"]["EURUSD"]
        a = rt._clean_actions([{"type": "place_limit", "symbol": "EURUSD", "side": "buy", "entry": info.ask - 0.0005, "sl": info.ask - 0.002, "tp": info.ask + 0.003,
                                "skills": ["liquidity_sweep_reversal"]}])
        n0 = len(rt.broker.pending())
        os.environ["AGENT_AUTONOMY"] = "observe"
        res, _ = rt.execute(a, obs, "agent")
        self.assertTrue(res[0]["ok"]); self.assertEqual(len(rt.broker.pending()), n0)
        os.environ["AGENT_AUTONOMY"] = "approval"
        res, _ = rt.execute(a, obs, "agent")
        self.assertEqual(len(rt.broker.pending()), n0)
        self.assertEqual(len(rt.proposals), 1)
        pid = next(iter(rt.proposals))
        out = rt.decide(pid, True)
        self.assertTrue(out["ok"], out)
        self.assertEqual(len(rt.broker.pending()), n0 + 1)
        os.environ["AGENT_AUTONOMY"] = "autonomous"
        rt.flatten("test")

    def test_operator_close_and_cancel_buttons(self):
        rt = self.rt
        obs = rt._locked(rt.observe)
        info = obs["infos"]["EURUSD"]
        os.environ["AGENT_AUTONOMY"] = "autonomous"
        o = rt.broker.place_pending("EURUSD", "buy_limit", 0.01, info.ask - 0.002, info.ask - 0.004, info.ask + 0.004)
        p = rt.broker.place_market("EURUSD", "sell", 0.01, info.bid + 0.003, info.bid - 0.006)
        self.assertTrue(rt.operator_order(o["ticket"], "cancel")["ok"])
        self.assertNotIn(o["ticket"], [x.ticket for x in rt.broker.pending()])
        self.assertTrue(rt.operator_order(p["ticket"], "close")["ok"])
        self.assertNotIn(p["ticket"], [x.ticket for x in rt.broker.positions()])
        with self.assertRaises(Exception):
            rt.operator_order(999999, "close")

    def test_chat_adjusts_settings_within_hard_limits(self):
        rt = self.rt
        r = rt.chat("please tighten risk")
        self.assertTrue(r["actions"][0]["ok"])
        self.assertEqual(os.environ["RISK_MAX_PER_TRADE_PCT"], "0.5")
        self.assertEqual(envfile.read_env(Path(ENV))["RISK_MAX_PER_TRADE_PCT"], "0.5")
        r = rt.chat("max risk 50")
        self.assertFalse(r["actions"][0]["ok"])                       # exceeds the hard cap of 5
        self.assertEqual(os.environ["RISK_MAX_PER_TRADE_PCT"], "0.5")
        r = rt.chat("/todo check the sweep stats")
        self.assertTrue(any(t["title"] == "check the sweep stats" for t in self.app.journal.todos("open")))
        os.environ.pop("RISK_MAX_PER_TRADE_PCT", None)

    def test_llm_failure_backs_off_without_crashing(self):
        rt = self.rt
        saved = os.environ["OPENROUTER_BASE_URL"]
        os.environ["OPENROUTER_BASE_URL"] = "http://127.0.0.1:1"      # nothing listens here
        rt.force_think = "test"
        rt.run_cycle()
        self.assertGreater(rt.backoff_until, time.time())
        self.assertEqual(rt.phase, "waiting")
        os.environ["OPENROUTER_BASE_URL"] = saved
        rt.backoff_until = 0


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = FakeLLM()
        os.environ.update({"AGENT_SYMBOLS": "EURUSD", "OPENROUTER_BASE_URL": cls.f.url, "OPENROUTER_API_KEY": "test",
                           "LLM_PROVIDER": "openrouter", "WORLD_NATIVE_ENABLED": "false",
                           "CTHULU_EXECUTION_MODE": "agentic"})
        cls.app = App(db_path=":memory:", env_path=ENV)
        cls.app.start_runtime(broker=PaperBroker(1000, seed=5), autostart=False)
        cls.app.runtime.run_cycle()
        cls.srv, _ = serve(cls.app, "127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close(); cls.f.close()

    def test_state_and_config_never_leak_keys(self):
        c, st = http("GET", self.base + "/api/state")
        self.assertEqual(c, 200)
        self.assertIn("account", st)
        c, cfg = http("GET", self.base + "/api/config")
        self.assertNotIn('"test"', json.dumps(cfg).replace('"test": ', ''))
        self.assertTrue(cfg["llm"]["providers"]["openrouter"]["has_key"])
        self.assertEqual(cfg["llm"]["active"], "openrouter")

    def test_dashboard_system_controls_queue_safe_scripts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / ".cthulu.killswitch"
            with patch("cthulu_agent.server.KILLSWITCH_FILE", marker), \
                    patch("cthulu_agent.server._schedule_system_script") as schedule:
                status, result = http("POST", self.base + "/api/system/kill", {})
                self.assertEqual(status, 200)
                self.assertTrue(result["kill_switch_active"])
                self.assertTrue(marker.is_file())
                schedule.assert_called_once_with("cthulu_killswitch.ps1")

                schedule.reset_mock()
                status, result = http("POST", self.base + "/api/system/restart", {})
                self.assertEqual(status, 200)
                self.assertTrue(result["restart_queued"])
                schedule.assert_called_once_with("cthulu_restart.ps1")

    def test_config_write_and_discovery_via_api(self):
        c, out = http("POST", self.base + "/api/config/llm", {"provider": "grok", "base_url": self.f.url, "api_key": "xai-abcdefgh", "model": "grok-test", "activate": False})
        self.assertEqual(c, 200)
        self.assertEqual(envfile.read_env(Path(ENV))["XAI_API_KEY"], "xai-abcdefgh")
        self.assertEqual(out["llm"]["providers"]["grok"]["key_hint"], "…efgh")
        c, m = http("POST", self.base + "/api/models/discover", {"provider": "grok"})
        self.assertEqual(c, 200); self.assertIn("vendor/model-a:free", [x["id"] for x in m["models"]])
        c, t = http("POST", self.base + "/api/llm/test", {"provider": "grok"})
        self.assertTrue(t["ok"])
        c, e = http("POST", self.base + "/api/config/agent", {"RISK_MAX_PER_TRADE_PCT": 99})
        self.assertEqual(c, 400)

    def test_execution_mode_switch_requires_flat_only_when_disabling_agent(self):
        with patch.object(self.app.runtime.broker, "positions", return_value=[]), \
                patch.object(self.app.runtime.broker, "pending", return_value=[object()]):
            c, result = http("POST", self.base + "/api/config/execution", {"mode": "legacy"})
        self.assertEqual(c, 409)
        self.assertIn("Flatten all positions", result["error"])

        with patch.object(self.app.runtime.broker, "positions", return_value=[]), \
                patch.object(self.app.runtime.broker, "pending", return_value=[]):
            c, result = http("POST", self.base + "/api/config/execution", {"mode": "legacy"})
        self.assertEqual(c, 200)
        self.assertEqual(result["execution_mode"]["mode"], "legacy")
        with patch.object(self.app.runtime.broker, "positions", return_value=[object()]), \
                patch.object(self.app.runtime.broker, "pending", return_value=[]):
            c, result = http("POST", self.base + "/api/config/execution", {"mode": "agentic"})
        self.assertEqual(c, 200)
        self.assertEqual(result["execution_mode"]["mode"], "agentic")
        self.assertEqual(envfile.read_env(Path(ENV))["CTHULU_EXECUTION_MODE"], "agentic")

    def test_network_mode_persists_and_generates_remote_token_once(self):
        try:
            c, result = http("POST", self.base + "/api/config/network", {"mode": "lan"})
            self.assertEqual(c, 200)
            self.assertTrue(result["restart_required"])
            self.assertEqual(result["network"]["mode"], "lan")
            token = result.get("token_once")
            self.assertTrue(token)
            self.assertEqual(envfile.read_env(Path(ENV))["DASHBOARD_TOKEN"], token)
            self.assertEqual(envfile.read_env(Path(ENV))["DASHBOARD_ACCESS_MODE"], "lan")

            c, result = http("POST", self.base + "/api/config/network", {"mode": "tailscale"})
            self.assertEqual(c, 200)
            self.assertEqual(result["network"]["mode"], "tailscale")
            self.assertNotIn("token_once", result)

            c, result = http("POST", self.base + "/api/config/network", {"mode": "public"})
            self.assertEqual(c, 400)
        finally:
            envfile.set_env({"DASHBOARD_ACCESS_MODE": "loopback", "DASHBOARD_TOKEN": None}, Path(ENV))

    def test_security(self):
        c, _ = http("GET", self.base + "/api/state", headers={"Host": "evil.example.com"})
        self.assertEqual(c, 403)                                       # DNS rebinding guard
        req = urllib.request.Request(self.base + "/api/control", data=b'{"action":"pause"}', method="POST", headers={"Content-Type": "text/plain"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 415)                       # simple cross-site POST rejected
        c, _ = http("POST", self.base + "/api/control", {"action": "pause"}, headers={"Origin": "http://evil.example.com"})
        self.assertEqual(c, 403)
        with self.assertRaises(SystemExit):
            serve(self.app, "0.0.0.0", 0, token="")                    # non-loopback requires a token

    def test_remote_api_requires_token_but_serves_frontend(self):
        srv, _ = serve(self.app, "127.0.0.1", 0, token="remote-test-token")
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            c, _ = http("GET", base + "/api/state")
            self.assertEqual(c, 401)
            c, state = http("GET", base + "/api/state", headers={"Authorization": "Bearer remote-test-token"})
            self.assertEqual(c, 200)
            self.assertIn("status", state)
            with urllib.request.urlopen(base + "/", timeout=5) as response:
                self.assertEqual(response.status, 200)
        finally:
            srv.shutdown()
            srv.server_close()

    def test_todos_journal_playbook_chat_world(self):
        c, t = http("POST", self.base + "/api/todos", {"title": "check spreads at open", "priority": 1}); self.assertEqual(c, 200)
        c, t2 = http("PATCH", self.base + f"/api/todos/{t['todo']['id']}", {"status": "done"}); self.assertEqual(t2["todo"]["status"], "done")
        c, j = http("GET", self.base + "/api/journal?q=spreads"); self.assertEqual(c, 200)
        c, p = http("GET", self.base + "/api/playbook"); self.assertGreaterEqual(len(p["skills"]), 7)
        c, p = http("POST", self.base + "/api/playbook", {"name": "my skill", "body": "do the thing", "kind": "rule"}); self.assertEqual(p["skill"]["name"], "my_skill")
        c, ch = http("POST", self.base + "/api/chat", {"text": "how are we doing?"}); self.assertIn("reply", ch)
        c, w = http("POST", self.base + "/api/world/ingest", {"headlines": ["x"] * 3}); self.assertTrue(w["ok"])
        self.app.runtime.run_cycle()
        c, w = http("GET", self.base + "/api/world"); self.assertTrue(w["brief"])
        self.assertEqual(self.app.runtime.state()["world"]["summary"], "Risk appetite remains steady across the currently available market feeds.")
        c, config = http("GET", self.base + "/api/config")
        self.assertIn("fred_dcoilwtico", config["world"]["native_feeds"])
        self.assertIn("sma_crossover", config["strategy_catalog"]["legacy_strategies"])
        self.assertIn("liquidity_sweep", config["strategy_catalog"]["agent_profiles"])
        self.assertEqual(config["strategy_catalog"]["legacy_aliases"]["mindsets"]["ultra"], "ultra_aggressive")
        self.assertFalse(config["world"]["native_enabled"])
        c, config = http("POST", self.base + "/api/config/world", {"native_enabled": True})
        self.assertEqual(c, 200); self.assertTrue(config["world"]["native_enabled"])
        c, _ = http("POST", self.base + "/api/config/world", {"native_enabled": "true"})
        self.assertEqual(c, 400)
        http("POST", self.base + "/api/config/world", {"native_enabled": False})

    def test_journal_api_never_exposes_system_entries(self):
        self.app.journal.add("system", "Old error", "internal diagnostic")
        self.app.journal.add("reason", "Normal reasoning", "keep this")

        for query in ("", "?kind=system", "?q=internal"):
            status, result = http("GET", self.base + "/api/journal" + query)
            self.assertEqual(status, 200)
            self.assertFalse(any(entry["kind"] == "system" for entry in result["entries"]))
            self.assertFalse(any(entry["title"] == "Old error" for entry in result["entries"]))

    def test_world_dashboard_config_omits_raw_error_details(self):
        self.app.world.native_feeds["fred_dcoilwtico"] = {
            "status": "error",
            "fetched_at": 0,
            "data": None,
            "error": "private transport diagnostic",
        }

        status, result = http("GET", self.base + "/api/config")

        self.assertEqual(status, 200)
        world = result["world"]
        self.assertNotIn("last_error", world)
        self.assertNotIn("digest_error", world)
        self.assertNotIn("error", world["native_feeds"]["fred_dcoilwtico"])
        self.assertEqual(world["native_feeds"]["fred_dcoilwtico"]["status"], "unavailable")

    def test_static_and_sse(self):
        with urllib.request.urlopen(self.base + "/") as r:
            body = r.read().decode()
            self.assertIn("Content-Security-Policy", dict(r.headers)); self.assertIn("<html", body.lower())
        r = urllib.request.urlopen(self.base + "/api/stream", timeout=5)
        self.assertEqual(r.headers["Content-Type"], "text/event-stream")
        self.app.bus.emit("alert", level="info", message="ping")
        buf = b""
        t0 = time.time()
        while b"ping" not in buf and time.time() - t0 < 4:
            buf += r.read1(2048) if hasattr(r, "read1") else r.read(64)
        self.assertIn(b"ping", buf)
        r.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
