"""The agent runtime.

Each cycle:  OBSERVE (cheap, every cycle)  ->  gate  ->  PLAN (periodic)  ->  REASON  ->  ADJUST (if the risk engine pushed back)
             ->  EXECUTE (through guardrails)  ->  REFLECT.
Closed trades are reviewed one by one (lessons and playbook edits); every N trades a meta review upgrades the process itself.
Everything is journaled. LLM calls are gated so a free-tier model isn't hammered when nothing has changed.
"""
from __future__ import annotations

import collections
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional

from . import envfile, market, prompts
from . import application_control
from .capabilities import capability_context
from .broker import Broker, BrokerError, PENDING_KINDS
from .discord_journal import DiscordJournalDelivery
from .events import EventBus
from .journal import Journal, slugify
from .llm import LLMError, LLMManager
from .risk import Proposal, RiskEngine
from .settings import Settings, validate_tunables
from .world import WorldIntel, normalize_world_brief, world_brief_validation_error
from execution_mode import ExecutionModeError, get_execution_mode
from shared_order_lock import account_order_lock

log = logging.getLogger("cthulu_agent")
ENTRY = ("place_limit", "place_stop", "place_market")
MANAGE = ("modify_order", "cancel_order", "modify_position", "close_position")
TODO_T = ("add_todo", "complete_todo")
META_EVERY_TRADES = 8


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
        return v if v == v and abs(v) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _utc(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ts or time.time()))


class AgentRuntime:
    def __init__(self, settings: Settings, broker: Broker, journal: Journal, llm: LLMManager, risk: RiskEngine,
                 world: WorldIntel, bus: EventBus):
        self.s, self.broker, self.j, self.llm, self.risk, self.world, self.bus = settings, broker, journal, llm, risk, world, bus
        config_path = Path(os.environ.get("CTHULU_CONFIG_PATH", Path(__file__).resolve().parents[1] / "config.json")).resolve()
        with config_path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
        dynamic_config = config.get("dynamic_sltp")
        if not isinstance(dynamic_config, dict):
            raise ValueError(f"dynamic_sltp must be an object in {config_path}")
        from cthulu.risk.dynamic_sltp import DynamicSLTPManager

        self.dynamic_sltp_manager = DynamicSLTPManager(dynamic_config) if dynamic_config.get("enabled") is True else None
        self.discord_journal = DiscordJournalDelivery(journal, world, tuple(self.s.symbols))
        self.lock = threading.RLock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.started = 0.0
        self.paused = bool(self.j.kv_get("paused", False))
        self.phase, self.phase_detail, self.cycle = "idle", "", 0
        self.proposals: Dict[int, Dict[str, Any]] = {}
        self._pid = 0
        self.last_obs: Optional[Dict[str, Any]] = None
        self.last_think, self.think_count = 0.0, 0
        self.think_times: Deque[float] = collections.deque(maxlen=200)
        self.last_fp: Dict[str, str] = {}
        self.next_think_at = 0.0
        self.force_think = ""
        self.force_plan = False
        self.last_plan_think = -999
        self.last_plan_day = ""
        self.last_think_reason = ""
        self.backoff_until = 0.0
        self._last_sys_msg: Dict[str, float] = {}
        self.rejections: Deque[Dict[str, Any]] = collections.deque(maxlen=10)
        self.review_fail: Dict[int, int] = {}
        self.stand_down_until = 0.0
        self.closed_since_think = False
        self._emergency_done: set = set()
        self.expiries: Dict[str, float] = {str(k): v for k, v in (self.j.kv_get("expiries", {}) or {}).items()}
        self._symbol_cursor = 0

    # ================================================================ lifecycle
    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self._stop.clear()
        self.started = time.time()
        self.discord_journal.start()
        self.thread = threading.Thread(target=self._loop, name="cthulu-agent", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self.discord_journal.stop()

    def _loop(self) -> None:
        self.bus.emit(
            "alert",
            level="info",
            message=f"Agent runtime started · broker={self.broker.name} · symbols={','.join(self.s.symbols)}",
        )
        while not self._stop.is_set():
            try:
                if self.paused:
                    self._phase("paused")
                else:
                    self.run_cycle()
            except BrokerError as e:
                self._sys("broker", f"Broker problem: {e}")
            except Exception as e:  # never let the loop die
                log.exception("cycle failed")
                self._sys("cycle", f"Cycle error: {type(e).__name__}: {e}")
            self._wake.wait(timeout=self.s.int("AGENT_CYCLE_SECONDS"))
            self._wake.clear()

    def wake(self) -> None:
        self._wake.set()

    # ================================================================ small helpers
    def _phase(self, phase: str, detail: str = "") -> None:
        self.phase, self.phase_detail = phase, detail
        self.bus.emit("phase", phase=phase, detail=detail, cycle=self.cycle)

    def note(self, kind: str, title: str, body: str = "", **kw: Any) -> Dict[str, Any]:
        if kind == "system":
            message = f"{title}: {body}" if body else title
            self.bus.emit("alert", level="info", message=message)
            return {"id": None, "ts": time.time(), "kind": kind, "title": title, "body": body}
        e = self.j.add(kind, title, body, cycle=self.cycle, **kw)
        self.discord_journal.enqueue(e)
        self.bus.emit("journal", entry=e)
        return e

    def _sys(self, key: str, msg: str) -> None:
        """Notify about a system problem without adding it to the journal."""
        if time.time() - self._last_sys_msg.get(key, 0) > 600:
            self._last_sys_msg[key] = time.time()
            self.bus.emit("alert", level="warn", message=msg)

    def effective_autonomy(self) -> tuple:
        a = self.s.str("AGENT_AUTONOMY")
        if a == "autonomous" and getattr(self.broker, "is_real", False) and os.environ.get("LIVE_RUN_CONFIRM") != "1":
            return "approval", "Live account detected. Set LIVE_RUN_CONFIRM=1 in .env to allow fully autonomous trading."
        return a, ""

    def _locked(self, fn: Callable, *a: Any, **k: Any) -> Any:
        with self.lock:
            return fn(*a, **k)

    # ================================================================ observe
    def observe(self) -> Dict[str, Any]:
        b, tf = self.broker, self.s.str("AGENT_TIMEFRAME")
        if self.s.raw("AGENT_SYMBOLS").strip() == "*":
            symbols = b.tradeable_symbols(self.s.float("AGENT_SYMBOL_MAX_SPREAD_PCT"))
            if not symbols:
                raise BrokerError("No tradable symbols currently pass the dynamic-universe filters")
            self.s.set_dynamic_symbols(symbols)
            self.discord_journal.symbols = tuple(symbols)
        syms = self.s.symbols
        if not syms:
            raise BrokerError("The agent has no symbols to observe")
        scan_limit = self.s.int("AGENT_SYMBOL_SCAN_LIMIT")
        if len(syms) > scan_limit:
            start = self._symbol_cursor % len(syms)
            scan_syms = [syms[(start + offset) % len(syms)] for offset in range(scan_limit)]
            self._symbol_cursor = (start + scan_limit) % len(syms)
        else:
            scan_syms = syms
            self._symbol_cursor = 0
        infos, info_errors = {}, {}
        for sym in scan_syms:
            try:
                infos[sym] = b.symbol_info(sym)
            except BrokerError as exc:
                info_errors[sym] = str(exc)
        acct, pos, pend = b.account(), b.positions(), b.pending()
        if not (self.s.bool("AGENT_MANAGE_FOREIGN")) and getattr(b, "MAGIC", None):
            pos = [p for p in pos if p.magic == b.MAGIC]
            pend = [o for o in pend if o.magic == b.MAGIC]
        snaps = {}
        for sym in scan_syms:
            try:
                if sym not in infos:
                    snaps[sym] = {"symbol": sym, "error": info_errors.get(sym, "symbol unavailable")}
                    continue
                info = infos[sym]
                htf = b.candles(sym, "H4", 120) if tf != "H4" else None
                snaps[sym] = market.snapshot(b.candles(sym, tf, 300), sym, tf, info.bid, info.ask, info.digits, htf=htf)
            except Exception as e:
                snaps[sym] = {"symbol": sym, "error": str(e)[:160]}
        risk = self.risk.summary(acct, pos, pend, b)
        self.j.equity_add(acct.balance, acct.equity)
        return {"acct": acct, "positions": pos, "pending": pend, "snaps": snaps, "infos": infos, "risk": risk, "ts": time.time()}

    # ================================================================ reconcile broker state with the journal
    def reconcile(self, obs: Dict[str, Any]) -> None:
        pos = {p.ticket: p for p in obs["positions"]}
        pend = {o.ticket: o for o in obs["pending"]}
        rows = self.j.trades(status="open,pending", limit=300)
        known = {r["ticket"] for r in rows}
        for t in rows:
            tk = t["ticket"]
            if t["status"] == "pending":
                if tk in pos:
                    p = pos[tk]
                    risk_amt = t["risk_amount"] or self.risk._risk_amount(self.broker, p.symbol, p.price_open, p.sl, p.volume)
                    self.j.trade_update(t["id"], status="open", entry=p.price_open, ts_open=time.time(), volume=p.volume, risk_amount=risk_amt)
                    self.note("trade_open", f"Filled {p.side} {p.symbol} {p.volume} @ {p.price_open}", t["thesis"] or "", symbol=p.symbol,
                              ref={"ticket": tk}, tags=t["skills"] or [])
                    self.bus.emit("trade", kind="filled", ticket=tk, symbol=p.symbol)
                elif tk not in pend:
                    d = self.broker.closed_deal(tk)
                    if d:
                        self._on_closed(t, d)
                    else:
                        self.j.trade_update(t["id"], status="cancelled", ts_close=time.time())
                        self.expiries.pop(str(tk), None)
                        self.note("action", f"Order #{tk} on {t['symbol']} is gone (cancelled or expired)", symbol=t["symbol"], ref={"ticket": tk})
            elif t["status"] == "open":
                if tk in pos:
                    p = pos[tk]
                    if (p.sl, p.tp) != (t["sl"], t["tp"]):
                        self.j.trade_update(t["id"], sl=p.sl, tp=p.tp)
                else:
                    d = self.broker.closed_deal(tk)
                    if d:
                        self._on_closed(t, d)
                    elif t["close_checks"] >= 3:
                        self.j.trade_update(t["id"], status="closed", ts_close=time.time(), pnl=0.0, r_multiple=0.0, reviewed=1)
                        self.note("system", f"Could not find closing deal for #{tk}; marked closed with unknown result", symbol=t["symbol"])
                    else:
                        self.j.trade_update(t["id"], close_checks=t["close_checks"] + 1)
        for tk, p in pos.items():  # positions opened outside the agent
            if tk not in known:
                self.j.trade_add(symbol=p.symbol, side=p.side, volume=p.volume, entry=p.price_open, sl=p.sl, tp=p.tp, ticket=tk, status="open",
                                 kind="external", skills=[], thesis="Opened outside the agent", source="external",
                                 risk_amount=self.risk._risk_amount(self.broker, p.symbol, p.price_open, p.sl, p.volume) if p.sl else 0)
                self.note("trade_open", f"Adopted external {p.side} {p.symbol} {p.volume} @ {p.price_open}", symbol=p.symbol, ref={"ticket": tk})
        for tk, o in pend.items():
            if tk not in known:
                self.j.trade_add(symbol=o.symbol, side="buy" if o.kind.startswith("buy") else "sell", volume=o.volume, entry=o.price, sl=o.sl, tp=o.tp,
                                 ticket=tk, status="pending", kind=o.kind, skills=[], thesis="Placed outside the agent", source="external")

    def _on_closed(self, t: Dict[str, Any], d: Dict[str, Any]) -> None:
        pnl = float(d["pnl"])
        ra = t["risk_amount"] or 0
        r = pnl / ra if ra else 0.0
        self.j.trade_update(t["id"], status="closed", ts_close=d.get("time_close") or time.time(), exit=d["price_close"], pnl=round(pnl, 2),
                            r_multiple=round(r, 3), reviewed=1 if t["source"] == "external" else 0)
        self.expiries.pop(str(t["ticket"]), None)
        changes = self.j.skill_record(t["skills"] or [], pnl, r) if t["source"] != "external" else []
        self.note("trade_close", f"Closed {t['side']} {t['symbol']}: {pnl:+.2f} ({r:+.2f}R)", t["thesis"] or "", symbol=t["symbol"],
                  tags=t["skills"] or [], ref={"ticket": t["ticket"], "pnl": pnl, "r": r})
        for c in changes:
            self.note("lesson", c, "Automatic, based on recorded results", tags=["auto"])
        self.closed_since_think = True
        self.bus.emit("trade", kind="closed", ticket=t["ticket"], symbol=t["symbol"], pnl=pnl, r=r)

    def housekeeping(self, obs: Dict[str, Any]) -> None:
        """Expire stale pending orders and make sure every position has a protective stop."""
        now = time.time()
        for o in obs["pending"]:
            exp = self.expiries.get(str(o.ticket))
            if exp and now >= exp:
                try:
                    with self.lock:
                        self.broker.cancel_pending(o.ticket)
                    self.note("action", f"Order #{o.ticket} {o.kind} {o.symbol} @ {o.price} expired and was cancelled", symbol=o.symbol, ref={"ticket": o.ticket})
                except BrokerError as e:
                    self._sys("expire", f"Could not cancel expired order #{o.ticket}: {e}")
        may_manage = self.effective_autonomy()[0] != "observe"
        positions = self._management_positions()
        if may_manage and get_execution_mode() == "agentic":
            self._manage_dynamic_sltp(obs, positions)
            positions = self._management_positions()
        if self.s.bool("AGENT_EMERGENCY_SL") and may_manage:
            for p in positions:
                if p.sl or p.ticket in self._emergency_done:
                    continue
                try:
                    info, snap = self._position_market_data(p, obs)
                    atr = _num(snap.get("atr"))
                    if not atr or atr <= 0:
                        continue
                    sl = round(p.price_open - 2 * atr if p.side == "buy" else p.price_open + 2 * atr, info.digits)
                    with self.lock:
                        self.broker.modify_position(p.ticket, sl=sl, tp=None)
                    self._emergency_done.add(p.ticket)
                    self.note("action", f"Attached emergency stop {sl} to unprotected {p.side} {p.symbol} #{p.ticket}", "2 ATR from entry", symbol=p.symbol, ref={"ticket": p.ticket})
                except BrokerError as e:
                    self._sys("esl", f"Could not set emergency stop on #{p.ticket}: {e}")
                except Exception as e:
                    log.exception("Emergency stop failed for position %s", p.ticket)
                    self._sys("esl", f"Could not set emergency stop on #{p.ticket}: {e}")
        if self.expiries:
            self.j.kv_set("expiries", self.expiries)

    def _management_positions(self):
        positions = self.broker.positions()
        if not self.s.bool("AGENT_MANAGE_FOREIGN"):
            magic = getattr(self.broker, "MAGIC", None)
            if magic is not None:
                positions = [position for position in positions if position.magic == magic]
        return positions

    def _position_market_data(self, position, obs: Dict[str, Any]):
        info = obs.get("infos", {}).get(position.symbol)
        if info is None:
            info = self.broker.symbol_info(position.symbol)
        snap = obs.get("snaps", {}).get(position.symbol)
        if not snap or not _num(snap.get("atr")):
            timeframe = self.s.str("AGENT_TIMEFRAME")
            candles = self.broker.candles(position.symbol, timeframe, 120)
            snap = market.snapshot(candles, position.symbol, timeframe, info.bid, info.ask, info.digits)
        return info, snap

    def _manage_dynamic_sltp(self, obs: Dict[str, Any], positions) -> None:
        if not self.dynamic_sltp_manager:
            return
        acct = obs.get("acct") or self.broker.account()
        balance, equity = float(acct.balance), float(acct.equity)
        initial_balance = float(self.j.kv_get("equity_start") or balance)
        drawdown_pct = float((obs.get("risk") or {}).get("drawdown_pct") or 0.0)
        for position in positions:
            try:
                info, snap = self._position_market_data(position, obs)
                atr = _num(snap.get("atr"))
                if not atr or atr <= 0:
                    self._sys(f"dynamic-atr:{position.symbol}", f"Dynamic exits skipped for {position.symbol}: ATR is unavailable.")
                    continue
                symbol_info = info.to_dict()
                symbol_info["name"] = position.symbol
                symbol_info["trade_stops_level"] = (
                    info.stops_level / info.point if info.point > 0 else 0
                )
                current_price = info.bid if position.side == "buy" else info.ask
                if not current_price:
                    current_price = position.price_current
                current_sl = position.sl or None
                current_tp = position.tp or None
                manager = self.dynamic_sltp_manager

                if current_sl is None or current_tp is None:
                    initial = manager.calculate_initial_sltp(
                        ticket=position.ticket,
                        direction=position.side.upper(),
                        entry_price=position.price_open,
                        atr=atr,
                        balance=balance,
                        equity=equity,
                        drawdown_pct=drawdown_pct,
                        initial_balance=initial_balance,
                        symbol_info=symbol_info,
                    )
                    min_distance = max(info.stops_level, info.tick_size, info.point)
                    new_sl = current_sl
                    new_tp = current_tp
                    if current_sl is None:
                        candidate = float(initial["sl"])
                        valid = candidate < current_price - min_distance if position.side == "buy" else candidate > current_price + min_distance
                        if valid:
                            new_sl = candidate
                    if current_tp is None:
                        candidate = float(initial["tp"])
                        valid = candidate > current_price + min_distance if position.side == "buy" else candidate < current_price - min_distance
                        if valid:
                            new_tp = candidate
                    if new_sl != current_sl or new_tp != current_tp:
                        with self.lock:
                            self.broker.modify_position(position.ticket, sl=new_sl, tp=new_tp)
                        self.note(
                            "action",
                            f"Attached configured dynamic protection to {position.side} {position.symbol} #{position.ticket}",
                            initial["reasoning"],
                            symbol=position.symbol,
                            ref={"ticket": position.ticket},
                        )
                        continue
                    if current_sl is None:
                        self._sys(f"dynamic-initial:{position.ticket}", f"Could not place a valid initial stop for #{position.ticket} ({position.symbol}); check broker distance and price.")
                        continue

                update = manager.update_position_sltp(
                    ticket=position.ticket,
                    entry_price=position.price_open,
                    current_price=current_price,
                    side=position.side.upper(),
                    current_sl=current_sl,
                    current_tp=current_tp,
                    atr=atr,
                    balance=balance,
                    equity=equity,
                    drawdown_pct=drawdown_pct,
                    initial_balance=initial_balance,
                    symbol_info=symbol_info,
                )
                if not update.get("update_sl") or update.get("new_sl") is None:
                    continue
                new_sl = float(update["new_sl"])
                improves = current_sl is None or (new_sl > current_sl if position.side == "buy" else new_sl < current_sl)
                min_distance = max(info.stops_level, info.tick_size, info.point)
                valid = new_sl < current_price - min_distance if position.side == "buy" else new_sl > current_price + min_distance
                if not improves or not valid:
                    self._sys(f"dynamic-skip:{position.ticket}", f"Dynamic stop update skipped for #{position.ticket}: it would not tighten safely.")
                    continue
                with self.lock:
                    self.broker.modify_position(position.ticket, sl=new_sl, tp=None)
                self.note(
                    "action",
                    f"Dynamic stop {update.get('action', 'tightened')} for {position.side} {position.symbol} #{position.ticket}",
                    update.get("reasoning", ""),
                    symbol=position.symbol,
                    ref={"ticket": position.ticket},
                )
            except BrokerError as e:
                self._sys(f"dynamic-broker:{position.ticket}", f"Dynamic exit update failed for #{position.ticket}: {e}")
            except Exception as e:
                log.exception("Dynamic exit update failed for position %s", position.ticket)
                self._sys(f"dynamic-error:{position.ticket}", f"Dynamic exit update failed for #{position.ticket}: {e}")

    # ================================================================ context for prompts
    def _compact_snap(self, s: Dict[str, Any]) -> Dict[str, Any]:
        if "error" in s:
            return s
        keep = ["symbol", "tf", "price", "bid", "ask", "spread_atr", "atr", "trend", "efficiency", "regime", "volatility", "session", "htf", "range20"]
        out = {k: s[k] for k in keep if k in s}
        out["levels"] = [{k: lv[k] for k in ("kind", "price", "dist_atr", "count") if k in lv} for lv in s["levels"][:8]]
        out["sweeps"] = s["sweeps"]
        out["last_candles_tohlc"] = s["candles"][-10:]
        return out

    def context(self, obs: Dict[str, Any], history: int = 10) -> Dict[str, Any]:
        trades = {t["ticket"]: t for t in self.j.trades(status="open,pending", limit=100)}
        r = obs["risk"]
        pos = []
        for p in obs["positions"]:
            t = trades.get(p.ticket, {})
            ra = t.get("risk_amount") or 0
            pos.append({"ticket": p.ticket, "symbol": p.symbol, "side": p.side, "volume": p.volume, "open": p.price_open, "sl": p.sl, "tp": p.tp,
                        "now": p.price_current, "profit": round(p.profit, 2), "r_now": round(p.profit / ra, 2) if ra else None,
                        "thesis": (t.get("thesis") or "")[:160], "invalidation": (t.get("invalidation") or "")[:120], "skills": t.get("skills") or []})
        pend = []
        for o in obs["pending"]:
            t = trades.get(o.ticket, {})
            exp = self.expiries.get(str(o.ticket))
            pend.append({"ticket": o.ticket, "symbol": o.symbol, "type": o.kind, "volume": o.volume, "price": o.price, "sl": o.sl, "tp": o.tp,
                         "expires_in_min": round((exp - time.time()) / 60) if exp else None, "thesis": (t.get("thesis") or "")[:160],
                         "skills": t.get("skills") or []})
        mt = next((s["candles"][-1][0] for s in obs["snaps"].values() if s.get("candles")), None)
        wb = self.world.brief
        try:
            from legacy_bridge import canonical_agent_symbol, latest_legacy_context
            legacy_data = latest_legacy_context()
            for record in legacy_data:
                record["agent_symbol"] = canonical_agent_symbol(record.get("symbol", ""))
        except (OSError, ValueError, sqlite3.Error) as exc:
            log.exception("Could not read the Legacy analysis bridge")
            legacy_data = {"error": str(exc)[:200]}
        return {
            "time_utc": _utc(mt), "account": {"balance": round(obs["acct"].balance, 2), "equity": round(obs["acct"].equity, 2), "currency": obs["acct"].currency},
            "risk_engine": {k: r[k] for k in ("tier", "risk_pct", "max_positions", "max_positions_per_symbol", "max_pending", "max_active_orders",
                                              "max_open_risk_pct", "open_risk_pct", "drawdown_pct", "daily_pnl", "daily_limit",
                                              "daily_loss_limit_enabled", "drawdown_halt_enabled", "halted", "next_tier", "next_tier_at")},
            "positions": pos, "pending_orders": pend,
            "markets": {k: self._compact_snap(v) for k, v in obs["snaps"].items()},
            "legacy_analysis": legacy_data,
            "plan": self.j.kv_get("current_plan"),
            "todos": [{"id": t["id"], "title": t["title"], "detail": t["detail"][:140], "priority": t["priority"]} for t in self.j.todos("open", 12)],
            "playbook": [{"name": p["name"], "kind": p["kind"], "status": p["status"], "uses": p["uses"], "expectancy_r": p["expectancy_r"],
                          "text": p["body"][:420]} for p in self.j.playbook(include_retired=False)],
            "recent_rejections": list(self.rejections)[-5:],
            "world_brief": ({"summary": wb.get("summary"), "themes": wb.get("themes", [])[:5], "event_risk": wb.get("event_risk", [])[:4],
                             "ts": wb.get("ts"), "stand_down": bool(self.stand_down_until > time.time())} if wb else "no world brief digested yet"),
            "world_status": self.world.public_config(),
            "strategy_controls": capability_context(self.s),
            "scaling_notes": self.j.kv_get("scaling_notes", ""), "process_notes": self.j.kv_get("process_notes", ""),
            "journal_history": "<journal_history>\n" + self.j.digest(history) + "\n</journal_history>",
        }

    # ================================================================ the gate: should the LLM think now?
    def should_think(self, obs: Dict[str, Any]) -> str:
        now = time.time()
        if self.force_think:
            return self.force_think
        if now < self.backoff_until:
            return ""
        per_hour = sum(1 for t in self.think_times if now - t < 3600)
        if per_hour >= self.s.int("AGENT_MAX_THINKS_PER_HOUR"):
            return ""
        gap = now - self.last_think
        book = bool(obs["positions"] or obs["pending"])
        fps = {k: market.fingerprint(v) for k, v in obs["snaps"].items()}
        if not self.last_think:
            return "first pass"
        if self.closed_since_think and gap >= 20:
            return "a trade just closed"
        if book and gap >= self.s.int("AGENT_MANAGE_INTERVAL"):
            return "managing the open book"
        if self.next_think_at and now >= self.next_think_at and gap >= 45:
            return "agent-scheduled check"
        if fps != self.last_fp and gap >= max(60, self.s.int("AGENT_MANAGE_INTERVAL")):
            return "market structure changed"
        if gap >= self.s.int("AGENT_IDLE_THINK_MINUTES") * 60:
            return "scheduled idle check"
        return ""

    # ================================================================ cycle
    def run_cycle(self) -> None:
        self.cycle += 1
        self._phase("observe")
        if self.broker.name == "paper":
            self.broker.advance(self.s.int("PAPER_SPEED"))
        obs = self._locked(self.observe)
        self._locked(self.reconcile, obs)
        self._locked(self.housekeeping, obs)
        self.last_obs = obs
        self.bus.emit("state", ts=time.time())
        self._expire_proposals()
        if time.time() < self.backoff_until:
            wait = max(1, round(self.backoff_until - time.time()))
            self._phase("waiting", f"LLM unavailable, retrying in {wait}s")
            return
        if not self.llm.configured:
            self._phase("waiting", "Add an LLM API key in Settings to start reasoning")
            self._sys("nokey", "No LLM API key configured. The agent is observing and protecting positions but cannot reason until a key is added in Settings.")
            return
        try:
            self._maybe_world()
            if time.time() < self.backoff_until:
                return
            self._review_one_trade(obs)
            self._maybe_meta_review()
            why = self.should_think(obs)
            if why:
                self.think(obs, why)
            else:
                self._phase("idle", self._idle_detail())
        except LLMError as e:
            wait = 180 if e.status == 429 else 60
            self.backoff_until = time.time() + wait
            self._phase("waiting", f"LLM unavailable, retrying in {wait}s")
            self._sys("llm", f"LLM call failed ({self.llm.active_provider()}): {e}. Existing orders keep their stops; retrying in {wait}s.")

    def _idle_detail(self) -> str:
        if self.next_think_at > time.time():
            return f"next look in {max(1, round((self.next_think_at - time.time()) / 60))} min"
        return "watching"

    # ================================================================ think = plan + reason + adjust + execute + reflect
    def think(self, obs: Dict[str, Any], why: str) -> None:
        self.last_think_reason = why
        self.force_think = ""
        self.think_count += 1
        self.think_times.append(time.time())
        today = time.strftime("%Y-%m-%d", time.gmtime())
        need_plan = (self.force_plan or not self.j.kv_get("current_plan") or self.think_count - self.last_plan_think >= self.s.int("AGENT_PLAN_EVERY")
                     or today != self.last_plan_day or self.closed_since_think)
        if need_plan:
            self._phase("plan", why)
            self.phase_plan(obs)
            self.force_plan = False
        self._phase("reason", why)
        ctx = self.context(obs)
        out = self.llm.chat_json(prompts.reason_prompt(ctx), purpose="reason", max_tokens=1600)
        out = out if isinstance(out, dict) else {}
        actions = self._clean_actions(out.get("actions"))
        title = (out.get("assessment") or "No assessment")[:280]
        idea_notes = []
        for action in actions:
            if action.get("type") not in ("place_limit", "place_stop", "place_market"):
                continue
            symbol = str(action.get("symbol") or "")
            side = str(action.get("side") or "").upper()
            order_type = str(action["type"]).removeprefix("place_").replace("_", " ").upper()
            details = [f"{side} {order_type} {symbol}".strip()]
            for key, label in (("entry", "entry"), ("sl", "stop"), ("tp", "target")):
                if action.get(key) is not None:
                    details.append(f"{label} {action[key]}")
            if action.get("thesis"):
                details.append(f"thesis: {action['thesis']}")
            if action.get("invalidation"):
                details.append(f"invalidation: {action['invalidation']}")
            idea_notes.append("Proposed setup (not execution confirmation): " + "; ".join(details) + ".")
        journal_body = (str(out.get("journal") or "") +
                        f"\n\nTrigger: {why}. Confidence: {out.get('confidence', '?')}.")
        if idea_notes:
            journal_body += "\n\n" + "\n".join(idea_notes)
        journal_symbol = next((str(action.get("symbol")) for action in actions if action.get("symbol")), "")
        self.note("reason", title, journal_body, symbol=journal_symbol)
        self._phase("execute", f"{len([a for a in actions if a['type'] != 'hold'])} action(s)")
        results, rejected = self.execute(actions, obs, source="agent")
        if rejected and any(r.get("fixable", True) for r in rejected):
            self._phase("adjust", f"{len(rejected)} rejected by risk engine")
            adj = self.llm.chat_json(prompts.adjust_prompt(self.context(obs, history=4), rejected), purpose="adjust", max_tokens=1200)
            fixed = self._clean_actions((adj or {}).get("actions") if isinstance(adj, dict) else None)
            if isinstance(adj, dict) and adj.get("note"):
                self.note("reason", "Adjusted after risk review", str(adj["note"]))
            if fixed:
                obs2 = self._locked(self.observe)
                r2, rej2 = self.execute(fixed, obs2, source="agent")
                results += r2
        executed = [r for r in results if r.get("ok") and r["action"] not in ("hold", "add_todo", "complete_todo")]
        self.last_think = time.time()
        self.last_fp = {k: market.fingerprint(v) for k, v in obs["snaps"].items()}
        self.closed_since_think = False
        nxt = _num(out.get("next_check_minutes"))
        self.next_think_at = time.time() + max(1.0, min(60.0, nxt or 15.0)) * 60
        if executed:
            self._phase("reflect")
            self.reflect(obs, results)
        self._phase("idle", self._idle_detail())

    def phase_plan(self, obs: Dict[str, Any]) -> None:
        ctx = self.context(obs, history=14)
        out = self.llm.chat_json(prompts.plan_prompt(ctx), purpose="plan", max_tokens=1400)
        if not isinstance(out, dict):
            return
        plan = {"focus": str(out.get("focus", ""))[:300], "bias": out.get("bias") if isinstance(out.get("bias"), dict) else {},
                "watch": (out.get("watch") or [])[:6] if isinstance(out.get("watch"), list) else [], "risks": (out.get("risks") or [])[:5]
                if isinstance(out.get("risks"), list) else [], "notes": str(out.get("notes", ""))[:400], "ts": time.time()}
        self.j.kv_set("current_plan", plan)
        self.last_plan_think, self.last_plan_day = self.think_count, time.strftime("%Y-%m-%d", time.gmtime())
        self._apply_todo_ops(out.get("todos"), source="agent")
        body = "\n".join(f"- {k}: {v}" for k, v in plan["bias"].items()) + ("\n" + "\n".join(f"- watch {w.get('symbol')} {w.get('level')}: {w.get('why')}"
                                                                                           for w in plan["watch"] if isinstance(w, dict)))
        self.note("plan", plan["focus"] or "New plan", body + (f"\n{plan['notes']}" if plan["notes"] else ""))
        self.bus.emit("plan", plan=plan)

    def reflect(self, obs: Dict[str, Any], results: List[Dict[str, Any]]) -> None:
        ctx = self.context(self._locked(self.observe), history=4)
        ctx["just_executed"] = [{k: r[k] for k in ("action", "ok", "detail") if k in r} for r in results]
        out = self.llm.chat_json(prompts.reflect_prompt(ctx), purpose="reflect", max_tokens=800)
        if not isinstance(out, dict):
            return
        self.note("reflection", f"{out.get('verdict', 'reflect')}: {str(out.get('notes', ''))[:240]}", str(out.get("notes", "")))
        self._apply_todo_ops(out.get("todos"), source="agent")
        nxt = _num(out.get("next_check_minutes"))
        if nxt:
            self.next_think_at = time.time() + max(1.0, min(60.0, nxt)) * 60

    # ================================================================ todos
    def _apply_todo_ops(self, ops: Any, source: str = "agent") -> None:
        if not isinstance(ops, dict):
            return
        open_n = len(self.j.todos("open", 50))
        for a in (ops.get("add") or [])[:5]:
            if isinstance(a, dict) and a.get("title") and open_n < 12:
                t = self.j.todo_add(str(a["title"]), str(a.get("detail", "")), int(_num(a.get("priority")) or 2), source=source)
                open_n += 1
                self.bus.emit("todo", todo=t)
        for c in ops.get("complete") or []:
            tid = c.get("id") if isinstance(c, dict) else c
            if _num(tid):
                t = self.j.todo_update(int(tid), status="done", result=str(c.get("result", ""))[:300] if isinstance(c, dict) else "")
                if t:
                    self.bus.emit("todo", todo=t)
        for d in ops.get("drop") or []:
            if _num(d):
                t = self.j.todo_update(int(d), status="dropped")
                if t:
                    self.bus.emit("todo", todo=t)

    # ================================================================ action normalisation
    def _clean_actions(self, raw: Any) -> List[Dict[str, Any]]:
        out = []
        if not isinstance(raw, list):
            return out
        known = {p["name"] for p in self.j.playbook(include_retired=False)}
        for a in raw[:4]:
            if not isinstance(a, dict):
                continue
            t = str(a.get("type", "")).strip().lower()
            if t not in ENTRY + MANAGE + TODO_T + ("hold",):
                continue
            c: Dict[str, Any] = {"type": t}
            for k in ("entry", "sl", "tp", "risk_pct", "fraction"):
                if k in a and _num(a[k]) is not None:
                    c[k] = _num(a[k])
            for k in ("ticket", "id", "priority", "expires_minutes"):
                if k in a and _num(a[k]) is not None:
                    c[k] = int(_num(a[k]))
            for k in ("symbol", "side", "thesis", "invalidation", "reason", "title", "detail", "result"):
                if k in a and a[k] is not None:
                    c[k] = str(a[k])[:400]
            if "symbol" in c:
                c["symbol"] = c["symbol"].strip()
            if "side" in c:
                c["side"] = c["side"].strip().lower()
            sk = a.get("skills") if isinstance(a.get("skills"), list) else []
            c["skills"] = [slugify(x) for x in sk if slugify(x) in known][:3]
            out.append(c)
        return out

    # ================================================================ execute
    def execute(self, actions: List[Dict[str, Any]], obs: Dict[str, Any], source: str) -> tuple:
        results: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []
        autonomy, _why = self.effective_autonomy()
        if source == "chat":
            autonomy = "autonomous" if autonomy != "observe" else "observe"
        try:
            mode = get_execution_mode()
        except ExecutionModeError as exc:
            mode = "disabled"
            mode_error = str(exc)
        else:
            mode_error = ""
        for a in actions:
            t = a["type"]
            if t in ENTRY + MANAGE and mode != "agentic":
                reason = mode_error or f"Agent execution is disabled while execution mode is {mode}."
                results.append({"action": t, "ok": False, "detail": reason})
                rejected.append({"action": a, "reasons": [reason], "fixable": False})
                self.note("action", f"Blocked {t}: execution owner is {mode}", reason, tags=["execution_mode"])
                continue
            try:
                if t == "hold":
                    results.append({"action": "hold", "ok": True, "detail": a.get("reason", "")})
                elif t in TODO_T:
                    self._apply_todo_ops({"add": [a]} if t == "add_todo" else {"complete": [a]}, source=source)
                    results.append({"action": t, "ok": True, "detail": a.get("title") or a.get("id")})
                elif t in ENTRY:
                    results.append(self._entry(a, obs, autonomy, source, rejected))
                else:
                    results.append(self._manage(a, obs, autonomy, source, rejected))
            except BrokerError as e:
                results.append({"action": t, "ok": False, "detail": f"broker error: {e}"})
                rejected.append({"action": a, "reasons": [f"broker error: {e}"], "fixable": False})
                self.note("action", f"{t} failed: {e}", symbol=a.get("symbol", ""))
        for r in rejected:
            self.rejections.append({"action": {k: r["action"].get(k) for k in ("type", "symbol", "side", "entry", "sl", "tp", "ticket")},
                                    "reasons": r["reasons"], "at": _utc()})
        if results:
            self.bus.emit("state", ts=time.time())
        return results, rejected

    def _proposal(self, a: Dict[str, Any]) -> Proposal:
        return Proposal(type=a["type"], symbol=a.get("symbol", ""), side=a.get("side", ""), entry=a.get("entry"), sl=a.get("sl"), tp=a.get("tp"),
                        risk_pct=a.get("risk_pct"), skills=a.get("skills", []), thesis=a.get("thesis", ""), invalidation=a.get("invalidation", ""),
                        expires_minutes=int(a.get("expires_minutes") or 240))

    def _entry(self, a: Dict[str, Any], obs: Dict[str, Any], autonomy: str, source: str, rejected: List[Dict[str, Any]]) -> Dict[str, Any]:
        with account_order_lock():
            fresh_obs = dict(obs)
            fresh_obs["acct"] = self.broker.account()
            fresh_obs["positions"] = self.broker.positions()
            fresh_obs["pending"] = self.broker.pending()
            return self._entry_locked(a, fresh_obs, autonomy, source, rejected)

    def _entry_locked(self, a: Dict[str, Any], obs: Dict[str, Any], autonomy: str, source: str,
                      rejected: List[Dict[str, Any]]) -> Dict[str, Any]:
        t = a["type"]
        p = self._proposal(a)
        snap = obs["snaps"].get(p.symbol)
        if not snap or snap.get("error") or p.symbol not in obs["infos"]:
            reason = f"{p.symbol} is not in the watchlist's current scan or its market data is unavailable"
            self.note("action", f"Rejected: {t} {p.side} {p.symbol}", reason, symbol=p.symbol, tags=["rejected"])
            rejected.append({"action": a, "reasons": [reason], "fixable": False})
            return {"action": t, "ok": False, "detail": reason}
        atr = (obs["snaps"].get(p.symbol) or {}).get("atr", 0.0)
        with self.lock:
            v = self.risk.review(p, self.broker, obs["acct"], obs["positions"], obs["pending"], atr)
        if self.stand_down_until > time.time() and v.ok and source == "agent":
            v.ok, v.reasons = False, ["world brief flagged a stand-down: no new entries for now"]
        label = f"{t.replace('place_', '')} {p.side} {p.symbol} @ {v.entry or p.entry} SL {v.sl or p.sl} TP {v.tp or p.tp}"
        if not v.ok:
            self.note("action", f"Rejected: {label}", "; ".join(v.reasons), symbol=p.symbol, tags=["rejected"], ref={"action": a})
            rejected.append({"action": a, "reasons": v.reasons, "fixable": True})
            return {"action": t, "ok": False, "detail": "; ".join(v.reasons)}
        if autonomy == "observe":
            self.note("action", f"Would place (observe mode): {label}", f"volume {v.volume}, risk {v.risk_pct}%\n{a.get('thesis', '')}", symbol=p.symbol, tags=["observe"])
            return {"action": t, "ok": True, "detail": "observe mode: not sent"}
        if autonomy == "approval":
            return self._queue(a, v, label)
        return self._send_entry(p, v, obs, label)

    def _send_entry(self, p: Proposal, v: Any, obs: Dict[str, Any], label: str) -> Dict[str, Any]:
        info = obs["infos"][p.symbol]
        sl, tp = v.sl, v.tp
        with self.lock:
            if v.kind == "market":
                r = self.broker.place_market(p.symbol, p.side, v.volume, sl, tp, "cthulu-agent")
            else:
                r = self.broker.place_pending(p.symbol, v.kind, v.volume, v.entry, sl, tp, "cthulu-agent")
        tk = r["ticket"]
        snap = obs["snaps"].get(p.symbol, {})
        meta = {"snapshot": {k: snap.get(k) for k in ("trend", "regime", "volatility", "session", "atr", "sweeps")}, "risk_pct": v.risk_pct, "notes": v.notes}
        self.j.trade_add(symbol=p.symbol, side=p.side, volume=v.volume, entry=v.entry, sl=sl, tp=tp, ticket=tk,
                         status="open" if v.kind == "market" else "pending", kind=v.kind, skills=p.skills, thesis=p.thesis,
                         invalidation=p.invalidation, risk_amount=v.risk_amount, meta=meta)
        if v.kind != "market":
            self.expiries[str(tk)] = time.time() + max(5, min(p.expires_minutes, 2880)) * 60
            self.j.kv_set("expiries", self.expiries)
        self.note("action", f"Placed {v.kind} {p.side} {p.symbol} {v.volume} @ {v.entry}",
                  f"SL {sl}, TP {tp or 'none'}, risk {v.risk_pct}% (${v.risk_amount}). Skills: {', '.join(p.skills) or 'none cited'}.\n"
                  f"Thesis: {p.thesis}\nInvalidation: {p.invalidation}" + ("\n" + "; ".join(v.notes) if v.notes else ""),
                  symbol=p.symbol, tags=p.skills, ref={"ticket": tk})
        self.bus.emit("trade", kind="placed", ticket=tk, symbol=p.symbol)
        return {"action": "place_" + ("market" if v.kind == "market" else v.kind.split("_")[1]), "ok": True, "ticket": tk,
                "detail": f"{v.kind} {p.symbol} {v.volume} @ {v.entry} (ticket {tk})"}

    # -- management actions
    def _manage(self, a: Dict[str, Any], obs: Dict[str, Any], autonomy: str, source: str, rejected: List[Dict[str, Any]]) -> Dict[str, Any]:
        t, tk = a["type"], a.get("ticket")
        pos = {p.ticket: p for p in obs["positions"]}
        pend = {o.ticket: o for o in obs["pending"]}

        def reject(msg: str, fixable: bool = True) -> Dict[str, Any]:
            rejected.append({"action": a, "reasons": [msg], "fixable": fixable})
            self.note("action", f"Rejected {t} #{tk}: {msg}", symbol=a.get("symbol", ""), tags=["rejected"])
            return {"action": t, "ok": False, "detail": msg}

        if t in ("modify_position", "close_position") and tk not in pos:
            return reject(f"no open position with ticket {tk}", False)
        if t in ("modify_order", "cancel_order") and tk not in pend:
            return reject(f"no pending order with ticket {tk}", False)
        reduces = t in ("cancel_order", "close_position")
        if t == "modify_position":
            p = pos[tk]
            sl, tp = a.get("sl"), a.get("tp")
            if sl is None and tp is None:
                return reject("nothing to change")
            if sl is not None:
                tighter = (sl > p.sl) if p.side == "buy" else (sl < p.sl or not p.sl)
                if p.sl and not tighter:
                    return reject("stops can only be tightened, never widened")
                if (p.side == "buy" and sl >= p.price_current) or (p.side == "sell" and sl <= p.price_current):
                    return reject("new stop is beyond the current price and would exit immediately; use close_position instead")
                reduces = True
        if t == "modify_order":
            o = pend[tk]
            tr = next((x for x in self.j.trades(status="pending", limit=100) if x["ticket"] == tk), None)
            prop = Proposal(type="place_limit" if "limit" in o.kind else "place_stop", symbol=o.symbol, side="buy" if o.kind.startswith("buy") else "sell",
                            entry=a.get("entry", o.price), sl=a.get("sl", o.sl), tp=a.get("tp", o.tp), skills=(tr or {}).get("skills") or [])
            others = [x for x in obs["pending"] if x.ticket != tk]
            with self.lock:
                v = self.risk.review(prop, self.broker, obs["acct"], obs["positions"], others, (obs["snaps"].get(o.symbol) or {}).get("atr", 0.0))
            if not v.ok:
                return reject("; ".join(v.reasons))
        if autonomy == "observe":
            self.note("action", f"Would {t} #{tk} (observe mode)", a.get("reason", ""), symbol=a.get("symbol", ""), tags=["observe"])
            return {"action": t, "ok": True, "detail": "observe mode: not sent"}
        if autonomy == "approval" and not reduces:
            return self._queue(a, None, f"{t} #{tk}")
        return self._do_manage(a, obs)

    def _do_manage(self, a: Dict[str, Any], obs: Dict[str, Any]) -> Dict[str, Any]:
        t, tk, why = a["type"], a.get("ticket"), a.get("reason", "")
        with self.lock:
            if t == "cancel_order":
                o = next((x for x in obs["pending"] if x.ticket == tk), None)
                self.broker.cancel_pending(tk)
                self.expiries.pop(str(tk), None)
                self.note("action", f"Cancelled order #{tk} {o.kind if o else ''} {o.symbol if o else ''}", why, symbol=o.symbol if o else "", ref={"ticket": tk})
            elif t == "modify_order":
                o = next(x for x in obs["pending"] if x.ticket == tk)
                d = obs["infos"][o.symbol].digits
                self.broker.modify_pending(tk, a.get("entry") and round(a["entry"], d), a.get("sl") and round(a["sl"], d), a.get("tp") and round(a["tp"], d))
                self.note("action", f"Moved order #{tk} {o.symbol}", f"entry {a.get('entry', o.price)} SL {a.get('sl', o.sl)} TP {a.get('tp', o.tp)}. {why}", symbol=o.symbol, ref={"ticket": tk})
            elif t == "modify_position":
                p = next(x for x in obs["positions"] if x.ticket == tk)
                d = obs["infos"][p.symbol].digits
                self.broker.modify_position(tk, a.get("sl") and round(a["sl"], d), a.get("tp") and round(a["tp"], d))
                self.note("action", f"Adjusted #{tk} {p.symbol}", f"SL {a.get('sl', p.sl)} TP {a.get('tp', p.tp)}. {why}", symbol=p.symbol, ref={"ticket": tk})
            elif t == "close_position":
                p = next(x for x in obs["positions"] if x.ticket == tk)
                frac = max(0.05, min(1.0, a.get("fraction") or 1.0))
                info = obs["infos"][p.symbol]
                vol = p.volume if frac >= 0.999 else max(info.vol_min, round(int(p.volume * frac / info.vol_step) * info.vol_step, 8))
                vol = p.volume if vol >= p.volume else vol
                self.broker.close_position(tk, vol)
                self.note("action", f"{'Closed' if vol >= p.volume else 'Partially closed'} #{tk} {p.symbol} ({vol} lots)", why, symbol=p.symbol, ref={"ticket": tk})
        self.bus.emit("trade", kind=t, ticket=tk)
        return {"action": t, "ok": True, "ticket": tk, "detail": f"{t} #{tk}"}

    # -- approvals
    def _queue(self, a: Dict[str, Any], v: Any, label: str) -> Dict[str, Any]:
        self._pid += 1
        prop = {"id": self._pid, "ts": time.time(), "expires": time.time() + 900, "action": a, "summary": label,
                "volume": getattr(v, "volume", None), "risk_pct": getattr(v, "risk_pct", None), "thesis": a.get("thesis", "") or a.get("reason", "")}
        self.proposals[self._pid] = prop
        self.note("action", f"Awaiting approval: {label}", prop["thesis"], symbol=a.get("symbol", ""), tags=["proposal"])
        self.bus.emit("proposal", proposal=prop)
        return {"action": a["type"], "ok": True, "detail": "queued for your approval"}

    def _expire_proposals(self) -> None:
        for k in [k for k, p in self.proposals.items() if p["expires"] < time.time()]:
            del self.proposals[k]

    def decide(self, pid: int, approve: bool) -> Dict[str, Any]:
        prop = self.proposals.pop(pid, None)
        if not prop:
            return {"ok": False, "error": "proposal expired or not found"}
        if not approve:
            self.note("action", f"Rejected by operator: {prop['summary']}", tags=["operator"])
            return {"ok": True, "detail": "rejected"}
        obs = self._locked(self.observe)
        results, rej = self.execute([prop["action"]], obs, source="chat")
        return {"ok": bool(results and results[0].get("ok")), "detail": results[0].get("detail") if results else "no result"}

    # ================================================================ learning
    def _review_one_trade(self, obs: Dict[str, Any]) -> None:
        todo = self.j.trades(status="closed", unreviewed=True, limit=1)
        if not todo:
            return
        t = todo[0]
        self._phase("review", f"{t['symbol']} {t['pnl']:+.2f}")
        ctx = {"trade": {k: t[k] for k in ("symbol", "side", "volume", "entry", "exit", "sl", "tp", "pnl", "r_multiple", "kind", "skills", "thesis", "invalidation")},
               "duration_min": round(((t["ts_close"] or 0) - (t["ts_open"] or 0)) / 60), "entry_context": (t.get("meta") or {}).get("snapshot"),
               "cited_skills": [self.j.skill(s) and {k: self.j.skill(s)[k] for k in ("name", "body", "status", "uses", "confidence")} for s in (t["skills"] or [])],
               "recent": "<journal_history>\n" + self.j.digest(8) + "\n</journal_history>"}
        try:
            out = self.llm.chat_json(prompts.trade_review_prompt(ctx), purpose="review", max_tokens=1200)
        except LLMError:
            self.review_fail[t["id"]] = self.review_fail.get(t["id"], 0) + 1
            if self.review_fail[t["id"]] >= 3:
                self.j.trade_update(t["id"], reviewed=1)
            raise
        self.j.trade_update(t["id"], reviewed=1)
        if not isinstance(out, dict):
            return
        lessons = [str(x)[:260] for x in (out.get("lessons") or [])[:3] if x]
        self.note("reflection", f"Review {t['symbol']} {t['pnl']:+.2f}: process {out.get('process', '?')}", str(out.get("outcome_vs_thesis", "")) + "\n" + "\n".join(f"- {l}" for l in lessons),
                  symbol=t["symbol"], tags=t["skills"] or [], ref={"trade": t["id"]})
        for l in lessons:
            self.note("lesson", l, symbol=t["symbol"], tags=t["skills"] or [])
        self._apply_skill_changes(out.get("skill_changes"), "trade review", max_changes=2)
        self._apply_todo_ops({"add": [x for x in (out.get("todos") or []) if isinstance(x, dict)][:2]}, source="agent")

    def _apply_skill_changes(self, changes: Any, origin: str, max_changes: int = 3) -> int:
        n = 0
        for c in (changes or [])[:max_changes] if isinstance(changes, list) else []:
            if not isinstance(c, dict) or not c.get("name"):
                continue
            act, name = str(c.get("action", "")).lower(), slugify(c["name"])
            cur = self.j.skill(name)
            reason = str(c.get("reason", ""))[:300]
            if act in ("add", "edit") and str(c.get("body", "")).strip():
                s = self.j.skill_upsert(name, str(c["body"]), kind=str(c.get("kind", "skill")), origin="agent", reason=f"{origin}: {reason}")
                self.note("lesson", f"Playbook {'updated' if cur else 'new skill'}: {name} (v{s['version']})", f"{reason}\n\n{str(c['body'])[:900]}", tags=[name])
                n += 1
            elif act == "retire" and cur and cur["uses"] >= 8:
                self.j.skill_upsert(name, "", status="retired", reason=reason)
                self.note("lesson", f"Retired skill: {name}", reason, tags=[name])
                n += 1
            elif act == "probation" and cur and cur["status"] == "active":
                self.j.skill_upsert(name, "", status="probation", reason=reason)
                self.note("lesson", f"Skill put on probation: {name}", reason, tags=[name])
                n += 1
        if n:
            self.bus.emit("playbook")
        return n

    def _maybe_meta_review(self, force: bool = False) -> None:
        closed = len(self.j.trades(status="closed", limit=5000))
        last = int(self.j.kv_get("meta_last_count", 0) or 0)
        last_ts = float(self.j.kv_get("meta_last_ts", 0) or 0)
        if not force and not (closed - last >= META_EVERY_TRADES or (closed - last >= 3 and time.time() - last_ts > 86400)):
            return
        self._phase("meta review", f"{closed} closed trades")
        st = self.j.stats()
        r = self.last_obs["risk"] if self.last_obs else {}
        ctx = {"stats": st, "skills": [{k: p[k] for k in ("name", "kind", "status", "uses", "win_rate", "expectancy_r", "confidence", "version")} | {"text": p["body"][:300]}
                                     for p in self.j.playbook()],
               "risk": {k: r.get(k) for k in ("tier", "risk_pct", "growth_pct", "drawdown_pct", "next_tier", "next_tier_at")},
               "scaling_ladder": r.get("ladder"), "lessons": [e["title"] for e in self.j.entries(kind="lesson", limit=12)],
               "open_todos": [t["title"] for t in self.j.todos("open", 10)], "previous_notes": {"scaling": self.j.kv_get("scaling_notes", ""), "process": self.j.kv_get("process_notes", "")}}
        out = self.llm.chat_json(prompts.meta_review_prompt(ctx), purpose="meta", max_tokens=1600)
        self.j.kv_set("meta_last_count", closed)
        self.j.kv_set("meta_last_ts", time.time())
        if not isinstance(out, dict):
            return
        if out.get("scaling_notes"):
            self.j.kv_set("scaling_notes", str(out["scaling_notes"])[:900])
        if out.get("process_notes"):
            self.j.kv_set("process_notes", str(out["process_notes"])[:900])
        self.note("reflection", "Meta review: " + str(out.get("summary", ""))[:240], str(out.get("summary", "")) + "\n\nScaling: " + str(out.get("scaling_notes", "")) +
                  "\nProcess: " + str(out.get("process_notes", "")), tags=["meta"])
        self._apply_skill_changes(out.get("skill_changes"), "meta review")
        self._apply_todo_ops({"add": [{"title": e.get("title"), "detail": e.get("detail", "")} for e in (out.get("experiments") or [])[:2] if isinstance(e, dict)]})

    def _maybe_world(self) -> None:
        w = self.world
        if not w.due():
            return
        self._phase("world", "reading the world feed")
        if w.refresh_due():
            w.fetch()
            if w.last_error:
                self._sys(
                    "world-fetch",
                    "Some world feeds are temporarily unavailable; cached data will be used where possible.",
                )
        raw = w.payload_for_prompt()
        if not raw:
            detail = w.last_error or "No world data is available to summarize."
            w.mark_digest_failed(detail)
            self._sys("world-digest", f"World Brief unavailable: {detail}")
            self.bus.emit("world", brief=w.brief, status=w.public_config())
            return
        try:
            out = self.llm.chat_json(prompts.world_prompt(raw, self.s.symbols), purpose="world", max_tokens=1400)
            out = normalize_world_brief(out)
            validation_error = world_brief_validation_error(out)
            if validation_error:
                out = self.llm.chat_json(
                    prompts.world_brief_repair_prompt(raw, out, validation_error),
                    purpose="world",
                    max_tokens=1400,
                )
                out = normalize_world_brief(out)
                validation_error = world_brief_validation_error(out)
        except LLMError as exc:
            w.mark_digest_failed(f"{type(exc).__name__}: {exc}")
            wait = 180 if exc.status == 429 else 60
            self.backoff_until = max(self.backoff_until, time.time() + wait)
            self._phase("waiting", f"LLM unavailable, retrying in {wait}s")
            log.warning("world brief digestion failed (%s): %s; retrying in %ss", type(exc).__name__, exc, wait)
            self._sys("world-digest", f"World Brief digestion failed: {type(exc).__name__}: {exc}")
            self.bus.emit("world", brief=w.brief, status=w.public_config())
            return
        except Exception as exc:
            w.mark_digest_failed(f"{type(exc).__name__}: {exc}")
            log.warning("world brief digestion failed (%s): %s", type(exc).__name__, exc)
            self._sys("world-digest", f"World Brief digestion failed: {type(exc).__name__}: {exc}")
            self.bus.emit("world", brief=w.brief, status=w.public_config())
            return
        if validation_error:
            w.mark_digest_failed(validation_error)
            self._sys("world-digest", f"World Brief digestion failed: {validation_error}")
            self.bus.emit("world", brief=w.brief, status=w.public_config())
            return
        w.set_brief(out)
        if out.get("stand_down"):
            self.stand_down_until = time.time() + 3600
        self.note("world", "World brief: " + str(out.get("summary", ""))[:240], str(out.get("summary", "")) + "\n" +
                  "\n".join(
                      f"- {t.get('theme')} ({t.get('bias')}, {t.get('urgency')}; assets: "
                      f"{', '.join(str(asset) for asset in t.get('assets', []) if asset) or 'not specified'}): {t.get('why', '')}"
                      for t in (out.get("themes") or []) if isinstance(t, dict)
                  ),
                  tags=["world"] + (["stand_down"] if out.get("stand_down") else []))
        self.bus.emit("world", brief=out, status=w.public_config())

    # ================================================================ operator controls
    def operator_order(self, ticket: int, what: str) -> Dict[str, Any]:
        obs = self._locked(self.observe)
        t = "close_position" if what == "close" else "cancel_order"
        res, _ = self.execute([{"type": t, "ticket": ticket, "fraction": 1.0, "reason": "operator request", "skills": []}], obs, source="chat")
        r = res[0] if res else {"ok": False, "detail": "nothing happened"}
        if not r.get("ok"):
            raise BrokerError(r.get("detail", "failed"))
        return {"ok": True, "detail": r.get("detail")}

    def pause(self) -> None:
        self.paused = True
        self.j.kv_set("paused", True)
        self.note("system", "Paused by operator")
        self._phase("paused")

    def resume(self) -> None:
        self.paused = False
        self.j.kv_set("paused", False)
        self.note("system", "Resumed by operator")
        self.wake()

    def flatten(self, reason: str = "operator request") -> Dict[str, int]:
        n_pos = n_ord = 0
        with self.lock:
            for o in self.broker.pending():
                try:
                    self.broker.cancel_pending(o.ticket)
                    n_ord += 1
                except BrokerError:
                    pass
            for p in self.broker.positions():
                if p.symbol in self.s.symbols:
                    try:
                        self.broker.close_position(p.ticket)
                        n_pos += 1
                    except BrokerError:
                        pass
        self.note("action", f"Flatten: closed {n_pos} position(s), cancelled {n_ord} order(s)", reason, tags=["flatten"])
        self.bus.emit("state", ts=time.time())
        return {"positions": n_pos, "orders": n_ord}

    def think_now(self, replan: bool = False) -> None:
        self.force_think = "operator request"
        self.force_plan = self.force_plan or replan
        self.backoff_until = 0
        self.wake()

    def run_review_now(self) -> None:
        threading.Thread(target=lambda: self._guard(lambda: self._maybe_meta_review(force=True)), daemon=True).start()

    def _guard(self, fn: Callable) -> None:
        try:
            fn()
        except Exception as e:
            self._sys("bg", f"Background task failed: {e}")

    # ================================================================ chat
    def chat(self, text: str) -> Dict[str, Any]:
        text = text.strip()[:4000]
        if not text:
            return {"reply": "", "actions": []}
        self.bus.emit("chat", role="user", content=text)
        self.j.chat_add("user", text)
        self.note("user", text[:200], text)
        slash = self._slash(text)
        if slash is not None:
            m = self.j.chat_add("assistant", slash["reply"], slash["actions"])
            self.bus.emit("chat", role="assistant", content=m["content"], actions=m["actions"])
            return slash
        if not self.llm.configured:
            msg = "I can't reason without an LLM key. Add one in Settings, or use commands: /status /pause /resume /flatten /think /todo <text>."
            m = self.j.chat_add("assistant", msg)
            self.bus.emit("chat", role="assistant", content=msg, actions=[])
            return {"reply": msg, "actions": []}
        obs = self.last_obs or self._locked(self.observe)
        ctx = self.context(obs, history=6)
        hist = [{"role": m["role"], "content": m["content"]} for m in self.j.chat_history(10)[:-1] if m["role"] in ("user", "assistant")]
        try:
            out = self.llm.chat_json(prompts.chat_prompt(ctx, hist, text), purpose="chat", max_tokens=1400, temperature=0.4)
        except LLMError as e:
            msg = f"The model call failed: {e}"
            self.j.chat_add("assistant", msg)
            self.bus.emit("chat", role="assistant", content=msg, actions=[])
            return {"reply": msg, "actions": []}
        reply = str((out or {}).get("reply", "")).strip() or "Done."
        results = self._chat_actions((out or {}).get("actions"), obs)
        m = self.j.chat_add("assistant", reply, results)
        self.bus.emit("chat", role="assistant", content=reply, actions=results)
        return {"reply": reply, "actions": results}

    def _chat_actions(self, raw: Any, obs: Dict[str, Any]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not isinstance(raw, list):
            return out
        trade_actions: List[Dict[str, Any]] = []
        known = {p["name"] for p in self.j.playbook(include_retired=False)}
        for a in raw[:6]:
            if not isinstance(a, dict):
                continue
            t = str(a.get("type", "")).lower()
            try:
                if t == "set_setting":
                    upd = validate_tunables({str(a.get("key")): a.get("value")})
                    envfile.set_env(upd)
                    out.append({"type": t, "ok": True, "detail": f"{a['key']} = {list(upd.values())[0]}"})
                    self.note("system", f"Setting changed by chat: {a['key']} = {list(upd.values())[0]}")
                    self.bus.emit("config")
                elif t == "pause":
                    self.pause(); out.append({"type": t, "ok": True, "detail": "paused"})
                elif t == "resume":
                    self.resume(); out.append({"type": t, "ok": True, "detail": "resumed"})
                elif t == "flatten":
                    r = self.flatten("requested in chat"); out.append({"type": t, "ok": True, "detail": f"closed {r['positions']} positions, cancelled {r['orders']} orders"})
                elif t == "think_now":
                    self.think_now(); out.append({"type": t, "ok": True, "detail": "thinking now"})
                elif t == "replan":
                    self.think_now(replan=True); out.append({"type": t, "ok": True, "detail": "re-planning"})
                elif t == "run_review":
                    self.run_review_now(); out.append({"type": t, "ok": True, "detail": "meta review started"})
                elif t == "note":
                    self.note("user", str(a.get("title", "Note"))[:200], str(a.get("body", ""))[:3000]); out.append({"type": t, "ok": True, "detail": "journaled"})
                elif t == "add_skill" and a.get("name") and a.get("body"):
                    s = self.j.skill_upsert(str(a["name"]), str(a["body"]), kind=str(a.get("kind", "skill")), origin="operator", reason="added in chat")
                    self.note("lesson", f"Operator added skill: {s['name']}", s["body"], tags=[s["name"]]); out.append({"type": t, "ok": True, "detail": s["name"]})
                elif t == "retire_skill" and a.get("name"):
                    self.j.skill_upsert(str(a["name"]), "", status="retired", reason="retired in chat"); out.append({"type": t, "ok": True, "detail": slugify(a["name"])})
                elif t in ENTRY + MANAGE + TODO_T + ("hold",):
                    trade_actions += self._clean_actions([a])
                else:
                    out.append({"type": t or "?", "ok": False, "detail": "unknown or incomplete action"})
            except (ValueError, KeyError) as e:
                out.append({"type": t, "ok": False, "detail": str(e)})
        if trade_actions:
            if self.effective_autonomy()[0] == "observe" and any(a["type"] in ENTRY for a in trade_actions):
                out.append({"type": "place", "ok": False, "detail": "autonomy is 'observe'. Switch to approval or autonomous to place trades."})
                trade_actions = [a for a in trade_actions if a["type"] not in ENTRY]
            obs2 = self._locked(self.observe)
            res, _rej = self.execute(trade_actions, obs2, source="chat")
            out += [{"type": r["action"], "ok": r["ok"], "detail": r.get("detail", "")} for r in res]
        return out

    def _slash(self, text: str) -> Optional[Dict[str, Any]]:
        if not text.startswith("/"):
            return None
        cmd, _, rest = text[1:].partition(" ")
        cmd = cmd.lower()
        acts: List[Dict[str, Any]] = []
        if cmd == "status":
            st = self.status()
            r = (self.last_obs or {}).get("risk", {})
            reply = (f"Phase: {st['phase']} ({st['phase_detail'] or '-'}). Autonomy: {st['autonomy']}. Broker: {st['broker']}. "
                     f"Equity {st['equity']}, tier {r.get('tier', '?')}, drawdown {r.get('drawdown_pct', 0)}%, "
                     f"{len((self.last_obs or {}).get('positions', []))} position(s), {len((self.last_obs or {}).get('pending', []))} order(s).")
        elif cmd == "pause":
            self.pause(); reply = "Paused. Existing stops stay at the broker."; acts.append({"type": "pause", "ok": True, "detail": ""})
        elif cmd == "resume":
            self.resume(); reply = "Resumed."; acts.append({"type": "resume", "ok": True, "detail": ""})
        elif cmd == "flatten":
            r = self.flatten("slash command"); reply = f"Closed {r['positions']} position(s) and cancelled {r['orders']} order(s)."; acts.append({"type": "flatten", "ok": True, "detail": ""})
        elif cmd == "think":
            self.think_now(replan="plan" in rest); reply = "Thinking now."; acts.append({"type": "think_now", "ok": True, "detail": ""})
        elif cmd == "todo" and rest.strip():
            t = self.j.todo_add(rest.strip(), source="user"); self.bus.emit("todo", todo=t); reply = f"Added todo #{t['id']}."; acts.append({"type": "add_todo", "ok": True, "detail": t["title"]})
        elif cmd == "app":
            parts = rest.lower().split()
            try:
                if parts == ["status"]:
                    reply = application_control.status_mt5()
                elif parts == ["launch", "mt5"]:
                    if self.broker.name != "mt5":
                        raise application_control.ApplicationControlError("Select the MT5 broker before launching its terminal.")
                    reply = application_control.launch_mt5()
                    self.broker.connect()
                elif parts == ["close", "mt5", "confirm"]:
                    if self.broker.name != "mt5":
                        raise application_control.ApplicationControlError("Select the MT5 broker before closing its terminal.")
                    if not self.paused:
                        raise application_control.ApplicationControlError("Pause the agent with /pause before closing MT5.")
                    self.broker.shutdown()
                    reply = application_control.close_mt5()
                else:
                    reply = "Use /app status, /app launch mt5, or /app close mt5 confirm. Closing requires /pause first."
                self.note("system", "MT5 application control", reply, tags=["application_control"])
                acts.append({"type": "application_control", "ok": True, "detail": reply})
            except (application_control.ApplicationControlError, BrokerError) as exc:
                reply = f"MT5 application control failed: {exc}"
                self.note("system", "MT5 application control failed", reply, tags=["application_control"])
                acts.append({"type": "application_control", "ok": False, "detail": str(exc)})
        else:
            reply = "Commands: /status /pause /resume /flatten /think [plan] /todo <text> /app status|launch mt5|close mt5 confirm. Anything else goes to the agent."
        return {"reply": reply, "actions": acts}

    # ================================================================ state for the dashboard
    def status(self) -> Dict[str, Any]:
        eff, why = self.effective_autonomy()
        acct = (self.last_obs or {}).get("acct")
        cfg = self.llm.provider_config(self.llm.active_provider())
        try:
            execution_mode = get_execution_mode()
            execution_mode_error = ""
        except ExecutionModeError as exc:
            execution_mode = "disabled"
            execution_mode_error = str(exc)
        return {"phase": self.phase, "phase_detail": self.phase_detail, "cycle": self.cycle, "paused": self.paused, "running": bool(self.thread and self.thread.is_alive()),
                "autonomy": eff, "autonomy_configured": self.s.str("AGENT_AUTONOMY"), "autonomy_note": why, "broker": self.broker.name, "real_account": bool(getattr(self.broker, "is_real", False)),
                "execution_mode": execution_mode, "execution_mode_error": execution_mode_error,
                "equity": round(acct.equity, 2) if acct else None, "uptime": round(time.time() - self.started) if self.started else 0,
                "llm": {"provider": self.llm.active_provider(), "model": cfg["model"], "configured": self.llm.configured, "busy": self.llm.busy},
                "last_think": self.last_think, "last_think_reason": self.last_think_reason, "next_check": self.next_think_at, "think_count": self.think_count,
                "thinks_last_hour": sum(1 for t in self.think_times if time.time() - t < 3600), "backoff": max(0, round(self.backoff_until - time.time())),
                "stand_down": self.stand_down_until > time.time(), "world": self.world.enabled}

    def state(self) -> Dict[str, Any]:
        o = self.last_obs
        out: Dict[str, Any] = {"status": self.status(), "plan": self.j.kv_get("current_plan"), "todos": self.j.todos(limit=60),
                               "proposals": list(self.proposals.values()), "world": self.world.brief,
                               "world_status": self.world.public_config(), "stats": self.j.stats(),
                               "scaling_notes": self.j.kv_get("scaling_notes", ""), "process_notes": self.j.kv_get("process_notes", "")}
        try:
            from legacy_bridge import canonical_agent_symbol, latest_legacy_context
            legacy_data = latest_legacy_context()
            for record in legacy_data:
                record["agent_symbol"] = canonical_agent_symbol(record.get("symbol", ""))
            out["legacy_analysis"] = legacy_data
        except (OSError, ValueError, sqlite3.Error) as exc:
            log.exception("Could not read the Legacy analysis bridge")
            self._sys("legacy-bridge", f"Legacy analysis temporarily unavailable: {type(exc).__name__}")
            out["legacy_analysis"] = []
        if o:
            tr = {t["ticket"]: t for t in self.j.trades(status="open,pending", limit=100)}
            out.update(account=o["acct"].to_dict(), risk=o["risk"], ts=o["ts"],
                       positions=[{**p.to_dict(), "thesis": (tr.get(p.ticket) or {}).get("thesis", ""), "skills": (tr.get(p.ticket) or {}).get("skills", []),
                                   "r_now": round(p.profit / tr[p.ticket]["risk_amount"], 2) if tr.get(p.ticket) and tr[p.ticket]["risk_amount"] else None} for p in o["positions"]],
                       pending=[{**p.to_dict(), "thesis": (tr.get(p.ticket) or {}).get("thesis", ""), "skills": (tr.get(p.ticket) or {}).get("skills", []),
                                 "expires": self.expiries.get(str(p.ticket))} for p in o["pending"]],
                       markets={k: {**{f: v.get(f) for f in ("price", "atr", "trend", "regime", "volatility", "session", "sweeps", "levels", "spread_atr", "candles")},
                                    "unavailable": bool(v.get("error"))}
                                for k, v in o["snaps"].items()})
        return out
