"""Broker abstraction used by the agent.

  PaperBroker  simulated market (default). Safe to run anywhere, used by the tests.
  MT5Broker    MetaTrader 5, with real pending orders (limit/stop), modify, cancel and partial close.
"""
from __future__ import annotations

import math
import os
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

TF_MIN = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}
PENDING_KINDS = ("buy_limit", "sell_limit", "buy_stop", "sell_stop", "buy_stop_limit", "sell_stop_limit")


class BrokerError(Exception):
    pass


@dataclass
class Account:
    balance: float
    equity: float
    margin_free: float = 0.0
    currency: str = "USD"
    leverage: int = 0
    login: str = ""
    server: str = ""
    real: bool = False

    def to_dict(self): return asdict(self)


@dataclass
class SymbolInfo:
    symbol: str
    digits: int
    point: float
    tick_size: float
    tick_value: float
    contract_size: float
    vol_min: float
    vol_max: float
    vol_step: float
    stops_level: float  # in price units
    bid: float = 0.0
    ask: float = 0.0

    def to_dict(self): return asdict(self)

    def loss_per_lot(self, entry: float, sl: float) -> float:
        return abs(entry - sl) / self.tick_size * self.tick_value


@dataclass
class Position:
    ticket: int
    symbol: str
    side: str  # buy | sell
    volume: float
    price_open: float
    sl: float
    tp: float
    price_current: float
    profit: float
    time: float
    comment: str = ""
    magic: int = 0

    def to_dict(self): return asdict(self)


@dataclass
class Pending:
    ticket: int
    symbol: str
    kind: str  # buy_limit | sell_limit | buy_stop | sell_stop
    volume: float
    price: float
    sl: float
    tp: float
    time: float
    comment: str = ""
    magic: int = 0

    def to_dict(self): return asdict(self)


class Broker(ABC):
    name = "base"
    is_real = False

    def tradeable_symbols(self, max_spread_pct: float = 0.0025) -> List[str]:
        raise BrokerError(f"{self.name} broker does not support dynamic symbol discovery")

    @abstractmethod
    def connect(self) -> None: ...
    @abstractmethod
    def account(self) -> Account: ...
    @abstractmethod
    def symbol_info(self, symbol: str) -> SymbolInfo: ...
    @abstractmethod
    def candles(self, symbol: str, tf: str, n: int = 300) -> List[Dict[str, float]]: ...
    @abstractmethod
    def positions(self) -> List[Position]: ...
    @abstractmethod
    def pending(self) -> List[Pending]: ...
    @abstractmethod
    def place_market(self, symbol: str, side: str, volume: float, sl: float, tp: float, comment: str = "") -> Dict[str, Any]: ...
    @abstractmethod
    def place_pending(self, symbol: str, kind: str, volume: float, price: float, sl: float, tp: float, comment: str = "") -> Dict[str, Any]: ...
    @abstractmethod
    def modify_pending(self, ticket: int, price: Optional[float], sl: Optional[float], tp: Optional[float]) -> Dict[str, Any]: ...
    @abstractmethod
    def cancel_pending(self, ticket: int) -> Dict[str, Any]: ...
    @abstractmethod
    def modify_position(self, ticket: int, sl: Optional[float], tp: Optional[float]) -> Dict[str, Any]: ...
    @abstractmethod
    def close_position(self, ticket: int, volume: Optional[float] = None) -> Dict[str, Any]: ...
    @abstractmethod
    def closed_deal(self, ticket: int) -> Optional[Dict[str, Any]]: ...

    def advance(self, steps: int = 1) -> None:  # paper only
        return None

    def shutdown(self) -> None:
        return None


# ====================================================================== paper
class PaperBroker(Broker):
    name = "paper"
    SPECS = {
        "XAUUSD": dict(price=2650.0, sigma=0.0006, digits=2, point=0.01, contract=100.0, vmin=0.01, vstep=0.01, vmax=50.0, spread=0.25),
        "EURUSD": dict(price=1.0850, sigma=0.00025, digits=5, point=0.00001, contract=100000.0, vmin=0.01, vstep=0.01, vmax=50.0, spread=0.00012),
        "BTCUSD": dict(price=65000.0, sigma=0.0014, digits=2, point=0.01, contract=1.0, vmin=0.01, vstep=0.01, vmax=10.0, spread=18.0),
    }

    def __init__(self, balance: float = 1000.0, seed: Optional[int] = None, history: int = 2800):
        self.rng = random.Random(seed if seed is not None else 7)
        self.balance = float(balance)
        self._lock = threading.RLock()
        self._next = 100000
        self._pos: Dict[int, Position] = {}
        self._pend: Dict[int, Pending] = {}
        self._deals: Dict[int, Dict[str, Any]] = {}
        self._bars: Dict[str, List[List[float]]] = {}
        self._px: Dict[str, float] = {}
        self._script: Dict[str, List[float]] = {}
        self._history = history

    # -- lifecycle
    def connect(self) -> None:
        with self._lock:
            if self._bars:
                return
            end = int(time.time() // 300 * 300)
            for sym, sp in self.SPECS.items():
                self._px[sym] = sp["price"]
                self._bars[sym] = []
                self._script[sym] = []
                t0 = end - 300 * self._history
                for i in range(self._history):
                    self._bars[sym].append(self._make_bar(sym, t0 + 300 * i, fills=False))

    def _spec(self, sym: str) -> Dict[str, float]:
        if sym not in self.SPECS:
            raise BrokerError(f"unknown paper symbol {sym}. Available: {', '.join(self.SPECS)}")
        return self.SPECS[sym]

    def _make_bar(self, sym: str, t: int, fills: bool = True) -> List[float]:
        sp = self._spec(sym)
        px = self._px[sym]
        sig = sp["sigma"] * px * (1.6 if (t // 300) % 288 in range(90, 150) else 1.0)  # busier mid-day
        script = self._script[sym]
        if not script and self.rng.random() < 0.035 and len(self._bars[sym]) > 45:
            recent = self._bars[sym][-40:]
            up = self.rng.random() < 0.5
            level = max(b[2] for b in recent) if up else min(b[3] for b in recent)
            target = level + (0.3 if up else -0.3) * sig * 1.4
            if abs(target - px) < 5 * sig:
                step = (target - px) / 3
                back = -(abs(target - px) + 2.2 * sig) / 4 * (1 if up else -1)
                self._script[sym] = script = [step] * 3 + [back] * 4
        drift = script.pop(0) if script else 0.0
        path = [px]
        for _ in range(4):
            path.append(path[-1] + drift / 4 + self.rng.gauss(0, sig / 2))
            if fills:
                self._fills(sym, path[-1])
        hi = max(path) + abs(self.rng.gauss(0, sig * 0.15))
        lo = min(path) - abs(self.rng.gauss(0, sig * 0.15))
        self._px[sym] = path[-1]
        return [float(t), path[0], hi, lo, path[-1]]

    # -- engine
    def _bid_ask(self, sym: str, mid: Optional[float] = None) -> Tuple[float, float]:
        mid = self._px[sym] if mid is None else mid
        h = self._spec(sym)["spread"] / 2
        return mid - h, mid + h

    def _fills(self, sym: str, mid: float) -> None:
        bid, ask = self._bid_ask(sym, mid)
        for t, o in list(self._pend.items()):
            if o.symbol != sym:
                continue
            hit = ((o.kind == "buy_limit" and ask <= o.price) or (o.kind == "sell_limit" and bid >= o.price) or
                   (o.kind == "buy_stop" and ask >= o.price) or (o.kind == "sell_stop" and bid <= o.price))
            if hit:
                del self._pend[t]
                self._pos[t] = Position(t, sym, "buy" if o.kind.startswith("buy") else "sell", o.volume, o.price, o.sl, o.tp,
                                        o.price, 0.0, time.time(), o.comment, o.magic)
        for t, p in list(self._pos.items()):
            if p.symbol != sym:
                continue
            px = bid if p.side == "buy" else ask
            if p.sl and ((p.side == "buy" and px <= p.sl) or (p.side == "sell" and px >= p.sl)):
                self._close(t, p.sl, p.volume)
            elif p.tp and ((p.side == "buy" and px >= p.tp) or (p.side == "sell" and px <= p.tp)):
                self._close(t, p.tp, p.volume)

    def _close(self, ticket: int, price: float, volume: float) -> float:
        p = self._pos[ticket]
        sp = self._spec(p.symbol)
        vol = min(volume, p.volume)
        pnl = (price - p.price_open) * (1 if p.side == "buy" else -1) * vol * sp["contract"]
        self.balance += pnl
        prev = self._deals.get(ticket, {"pnl": 0.0, "volume": 0.0})
        self._deals[ticket] = {"ticket": ticket, "pnl": prev["pnl"] + pnl, "price_close": price,
                               "time_close": time.time(), "volume": prev["volume"] + vol, "symbol": p.symbol, "closed": False}
        if vol >= p.volume - 1e-9:
            del self._pos[ticket]
            self._deals[ticket]["closed"] = True
        else:
            p.volume = round(p.volume - vol, 8)
        return pnl

    def advance(self, steps: int = 1) -> None:
        with self._lock:
            for sym in self.SPECS:
                for _ in range(steps):
                    t = int(self._bars[sym][-1][0]) + 300
                    self._bars[sym].append(self._make_bar(sym, t, fills=True))
                self._bars[sym] = self._bars[sym][-self._history - 400:]

    # -- reads
    def account(self) -> Account:
        with self._lock:
            fl = sum(self._float(p) for p in self._pos.values())
            return Account(self.balance, self.balance + fl, margin_free=max(0.0, self.balance + fl), login="paper", server="simulated")

    def _float(self, p: Position) -> float:
        bid, ask = self._bid_ask(p.symbol)
        px = bid if p.side == "buy" else ask
        return (px - p.price_open) * (1 if p.side == "buy" else -1) * p.volume * self._spec(p.symbol)["contract"]

    def symbol_info(self, symbol: str) -> SymbolInfo:
        sp = self._spec(symbol)
        bid, ask = self._bid_ask(symbol)
        tick = sp["point"]
        return SymbolInfo(symbol, sp["digits"], sp["point"], tick, tick * sp["contract"], sp["contract"], sp["vmin"], sp["vmax"],
                          sp["vstep"], 10 * sp["point"], round(bid, sp["digits"]), round(ask, sp["digits"]))

    def tradeable_symbols(self, max_spread_pct: float = 0.0025) -> List[str]:
        return sorted(
            symbol for symbol, spec in self.SPECS.items()
            if spec["spread"] / spec["price"] <= max_spread_pct
        )

    def candles(self, symbol: str, tf: str, n: int = 300) -> List[Dict[str, float]]:
        with self._lock:
            self._spec(symbol)
            df = pd.DataFrame(self._bars[symbol], columns=["time", "open", "high", "low", "close"])
            m = TF_MIN.get(tf, 15)
            if m > 5:
                df.index = pd.to_datetime(df["time"], unit="s", utc=True)
                df = df.resample(f"{m}min").agg({"time": "first", "open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
            df = df.tail(n)
            d = self._spec(symbol)["digits"]
            return [{"time": float(r.time), "open": round(r.open, d), "high": round(r.high, d), "low": round(r.low, d),
                     "close": round(r.close, d), "volume": 1.0} for r in df.itertuples()]

    def positions(self) -> List[Position]:
        with self._lock:
            out = []
            for p in self._pos.values():
                bid, ask = self._bid_ask(p.symbol)
                p.price_current = bid if p.side == "buy" else ask
                p.profit = round(self._float(p), 2)
                out.append(Position(**asdict(p)))
            return out

    def pending(self) -> List[Pending]:
        with self._lock:
            return [Pending(**asdict(o)) for o in self._pend.values()]

    # -- writes
    def _ticket(self) -> int:
        self._next += 1
        return self._next

    def place_market(self, symbol, side, volume, sl, tp, comment="") -> Dict[str, Any]:
        with self._lock:
            bid, ask = self._bid_ask(symbol)
            price = ask if side == "buy" else bid
            t = self._ticket()
            self._pos[t] = Position(t, symbol, side, volume, price, sl or 0.0, tp or 0.0, price, 0.0, time.time(), comment, 0)
            return {"ok": True, "ticket": t, "price": price}

    def place_pending(self, symbol, kind, volume, price, sl, tp, comment="") -> Dict[str, Any]:
        with self._lock:
            if kind not in PENDING_KINDS:
                raise BrokerError(f"bad pending type {kind}")
            self._spec(symbol)
            t = self._ticket()
            self._pend[t] = Pending(t, symbol, kind, volume, price, sl or 0.0, tp or 0.0, time.time(), comment, 0)
            return {"ok": True, "ticket": t, "price": price}

    def modify_pending(self, ticket, price=None, sl=None, tp=None) -> Dict[str, Any]:
        with self._lock:
            o = self._pend.get(ticket)
            if not o:
                raise BrokerError(f"no pending order {ticket}")
            if price is not None: o.price = price
            if sl is not None: o.sl = sl
            if tp is not None: o.tp = tp
            return {"ok": True, "ticket": ticket}

    def cancel_pending(self, ticket) -> Dict[str, Any]:
        with self._lock:
            if ticket not in self._pend:
                raise BrokerError(f"no pending order {ticket}")
            del self._pend[ticket]
            return {"ok": True, "ticket": ticket}

    def modify_position(self, ticket, sl=None, tp=None) -> Dict[str, Any]:
        with self._lock:
            p = self._pos.get(ticket)
            if not p:
                raise BrokerError(f"no position {ticket}")
            if sl is not None: p.sl = sl
            if tp is not None: p.tp = tp
            return {"ok": True, "ticket": ticket}

    def close_position(self, ticket, volume=None) -> Dict[str, Any]:
        with self._lock:
            p = self._pos.get(ticket)
            if not p:
                raise BrokerError(f"no position {ticket}")
            bid, ask = self._bid_ask(p.symbol)
            pnl = self._close(ticket, bid if p.side == "buy" else ask, volume or p.volume)
            return {"ok": True, "ticket": ticket, "pnl": pnl}

    def closed_deal(self, ticket) -> Optional[Dict[str, Any]]:
        d = self._deals.get(ticket)
        return dict(d) if d and d["closed"] else None


# ====================================================================== MT5
class MT5Broker(Broker):
    name = "mt5"
    is_real = True
    MAGIC = int(os.environ.get("AGENT_MAGIC", "777001"))

    def __init__(self):
        self.mt5 = None
        self._lock = threading.RLock()
        self._map: Dict[str, str] = {}
        self.demo = True
        self._universe_cache: List[str] = []
        self._universe_cached_at = 0.0
        self._universe_spread_limit: Optional[float] = None

    def connect(self) -> None:
        try:
            import MetaTrader5 as mt5  # type: ignore
        except ImportError:
            raise BrokerError("MetaTrader5 package not installed. Run: pip install MetaTrader5 (Windows only)")
        self.mt5 = mt5
        kw: Dict[str, Any] = {}
        if os.environ.get("MT5_LOGIN"):
            kw.update(login=int(os.environ["MT5_LOGIN"]), password=os.environ.get("MT5_PASSWORD", ""), server=os.environ.get("MT5_SERVER", ""))
        if os.environ.get("MT5_PATH"):
            kw["path"] = os.environ["MT5_PATH"]
        with self._lock:
            if not mt5.initialize(**kw):
                raise BrokerError(f"MT5 initialize failed: {mt5.last_error()}")
            info = mt5.account_info()
            self.demo = bool(info and info.trade_mode == getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", 0))
            self.is_real = not self.demo

    def shutdown(self) -> None:
        if self.mt5:
            with self._lock:
                self.mt5.shutdown()

    def _sym(self, symbol: str) -> str:
        if symbol in self._map:
            return self._map[symbol]
        m = self.mt5
        with self._lock:
            if m.symbol_info(symbol) is not None:
                real = symbol
            else:
                aliases = {
                    "WTI": ("OILCASH", "USOIL"),
                    "XAUUSD": ("GOLD#", "GOLDm#", "GOLDm", "GOLD"),
                    "GOLD": ("GOLD#", "GOLDm#", "XAUUSD"),
                }
                available = [s.name for s in (m.symbols_get() or [])]
                targets = (symbol, *aliases.get(symbol.upper().rstrip("#."), ()))
                normalized = lambda value: "".join(c for c in value.upper() if c.isalnum())
                cands = []
                for target in targets:
                    target_norm = normalized(target)
                    cands = [name for name in available if normalized(name) == target_norm]
                    if not cands:
                        cands = [
                            name for name in available
                            if normalized(name).startswith(target_norm)
                            and len(normalized(name)) - len(target_norm) <= 4
                        ]
                    if cands:
                        break
                if not cands:
                    raise BrokerError(f"symbol {symbol} not found at this broker")
                real = sorted(cands, key=len)[0]
            m.symbol_select(real, True)
        self._map[symbol] = real
        return real

    def account(self) -> Account:
        with self._lock:
            a = self.mt5.account_info()
        if a is None:
            raise BrokerError(f"account_info failed: {self.mt5.last_error()}")
        return Account(a.balance, a.equity, a.margin_free, a.currency, a.leverage, str(a.login), a.server, self.is_real)

    def symbol_info(self, symbol: str) -> SymbolInfo:
        real = self._sym(symbol)
        with self._lock:
            i, t = self.mt5.symbol_info(real), self.mt5.symbol_info_tick(real)
        tick = i.trade_tick_size or i.point
        return SymbolInfo(symbol, i.digits, i.point, tick, i.trade_tick_value or 1.0, i.trade_contract_size, i.volume_min,
                          i.volume_max, i.volume_step, (i.trade_stops_level or 0) * i.point, t.bid if t else 0.0, t.ask if t else 0.0)

    def tradeable_symbols(self, max_spread_pct: float = 0.0025) -> List[str]:
        if self.mt5 is None:
            raise BrokerError("MT5 broker is not connected")
        now = time.time()
        if (
            self._universe_spread_limit == max_spread_pct
            and now - self._universe_cached_at < 900
        ):
            return list(self._universe_cache)

        with self._lock:
            rows = self.mt5.symbols_get()
        if rows is None:
            raise BrokerError(f"MT5 symbol discovery failed: {self.mt5.last_error()}")
        allowed_modes = {
            getattr(self.mt5, "SYMBOL_TRADE_MODE_LONGONLY", 1),
            getattr(self.mt5, "SYMBOL_TRADE_MODE_SHORTONLY", 2),
            getattr(self.mt5, "SYMBOL_TRADE_MODE_FULL", 4),
        }
        timeframe = getattr(self.mt5, "TIMEFRAME_M1", None)
        if timeframe is None:
            raise BrokerError("MT5 M1 timeframe is unavailable")

        selected = []
        for row in rows:
            name = getattr(row, "name", None)
            if not name or getattr(row, "trade_mode", None) not in allowed_modes:
                continue
            try:
                with self._lock:
                    if not self.mt5.symbol_select(name, True):
                        continue
                    info = self.mt5.symbol_info(name)
                    tick = self.mt5.symbol_info_tick(name)
                    if not info or not tick or info.point <= 0:
                        continue
                    bid, ask = float(tick.bid), float(tick.ask)
                    mid = (bid + ask) / 2.0
                    if bid <= 0 or ask < bid or mid <= 0 or (ask - bid) / mid > max_spread_pct:
                        continue
                    tick_time = float(getattr(tick, "time", 0) or 0)
                    if tick_time <= 0 or now - tick_time > 300:
                        continue
                    rates = self.mt5.copy_rates_from_pos(name, timeframe, 0, 120)
                if rates is None or len(rates) < 100:
                    continue
                volumes = rates["tick_volume"][-20:]
                if sum(float(volume) > 0 for volume in volumes) < 10:
                    continue
                selected.append(name)
            except (AttributeError, TypeError, ValueError, KeyError):
                continue

        selected.sort()
        self._universe_cache = selected
        self._universe_cached_at = now
        self._universe_spread_limit = max_spread_pct
        return list(selected)

    def candles(self, symbol: str, tf: str, n: int = 300) -> List[Dict[str, float]]:
        real = self._sym(symbol)
        tfc = getattr(self.mt5, "TIMEFRAME_" + tf, None)
        if tfc is None:
            raise BrokerError(f"bad timeframe {tf}")
        with self._lock:
            rates = self.mt5.copy_rates_from_pos(real, tfc, 0, n)
        if rates is None or len(rates) == 0:
            raise BrokerError(f"no candles for {symbol} {tf}")
        return [{"time": float(r["time"]), "open": float(r["open"]), "high": float(r["high"]), "low": float(r["low"]),
                 "close": float(r["close"]), "volume": float(r["tick_volume"])} for r in rates]

    def positions(self) -> List[Position]:
        with self._lock:
            rows = self.mt5.positions_get()
        if rows is None:
            raise BrokerError(f"MT5 position query failed: {self.mt5.last_error()}")
        return [Position(p.ticket, self._back(p.symbol), "buy" if p.type == 0 else "sell", p.volume, p.price_open, p.sl, p.tp,
                         p.price_current, p.profit + getattr(p, "swap", 0.0), float(p.time), p.comment, p.magic) for p in rows]

    def pending(self) -> List[Pending]:
        kinds = {
            2: "buy_limit",
            3: "sell_limit",
            4: "buy_stop",
            5: "sell_stop",
            6: "buy_stop_limit",
            7: "sell_stop_limit",
        }
        with self._lock:
            rows = self.mt5.orders_get()
        if rows is None:
            raise BrokerError(f"MT5 pending-order query failed: {self.mt5.last_error()}")
        return [Pending(o.ticket, self._back(o.symbol), kinds[o.type], o.volume_current, o.price_open, o.sl, o.tp, float(o.time_setup),
                        o.comment, o.magic) for o in rows if o.type in kinds]

    def _back(self, real: str) -> str:
        for k, v in self._map.items():
            if v == real:
                return k
        return real

    def _fill_mode(self, real: str, pending: bool) -> int:
        m = self.mt5
        if pending:
            return m.ORDER_FILLING_RETURN
        fm = m.symbol_info(real).filling_mode
        return m.ORDER_FILLING_FOK if fm & 1 else m.ORDER_FILLING_IOC if fm & 2 else m.ORDER_FILLING_RETURN

    def _send(self, req: Dict[str, Any]) -> Dict[str, Any]:
        m = self.mt5
        with self._lock:
            res = m.order_send(req)
        if res is None:
            raise BrokerError(f"order_send returned None: {m.last_error()}")
        if res.retcode not in (m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_PLACED, getattr(m, "TRADE_RETCODE_DONE_PARTIAL", 10010)):
            raise BrokerError(f"broker rejected request: {res.retcode} {res.comment}")
        return {"ok": True, "ticket": res.order or res.deal, "price": res.price, "retcode": res.retcode}

    def place_market(self, symbol, side, volume, sl, tp, comment="") -> Dict[str, Any]:
        real, m = self._sym(symbol), self.mt5
        with self._lock:
            t = m.symbol_info_tick(real)
            req = {"action": m.TRADE_ACTION_DEAL, "symbol": real, "volume": float(volume),
                   "type": m.ORDER_TYPE_BUY if side == "buy" else m.ORDER_TYPE_SELL, "price": t.ask if side == "buy" else t.bid,
                   "sl": float(sl or 0), "tp": float(tp or 0), "deviation": 20, "magic": self.MAGIC, "comment": comment[:30] or "cthulu-agent",
                   "type_time": m.ORDER_TIME_GTC, "type_filling": self._fill_mode(real, False)}
        r = self._send(req)
        with self._lock:  # position id of a market deal == the order ticket
            deals = m.history_deals_get(ticket=r["ticket"]) if r["ticket"] else None
        r["ticket"] = deals[0].position_id if deals else r["ticket"]
        return r

    def place_pending(self, symbol, kind, volume, price, sl, tp, comment="") -> Dict[str, Any]:
        if kind not in PENDING_KINDS:
            raise BrokerError(f"bad pending type {kind}")
        real, m = self._sym(symbol), self.mt5
        types = {"buy_limit": m.ORDER_TYPE_BUY_LIMIT, "sell_limit": m.ORDER_TYPE_SELL_LIMIT,
                 "buy_stop": m.ORDER_TYPE_BUY_STOP, "sell_stop": m.ORDER_TYPE_SELL_STOP}
        req = {"action": m.TRADE_ACTION_PENDING, "symbol": real, "volume": float(volume), "type": types[kind], "price": float(price),
               "sl": float(sl or 0), "tp": float(tp or 0), "deviation": 20, "magic": self.MAGIC, "comment": comment[:30] or "cthulu-agent",
               "type_time": m.ORDER_TIME_GTC, "type_filling": self._fill_mode(real, True)}
        return self._send(req)

    def modify_pending(self, ticket, price=None, sl=None, tp=None) -> Dict[str, Any]:
        m = self.mt5
        with self._lock:
            o = (m.orders_get(ticket=ticket) or [None])[0]
        if o is None:
            raise BrokerError(f"no pending order {ticket}")
        req = {"action": m.TRADE_ACTION_MODIFY, "order": ticket, "price": float(price if price is not None else o.price_open),
               "sl": float(o.sl if sl is None else sl), "tp": float(o.tp if tp is None else tp), "type_time": m.ORDER_TIME_GTC,
               "type_filling": m.ORDER_FILLING_RETURN}
        return self._send(req)

    def cancel_pending(self, ticket) -> Dict[str, Any]:
        return self._send({"action": self.mt5.TRADE_ACTION_REMOVE, "order": ticket})

    def modify_position(self, ticket, sl=None, tp=None) -> Dict[str, Any]:
        m = self.mt5
        with self._lock:
            p = (m.positions_get(ticket=ticket) or [None])[0]
        if p is None:
            raise BrokerError(f"no position {ticket}")
        return self._send({"action": m.TRADE_ACTION_SLTP, "position": ticket, "symbol": p.symbol,
                           "sl": float(p.sl if sl is None else sl), "tp": float(p.tp if tp is None else tp)})

    def close_position(self, ticket, volume=None) -> Dict[str, Any]:
        m = self.mt5
        with self._lock:
            p = (m.positions_get(ticket=ticket) or [None])[0]
            if p is None:
                raise BrokerError(f"no position {ticket}")
            t = m.symbol_info_tick(p.symbol)
            buy = p.type == 0
            req = {"action": m.TRADE_ACTION_DEAL, "position": ticket, "symbol": p.symbol, "volume": float(volume or p.volume),
                   "type": m.ORDER_TYPE_SELL if buy else m.ORDER_TYPE_BUY, "price": t.bid if buy else t.ask, "deviation": 20,
                   "magic": self.MAGIC, "comment": "cthulu-agent close", "type_time": m.ORDER_TIME_GTC,
                   "type_filling": self._fill_mode(p.symbol, False)}
        return self._send(req)

    def closed_deal(self, ticket) -> Optional[Dict[str, Any]]:
        m = self.mt5
        with self._lock:
            deals = m.history_deals_get(position=ticket)
        if not deals:
            return None
        outs = [d for d in deals if d.entry in (1, 2, 3)]
        if not outs:
            return None
        pnl = sum(d.profit + d.commission + d.swap + getattr(d, "fee", 0.0) for d in deals)
        last = max(outs, key=lambda d: d.time)
        vol_out = sum(d.volume for d in outs)
        vol_in = sum(d.volume for d in deals if d.entry == 0)
        return {"ticket": ticket, "pnl": pnl, "price_close": last.price, "time_close": float(last.time), "volume": vol_out,
                "symbol": self._back(last.symbol), "closed": vol_out >= vol_in - 1e-9}


def make_broker(kind: str, paper_balance: float = 1000.0) -> Broker:
    if kind == "mt5":
        return MT5Broker()
    return PaperBroker(balance=paper_balance)
