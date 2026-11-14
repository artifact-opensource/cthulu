"""Deterministic guardrails. The LLM proposes, this layer disposes.

Scaling policy (tiny to large accounts):
  * Risk per trade is a percentage of *equity*, chosen by tier, so size compounds up as the account grows.
  * Risk shrinks during drawdown and never increases to "win it back".
  * A skill with no track record gets a small multiplier; proven skills earn up to the full tier budget.
  * Hard caps in settings can't be exceeded by the model or by chat.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .broker import Account, Broker, Pending, Position, SymbolInfo
from .journal import Journal
from .settings import Settings
from .capabilities import AGENT_PROFILES


@dataclass
class Tier:
    name: str
    min_equity: float
    risk_pct: float
    max_positions: int
    max_pending: int
    max_open_risk_pct: float
    note: str


TIERS: List[Tier] = [
    Tier("seed", 0, 2.0, 1, 2, 2.5, "Prove the process on one trade at a time. Volume is limited by minimum lot size."),
    Tier("sprout", 100, 1.5, 2, 3, 3.0, "Two positions, still one idea at a time."),
    Tier("grow", 500, 1.0, 3, 4, 3.5, "Risk per trade tightens while position count widens."),
    Tier("steady", 2_000, 0.75, 4, 6, 4.0, "Diversify across symbols; consistency over speed."),
    Tier("scale", 10_000, 0.5, 6, 8, 4.0, "Capital preservation leads; compounding does the work."),
    Tier("capital", 100_000, 0.25, 8, 10, 3.0, "Large account: small fractions, liquidity-aware sizing."),
]

DAILY_LOSS_BASELINE_KEY = "risk_daily_loss_baseline_ts"
DAILY_LOSS_BASELINE_TRADE_ID_KEY = "risk_daily_loss_baseline_trade_id"
DAILY_LOSS_BASELINE_OPEN_IDS_KEY = "risk_daily_loss_baseline_open_trade_ids"


@dataclass
class Proposal:
    type: str                      # place_limit | place_stop | place_market
    symbol: str
    side: str                      # buy | sell
    entry: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    risk_pct: Optional[float] = None
    skills: List[str] = field(default_factory=list)
    thesis: str = ""
    invalidation: str = ""
    expires_minutes: int = 240


@dataclass
class Verdict:
    ok: bool
    volume: float = 0.0
    risk_pct: float = 0.0
    risk_amount: float = 0.0
    kind: str = ""
    entry: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self): return self.__dict__.copy()


class RiskEngine:
    def __init__(self, settings: Settings, journal: Journal):
        self.s, self.j = settings, journal

    # ---------------------------------------------------------------- state
    def tier_for(self, equity: float) -> Tier:
        t = TIERS[0]
        for x in TIERS:
            if equity >= x.min_equity:
                t = x
        return t

    def track_equity(self, equity: float) -> Dict[str, Any]:
        peak = max(float(self.j.kv_get("equity_peak", equity) or equity), equity)
        self.j.kv_set("equity_peak", peak)
        start = self.j.kv_get("equity_start")
        if not start:
            start = equity
            self.j.kv_set("equity_start", start)
        dd = (peak - equity) / peak * 100 if peak else 0.0
        halt = self.s.float("RISK_DRAWDOWN_HALT_PCT")
        halted = halt > 0 and dd >= halt
        mult = 0.0 if halted else 0.25 if halt > 0 and dd >= halt * 0.66 else 0.5 if halt > 0 and dd >= halt * 0.33 else 1.0
        return {"peak": peak, "start": start, "drawdown_pct": round(dd, 2), "dd_mult": mult, "halted": halted,
                "growth_pct": round((equity / start - 1) * 100, 2) if start else 0.0}

    def daily_pnl(self, acct: Account, positions: List[Position]) -> float:
        now = time.time()
        day0 = now - (now % 86400)
        reset_at = self.j.kv_get(DAILY_LOSS_BASELINE_KEY, 0)
        if isinstance(reset_at, (int, float)) and math.isfinite(reset_at):
            day0 = max(day0, float(reset_at))
        trades = self.j.trades(status="closed", limit=300)
        baseline_trade_id = self.j.kv_get(DAILY_LOSS_BASELINE_TRADE_ID_KEY)
        baseline_open_ids = self.j.kv_get(DAILY_LOSS_BASELINE_OPEN_IDS_KEY, [])
        if (
            isinstance(reset_at, (int, float))
            and math.isfinite(reset_at)
            and float(reset_at) >= now - (now % 86400)
            and isinstance(baseline_trade_id, int)
            and not isinstance(baseline_trade_id, bool)
        ):
            open_ids = {
                value for value in baseline_open_ids
                if isinstance(value, int) and not isinstance(value, bool)
            } if isinstance(baseline_open_ids, list) else set()
            realized_trades = (
                t for t in trades
                if isinstance(t.get("id"), int)
                and (t["id"] > baseline_trade_id or t["id"] in open_ids)
            )
        else:
            realized_trades = (t for t in trades if (t["ts_close"] or 0) >= day0)
        realised = sum((t["pnl"] or 0) for t in realized_trades)
        return realised + sum(min(p.profit, 0) for p in positions)

    def reset_daily_loss_baseline(self) -> float:
        trade_id, open_trade_ids = self.j.trade_baseline()
        self.j.kv_set(DAILY_LOSS_BASELINE_TRADE_ID_KEY, trade_id)
        self.j.kv_set(DAILY_LOSS_BASELINE_OPEN_IDS_KEY, open_trade_ids)
        reset_at = time.time()
        self.j.kv_set(DAILY_LOSS_BASELINE_KEY, reset_at)
        return reset_at

    def max_risk_pct(self, equity: float, skills: List[str], dd_mult: float) -> float:
        profile = AGENT_PROFILES.get(self.s.str("AGENT_PROFILE"), AGENT_PROFILES["balanced"])
        tier_cap = profile["risk_pct"] if self.s.str("AGENT_PROFILE") == "hft" else min(
            self.tier_for(equity).risk_pct, profile["risk_pct"]
        )
        base = tier_cap * dd_mult * self.j.skill_multiplier(skills)
        return round(min(base, self.s.float("RISK_MAX_PER_TRADE_PCT")), 4)

    def summary(self, acct: Account, positions: List[Position], pend: List[Pending], broker: Broker) -> Dict[str, Any]:
        t = self.tier_for(acct.equity)
        st = self.track_equity(acct.equity)
        open_risk = self._open_risk(broker, positions, pend)
        daily = self.daily_pnl(acct, positions)
        daily_loss_pct = self.s.float("RISK_DAILY_LOSS_PCT")
        daily_limit = acct.equity * daily_loss_pct / 100 if daily_loss_pct > 0 else 0.0
        halted = st["halted"] or (daily_loss_pct > 0 and daily <= -daily_limit)
        idx = TIERS.index(t)
        profile = AGENT_PROFILES.get(self.s.str("AGENT_PROFILE"), AGENT_PROFILES["balanced"])
        active_orders = min(profile["active_orders"], self.s.int("RISK_MAX_ACTIVE_ORDERS"))
        return {"tier": t.name, "tier_note": t.note, "risk_pct": t.risk_pct,
                "max_positions": min(active_orders, self.s.int("RISK_MAX_POSITIONS")),
                "max_positions_per_symbol": min(active_orders, self.s.int("RISK_MAX_POSITIONS_PER_SYMBOL")),
                "max_pending": min(active_orders, self.s.int("RISK_MAX_PENDING")),
                "max_active_orders": active_orders,
                "max_open_risk_pct": min(profile["open_risk_pct"], self.s.float("RISK_MAX_OPEN_RISK_PCT")),
                "next_tier": TIERS[idx + 1].name if idx + 1 < len(TIERS) else None,
                "next_tier_at": TIERS[idx + 1].min_equity if idx + 1 < len(TIERS) else None,
                "open_risk_pct": round(open_risk / acct.equity * 100, 2) if acct.equity else 0.0,
                **st,
                "daily_pnl": round(daily, 2), "daily_limit": round(daily_limit, 2), "halted": halted,
                "daily_loss_limit_enabled": daily_loss_pct > 0,
                "drawdown_halt_enabled": self.s.float("RISK_DRAWDOWN_HALT_PCT") > 0,
                "halt_reason": ("drawdown limit reached" if st["halted"] else "daily loss limit reached") if halted else "",
                "ladder": [{"name": x.name, "min_equity": x.min_equity, "risk_pct": x.risk_pct} for x in TIERS]}

    # ---------------------------------------------------------------- sizing
    def _open_risk(self, broker: Broker, positions: List[Position], pend: List[Pending]) -> float:
        total = 0.0
        for p in positions:
            if p.sl:
                total += self._risk_amount(broker, p.symbol, p.price_open if self._sl_beyond_entry(p) else p.price_current, p.sl, p.volume)
        for o in pend:
            if o.sl:
                total += self._risk_amount(broker, o.symbol, o.price, o.sl, o.volume)
        return total

    @staticmethod
    def _sl_beyond_entry(p: Position) -> bool:
        return (p.sl < p.price_open) if p.side == "buy" else (p.sl > p.price_open)

    @staticmethod
    def _risk_amount(broker: Broker, symbol: str, entry: float, sl: float, volume: float) -> float:
        try:
            return broker.symbol_info(symbol).loss_per_lot(entry, sl) * volume
        except Exception:
            return 0.0

    @staticmethod
    def volume_for(info: SymbolInfo, entry: float, sl: float, risk_amount: float) -> float:
        lpl = info.loss_per_lot(entry, sl)
        if lpl <= 0:
            return 0.0
        raw = risk_amount / lpl
        steps = math.floor(raw / info.vol_step + 1e-9)
        return round(min(steps * info.vol_step, info.vol_max), 8)

    @staticmethod
    def _price_to_tick(price: float, info: SymbolInfo) -> float:
        tick_size = info.tick_size or info.point
        if tick_size <= 0:
            return round(price, info.digits)
        return round(round(price / tick_size) * tick_size, info.digits)

    @staticmethod
    def _tp_boundary(entry: float, sl: float, side: str, min_rr: float, info: SymbolInfo) -> float:
        """Return the nearest tick-valid TP that meets min_rr, rounding outward."""
        distance = abs(entry - sl) * min_rr
        target = entry + distance if side == "buy" else entry - distance
        tick_size = info.tick_size or info.point
        if tick_size <= 0:
            return round(target, info.digits)
        ticks = target / tick_size
        rounded_ticks = math.ceil(ticks - 1e-12) if side == "buy" else math.floor(ticks + 1e-12)
        return round(rounded_ticks * tick_size, info.digits)

    # ---------------------------------------------------------------- review
    def review(self, p: Proposal, broker: Broker, acct: Account, positions: List[Position], pend: List[Pending],
               atr_value: float) -> Verdict:
        v = Verdict(ok=False)
        r = v.reasons
        s = self.s
        symbols = s.symbols
        if p.symbol not in symbols:
            r.append(f"{p.symbol} is not in the watchlist ({', '.join(symbols)})")
            return v
        if p.side not in ("buy", "sell"):
            r.append("side must be buy or sell")
            return v
        entry_mode = s.str("AGENT_ENTRY_MODE")
        if entry_mode == "market_only" and p.type != "place_market":
            r.append("entry mode is market_only; pending limit and stop entries are disabled")
            return v
        if entry_mode == "pending_only" and p.type == "place_market":
            r.append("entry mode is pending_only; market entries are disabled")
            return v
        summ = self.summary(acct, positions, pend, broker)
        if summ["halted"]:
            r.append(f"trading halted: {summ['halt_reason']}")
            return v
        info = broker.symbol_info(p.symbol)
        bid, ask = info.bid, info.ask
        a = atr_value or abs(ask - bid) * 10 or info.point * 50
        px = ask if p.side == "buy" else bid
        proposed_entry = px if p.type == "place_market" else p.entry
        if proposed_entry is None or proposed_entry <= 0:
            r.append("entry price is required")
            return v
        entry = self._price_to_tick(proposed_entry, info)
        if p.sl is None or p.sl <= 0:
            r.append("a stop loss is required on every entry")
            return v
        sl = self._price_to_tick(p.sl, info)
        tp = self._price_to_tick(p.tp, info) if p.tp else 0.0
        # kind of pending order from where entry sits relative to market
        if p.type == "place_market":
            kind = "market"
        elif p.type == "place_limit":
            kind = "buy_limit" if p.side == "buy" else "sell_limit"
            ok = entry < ask - info.stops_level if p.side == "buy" else entry > bid + info.stops_level
            if not ok:
                r.append(f"a {p.side} limit must sit {'below' if p.side == 'buy' else 'above'} the current price ({ask if p.side == 'buy' else bid})")
        elif p.type == "place_stop":
            kind = "buy_stop" if p.side == "buy" else "sell_stop"
            ok = entry > ask + info.stops_level if p.side == "buy" else entry < bid - info.stops_level
            if not ok:
                r.append(f"a {p.side} stop must sit {'above' if p.side == 'buy' else 'below'} the current price")
        else:
            r.append(f"unknown order type {p.type}")
            return v
        v.kind, v.entry = kind, entry
        if (p.side == "buy" and sl >= entry) or (p.side == "sell" and sl <= entry):
            r.append("stop loss is on the wrong side of entry")
        dist = abs(entry - sl)
        if dist <= 0:
            r.append("stop loss must be at least one broker tick from entry")
        if dist < 0.3 * a:
            r.append(f"stop is too tight ({dist / a:.2f} ATR, minimum 0.3)")
        if dist > 6 * a:
            r.append(f"stop is too wide ({dist / a:.1f} ATR, maximum 6)")
        if dist < info.stops_level:
            r.append("stop is inside the broker's minimum distance")
        if kind != "market" and abs(entry - (ask + bid) / 2) > s.float("RISK_MAX_ENTRY_ATR") * a:
            r.append(f"entry is more than {s.float('RISK_MAX_ENTRY_ATR'):.0f} ATR from price")
        if (ask - bid) > s.float("RISK_MAX_SPREAD_ATR") * a:
            r.append("spread is too wide for an entry")
        if tp:
            if (p.side == "buy" and tp <= entry) or (p.side == "sell" and tp >= entry):
                r.append("take profit is on the wrong side of entry")
            elif dist > 0 and abs(tp - entry) / dist < s.float("RISK_MIN_RR"):
                boundary = self._tp_boundary(entry, sl, p.side, s.float("RISK_MIN_RR"), info)
                direction = "at least" if p.side == "buy" else "at most"
                r.append(
                    f"reward to risk {abs(tp - entry) / dist:.2f} is below the minimum "
                    f"{s.float('RISK_MIN_RR'):.2f} after broker tick-size rounding; "
                    f"the {p.side} TP must be {direction} {boundary:.{info.digits}f}, "
                    "or drop the trade"
                )
        v.entry, v.sl, v.tp = entry, sl, tp
        tier = self.tier_for(acct.equity)
        same_symbol = [x for x in positions if x.symbol == p.symbol] + [x for x in pend if x.symbol == p.symbol]
        if len(positions) + len(pend) >= summ["max_active_orders"]:
            r.append(f"the active-order limit allows {summ['max_active_orders']} open position(s) and pending order(s) combined")
        if kind == "market" and len(positions) + 1 > summ["max_positions"]:
            r.append(f"the effective limit allows {summ['max_positions']} open position(s)")
        if len(pend) + (1 if kind != "market" else 0) > summ["max_pending"] and kind != "market":
            r.append(f"the effective limit allows {summ['max_pending']} pending order(s)")
        if len(same_symbol) >= summ["max_positions_per_symbol"]:
            r.append(f"the effective per-symbol limit allows {summ['max_positions_per_symbol']} position(s) or order(s) on {p.symbol}")
        cap = self.max_risk_pct(acct.equity, p.skills, summ["dd_mult"])
        want = min(p.risk_pct, cap) if p.risk_pct else cap
        if p.risk_pct and p.risk_pct > cap:
            v.notes.append(f"risk reduced from {p.risk_pct}% to {cap}% (tier, drawdown and skill track record)")
        risk_amount = acct.equity * want / 100
        vol = self.volume_for(info, entry, sl, risk_amount)
        if vol < info.vol_min:
            r.append(f"minimum lot {info.vol_min} would risk about "
                     f"{info.loss_per_lot(entry, sl) * info.vol_min / acct.equity * 100:.2f}% of equity, above the {want:.2f}% budget")
        else:
            real_risk = info.loss_per_lot(entry, sl) * vol
            open_risk = self._open_risk(broker, positions, pend)
            if (open_risk + real_risk) / acct.equity * 100 > summ["max_open_risk_pct"]:
                r.append(f"total open risk would exceed the effective {summ['max_open_risk_pct']}% of equity limit")
            v.volume, v.risk_amount, v.risk_pct = vol, round(real_risk, 2), round(real_risk / acct.equity * 100, 3)
        v.ok = not r
        return v
