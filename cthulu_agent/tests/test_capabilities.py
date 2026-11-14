import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cthulu_agent import application_control, prompts
from cthulu_agent.agent import AgentRuntime
from cthulu_agent.capabilities import LEGACY_MINDSETS, LEGACY_STRATEGIES, STRATEGY_PROFILES, capability_context
from cthulu_agent.settings import Settings, validate_tunables


class ApplicationControlTests(unittest.TestCase):
    def test_mt5_path_must_be_configured_and_be_a_terminal_executable(self):
        with patch.dict(os.environ, {"MT5_PATH": ""}):
            with self.assertRaisesRegex(application_control.ApplicationControlError, "not configured"):
                application_control.configured_mt5_path()

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "powershell.exe"
            path.touch()
            with patch.dict(os.environ, {"MT5_PATH": str(path)}):
                with self.assertRaisesRegex(application_control.ApplicationControlError, "terminal64.exe"):
                    application_control.configured_mt5_path()

    def test_launch_does_not_create_another_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "terminal64.exe"
            path.touch()
            with patch.dict(os.environ, {"MT5_PATH": str(path)}), \
                    patch.object(application_control, "_process_ids_for_path", return_value=[42]), \
                    patch.object(application_control.subprocess, "Popen") as popen:
                message = application_control.launch_mt5()
        self.assertIn("already running", message)
        popen.assert_not_called()

    def test_close_requires_explicit_operator_confirmation_and_pause(self):
        runtime = object.__new__(AgentRuntime)
        runtime.paused = False
        runtime.broker = SimpleNamespace(name="mt5")
        runtime.j = Mock()
        runtime.discord_journal = Mock()
        runtime.bus = Mock()
        runtime.cycle = 0

        result = runtime._slash("/app close mt5 confirm")

        self.assertIn("Pause the agent", result["reply"])
        self.assertFalse(result["actions"][0]["ok"])

    def test_elden_god_persona_does_not_claim_certainty_or_bypass_controls(self):
        self.assertIn("Elden God", prompts.SYSTEM_CORE)
        self.assertIn("Never let the Elden God persona imply omniscience", prompts.SYSTEM_CORE)
        self.assertIn("risk engine", prompts.SYSTEM_CORE)
        self.assertIn("primary objective is to grow the account through positive, risk-adjusted trading returns", prompts.SYSTEM_CORE)
        self.assertIn("Never overtrade, fabricate evidence, evade laws or broker rules", prompts.SYSTEM_CORE)
        self.assertIn("Hold when evidence does not support a positive risk-adjusted opportunity", prompts.SYSTEM_CORE)
        reason = prompts.reason_prompt({})[1]["content"]
        self.assertIn("best available risk-adjusted opportunity", reason)
        self.assertIn("evaluate each configured symbol for an executable pending-limit setup", reason)
        self.assertIn("return a place_limit action now", reason)
        self.assertIn("Sub-1-ATR displacement may qualify", reason)
        self.assertIn("never invent levels or force an order", reason)
        plan = prompts.plan_prompt({})[1]["content"]
        self.assertIn("do not make a fixed 1-ATR displacement a universal prerequisite", plan)

    def test_strategy_catalog_distinguishes_agent_profiles_from_legacy_capabilities(self):
        context = capability_context(Settings())
        self.assertIn("liquidity_sweep", context["agent_strategy_profiles"])
        self.assertIn("sma_crossover", context["legacy_strategies"])
        self.assertIn("high_frequency", context["legacy_mindsets"])
        self.assertIn("never executed by this agent", prompts.SYSTEM_CORE)
        self.assertIn("AGENT_ENTRY_MODE", prompts.SYSTEM_CORE)

    def test_strategy_and_entry_settings_are_validated(self):
        self.assertEqual(validate_tunables({
            "AGENT_STRATEGY_PROFILE": "mean_reversion",
            "AGENT_ENTRY_MODE": "pending_only",
            "RISK_MAX_POSITIONS": 2,
            "RISK_MAX_PENDING": 0,
        }), {
            "AGENT_STRATEGY_PROFILE": "mean_reversion",
            "AGENT_ENTRY_MODE": "pending_only",
            "RISK_MAX_POSITIONS": "2",
            "RISK_MAX_PENDING": "0",
        })
        with self.assertRaisesRegex(ValueError, "must be one of"):
            validate_tunables({"AGENT_ENTRY_MODE": "anything"})


if __name__ == "__main__":
    unittest.main()
