"""SQLite bridge exposing the latest Legacy analysis to the Agentic runtime."""
from __future__ import annotations

import json
import math
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional


def _db_path() -> Path:
    configured = os.environ.get("CTHULU_AGENT_BRIDGE_DB", "").strip()
    return Path(configured) if configured else Path(__file__).resolve().parent / "data" / "legacy_agent_bridge.sqlite"


def _plain(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return str(value)[:160]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k)[:80]: _plain(v, depth + 1) for k, v in list(value.items())[:60]}
    if isinstance(value, (list, tuple)):
        return [_plain(item, depth + 1) for item in value[:30]]
    if hasattr(value, "tolist"):
        try:
            array_value = value.tolist()
            return _plain(array_value[-1] if isinstance(array_value, list) and array_value else array_value, depth + 1)
        except (TypeError, ValueError):
            pass
    if hasattr(value, "item"):
        try:
            return _plain(value.item(), depth + 1)
        except (TypeError, ValueError):
            pass
    if hasattr(value, "to_dict"):
        try:
            return _plain(value.to_dict(), depth + 1)
        except (TypeError, ValueError):
            pass
    if hasattr(value, "__dict__"):
        return _plain(vars(value), depth + 1)
    return str(value)[:160]


def publish_legacy_context(
    symbol: str,
    timeframe: str,
    *,
    bar: Optional[Dict[str, Any]] = None,
    indicators: Optional[Dict[str, Any]] = None,
    signal: Any = None,
    regime: str = "unknown",
    strategy: str = "unknown",
    score: Optional[float] = None,
    rejection: str = "",
) -> None:
    """Atomically store one symbol's newest Legacy analysis snapshot."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "symbol": str(symbol),
        "timeframe": str(timeframe),
        "regime": str(regime),
        "strategy": str(strategy),
        "score": _plain(score),
        "bar": _plain(bar or {}),
        "indicators": _plain(indicators or {}),
        "signal": _plain(signal),
        "rejection": str(rejection)[:240],
    }
    with sqlite3.connect(path, timeout=5) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS legacy_context (
                   symbol TEXT PRIMARY KEY,
                   updated_at REAL NOT NULL,
                   payload TEXT NOT NULL
               )"""
        )
        conn.execute(
            """INSERT INTO legacy_context (symbol, updated_at, payload)
               VALUES (?, ?, ?)
               ON CONFLICT(symbol) DO UPDATE SET
                   updated_at=excluded.updated_at, payload=excluded.payload""",
            (str(symbol), time.time(), json.dumps(payload, ensure_ascii=True, separators=(",", ":"))),
        )


def latest_legacy_context(limit: int = 8) -> list:
    """Return recent Legacy snapshots, newest first; an absent DB means no data yet."""
    path = _db_path()
    if not path.is_file():
        return []
    with sqlite3.connect(path, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT updated_at, payload FROM legacy_context ORDER BY updated_at DESC LIMIT ?",
            (max(1, min(int(limit), 30)),),
        ).fetchall()
    return [
        {"updated_at": row["updated_at"], **json.loads(row["payload"])}
        for row in rows
    ]


def canonical_agent_symbol(symbol: str) -> str:
    """Translate common Legacy broker symbols to the Agent watchlist symbols."""
    normalized = "".join(char for char in str(symbol).upper() if char.isalnum())
    if normalized.startswith(("GOLD", "XAU")):
        return "XAUUSD"
    if normalized.startswith("BTCUSD"):
        return "BTCUSD"
    if normalized in {"WTI", "USOIL", "OILCASH"}:
        return "WTI"
    return str(symbol)
