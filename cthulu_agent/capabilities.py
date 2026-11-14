"""Verified strategy and execution capabilities exposed to the agent."""
from __future__ import annotations

from typing import Any, Dict

from .settings import Settings
from execution_mode import ExecutionModeError, get_execution_mode


AGENT_PROFILES = {
    "conservative": {
        "directive": "Require strong independent confirmation, prefer fewer trades, and preserve capital.",
        "risk_pct": 0.25,
        "open_risk_pct": 1.0,
        "active_orders": 2,
    },
    "balanced": {
        "directive": "Seek clear risk-adjusted opportunities with measured turnover and ordinary position management.",
        "risk_pct": 0.5,
        "open_risk_pct": 2.5,
        "active_orders": 4,
    },
    "aggressive": {
        "directive": "Actively seek corroborated opportunities and accept moderate uncertainty without relaxing hard risk controls.",
        "risk_pct": 0.75,
        "open_risk_pct": 3.5,
        "active_orders": 6,
    },
    "ultra_aggressive": {
        "directive": "Evaluate opportunities proactively and manage them tightly; never trade solely to increase activity.",
        "risk_pct": 1.0,
        "open_risk_pct": 4.0,
        "active_orders": 8,
    },
    "hft": {
        "directive": "Scan the broker universe on M1 for short-horizon momentum, evaluate setups eagerly, and manage entries/exits quickly. Never invent signals, chase price, or raise risk to recover losses; every entry still needs a protective stop and must fit the active-order and aggregate-risk caps.",
        "risk_pct": 1.0,
        "open_risk_pct": 5.0,
        "active_orders": 10,
    },
}

STRATEGY_PROFILES: Dict[str, str] = {
    "adaptive": "Adapt to the observed regime; actively test both reversal and continuation entries, accept corroborated sub-1-ATR setups, and never force a trade.",
    "trend_following": "Prioritize established trend direction, higher-timeframe alignment, and pullback entries; avoid fading strong trends.",
    "mean_reversion": "Prioritize stretched moves back toward value and range boundaries; avoid fading a confirmed breakout.",
    "momentum_breakout": "Prioritize volatility expansion, range breaks, and follow-through; avoid entering before confirmation.",
    "scalping": "Prioritize near-term structure and spread-aware, short-horizon opportunities; skip setups whose costs or noise overwhelm the edge.",
    "liquidity_sweep": "Prioritize raids of visible highs/lows followed by reclaim and corroborating displacement; sub-1-ATR moves can qualify with independent confirmation, and resting retest entries are preferred.",
}

LEGACY_STRATEGIES: Dict[str, str] = {
    "sma_crossover": "Simple moving-average crossover strategy.",
    "ema_crossover": "Exponential moving-average crossover strategy.",
    "scalping": "Short-horizon scalping strategy.",
    "momentum_breakout": "Indicator-aligned momentum breakout strategy.",
    "mean_reversion": "Range and mean-reversion strategy.",
    "trend_following": "Trend continuation strategy.",
    "rsi_reversal": "RSI reversal strategy.",
}

LEGACY_MINDSETS: Dict[str, str] = {
    "conservative": "Legacy risk preset focused on capital preservation and stricter filters.",
    "balanced": "Legacy preset with moderate risk and reward settings.",
    "aggressive": "Legacy preset with faster signals and higher risk tolerance.",
    "ultra_aggressive": "Legacy high-risk preset.",
    "high_frequency": "Legacy high-frequency preset.",
}

LEGACY_ALIASES = {
    "strategies": {"momentum": "momentum_breakout"},
    "mindsets": {"ultra": "ultra_aggressive", "high-frequency": "high_frequency"},
}


def capability_context(settings: Settings) -> Dict[str, Any]:
    """Describe selectable agent behavior without implying legacy strategy execution."""
    profile = settings.str("AGENT_PROFILE")
    profile_config = AGENT_PROFILES.get(profile, AGENT_PROFILES["balanced"])
    return {
        "execution_owner": _execution_owner(),
        "agent_profile": profile,
        "agent_profile_directive": profile_config["directive"],
        "agent_profile_limits": {
            "per_entry_risk_pct_cap": min(profile_config["risk_pct"], settings.float("RISK_MAX_PER_TRADE_PCT")),
            "aggregate_open_risk_pct_cap": min(profile_config["open_risk_pct"], settings.float("RISK_MAX_OPEN_RISK_PCT")),
            "active_orders_cap": min(profile_config["active_orders"], settings.int("RISK_MAX_ACTIVE_ORDERS")),
        },
        "agent_objective": settings.str("AGENT_OBJECTIVE"),
        "symbol_universe": "all broker-tradable symbols" if settings.raw("AGENT_SYMBOLS").strip() == "*" else settings.symbols,
        "agent_strategy_profile": settings.str("AGENT_STRATEGY_PROFILE"),
        "agent_strategy_profiles": STRATEGY_PROFILES,
        "entry_mode": settings.str("AGENT_ENTRY_MODE"),
        "legacy_strategies": LEGACY_STRATEGIES,
        "legacy_mindsets": LEGACY_MINDSETS,
        "legacy_aliases": LEGACY_ALIASES,
        "legacy_boundary": (
            "Legacy strategies and mindsets are catalogued for operator awareness only. "
            "The Agentic runtime does not execute those legacy classes or apply their risk presets. "
            "The Legacy engine continues to run its configured strategies in both execution modes."
        ),
    }


def _execution_owner() -> str:
    try:
        mode = get_execution_mode()
    except ExecutionModeError as exc:
        return f"execution owner unavailable; trading is blocked ({exc})"
    return "Legacy + Agentic hybrid: both loops run; agent may manage shared-account trades" if mode == "agentic" else "Legacy-only: agent trade actions are blocked"


def system_notes() -> str:
    profile_lines = "\n".join(f"- {name}: {description}" for name, description in STRATEGY_PROFILES.items())
    legacy_lines = "\n".join(f"- {name}: {description}" for name, description in LEGACY_STRATEGIES.items())
    mindset_lines = "\n".join(f"- {name}: {description}" for name, description in LEGACY_MINDSETS.items())
    return f"""Capability and execution boundaries:
- Your selected Agentic strategy profile is a prompt-level decision preference, not a separately running legacy strategy implementation. Follow it when choosing and explaining analysis, without forcing a trade.
- AGENT_ENTRY_MODE is enforced by the risk engine: adaptive permits market and pending entries; market_only rejects pending entries; pending_only rejects market entries.
- Strategy profiles: {profile_lines}
- Legacy-only strategies (never executed by this agent): {legacy_lines}
- Legacy-only risk mindsets (never copied into the agent's risk limits): {mindset_lines}
- Legacy aliases: momentum → momentum_breakout; ultra → ultra_aggressive; high-frequency → high_frequency.
- The shared execution-mode switch is authoritative. Legacy runs in both modes. Agentic mode adds agent entries and management on top of Legacy; Legacy-only mode blocks agent trade actions. Switching to Legacy-only requires a flat account.
- Agent entries always pass the hard risk engine. Configured per-entry and aggregate-risk caps, active-order limits, stop-loss requirements, reward/risk rules, and autonomy checks cannot be overridden by a strategy profile."""
