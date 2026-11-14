"""Native, read-only public market and macro feeds plus optional custom ingestion."""
from __future__ import annotations

import csv
import html
import io
import json
import math
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

MAX_CHARS = 14000
MAX_FEED_BYTES = 1_000_000
FEED_TIMEOUT_SECONDS = 10
NATIVE_CACHE_KEY = "world_native_feed_cache"

NATIVE_FEEDS = {
    "coingecko_bitcoin": {
        "url": "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true",
        "description": "Bitcoin USD spot price and 24-hour change",
    },
    "fred_dgs10": {
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10",
        "description": "US 10-year Treasury constant-maturity yield",
    },
    "fred_dtwexbgs": {
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTWEXBGS",
        "description": "US trade-weighted broad dollar index",
    },
    "fred_dcoilwtico": {
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILWTICO",
        "description": "WTI Cushing spot price, USD per barrel",
    },
    "bbc_world": {
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "description": "BBC World headlines and summaries for geopolitical context",
    },
    "bbc_business": {
        "url": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "description": "BBC Business headlines and summaries for macro context",
    },
}


def shrink(obj: Any, budget: int = MAX_CHARS) -> Any:
    """Prune big payloads (long arrays, long strings, deep nesting) to fit a prompt budget."""
    def go(o: Any, depth: int, per_list: int, str_len: int) -> Any:
        if isinstance(o, dict):
            return {str(k)[:60]: go(v, depth + 1, per_list, str_len) for k, v in list(o.items())[:40]} if depth < 6 else "…"
        if isinstance(o, list):
            return [go(x, depth + 1, per_list, str_len) for x in o[:per_list]] + ([f"… {len(o) - per_list} more"] if len(o) > per_list else [])
        if isinstance(o, str):
            return o[:str_len] + ("…" if len(o) > str_len else "")
        return o
    for per_list, str_len in ((25, 300), (12, 200), (6, 140), (3, 100)):
        out = go(obj, 0, per_list, str_len)
        if len(json.dumps(out, default=str)) <= budget:
            return out
    return json.dumps(out, default=str)[:budget]


def normalize_world_brief(brief: Any) -> Any:
    """Normalize common singleton/object encodings without inventing market data."""
    if not isinstance(brief, dict):
        return brief

    normalized = dict(brief)
    for field, item_key in (("themes", "theme"), ("event_risk", "what")):
        value = normalized.get(field)
        if value is None:
            normalized[field] = []
            continue
        if isinstance(value, dict):
            wrapped = value.get(field)
            if isinstance(wrapped, list):
                normalized[field] = wrapped
            elif item_key in value:
                normalized[field] = [value]
            continue
        if isinstance(value, str):
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, list):
                normalized[field] = decoded
            elif isinstance(decoded, dict):
                wrapped = decoded.get(field)
                normalized[field] = wrapped if isinstance(wrapped, list) else [decoded] if item_key in decoded else decoded

    stand_down = normalized.get("stand_down")
    if stand_down is None:
        normalized["stand_down"] = False
    if isinstance(stand_down, str):
        boolean_values = {
            "true": True, "false": False,
            "yes": True, "no": False,
            "on": True, "off": False,
            "1": True, "0": False,
        }
        normalized_value = boolean_values.get(stand_down.strip().lower())
        if normalized_value is not None:
            normalized["stand_down"] = normalized_value
    elif (
        isinstance(stand_down, (int, float))
        and not isinstance(stand_down, bool)
        and stand_down in (0, 1)
    ):
        normalized["stand_down"] = bool(stand_down)
    return normalized


def world_brief_validation_error(brief: Any) -> str:
    """Reject schema-shaped model output that is not an actual market brief."""
    if not isinstance(brief, dict):
        return "The model response is not a JSON object."

    summary = brief.get("summary")
    if not isinstance(summary, str):
        return "The World Brief summary is missing or invalid."
    normalized_summary = " ".join(summary.lower().split())
    if normalized_summary in {"3-5 sentences", "summary", "market summary", "your summary here"}:
        return "The model returned the summary placeholder instead of a World Brief."
    if len(summary.strip()) < 40:
        return "The World Brief summary is missing or too short."

    if not isinstance(brief.get("themes"), list):
        return "The World Brief themes field must be a list."
    if not isinstance(brief.get("event_risk"), list):
        return "The World Brief event_risk field must be a list."
    if not isinstance(brief.get("stand_down"), bool):
        return "The World Brief stand_down field must be a boolean."

    for theme in brief["themes"]:
        if not isinstance(theme, dict):
            return "A World Brief theme is not an object."
        title = theme.get("theme")
        why = theme.get("why")
        if not isinstance(title, str) or not title.strip() or not isinstance(why, str) or len(why.strip()) < 12:
            return "A World Brief theme contains empty or placeholder fields."
        if "symbol or asset class" in title.lower() or "|" in str(theme.get("bias", "")) or "|" in str(theme.get("urgency", "")):
            return "A World Brief theme contains schema placeholders."

    for event in brief["event_risk"]:
        if not isinstance(event, dict) or not isinstance(event.get("what"), str) or not event["what"].strip():
            return "A World Brief event-risk item contains empty or invalid fields."

    return ""


class WorldIntel:
    def __init__(self, journal: Any = None):
        self._lock = threading.Lock()
        self.journal = journal
        self.raw: Any = None
        self.raw_ts = 0.0
        self.brief: Optional[Dict[str, Any]] = None
        self.last_error = ""
        self.last_fetch = 0.0
        self.digested_ts = 0.0
        self.digest_error = ""
        self.digest_attempts = 0
        self.digest_retry_at = 0.0
        cached = journal.kv_get(NATIVE_CACHE_KEY, {}) if journal else {}
        self.native_feeds = {
            key: value for key, value in cached.items()
            if key in NATIVE_FEEDS and isinstance(value, dict)
        } if isinstance(cached, dict) else {}
        if self.native_feeds:
            self.raw = self._native_payload()
            self.raw_ts = max(
                (float(v.get("fetched_at", 0)) for v in self.native_feeds.values()
                 if isinstance(v.get("fetched_at", 0), (int, float))),
                default=0.0,
            )

    # -- config
    @property
    def url(self) -> str: return os.environ.get("WORLD_API_URL", "").strip()
    @property
    def native_enabled(self) -> bool:
        return os.environ.get("WORLD_NATIVE_ENABLED", "true").strip().lower() not in ("0", "false", "no", "off")
    @property
    def enabled(self) -> bool: return self.native_enabled or bool(self.url) or self.raw is not None
    @property
    def refresh_seconds(self) -> int:
        try: return max(60, int(float(os.environ.get("WORLD_REFRESH_MIN", "30")) * 60))
        except ValueError: return 1800

    def public_config(self) -> Dict[str, Any]:
        return {"url": self.url, "has_key": bool(os.environ.get("WORLD_API_KEY")), "header": os.environ.get("WORLD_API_HEADER", "Authorization"),
                "scheme": os.environ.get("WORLD_API_SCHEME", "Bearer"), "paths": os.environ.get("WORLD_API_PATHS", ""),
                "refresh_min": os.environ.get("WORLD_REFRESH_MIN", "30"), "enabled": self.enabled,
                "native_enabled": self.native_enabled, "native_feeds": self.public_native_feed_status(),
                "last_fetch": self.last_fetch, "has_brief": bool(self.brief)}

    def native_feed_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            feed_id: {
                "description": config["description"],
                "status": (self.native_feeds.get(feed_id) or {}).get("status", "waiting"),
                "fetched_at": (self.native_feeds.get(feed_id) or {}).get("fetched_at", 0),
                "error": (self.native_feeds.get(feed_id) or {}).get("error", ""),
                "data": (self.native_feeds.get(feed_id) or {}).get("data"),
            }
            for feed_id, config in NATIVE_FEEDS.items()
        }

    def public_native_feed_status(self) -> Dict[str, Dict[str, Any]]:
        return {
            feed_id: {
                "description": feed["description"],
                "status": "unavailable" if feed["status"] == "error" else feed["status"],
                "fetched_at": feed["fetched_at"],
                "data": feed["data"],
            }
            for feed_id, feed in self.native_feed_status().items()
        }

    # -- data
    def ingest(self, payload: Any) -> None:
        with self._lock:
            self.raw, self.raw_ts = payload, time.time()
            self.digest_attempts = 0
            self.digest_retry_at = 0.0
            self.digest_error = ""

    def refresh_due(self) -> bool:
        return bool((self.native_enabled or self.url) and time.time() - self.last_fetch >= self.refresh_seconds)

    @staticmethod
    def _read_url(url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json,text/csv,application/rss+xml,application/xml", "User-Agent": "cthulu-agent/1.0"},
        )
        with urllib.request.urlopen(request, timeout=FEED_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_FEED_BYTES + 1)
        if len(body) > MAX_FEED_BYTES:
            raise ValueError("response exceeded the 1 MB feed limit")
        return body

    @staticmethod
    def _parse_feed(feed_id: str, body: bytes) -> Dict[str, Any]:
        if feed_id == "coingecko_bitcoin":
            payload = json.loads(body.decode("utf-8"))
            bitcoin = payload.get("bitcoin") if isinstance(payload, dict) else None
            if not isinstance(bitcoin, dict) or not isinstance(bitcoin.get("usd"), (int, float)) or not math.isfinite(bitcoin["usd"]):
                raise ValueError("response did not contain a Bitcoin USD price")
            change = bitcoin.get("usd_24h_change")
            return {
                "usd": float(bitcoin["usd"]),
                "change_24h_pct": float(change) if isinstance(change, (int, float)) and math.isfinite(change) else None,
            }

        if feed_id in ("bbc_world", "bbc_business"):
            root = ET.fromstring(body)
            channel = root.find("channel")
            if channel is None:
                raise ValueError("RSS response did not contain a channel")
            items = []
            for item in channel.findall("item")[:20]:
                title = " ".join((item.findtext("title") or "").split())
                if not title:
                    continue
                description = html.unescape(item.findtext("description") or "")
                description = " ".join(re.sub(r"<[^>]*>", " ", description).split())[:280]
                items.append({
                    "title": title[:240],
                    "summary": description,
                    "published": (item.findtext("pubDate") or "").strip()[:80],
                    "url": (item.findtext("link") or "").strip()[:500],
                })
            if not items:
                raise ValueError("RSS response contained no usable headlines")
            return {
                "channel": " ".join((channel.findtext("title") or feed_id).split())[:120],
                "updated": (channel.findtext("lastBuildDate") or "").strip()[:80],
                "items": items,
            }

        rows = csv.DictReader(io.StringIO(body.decode("utf-8-sig")))
        last = None
        for row in rows:
            value = (row.get(feed_id.removeprefix("fred_").upper()) or "").strip()
            if value and value != ".":
                try:
                    last = {"date": row.get("observation_date", ""), "value": float(value)}
                except ValueError:
                    continue
        if not last:
            raise ValueError("response contained no numeric observations")
        return last

    def _native_payload(self) -> Dict[str, Any]:
        return {"source": "cthulu_native_public_feeds", "sources": self.native_feeds}

    def _fetch_native(self) -> tuple[bool, list[str]]:
        errors = []
        fetched_any = False

        def fetch_one(feed_id: str) -> tuple[str, Dict[str, Any]]:
            body = self._read_url(NATIVE_FEEDS[feed_id]["url"])
            return feed_id, self._parse_feed(feed_id, body)

        with ThreadPoolExecutor(max_workers=len(NATIVE_FEEDS)) as pool:
            futures = {pool.submit(fetch_one, feed_id): feed_id for feed_id in NATIVE_FEEDS}
            for future, feed_id in ((future, futures[future]) for future in futures):
                try:
                    _, data = future.result()
                    self.native_feeds[feed_id] = {"status": "ok", "fetched_at": time.time(), "data": data, "error": ""}
                    fetched_any = True
                except (OSError, TimeoutError, urllib.error.URLError, ValueError, UnicodeDecodeError, json.JSONDecodeError, csv.Error, ET.ParseError) as exc:
                    previous = self.native_feeds.get(feed_id, {})
                    self.native_feeds[feed_id] = {
                        "status": "stale" if previous.get("data") else "error",
                        "fetched_at": previous.get("fetched_at", 0),
                        "data": previous.get("data"),
                        "error": str(exc)[:240],
                    }
                    errors.append(f"{feed_id}: {str(exc)[:240]}")

        if self.journal:
            self.journal.kv_set(NATIVE_CACHE_KEY, self.native_feeds)
        return fetched_any, errors

    def fetch(self) -> bool:
        """Refresh native public feeds and, when configured, the optional custom pull feed."""
        data: Dict[str, Any] = {}
        errs = []
        fetched_any = False
        if self.native_enabled:
            fetched_any, native_errors = self._fetch_native()
            data["native_public_feeds"] = self._native_payload()
            errs.extend(native_errors)
        if self.url:
            base = self.url.rstrip("/")
            paths = [p.strip() for p in os.environ.get("WORLD_API_PATHS", "").split(",") if p.strip()] or [""]
            headers = {"Accept": "application/json", "User-Agent": "cthulu-agent/1.0"}
            key = os.environ.get("WORLD_API_KEY", "")
            if key:
                h, sch = os.environ.get("WORLD_API_HEADER", "Authorization"), os.environ.get("WORLD_API_SCHEME", "Bearer")
                headers[h] = f"{sch} {key}".strip()
            for p in paths:
                url = base + ("/" + p.lstrip("/") if p else "")
                if urllib.parse.urlparse(url).scheme not in ("http", "https"):
                    errs.append("URL must be http(s)")
                    continue
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25) as r:
                        body = r.read(2_000_000).decode("utf-8", "replace")
                    try:
                        data[p or "/"] = json.loads(body)
                    except ValueError:
                        data[p or "/"] = body[:4000]
                    fetched_any = True
                except urllib.error.HTTPError as e:
                    errs.append(f"{p or '/'}: HTTP {e.code}")
                except (urllib.error.URLError, TimeoutError) as e:
                    errs.append(f"{p or '/'}: {getattr(e, 'reason', e)}")
        self.last_fetch = time.time()
        self.last_error = "; ".join(errs)
        if data:
            self.ingest(data if len(data) > 1 else next(iter(data.values())))
        return fetched_any

    def due(self) -> bool:
        if not self.enabled:
            return False
        if self.refresh_due():
            return True
        return (self.raw is not None and self.raw_ts > self.digested_ts
                and time.time() >= self.digest_retry_at)

    def payload_for_prompt(self) -> str:
        with self._lock:
            return json.dumps(shrink(self.raw), default=str, ensure_ascii=False) if self.raw is not None else ""

    def set_brief(self, brief: Dict[str, Any]) -> None:
        brief["ts"] = time.time()
        self.brief, self.digested_ts = brief, time.time()
        self.digest_error = ""
        self.digest_attempts = 0
        self.digest_retry_at = 0.0

    def mark_digest_failed(self, error: str) -> None:
        self.digest_attempts += 1
        self.digest_error = error[:400]
        delay = min(900, 30 * (2 ** min(self.digest_attempts - 1, 5)))
        self.digest_retry_at = time.time() + delay
