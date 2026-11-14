"""Durable, optional delivery of selected journal entries to a Discord webhook."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from .journal import Journal
from .market import SESSIONS_UTC

log = logging.getLogger("cthulu_agent")
WEBHOOK_ENV = "DISCORD_TRADING_JOURNAL_WEBHOOK_URL"
JOURNAL_THREAD_ENV = "DISCORD_TRADING_JOURNAL_THREAD_ID"
WORLD_THREAD_ENV = "DISCORD_WORLD_BRIEF_THREAD_ID"
WEBHOOK_PATH = re.compile(r"^/api/webhooks/\d+/[\w.-]+$")
THREAD_ID = re.compile(r"^[1-9]\d{0,19}$")
SESSION_PREP_MINUTES = 5
SCHEDULE_WINDOW_SECONDS = 90
SCHEDULE_POLL_SECONDS = 30


def _discord_error_text(body: bytes) -> str:
    try:
        payload = json.loads(body.decode("utf-8", "replace"))
    except (TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""
    parts = []
    if payload.get("code") is not None:
        parts.append(f"code {str(payload['code'])[:24]}")
    if payload.get("message"):
        parts.append(str(payload["message"])[:100])

    details = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            errors = value.get("_errors")
            if isinstance(errors, list):
                for item in errors:
                    if isinstance(item, dict) and item.get("message"):
                        details.append(str(item["message"])[:100])
            for key, child in value.items():
                if key != "_errors":
                    collect(child)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(payload.get("errors"))
    parts.extend(details[:2])
    return ": ".join(parts)[:180]


def _forum_thread_name(payload: Dict[str, Any]) -> str:
    embeds = payload.get("embeds")
    title = ""
    timestamp = ""
    if isinstance(embeds, list) and embeds and isinstance(embeds[0], dict):
        title = str(embeds[0].get("title") or "").strip()
        timestamp = str(embeds[0].get("timestamp") or "")
    try:
        date = time.strftime("%Y-%m-%d %H:%M UTC", time.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ"))
    except ValueError:
        date = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    return f"{date} · {title or 'Trading journal entry'}"[:100]


def _webhook_url() -> str:
    value = os.environ.get(WEBHOOK_ENV, "").strip()
    parsed = urllib.parse.urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme != "https"
        or parsed.hostname != "discord.com"
        or port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not WEBHOOK_PATH.fullmatch(parsed.path)
    ):
        return ""
    return value


def _chart_url(symbol: str) -> str:
    symbol = symbol.strip().upper().rstrip("#")
    aliases = {
        "BTCUSD": "COINBASE:BTCUSD",
        "GOLD": "OANDA:XAUUSD",
        "GOLDM": "OANDA:XAUUSD",
        "XAUUSD": "OANDA:XAUUSD",
        "WTI": "TVC:USOIL",
        "USOIL": "TVC:USOIL",
        "OILCASH": "TVC:USOIL",
    }
    chart_symbol = aliases.get(symbol, symbol)
    if re.fullmatch(r"[A-Z]{6}", chart_symbol):
        chart_symbol = f"OANDA:{chart_symbol}"
    return "https://www.tradingview.com/chart/?" + urllib.parse.urlencode({"symbol": chart_symbol})


def _message(entry: Dict[str, Any]) -> Dict[str, Any]:
    is_world = entry["kind"] == "world"
    label = "🌍 World Brief" if is_world else "🧠 Agent Journal"
    title = str(entry.get("title") or label).strip()
    description = str(entry.get("body") or "No additional notes were recorded.").strip()
    if len(description) > 3500:
        description = description[:3497].rstrip() + "..."
    fields = []
    symbol = str(entry.get("symbol") or "").strip()
    if symbol:
        fields.extend([
            {"name": "Instrument", "value": symbol[:128], "inline": True},
            {"name": "Chart", "value": f"[Open {symbol[:80]} chart ↗]({_chart_url(symbol)})", "inline": True},
        ])
    cycle = entry.get("cycle")
    if cycle:
        fields.append({"name": "Journal cycle", "value": str(cycle)[:100], "inline": True})

    timestamp = entry.get("ts")
    if not isinstance(timestamp, (int, float)):
        timestamp = time.time()
    timestamp_text = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp))
    embed = {
        "title": f"{label} · {title}"[:256],
        "description": description,
        "color": 0x2E9D8F if is_world else 0x6688CC,
        "fields": fields,
        "footer": {"text": "Cthulu Trading Journal · Ideas are not execution confirmations"},
        "timestamp": timestamp_text,
    }
    if symbol:
        embed["url"] = _chart_url(symbol)
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


def _scheduled_message(title: str, description: str, timestamp: float, color: int,
                       symbols: Tuple[str, ...] = ()) -> Dict[str, Any]:
    description = description.strip() or "No additional journal notes were recorded."
    if len(description) > 3500:
        description = description[:3497].rstrip() + "..."
    fields = []
    charts = list(dict.fromkeys(symbol.strip() for symbol in symbols if symbol.strip()))
    if charts:
        links = [f"[{symbol[:40]}]({_chart_url(symbol)})" for symbol in charts[:8]]
        fields.append({"name": "Charts", "value": " · ".join(links)[:1024], "inline": False})
    embed = {
        "title": title[:256],
        "description": description,
        "color": color,
        "fields": fields,
        "footer": {"text": "Cthulu Trading Journal · Ideas are not execution confirmations"},
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(timestamp)),
    }
    return {"embeds": [embed], "allowed_mentions": {"parse": []}}


def _post(url: str, payload: Dict[str, Any]) -> Tuple[bool, float, str]:
    payload = dict(payload)
    thread_id = payload.pop("_discord_thread_id", None)
    if thread_id is not None:
        if not isinstance(thread_id, str) or not THREAD_ID.fullmatch(thread_id):
            return False, 0.0, "invalid_thread_id"
        parts = urllib.parse.urlsplit(url)
        query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        query = [(key, value) for key, value in query if key != "thread_id"]
        query.append(("thread_id", thread_id))
        url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
    elif os.environ.get("DISCORD_TRADING_JOURNAL_FORUM_MODE", "").strip().lower() in ("1", "true", "yes", "on"):
        payload["thread_name"] = _forum_thread_name(payload)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Cthulu-Agent-Journal"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            if 200 <= response.status < 300:
                return True, 0.0, ""
            return False, 0.0, f"http_{response.status}"
    except urllib.error.HTTPError as error:
        if error.code == 429:
            retry_after = error.headers.get("Retry-After", "")
            try:
                delay = max(1.0, float(retry_after))
            except (TypeError, ValueError):
                delay = 60.0
        else:
            delay = 0.0
        detail = _discord_error_text(error.read(4096))
        return False, delay, f"http_{error.code}" + (f" ({detail})" if detail else "")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return False, 0.0, type(error).__name__


class DiscordJournalDelivery:
    def __init__(self, journal: Journal, world: Any = None, symbols: Tuple[str, ...] = ()):
        self.journal = journal
        self.world = world
        self.symbols = symbols
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._warned_invalid_url = False

    def enqueue(self, entry: Dict[str, Any]) -> None:
        """Keep journal writes local; scheduled Discord posts are queued separately."""
        return

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        configured_url = os.environ.get(WEBHOOK_ENV, "").strip()
        if not configured_url:
            log.warning("Discord journal delivery is not configured; set %s to a rotated webhook URL", WEBHOOK_ENV)
        elif not _webhook_url():
            log.warning("Discord journal delivery disabled: webhook URL is not a valid HTTPS Discord webhook")
            self._warned_invalid_url = True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="cthulu-discord-journal", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _enqueue_scheduled(self, schedule_type: int, scheduled_at: float,
                           payload: Dict[str, Any]) -> None:
        schedule_id = -(int(scheduled_at) * 10 + schedule_type)
        env_key = WORLD_THREAD_ENV if schedule_type == 1 else JOURNAL_THREAD_ENV
        thread_id = os.environ.get(env_key, "").strip()
        if thread_id:
            payload = {**payload, "_discord_thread_id": thread_id}
        self.journal.discord_enqueue(schedule_id, json.dumps(payload, ensure_ascii=False))
        self._wake.set()

    def _world_update(self, scheduled_at: float) -> None:
        brief = getattr(self.world, "brief", None)
        if not isinstance(brief, dict) or not str(brief.get("summary") or "").strip():
            return
        lines = [str(brief["summary"]).strip()]
        themes = brief.get("themes")
        theme_symbols = []
        if isinstance(themes, list):
            for theme in themes:
                if not isinstance(theme, dict):
                    continue
                title = str(theme.get("theme") or "").strip()
                why = str(theme.get("why") or "").strip()
                bias = str(theme.get("bias") or "neutral").strip()
                assets = theme.get("assets")
                if isinstance(assets, list):
                    asset_names = [str(asset).strip() for asset in assets if str(asset).strip()]
                    theme_symbols.extend(asset_names)
                else:
                    asset_names = []
                detail = f" — {why}" if why else ""
                asset_text = f" · {', '.join(asset_names[:4])}" if asset_names else ""
                if title:
                    lines.append(f"• **{title}** ({bias}{asset_text}){detail}")

        risks = brief.get("event_risk")
        if isinstance(risks, list) and risks:
            lines.append("\n**Event watch**")
            for event in risks:
                if isinstance(event, dict) and event.get("what"):
                    when = f" · {event['when']}" if event.get("when") else ""
                    lines.append(f"• {str(event['what']).strip()}{when}")
        if brief.get("stand_down") is True:
            lines.append("\n**Risk posture:** stand down from new entries.")
        brief_ts = brief.get("ts")
        if isinstance(brief_ts, (int, float)):
            lines.append(f"\nLatest brief: {time.strftime('%H:%M UTC', time.gmtime(brief_ts))}")
        symbols = tuple(dict.fromkeys((*self.symbols, *theme_symbols)))
        payload = _scheduled_message(
            "🌍 Hourly World Brief",
            "\n".join(lines),
            scheduled_at,
            0x2E9D8F,
            symbols,
        )
        self._enqueue_scheduled(1, scheduled_at, payload)

    def _session_update(self, name: str, stage: str, scheduled_at: float) -> None:
        display_name = name.replace("_", " ").title()
        if stage == "pre":
            title = f"📓 {display_name} · Pre-session journal"
            color = 0x6688CC
            interval = next((f"{start:02d}:00–{end:02d}:00 UTC"
                             for session, start, end in SESSIONS_UTC if session == name), "")
            heading = f"Session opens at {time.strftime('%H:%M UTC', time.gmtime(scheduled_at + SESSION_PREP_MINUTES * 60))}"
            if interval:
                heading += f" · {interval}"
        else:
            title = f"📓 {display_name} · Session close journal"
            color = 0x8B6BB8
            heading = f"Session closed at {time.strftime('%H:%M UTC', time.gmtime(scheduled_at))}"

        digest = self.journal.digest(
            n=8,
            kinds="reason,action,reflection,lesson,trade_close,plan",
        )
        body = heading + "\n\n" + (digest or "No recent journal activity is recorded.")
        payload = _scheduled_message(title, body, scheduled_at, color, self.symbols)
        self._enqueue_scheduled(2 if stage == "pre" else 3, scheduled_at, payload)

    def schedule_due(self, now: Optional[float] = None) -> None:
        """Queue Discord-only updates; this never triggers World or trading ingest."""
        if not _webhook_url():
            return
        current = time.time() if now is None else now
        hour = int(current // 3600) * 3600
        if 0 <= current - hour <= SCHEDULE_WINDOW_SECONDS:
            self._world_update(hour)

        today = datetime.fromtimestamp(current, timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for day_offset in (-1, 0, 1):
            day_start = (today.timestamp() + day_offset * 86400)
            for name, start, end in SESSIONS_UTC:
                if name == "off_hours":
                    continue
                opens_at = day_start + start * 3600
                closes_at = day_start + end * 3600
                prep_at = opens_at - SESSION_PREP_MINUTES * 60
                if 0 <= current - prep_at <= SCHEDULE_WINDOW_SECONDS:
                    self._session_update(name, "pre", prep_at)
                if 0 <= current - closes_at <= SCHEDULE_WINDOW_SECONDS:
                    self._session_update(name, "post", closes_at)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.schedule_due()
            url = _webhook_url()
            if not url:
                if os.environ.get(WEBHOOK_ENV, "").strip() and not self._warned_invalid_url:
                    log.warning("Discord journal delivery disabled: webhook URL is not a valid HTTPS Discord webhook")
                    self._warned_invalid_url = True
                self._wake.wait(timeout=SCHEDULE_POLL_SECONDS)
                self._wake.clear()
                continue
            self._warned_invalid_url = False
            pending = self.journal.discord_pending(limit=10)
            for item in pending:
                if self._stop.is_set():
                    break
                try:
                    payload = json.loads(item["content"])
                except (TypeError, ValueError):
                    payload = {"content": item["content"], "allowed_mentions": {"parse": []}}
                if not isinstance(payload, dict):
                    payload = {"content": item["content"], "allowed_mentions": {"parse": []}}
                delivered, retry_after, error = _post(url, payload)
                if delivered:
                    self.journal.discord_mark_delivered(item["journal_id"])
                    continue
                attempts = int(item["attempts"]) + 1
                if error == "invalid_thread_id" or error.startswith(("http_400", "http_401", "http_403", "http_404")):
                    self.journal.discord_mark_permanent_failure(
                        item["journal_id"], attempts, error or "permanent_delivery_failure"
                    )
                    log.error("Discord journal delivery stopped for rejected item (%s)", error)
                    continue
                delay = retry_after or min(3600.0, 30.0 * (2 ** min(attempts - 1, 7)))
                self.journal.discord_mark_failed(
                    item["journal_id"], attempts, delay, error or "delivery_failed"
                )
                log.warning("Discord journal delivery failed (%s); retry scheduled", error or "delivery_failed")
            self._wake.wait(timeout=5.0 if pending else SCHEDULE_POLL_SECONDS)
            self._wake.clear()
