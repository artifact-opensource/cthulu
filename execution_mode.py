"""Shared execution mode for Legacy-only and parallel Agentic+Legacy operation."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

MODE_KEY = "CTHULU_EXECUTION_MODE"
VALID_MODES = ("legacy", "agentic")
KILLSWITCH_FILE = Path(__file__).resolve().parent / ".cthulu.killswitch"


class ExecutionModeError(RuntimeError):
    pass


def require_trading_enabled() -> None:
    """Block every trading entry point while the persistent kill switch is active."""
    if KILLSWITCH_FILE.exists():
        raise ExecutionModeError(
            f"Trading is disabled by the kill switch at {KILLSWITCH_FILE}. "
            "Use the launcher to explicitly resume."
        )


def execution_mode_path(env_path: Optional[Path] = None) -> Path:
    """Return the shared mode file, independent of component-specific .env files."""
    configured = os.environ.get("CTHULU_EXECUTION_MODE_FILE")
    return Path(env_path or configured or Path(__file__).resolve().parent / ".env")


def get_execution_mode(env_path: Optional[Path] = None) -> str:
    path = execution_mode_path(env_path)
    value = None
    try:
        if path.is_file():
            for line in path.read_text(encoding="utf-8-sig").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, raw = stripped.split("=", 1)
                    if key.strip() == MODE_KEY:
                        value = raw.strip().strip("\"'").lower()
    except OSError as exc:
        raise ExecutionModeError(f"Could not read the execution-mode setting from {path}: {exc}") from exc

    if value is None:
        value = os.environ.get(MODE_KEY, "legacy").strip().lower()
    if value not in VALID_MODES:
        raise ExecutionModeError(f"{MODE_KEY} must be one of: {', '.join(VALID_MODES)}")
    return value


def require_legacy_execution() -> None:
    mode = get_execution_mode()
    if not legacy_execution_enabled(mode):
        raise ExecutionModeError(f"Legacy execution is disabled while execution mode is {mode}.")


def legacy_execution_enabled(mode: Optional[str] = None) -> bool:
    """Legacy remains active in both Legacy-only and Agentic hybrid modes."""
    return (mode or get_execution_mode()) in VALID_MODES


def agent_execution_enabled(mode: Optional[str] = None) -> bool:
    """The agent may trade/manage only in the parallel Agentic hybrid mode."""
    return (mode or get_execution_mode()) == "agentic"
