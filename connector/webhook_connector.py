"""
Webhook Connector - Linux/Wine Bridge for MT5
Bridges Cthulu's trading loop to MT5 via the webhook_db_server HTTP API.

On Linux, the MetaTrader5 Python package is unavailable. Instead:
  - MarketPublisher.mq5 pushes ticks/bars to webhook_db_server (port 9002)
  - WebhookPoller.mq5 polls for trade jobs and executes them inside MT5
  - This connector speaks HTTP to that server, presenting the same interface
    as MT5Connector so the rest of Cthulu doesn't know the difference.

Usage:
    from connector.webhook_connector import WebhookConnector
    connector = WebhookConnector(config)
    connector.connect()
    bars = connector.get_ohlcv("EURUSD", "M5", 200)

Zero external dependencies — stdlib only (urllib).
"""
import json
import logging
import os
import time
import threading
import urllib.request
import urllib.error
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# ── Position dataclass (mirrors mt5_connector.PositionInfo) ──────────

@dataclass
class PositionInfo:
    """Position information — local shadow of what MT5 holds."""
    ticket: int
    symbol: str
    type: int           # 0 = buy, 1 = sell
    volume: float
    price_open: float
    price_current: float
    sl: float
    tp: float
    profit: float
    magic: int
    comment: str
    time: float


# ── Default symbol profiles ─────────────────────────────────────────
# Used when MT5 can't be queried directly. Covers the most common
# instruments. Extend as needed.

_SYMBOL_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # Forex majors (5-digit)
    "EURUSDm#": {"point": 0.00001, "digits": 5, "spread": 12,  "tick_size": 0.00001, "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    "EURUSD":  {"point": 0.00001, "digits": 5, "spread": 12,  "tick_size": 0.00001, "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    "GBPUSD":  {"point": 0.00001, "digits": 5, "spread": 15,  "tick_size": 0.00001, "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    "USDJPY":  {"point": 0.001,   "digits": 3, "spread": 12,  "tick_size": 0.001,   "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    "USDCHF":  {"point": 0.00001, "digits": 5, "spread": 14,  "tick_size": 0.00001, "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    "AUDUSD":  {"point": 0.00001, "digits": 5, "spread": 14,  "tick_size": 0.00001, "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    "USDCAD":  {"point": 0.00001, "digits": 5, "spread": 16,  "tick_size": 0.00001, "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    "NZDUSD":  {"point": 0.00001, "digits": 5, "spread": 18,  "tick_size": 0.00001, "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    # Metals / CFDs
    "XAUUSD":  {"point": 0.01,    "digits": 2, "spread": 25,  "tick_size": 0.01,    "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    "GOLDm#":  {"point": 0.01,    "digits": 2, "spread": 25,  "tick_size": 0.01,    "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
    # Crypto CFDs (XM-style)
    "BTCUSD":  {"point": 0.01,    "digits": 2, "spread": 5000,"tick_size": 0.01,    "vol_min": 0.01, "vol_max": 50.0,  "vol_step": 0.01},
    "BTCUSD#": {"point": 0.01,    "digits": 2, "spread": 5000,"tick_size": 0.01,    "vol_min": 0.01, "vol_max": 50.0,  "vol_step": 0.01},
    "ETHUSD":  {"point": 0.01,    "digits": 2, "spread": 500, "tick_size": 0.01,    "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01},
}

# Generic fallback for anything not listed above
_GENERIC_SYMBOL = {"point": 0.0001, "digits": 5, "spread": 20, "tick_size": 0.0001, "vol_min": 0.01, "vol_max": 100.0, "vol_step": 0.01}


# ── Connector ────────────────────────────────────────────────────────

class WebhookConnector:
    """
    HTTP-webhook bridge that speaks the same interface as MT5Connector.

    Market data flows:  MT5 → MarketPublisher.mq5 → webhook_db_server → this connector
    Order flow:         this connector → webhook_db_server → WebhookPoller.mq5 → MT5
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._connected = False
        self._account_info: Dict[str, Any] = {}

        # Server URL (resolve from multiple config locations)
        self._server_url = (
            config.get("market_data_server", {}).get("url")
            or config.get("data", {}).get("market_data_server", {}).get("url")
            or config.get("market_server_url")
            or "http://127.0.0.1:9002"
        ).rstrip("/")

        # Authentication (optional — matches webhook_db_server's X-API-KEY)
        self._api_key = os.environ.get("WEBHOOK_SECRET", config.get("webhook_secret", ""))

        # Timeouts
        self._timeout = config.get("webhook_timeout", 10)

        # Dry-run passthrough
        self.dry_run = config.get("mode", "live").lower() == "dry_run"

        # ── Local position shadow ────────────────────────────────────
        # Positions live inside MT5 (managed by WebhookPoller EA).  We
        # keep a lightweight shadow so the rest of Cthulu can query them.
        # Shadow is updated when we send/close orders.
        self._positions: Dict[int, PositionInfo] = {}
        self._next_shadow_ticket = 900_000  # synthetic ticket counter
        self._pos_lock = threading.Lock()

    # ── HTTP helpers ─────────────────────────────────────────────────

    def _headers(self, content_type: str = "application/json") -> Dict[str, str]:
        h: Dict[str, str] = {"Content-Type": content_type}
        if self._api_key:
            h["X-API-KEY"] = self._api_key
        return h

    def _get(self, path: str, params: Optional[Dict[str, str]] = None) -> Optional[Any]:
        """HTTP GET, returns parsed JSON or None."""
        url = f"{self._server_url}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, method="GET")
        for k, v in self._headers().items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                if resp.status == 204:
                    return None
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 204:
                return None
            logger.warning(f"GET {path} failed: HTTP {e.code}")
            return None
        except Exception as e:
            logger.error(f"GET {path} error: {e}")
            return None

    def _post(self, path: str, payload: Any = None) -> Optional[Any]:
        """HTTP POST, returns parsed JSON or None."""
        url = f"{self._server_url}{path}"
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        req = urllib.request.Request(url, data=body, method="POST")
        for k, v in self._headers().items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            logger.warning(f"POST {path} failed: HTTP {e.code}")
            return None
        except Exception as e:
            logger.error(f"POST {path} error: {e}")
            return None

    # ── Connection lifecycle ─────────────────────────────────────────

    def connect(self) -> bool:
        """
        Verify that webhook_db_server is reachable.
        No persistent connection — each call is an independent HTTP request.
        """
        if self.dry_run:
            logger.info("Dry-run mode: webhook connector simulated")
            self._connected = True
            return True

        # Probe the server with a lightweight GET
        try:
            url = f"{self._server_url}/latest_tick"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                # 200 or 204 both mean server is alive
                pass
            self._connected = True
            logger.info(f"WebhookConnector connected to {self._server_url}")
            return True
        except Exception as e:
            logger.warning(f"Webhook server probe failed ({e}); will retry on first data call")
            # Allow system to continue — data calls will retry individually
            self._connected = True
            return True

    def disconnect(self):
        """No persistent connection to tear down."""
        self._connected = False
        logger.info("WebhookConnector disconnected")

    # ── Account info ─────────────────────────────────────────────────

    def get_account_info(self) -> Dict[str, Any]:
        """
        Fetch live account info from the webhook server.
        Falls back to conservative defaults if the endpoint is unavailable.
        """
        if self.dry_run:
            return {
                "balance": 1000.0,
                "equity": 1000.0,
                "margin": 0.0,
                "free_margin": 1000.0,
                "margin_level": 0.0,
                "trade_allowed": True,
            }

        # Try to get live account data from webhook server
        try:
            data = self._get("/account")
            if data and isinstance(data, dict) and "balance" in data:
                return {
                    "balance": data.get("balance", 0),
                    "equity": data.get("equity", 0),
                    "margin": data.get("margin", 0),
                    "free_margin": data.get("margin_free", data.get("free_margin", 0)),
                    "margin_level": data.get("margin_level", 0),
                    "leverage": data.get("leverage", 1),
                    "profit": data.get("profit", 0),
                    "currency": data.get("currency", "USD"),
                    "trade_allowed": True,
                    "login": data.get("login", 0),
                    "server": data.get("server", ""),
                }
        except Exception as e:
            logger.debug(f"Failed to fetch live account info: {e}")

        # Fallback to config overrides or defaults
        defaults = {
            "balance": 10000.0,
            "equity": 10000.0,
            "margin": 0.0,
            "free_margin": 10000.0,
            "margin_level": 0.0,
            "trade_allowed": True,
        }
        overrides = self.config.get("webhook_account", {})
        defaults.update(overrides)
        return defaults

    # ── Market data ──────────────────────────────────────────────────

    def get_ohlcv(self, symbol: str, timeframe: str, count: int = 200):
        """
        Fetch OHLCV bars from webhook_db_server's /latest_bars endpoint.

        Returns a pandas DataFrame matching MT5Connector's format, or None.
        """
        if self.dry_run:
            return self._dummy_ohlcv(count)

        data = self._get("/latest_bars", {"symbol": symbol, "tf": timeframe, "count": str(count)})
        if data is None:
            return None

        bars = data.get("bars", [])
        if not bars:
            logger.debug(f"No bars returned for {symbol} {timeframe}")
            return None

        try:
            import pandas as pd

            df = pd.DataFrame(bars)
            for col in ("open", "high", "low", "close", "volume"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            if "time" in df.columns:
                # Bridge sends epoch timestamps as strings — convert properly
                try:
                    # Try as epoch seconds first (most common from MT5 bridge)
                    time_numeric = pd.to_numeric(df["time"], errors="coerce")
                    if time_numeric.notna().all() and (time_numeric > 1e9).all():
                        df["time"] = pd.to_datetime(time_numeric, unit="s", utc=True)
                    else:
                        df["time"] = pd.to_datetime(df["time"], errors="coerce")
                except Exception:
                    df["time"] = pd.to_datetime(df["time"], errors="coerce")
            # Server returns newest-first; sort ascending for indicator calcs
            df = df.sort_values("time").reset_index(drop=True)
            return df
        except Exception as e:
            logger.error(f"Failed to parse bars: {e}")
            return None

    def get_tick(self, symbol: str) -> Dict[str, Any]:
        """Fetch latest tick from /latest_tick endpoint."""
        if self.dry_run:
            return {"bid": 1.10000, "ask": 1.10020, "last": 1.10010, "time": 0}

        data = self._get("/latest_tick", {"symbol": symbol})
        if data is None:
            return {}

        return {
            "bid": float(data.get("bid", 0)),
            "ask": float(data.get("ask", 0)),
            "last": (float(data.get("bid", 0)) + float(data.get("ask", 0))) / 2,
            "time": data.get("time", 0),
        }

    # ── Symbol info ──────────────────────────────────────────────────

    def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
        """
        Return symbol specification.
        MT5 can't be queried over HTTP, so we use built-in defaults
        that can be overridden via config['symbol_overrides'].
        """
        if self.dry_run:
            return {
                "symbol": symbol,
                "point": 0.00001,
                "digits": 5,
                "spread": 12,
                "trade_tick_size": 0.00001,
                "volume_min": 0.01,
                "volume_max": 100.0,
                "volume_step": 0.01,
            }

        # Check config overrides first
        overrides = self.config.get("symbol_overrides", {}).get(symbol, {})

        # Then built-in defaults
        profile = _SYMBOL_DEFAULTS.get(symbol, _GENERIC_SYMBOL)

        info = {
            "symbol": symbol,
            "point": profile["point"],
            "digits": profile["digits"],
            "spread": profile["spread"],
            "trade_tick_size": profile["tick_size"],
            "volume_min": profile["vol_min"],
            "volume_max": profile["vol_max"],
            "volume_step": profile["vol_step"],
        }
        info.update(overrides)
        return info

    # ── Position tracking (shadow + live sync) ────────────────────────

    def get_positions(self) -> List[PositionInfo]:
        """
        Return positions — prefers live data from webhook server,
        falls back to shadow positions if server is unavailable.
        """
        try:
            data = self._get("/positions")
            if data and isinstance(data, dict) and "positions" in data:
                live_positions = []
                for p in data["positions"]:
                    pos = PositionInfo(
                        ticket=p.get("ticket", 0),
                        symbol=p.get("symbol", ""),
                        type=p.get("type", 0),
                        volume=p.get("volume", 0),
                        price_open=p.get("price_open", 0),
                        price_current=p.get("price_current", 0),
                        sl=p.get("sl", 0),
                        tp=p.get("tp", 0),
                        profit=p.get("profit", 0),
                        magic=p.get("magic", 0),
                        comment=p.get("comment", ""),
                        time=p.get("time", 0),
                    )
                    live_positions.append(pos)
                # Also sync shadow positions with live data
                with self._pos_lock:
                    for pos in live_positions:
                        self._positions[pos.ticket] = pos
                return live_positions
        except Exception as e:
            logger.debug(f"Failed to fetch live positions: {e}")
        
        # Fallback to shadow positions
        with self._pos_lock:
            return list(self._positions.values())

    def get_position(self, ticket: int) -> Optional[PositionInfo]:
        """Get a specific shadow position by ticket."""
        with self._pos_lock:
            return self._positions.get(ticket)

    def _register_shadow_position(
        self,
        symbol: str,
        direction: str,
        volume: float,
        price: float,
        sl: float = 0.0,
        tp: float = 0.0,
        magic: int = 123456,
        comment: str = "",
        job_id: Optional[int] = None,
    ) -> int:
        """
        Create a shadow position after a successful order enqueue.
        Returns the shadow ticket number.
        """
        with self._pos_lock:
            ticket = job_id if job_id else self._next_shadow_ticket
            self._next_shadow_ticket += 1

            self._positions[ticket] = PositionInfo(
                ticket=ticket,
                symbol=symbol,
                type=0 if direction.lower() == "buy" else 1,
                volume=volume,
                price_open=price,
                price_current=price,
                sl=sl,
                tp=tp,
                profit=0.0,
                magic=magic,
                comment=comment,
                time=time.time(),
            )
            return ticket

    def _remove_shadow_position(self, ticket: int) -> bool:
        with self._pos_lock:
            return self._positions.pop(ticket, None) is not None

    # ── Order execution ──────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        order_type: str,       # 'buy' or 'sell'
        volume: float,
        price: float = 0,
        sl: float = 0,
        tp: float = 0,
        magic: int = 123456,
        comment: str = "Cthulu",
        order_style: str = "market",
    ) -> Dict[str, Any]:
        """
        Enqueue an order via webhook_db_server for WebhookPoller EA to execute.

        The payload format matches what /next_job returns to the EA:
            id|CMD|SYMBOL|VOLUME|PRICE|SL|TP|ORDER_TYPE
        """
        if self.dry_run:
            import random
            return {
                "success": True,
                "ticket": random.randint(100000, 999999),
                "price": price or 1.10000,
                "volume": volume,
            }

        cmd = "BUY" if order_type.lower() == "buy" else "SELL"

        payload = {
            "command": cmd,
            "action": cmd,  # Bridge reads "action", next_job reads "command"
            "symbol": symbol,
            "volume": volume,
            "price": price if order_style in ("limit", "stop") else 0,
            "sl": sl,
            "tp": tp,
            "order_type": order_style,
        }

        result = self._post("/webhook", payload)
        if result is None:
            return {"success": False, "error": "Webhook server unreachable"}

        job_id = result.get("id")
        if job_id is None:
            return {"success": False, "error": "No job ID returned"}

        # Determine entry price for shadow (use provided price or fetch tick)
        entry_price = price
        if not entry_price or entry_price <= 0:
            tick = self.get_tick(symbol)
            if tick:
                entry_price = tick.get("ask", 0) if cmd == "BUY" else tick.get("bid", 0)

        # Register shadow
        ticket = self._register_shadow_position(
            symbol=symbol,
            direction=order_type,
            volume=volume,
            price=entry_price,
            sl=sl,
            tp=tp,
            magic=magic,
            comment=comment,
            job_id=job_id,
        )

        logger.info(
            f"Order enqueued: job_id={job_id} {cmd} {volume} {symbol} "
            f"@ {entry_price:.5f} SL={sl} TP={tp} style={order_style}"
        )

        return {
            "success": True,
            "ticket": ticket,
            "price": entry_price,
            "volume": volume,
            "routed": True,
            "job_id": job_id,
        }

    def send_order(self, *args, **kwargs) -> Dict[str, Any]:
        """Alias for place_order (some callers use this name)."""
        return self.place_order(*args, **kwargs)

    # ── Position modification ────────────────────────────────────────

    def modify_position(
        self,
        ticket: int,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
    ) -> bool:
        """
        Enqueue a MODIFY command for the EA to adjust SL/TP.

        Note: The EA must support a MODIFY command for this to take effect
        inside MT5. We also update the local shadow.
        """
        if self.dry_run:
            logger.info(f"Dry-run: Modified position {ticket} SL={sl} TP={tp}")
            return True

        pos = self.get_position(ticket)
        new_sl = sl if sl is not None else (pos.sl if pos else 0)
        new_tp = tp if tp is not None else (pos.tp if pos else 0)

        payload = {
            "command": "MODIFY",
            "action": "MODIFY",  # Bridge reads "action"
            "ticket": ticket,
            "symbol": pos.symbol if pos else "",
            "sl": new_sl,
            "tp": new_tp,
        }

        result = self._post("/webhook", payload)
        if result is None:
            logger.warning(f"Failed to enqueue MODIFY for ticket {ticket}")
            return False

        # Update shadow
        if pos:
            with self._pos_lock:
                if ticket in self._positions:
                    self._positions[ticket].sl = new_sl
                    self._positions[ticket].tp = new_tp

        logger.info(f"MODIFY enqueued for ticket {ticket}: SL={new_sl}, TP={new_tp}")
        return True

    # ── Position closing ─────────────────────────────────────────────

    def close_position(self, ticket: int, volume: Optional[float] = None) -> bool:
        """
        Enqueue a CLOSE command for the EA.
        """
        if self.dry_run:
            logger.info(f"Dry-run: Closed position {ticket}")
            self._remove_shadow_position(ticket)
            return True

        pos = self.get_position(ticket)

        payload = {
            "command": "CLOSE",
            "action": "CLOSE",  # Bridge reads "action"
            "ticket": ticket,
            "symbol": pos.symbol if pos else "",
            "volume": volume if volume else (pos.volume if pos else 0),
        }

        result = self._post("/webhook", payload)
        if result is None:
            logger.warning(f"Failed to enqueue CLOSE for ticket {ticket}")
            return False

        # Remove shadow
        self._remove_shadow_position(ticket)
        logger.info(f"CLOSE enqueued for ticket {ticket}")
        return True

    # ── Dry-run helpers ──────────────────────────────────────────────

    @staticmethod
    def _dummy_ohlcv(count: int = 200):
        """Generate dummy OHLCV data for dry-run mode."""
        import pandas as pd
        import numpy as np

        dates = pd.date_range(end=pd.Timestamp.now(), periods=count, freq="5min")
        base = 1.10000
        data = {
            "time": dates,
            "open": np.random.normal(base, 0.0005, count),
            "high": np.random.normal(base + 0.0003, 0.0005, count),
            "low": np.random.normal(base - 0.0003, 0.0005, count),
            "close": np.random.normal(base, 0.0005, count),
            "volume": np.random.randint(50, 500, count),
        }
        return pd.DataFrame(data)


# ── Factory ──────────────────────────────────────────────────────────

def create_connector(config: Dict[str, Any]):
    """
    Factory: pick the right connector based on config['connector_mode'].

        'mt5'     → MT5Connector   (requires MetaTrader5 Python package)
        'webhook' → WebhookConnector (HTTP bridge, works on Linux/Wine)

    Default is 'mt5' for backward compatibility.
    """
    mode = config.get("connector_mode", "mt5").lower()

    if mode == "webhook":
        logger.info("Using WebhookConnector (HTTP bridge to MT5 via webhook_db_server)")
        return WebhookConnector(config)
    else:
        from connector.mt5_connector import MT5Connector
        logger.info("Using native MT5Connector")
        return MT5Connector(config)
