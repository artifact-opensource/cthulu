"""The agent's long-term memory: journal, todos, playbook (skills), trades, equity, chat.

Everything the agent thinks, decides and learns is written here, so it can read its own history back,
and so the operator can audit every decision.
"""
from __future__ import annotations

import json
import math
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY, ts REAL, kind TEXT, title TEXT, body TEXT,
  tags TEXT, symbol TEXT, ref TEXT, cycle INTEGER);
CREATE INDEX IF NOT EXISTS ix_journal_kind ON journal(kind, id);
CREATE TABLE IF NOT EXISTS todos(id INTEGER PRIMARY KEY, ts REAL, title TEXT, detail TEXT, status TEXT DEFAULT 'open',
  priority INTEGER DEFAULT 2, symbol TEXT, source TEXT DEFAULT 'agent', updated REAL, result TEXT);
CREATE TABLE IF NOT EXISTS playbook(id INTEGER PRIMARY KEY, name TEXT UNIQUE, kind TEXT DEFAULT 'skill', body TEXT,
  status TEXT DEFAULT 'probation', confidence REAL DEFAULT 0.35, version INTEGER DEFAULT 1, uses INTEGER DEFAULT 0,
  wins INTEGER DEFAULT 0, losses INTEGER DEFAULT 0, pnl_sum REAL DEFAULT 0, r_sum REAL DEFAULT 0,
  origin TEXT DEFAULT 'agent', created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS playbook_versions(id INTEGER PRIMARY KEY, skill_id INTEGER, version INTEGER, body TEXT, ts REAL, reason TEXT);
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY, ts_open REAL, ts_close REAL, symbol TEXT, side TEXT, volume REAL,
  entry REAL, exit REAL, sl REAL, tp REAL, pnl REAL, r_multiple REAL, risk_amount REAL, ticket INTEGER, status TEXT,
  kind TEXT, skills TEXT, thesis TEXT, invalidation TEXT, meta TEXT, source TEXT DEFAULT 'agent', reviewed INTEGER DEFAULT 0,
  close_checks INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_trades_status ON trades(status);
CREATE TABLE IF NOT EXISTS equity(ts REAL, balance REAL, equity REAL);
CREATE TABLE IF NOT EXISTS chat(id INTEGER PRIMARY KEY, ts REAL, role TEXT, content TEXT, actions TEXT);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS discord_outbox(
  journal_id INTEGER PRIMARY KEY, created REAL NOT NULL, content TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
  delivered_at REAL, failed_at REAL, last_error TEXT NOT NULL DEFAULT ''
);
"""

SEED_SKILLS = [
    ("liquidity_sweep_reversal", "setup",
     "Price runs beyond an obvious liquidity pool (equal highs/lows, prior day or session extreme), closes back inside, "
     "then shows displacement away from the level. Displacement below 1 ATR can qualify when the reclaim and at least one independent confirmation (follow-through, trend alignment, or nearby level confluence) support the reversal; do not use 1 ATR as a universal cutoff. "
     "Trade the reversal with a limit order at the 50% retrace of the displacement leg "
     "or the sweep candle's body. Stop beyond the sweep wick. Target the opposite side's liquidity or at least 1.5R. "
     "Skip when the sweep happens into a higher-timeframe trend with no reclaim."),
    ("equal_levels_raid", "setup",
     "Equal highs or equal lows act as stop magnets. Expect a raid before a real move. Do not place entries just beyond them; "
     "wait for the raid and the reclaim, or place limits at the opposite side after the raid completes."),
    ("session_open_fakeout", "setup",
     "Asian range extremes get raided around the London and New York opens. If price sweeps the Asian high or low early in the session "
     "and reclaims, fade the move toward the opposite end of the range. If it holds beyond with displacement, stand aside or follow."),
    ("trend_pullback_limit", "setup",
     "With a clear higher-timeframe trend (EMA alignment, high efficiency ratio), rest a limit order at the pullback zone "
     "(0.5-0.7 of the last impulse or the EMA20/50 area) with the stop beyond the last swing. Cancel the order if price breaks structure first."),
    ("position_management", "rule",
     "Manage open trades: move stop to breakeven after +1R, take partials near +1.5R when the target is far, trail behind new swing points, "
     "close early when the thesis is invalidated, and cancel pending orders whose setup has expired or whose level has been taken out."),
    ("news_stand_down", "rule",
     "When the world brief flags a high-impact event or a sharp risk-off shock for a symbol's drivers, avoid new entries, "
     "tighten or reduce exposure, and cancel resting orders that sit in the path of a likely spike."),
    ("scaling_ladder", "rule",
     "Grow the account by compounding small, consistent risk: size from equity, shrink risk during drawdown, never raise risk to recover losses, "
     "and let tier changes (not mood or a hot streak) raise the risk budget."),
]


def _now() -> float:
    return time.time()


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return s[:48] or "skill"


class Journal:
    def __init__(self, path: Path | str = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        with self._lock:
            try:
                self._db.execute("PRAGMA journal_mode=WAL")
            except sqlite3.DatabaseError:
                pass
            self._db.executescript(SCHEMA)
            discord_columns = {
                row["name"] for row in self._db.execute("PRAGMA table_info(discord_outbox)")
            }
            if "failed_at" not in discord_columns:
                self._db.execute("ALTER TABLE discord_outbox ADD COLUMN failed_at REAL")
            try:
                self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS journal_fts USING fts5(title, body, tags)")
                self.fts = True
            except sqlite3.OperationalError:
                self.fts = False
            self.purge_system_entries()
        self._seed()

    # ------------------------------------------------------------ helpers
    def _x(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._db.execute(sql, params)

    def _q(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    @staticmethod
    def _jload(row: Dict[str, Any], *fields: str) -> Dict[str, Any]:
        for f in fields:
            if row.get(f):
                try:
                    row[f] = json.loads(row[f])
                except (TypeError, ValueError):
                    pass
        return row

    # ------------------------------------------------------------ kv
    def kv_get(self, key: str, default: Any = None) -> Any:
        r = self._q("SELECT value FROM kv WHERE key=?", (key,))
        if not r:
            return default
        try:
            return json.loads(r[0]["value"])
        except ValueError:
            return default

    def kv_set(self, key: str, value: Any) -> None:
        self._x("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, default=str)))

    # ------------------------------------------------------------ journal
    def add(self, kind: str, title: str, body: str = "", tags: Optional[List[str]] = None, symbol: str = "",
            ref: Optional[dict] = None, cycle: int = 0) -> Dict[str, Any]:
        ts = _now()
        with self._lock:
            cur = self._db.execute("INSERT INTO journal(ts,kind,title,body,tags,symbol,ref,cycle) VALUES(?,?,?,?,?,?,?,?)",
                                   (ts, kind, title[:300], body[:12000], json.dumps(tags or []), symbol,
                                    json.dumps(ref or {}, default=str), cycle))
            rid = cur.lastrowid
            if self.fts:
                self._db.execute("INSERT INTO journal_fts(rowid,title,body,tags) VALUES(?,?,?,?)",
                                 (rid, title, body, " ".join(tags or [])))
        return {"id": rid, "ts": ts, "kind": kind, "title": title[:300], "body": body[:12000],
                "tags": tags or [], "symbol": symbol, "ref": ref or {}, "cycle": cycle}

    def purge_system_entries(self) -> int:
        """Remove legacy operational/system entries and their local delivery records."""
        with self._lock:
            ids = [
                row["id"] for row in self._db.execute(
                    "SELECT id FROM journal WHERE lower(kind)='system'"
                )
            ]
            if not ids:
                return 0
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if self.fts:
                    self._db.executemany(
                        "DELETE FROM journal_fts WHERE rowid=?",
                        ((rid,) for rid in ids),
                    )
                self._db.executemany(
                    "DELETE FROM discord_outbox WHERE journal_id=?",
                    ((rid,) for rid in ids),
                )
                self._db.executemany(
                    "DELETE FROM journal WHERE id=?",
                    ((rid,) for rid in ids),
                )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
            return len(ids)

    def discord_enqueue(self, journal_id: int, content: str) -> None:
        self._x(
            """INSERT OR IGNORE INTO discord_outbox(journal_id, created, content)
               VALUES(?,?,?)""",
            (journal_id, _now(), content),
        )

    def discord_pending(self, now: Optional[float] = None, limit: int = 10) -> List[Dict[str, Any]]:
        return self._q(
            """SELECT journal_id, content, attempts FROM discord_outbox
               WHERE delivered_at IS NULL AND failed_at IS NULL AND next_attempt <= ?
               ORDER BY journal_id LIMIT ?""",
            (now if now is not None else _now(), max(1, min(int(limit), 50))),
        )

    def discord_mark_delivered(self, journal_id: int) -> None:
        self._x(
            "UPDATE discord_outbox SET delivered_at=?, last_error='' WHERE journal_id=?",
            (_now(), journal_id),
        )

    def discord_mark_failed(self, journal_id: int, attempts: int, retry_after: float, error: str) -> None:
        self._x(
            """UPDATE discord_outbox
               SET attempts=?, next_attempt=?, last_error=?
               WHERE journal_id=? AND delivered_at IS NULL AND failed_at IS NULL""",
            (attempts, _now() + max(1.0, retry_after), error[:160], journal_id),
        )

    def discord_mark_permanent_failure(self, journal_id: int, attempts: int, error: str) -> None:
        self._x(
            """UPDATE discord_outbox
               SET attempts=?, failed_at=?, last_error=?
               WHERE journal_id=? AND delivered_at IS NULL""",
            (attempts, _now(), error[:160], journal_id),
        )

    def entries(self, kind: Optional[str] = None, q: str = "", limit: int = 60, before: int = 0,
                symbol: str = "") -> List[Dict[str, Any]]:
        limit = max(1, min(limit, 300))
        where, params = ["lower(j.kind)!='system'"], []
        if kind and kind != "all":
            kinds = kind.split(",")
            where.append("j.kind IN (%s)" % ",".join("?" * len(kinds)))
            params += kinds
        if symbol:
            where.append("j.symbol=?")
            params.append(symbol)
        if before:
            where.append("j.id<?")
            params.append(before)
        q = (q or "").strip()
        if q and self.fts:
            terms = " ".join('"%s"' % t.replace('"', "") for t in q.split()[:8])
            where.append("j.id IN (SELECT rowid FROM journal_fts WHERE journal_fts MATCH ?)")
            params.append(terms)
        elif q:
            where.append("(j.title LIKE ? OR j.body LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        sql = "SELECT j.* FROM journal j" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY j.id DESC LIMIT ?"
        rows = self._q(sql, tuple(params) + (limit,))
        return [self._jload(r, "tags", "ref") for r in rows]

    def digest(self, n: int = 12, kinds: str = "reason,action,reflection,lesson,trade_close,plan") -> str:
        """Compact text of recent history for prompts."""
        out = []
        for e in reversed(self.entries(kind=kinds, limit=n)):
            t = time.strftime("%m-%d %H:%M", time.gmtime(e["ts"]))
            out.append(f"[{t}] {e['kind']}: {e['title']}" + (f" | {e['body'][:160]}" if e["body"] else ""))
        return "\n".join(out)

    # ------------------------------------------------------------ todos
    def todo_add(self, title: str, detail: str = "", priority: int = 2, symbol: str = "", source: str = "agent") -> Dict[str, Any]:
        title = title.strip()[:200]
        dup = self._q("SELECT * FROM todos WHERE status IN ('open','doing') AND lower(title)=lower(?)", (title,))
        if dup:
            return dup[0]
        ts = _now()
        cur = self._x("INSERT INTO todos(ts,title,detail,priority,symbol,source,updated) VALUES(?,?,?,?,?,?,?)",
                      (ts, title, detail[:1000], max(1, min(3, int(priority or 2))), symbol, source, ts))
        return self._q("SELECT * FROM todos WHERE id=?", (cur.lastrowid,))[0]

    def todo_update(self, tid: int, **fields: Any) -> Optional[Dict[str, Any]]:
        allowed = {"title", "detail", "status", "priority", "result", "symbol"}
        sets, params = [], []
        for k, v in fields.items():
            if k in allowed and v is not None:
                if k == "status" and v not in ("open", "doing", "done", "dropped"):
                    continue
                sets.append(f"{k}=?")
                params.append(v)
        if not sets:
            return None
        sets.append("updated=?")
        params += [_now(), int(tid)]
        self._x(f"UPDATE todos SET {', '.join(sets)} WHERE id=?", tuple(params))
        r = self._q("SELECT * FROM todos WHERE id=?", (int(tid),))
        return r[0] if r else None

    def todos(self, status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        if status:
            return self._q("SELECT * FROM todos WHERE status=? ORDER BY priority, id DESC LIMIT ?", (status, limit))
        return self._q("SELECT * FROM todos ORDER BY CASE status WHEN 'doing' THEN 0 WHEN 'open' THEN 1 WHEN 'done' THEN 2 ELSE 3 END, "
                       "priority, id DESC LIMIT ?", (limit,))

    # ------------------------------------------------------------ playbook
    def _seed(self) -> None:
        if self.kv_get("seeded"):
            return
        for name, kind, body in SEED_SKILLS:
            self.skill_upsert(name, body, kind=kind, origin="seed", reason="initial playbook", status="probation")
        self.kv_set("seeded", True)

    def skill_upsert(self, name: str, body: str, kind: str = "skill", origin: str = "agent", reason: str = "",
                     status: Optional[str] = None) -> Dict[str, Any]:
        name = slugify(name)
        body = body.strip()[:1500]
        ts = _now()
        with self._lock:
            row = self._q("SELECT * FROM playbook WHERE name=?", (name,))
            if row:
                r = row[0]
                if body and body != r["body"]:
                    v = r["version"] + 1
                    self._x("UPDATE playbook SET body=?, version=?, updated=? WHERE id=?", (body, v, ts, r["id"]))
                    self._x("INSERT INTO playbook_versions(skill_id,version,body,ts,reason) VALUES(?,?,?,?,?)",
                            (r["id"], v, body, ts, reason))
                if status in ("active", "probation", "retired"):
                    self._x("UPDATE playbook SET status=?, updated=? WHERE id=?", (status, ts, r["id"]))
            else:
                cur = self._x("INSERT INTO playbook(name,kind,body,status,origin,created,updated) VALUES(?,?,?,?,?,?,?)",
                              (name, kind if kind in ("skill", "setup", "rule") else "skill", body,
                               status or "probation", origin, ts, ts))
                self._x("INSERT INTO playbook_versions(skill_id,version,body,ts,reason) VALUES(?,?,?,?,?)",
                        (cur.lastrowid, 1, body, ts, reason or "created"))
        return self.skill(name)

    def skill(self, name: str) -> Optional[Dict[str, Any]]:
        r = self._q("SELECT * FROM playbook WHERE name=?", (slugify(name),))
        return r[0] if r else None

    def playbook(self, include_retired: bool = True) -> List[Dict[str, Any]]:
        rows = self._q("SELECT * FROM playbook " + ("" if include_retired else "WHERE status!='retired' ") +
                       "ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'probation' THEN 1 ELSE 2 END, confidence DESC")
        for r in rows:
            r["expectancy_r"] = round(r["r_sum"] / r["uses"], 3) if r["uses"] else 0.0
            r["win_rate"] = round(r["wins"] / r["uses"], 3) if r["uses"] else 0.0
        return rows

    def skill_versions(self, name: str) -> List[Dict[str, Any]]:
        s = self.skill(name)
        return self._q("SELECT version,body,ts,reason FROM playbook_versions WHERE skill_id=? ORDER BY version DESC", (s["id"],)) if s else []

    def skill_record(self, names: List[str], pnl: float, r: float) -> List[str]:
        """Attribute a closed trade to skills, recompute confidence, apply deterministic promotion/demotion."""
        changes = []
        for n in names:
            s = self.skill(n)
            if not s:
                continue
            uses, wins, losses = s["uses"] + 1, s["wins"] + (pnl > 0), s["losses"] + (pnl < 0)
            r_sum, pnl_sum = s["r_sum"] + r, s["pnl_sum"] + pnl
            exp = r_sum / uses
            w = min(1.0, uses / 12)
            conf = 0.35 * (1 - w) + (0.5 + 0.5 * math.tanh(1.5 * exp)) * w
            status = s["status"]
            if status == "active" and uses >= 8 and exp < -0.25:
                status = "probation"
                changes.append(f"{s['name']}: demoted to probation (expectancy {exp:+.2f}R over {uses} trades)")
            elif status != "retired" and uses >= 15 and exp < -0.15:
                status = "retired"
                changes.append(f"{s['name']}: retired (expectancy {exp:+.2f}R over {uses} trades)")
            elif status == "probation" and uses >= 10 and exp > 0.15:
                status = "active"
                changes.append(f"{s['name']}: promoted to active (expectancy {exp:+.2f}R over {uses} trades)")
            self._x("UPDATE playbook SET uses=?,wins=?,losses=?,r_sum=?,pnl_sum=?,confidence=?,status=?,updated=? WHERE id=?",
                    (uses, wins, losses, r_sum, pnl_sum, round(conf, 4), status, _now(), s["id"]))
        return changes

    def skill_multiplier(self, names: List[str]) -> float:
        """Risk multiplier from the confidence of the skills a trade cites. Unknown or retired skills get the floor."""
        vals = []
        for n in names or []:
            s = self.skill(n)
            if s and s["status"] != "retired":
                vals.append(0.25 + 0.75 * s["confidence"])
        return max(vals) if vals else 0.25

    # ------------------------------------------------------------ trades
    def trade_add(self, **f: Any) -> int:
        cols = ["ts_open", "ts_close", "symbol", "side", "volume", "entry", "exit", "sl", "tp", "pnl", "r_multiple", "risk_amount",
                "ticket", "status", "kind", "skills", "thesis", "invalidation", "meta", "source"]
        f.setdefault("ts_open", _now())
        for k in ("skills", "meta"):
            if k in f and not isinstance(f[k], str):
                f[k] = json.dumps(f[k], default=str)
        use = [c for c in cols if c in f]
        cur = self._x(f"INSERT INTO trades({','.join(use)}) VALUES({','.join('?' * len(use))})", tuple(f[c] for c in use))
        return cur.lastrowid

    def trade_update(self, tid: int, **f: Any) -> None:
        for k in ("skills", "meta"):
            if k in f and not isinstance(f[k], str):
                f[k] = json.dumps(f[k], default=str)
        if not f:
            return
        self._x(f"UPDATE trades SET {','.join(k + '=?' for k in f)} WHERE id=?", tuple(f.values()) + (tid,))

    def trades(self, status: Optional[str] = None, limit: int = 100, unreviewed: bool = False) -> List[Dict[str, Any]]:
        where, params = [], []
        if status:
            sts = status.split(",")
            where.append("status IN (%s)" % ",".join("?" * len(sts)))
            params += sts
        if unreviewed:
            where.append("reviewed=0")
        sql = "SELECT * FROM trades" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
        return [self._jload(r, "skills", "meta") for r in self._q(sql, tuple(params) + (limit,))]

    def trade_baseline(self) -> tuple[int, List[int]]:
        """Return the trade ID high-water mark and IDs that are currently open or pending."""
        watermark = self._q("SELECT COALESCE(MAX(id), 0) AS id FROM trades")[0]["id"]
        active = self._q("SELECT id FROM trades WHERE status IN ('open', 'pending')")
        return int(watermark), [int(row["id"]) for row in active]

    # ------------------------------------------------------------ equity & stats
    def equity_add(self, balance: float, equity: float) -> None:
        last = self._q("SELECT ts,equity FROM equity ORDER BY ts DESC LIMIT 1")
        if last and _now() - last[0]["ts"] < 20 and abs(last[0]["equity"] - equity) < 1e-9:
            return
        self._x("INSERT INTO equity(ts,balance,equity) VALUES(?,?,?)", (_now(), balance, equity))

    def equity_series(self, limit: int = 600) -> List[Dict[str, float]]:
        rows = self._q("SELECT ts,balance,equity FROM equity ORDER BY ts DESC LIMIT ?", (limit,))
        return list(reversed(rows))

    def stats(self) -> Dict[str, Any]:
        t = self._q("SELECT * FROM trades WHERE status='closed' ORDER BY ts_close")
        n = len(t)
        now = _now()
        today_start = now - (now % 86400)
        today_trades = [x for x in t if today_start <= (x["ts_close"] or 0) < today_start + 86400]
        today_pnls = [x["pnl"] or 0 for x in today_trades]
        today_n = len(today_trades)
        today_wins = sum(1 for pnl in today_pnls if pnl > 0)
        today_losses = sum(1 for pnl in today_pnls if pnl < 0)
        today_gp = sum(pnl for pnl in today_pnls if pnl > 0)
        today_gl = -sum(pnl for pnl in today_pnls if pnl < 0)
        out: Dict[str, Any] = {"trades": n, "wins": 0, "losses": 0, "win_rate": 0.0, "pnl": 0.0, "avg_r": 0.0,
                               "profit_factor": 0.0, "best": 0.0, "worst": 0.0, "streak": 0, "by_symbol": {}, "by_skill": {},
                               "today": {
                                   "date": time.strftime("%Y-%m-%d", time.gmtime(today_start)),
                                   "trades": today_n, "wins": today_wins, "losses": today_losses,
                                   "win_rate": round(today_wins / today_n, 3) if today_n else 0.0,
                                   "pnl": round(sum(today_pnls), 2),
                                   "avg_r": round(sum(x["r_multiple"] or 0 for x in today_trades) / today_n, 3) if today_n else 0.0,
                                   "profit_factor": round(today_gp / today_gl, 2) if today_gl else (round(today_gp, 2) if today_gp else 0.0),
                               }}
        if not n:
            return out
        gp = sum(x["pnl"] for x in t if (x["pnl"] or 0) > 0)
        gl = -sum(x["pnl"] for x in t if (x["pnl"] or 0) < 0)
        out.update(wins=sum(1 for x in t if (x["pnl"] or 0) > 0), losses=sum(1 for x in t if (x["pnl"] or 0) < 0),
                   pnl=round(sum(x["pnl"] or 0 for x in t), 2), avg_r=round(sum(x["r_multiple"] or 0 for x in t) / n, 3),
                   profit_factor=round(gp / gl, 2) if gl else (round(gp, 2) if gp else 0.0),
                   best=round(max(x["pnl"] or 0 for x in t), 2), worst=round(min(x["pnl"] or 0 for x in t), 2))
        out["win_rate"] = round(out["wins"] / n, 3)
        s = 0
        for x in reversed(t):
            p = x["pnl"] or 0
            if p == 0 or (s and (p > 0) != (s > 0)):
                break
            s += 1 if p > 0 else -1
        out["streak"] = s
        for x in t:
            d = out["by_symbol"].setdefault(x["symbol"], {"n": 0, "pnl": 0.0})
            d["n"] += 1
            d["pnl"] = round(d["pnl"] + (x["pnl"] or 0), 2)
        for p in self.playbook():
            if p["uses"]:
                out["by_skill"][p["name"]] = {"n": p["uses"], "win_rate": p["win_rate"], "expectancy_r": p["expectancy_r"], "status": p["status"]}
        return out

    # ------------------------------------------------------------ chat
    def chat_add(self, role: str, content: str, actions: Optional[list] = None) -> Dict[str, Any]:
        ts = _now()
        cur = self._x("INSERT INTO chat(ts,role,content,actions) VALUES(?,?,?,?)",
                      (ts, role, content[:8000], json.dumps(actions or [], default=str)))
        return {"id": cur.lastrowid, "ts": ts, "role": role, "content": content[:8000], "actions": actions or []}

    def chat_history(self, limit: int = 60) -> List[Dict[str, Any]]:
        rows = self._q("SELECT * FROM chat ORDER BY id DESC LIMIT ?", (limit,))
        return [self._jload(r, "actions") for r in reversed(rows)]
