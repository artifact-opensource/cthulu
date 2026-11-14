"""Runtime settings. Everything lives in environment variables (mirrored to .env), so
changes made from the dashboard or chat take effect immediately, no restart needed."""
from __future__ import annotations

import os
from typing import Any, Dict, Tuple

# key -> (type, min, max, default, label). Hard caps live here: neither chat nor the LLM can exceed them.
TUNABLES: Dict[str, Tuple[Any, ...]] = {
    "AGENT_AUTONOMY": ("choice", ["observe", "approval", "autonomous"], None, "autonomous", "How much the agent may do on its own"),
    "AGENT_SYMBOLS": ("str", None, None, "XAUUSD,EURUSD,BTCUSD", "Symbols to watch (comma separated)"),
    "AGENT_TIMEFRAME": ("choice", ["M1", "M5", "M15", "M30", "H1", "H4"], None, "M15", "Primary decision timeframe"),
    "AGENT_SYMBOL_SCAN_LIMIT": ("int", 1, 100, 25, "Maximum symbols to include in one reasoning pass when scanning the broker universe"),
    "AGENT_SYMBOL_MAX_SPREAD_PCT": ("float", 0.0001, 0.05, 0.0025, "Maximum quoted spread as a fraction of mid-price for dynamic symbol discovery"),
    "AGENT_PROFILE": ("choice", ["conservative", "balanced", "aggressive", "ultra_aggressive", "hft"], None, "balanced", "Agent risk and decision profile"),
    "AGENT_OBJECTIVE": ("str", None, None, "Grow through positive risk-adjusted returns; prioritize confirmed momentum and scale only validated winners.", "Editable objective that guides planning and reasoning"),
    "AGENT_STRATEGY_PROFILE": ("choice", ["adaptive", "trend_following", "mean_reversion", "momentum_breakout", "scalping", "liquidity_sweep"], None, "adaptive", "Agentic strategy reasoning profile"),
    "AGENT_ENTRY_MODE": ("choice", ["adaptive", "market_only", "pending_only"], None, "adaptive", "Allowed Agentic entry order types"),
    "AGENT_CYCLE_SECONDS": ("int", 5, 600, 30, "Seconds between observation cycles"),
    "AGENT_MANAGE_INTERVAL": ("int", 20, 3600, 120, "Min seconds between reasoning passes while positions or orders are open"),
    "AGENT_IDLE_THINK_MINUTES": ("int", 1, 240, 15, "Max minutes between reasoning passes when flat"),
    "AGENT_MAX_THINKS_PER_HOUR": ("int", 1, 240, 20, "Cap on reasoning passes per hour (protects free-tier rate limits)"),
    "AGENT_PLAN_EVERY": ("int", 1, 100, 8, "Re-plan after this many reasoning passes"),
    "AGENT_MANAGE_FOREIGN": ("bool", None, None, "true", "Also manage positions and orders opened outside the agent"),
    "AGENT_EMERGENCY_SL": ("bool", None, None, "true", "Attach a protective stop to any position missing one"),
    "RISK_MAX_PER_TRADE_PCT": ("float", 0.05, 5.0, 2.0, "Hard cap on risk per trade (% of equity)"),
    "RISK_MAX_POSITIONS": ("int", 1, 10, 10, "Hard cap on simultaneous open positions (also constrained by account tier)"),
    "RISK_MAX_POSITIONS_PER_SYMBOL": ("int", 1, 10, 2, "Hard cap on positions and pending orders per symbol"),
    "RISK_MAX_PENDING": ("int", 0, 10, 10, "Hard cap on simultaneous pending orders (also constrained by account tier)"),
    "RISK_MAX_ACTIVE_ORDERS": ("int", 1, 100, 10, "Hard cap on combined open positions and pending orders"),
    "RISK_MAX_OPEN_RISK_PCT": ("float", 0.1, 20.0, 4.0, "Hard cap on combined open and pending risk (% of equity)"),
    "RISK_MIN_RR": ("float", 0.5, 5.0, 1.5, "Minimum reward to risk when a take profit is set"),
    "RISK_DAILY_LOSS_PCT": ("float", 0.0, 20.0, 4.0, "Stop opening trades after this daily loss (% of equity); 0 disables the daily stop"),
    "RISK_DRAWDOWN_HALT_PCT": ("float", 0.0, 60.0, 15.0, "Halt trading at this drawdown from peak equity (%); 0 disables the drawdown halt"),
    "RISK_MAX_ENTRY_ATR": ("float", 0.5, 20.0, 6.0, "Max distance of a pending entry from price, in ATR"),
    "RISK_MAX_SPREAD_ATR": ("float", 0.01, 1.0, 0.25, "Skip entries when spread exceeds this many ATR"),
    "PAPER_BALANCE": ("float", 10.0, 10_000_000.0, 1000.0, "Starting balance for the paper broker"),
    "PAPER_SPEED": ("int", 1, 60, 3, "Paper broker: 5 minute bars simulated per cycle"),
}

TIMEFRAMES = ["M1", "M5", "M15", "M30", "H1", "H4", "D1"]


def _coerce(key: str, raw: Any) -> str:
    spec = TUNABLES[key]
    kind, lo, hi = spec[0], spec[1], spec[2]
    if kind == "bool":
        s = str(raw).strip().lower()
        if s not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
            raise ValueError(f"{key} must be true or false")
        return "true" if s in ("true", "1", "yes", "on") else "false"
    if kind == "choice":
        s = str(raw).strip()
        if s not in lo:
            raise ValueError(f"{key} must be one of {', '.join(lo)}")
        return s
    if kind == "str":
        s = str(raw).strip()
        if not s or len(s) > 300:
            raise ValueError(f"{key} must be 1-300 characters")
        return s
    try:
        v = float(raw) if kind == "float" else int(float(raw))
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be a number")
    if v < lo or v > hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return str(v)


def validate_tunables(updates: Dict[str, Any]) -> Dict[str, str]:
    out = {}
    for k, v in updates.items():
        if k not in TUNABLES:
            raise ValueError(f"unknown setting: {k}")
        out[k] = _coerce(k, v)
    return out


class Settings:
    """Live view over os.environ (so .env edits and hot-swaps apply immediately)."""

    def raw(self, key: str) -> str:
        spec = TUNABLES.get(key)
        return os.environ.get(key) or (str(spec[3]) if spec else "")

    def str(self, key: str) -> str:
        return self.raw(key)

    def int(self, key: str) -> int:
        try:
            return int(float(self.raw(key)))
        except ValueError:
            return int(float(TUNABLES[key][3]))

    def float(self, key: str) -> float:
        try:
            return float(self.raw(key))
        except ValueError:
            return float(TUNABLES[key][3])

    def bool(self, key: str) -> bool:
        return self.raw(key).strip().lower() in ("1", "true", "yes", "on")

    @property
    def symbols(self):
        raw = self.raw("AGENT_SYMBOLS").strip()
        if raw == "*":
            return list(getattr(self, "_dynamic_symbols", []))
        return [s.strip() for s in raw.split(",") if s.strip()]

    def set_dynamic_symbols(self, symbols):
        self._dynamic_symbols = list(dict.fromkeys(str(s).strip() for s in symbols if str(s).strip()))

    @property
    def broker(self) -> str:
        return (os.environ.get("BROKER") or "paper").strip().lower()

    def tunables(self) -> Dict[str, Dict[str, Any]]:
        out = {}
        for k, spec in TUNABLES.items():
            out[k] = {"value": self.raw(k), "type": spec[0], "options": spec[1] if spec[0] == "choice" else None,
                      "min": spec[1] if spec[0] in ("int", "float") else None,
                      "max": spec[2] if spec[0] in ("int", "float") else None,
                      "default": str(spec[3]), "label": spec[4]}
        return out
