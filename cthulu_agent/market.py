"""Market structure features for the agent: volatility, trend, liquidity pools and sweeps.

Everything returns plain JSON-serialisable dicts sized for an LLM prompt. These are *evidence* for the agent
to reason over; none of it is a trading signal by itself.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

SESSIONS_UTC = [("asia", 0, 7), ("london", 7, 12), ("new_york", 12, 21), ("off_hours", 21, 24)]


def to_df(candles: Any) -> pd.DataFrame:
    """candles: DataFrame or list of dicts with time(epoch s), open, high, low, close[, volume]."""
    df = candles if isinstance(candles, pd.DataFrame) else pd.DataFrame(candles)
    if df.empty:
        return df
    df = df.copy()
    if "time" in df.columns:
        df.index = pd.to_datetime(df["time"], unit="s", utc=True)
    return df.sort_index()


def atr(df: pd.DataFrame, n: int = 14) -> float:
    if len(df) < 3:
        return 0.0
    h, l, c = df["high"].values, df["low"].values, df["close"].values
    tr = np.maximum(h[1:] - l[1:], np.maximum(abs(h[1:] - c[:-1]), abs(l[1:] - c[:-1])))
    return float(pd.Series(tr).ewm(alpha=1 / n, adjust=False).mean().iloc[-1])


def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def efficiency_ratio(close: pd.Series, n: int = 20) -> float:
    if len(close) <= n:
        return 0.0
    net = abs(close.iloc[-1] - close.iloc[-n - 1])
    path = close.diff().abs().iloc[-n:].sum()
    return float(net / path) if path else 0.0


def swings(df: pd.DataFrame, left: int = 3, right: int = 3) -> Dict[str, List[Dict[str, float]]]:
    h, l, idx = df["high"].values, df["low"].values, df.index
    hi, lo = [], []
    for i in range(left, len(df) - right):
        if h[i] >= h[i - left:i].max() and h[i] > h[i + 1:i + right + 1].max():
            hi.append({"i": i, "price": float(h[i]), "t": int(idx[i].timestamp())})
        if l[i] <= l[i - left:i].min() and l[i] < l[i + 1:i + right + 1].min():
            lo.append({"i": i, "price": float(l[i]), "t": int(idx[i].timestamp())})
    return {"highs": hi, "lows": lo}


def _cluster(points: List[Dict[str, float]], tol: float) -> List[Dict[str, Any]]:
    pts = sorted(points, key=lambda p: p["price"])
    groups: List[List[Dict[str, float]]] = []
    for p in pts:
        if groups and abs(p["price"] - groups[-1][-1]["price"]) <= tol:
            groups[-1].append(p)
        else:
            groups.append([p])
    return [{"price": max(x["price"] for x in g), "low": min(x["price"] for x in g), "count": len(g),
             "last_i": max(x["i"] for x in g)} for g in groups]


def liquidity_pools(df: pd.DataFrame, a: float, lookback: int = 150) -> List[Dict[str, Any]]:
    d = df.iloc[-lookback:]
    if len(d) < 12 or a <= 0:
        return []
    sw = swings(d)
    base = len(df) - len(d)
    out: List[Dict[str, Any]] = []
    for kind, pts, eq_name, one_name in (("buy_side", sw["highs"], "equal_highs", "swing_high"),
                                         ("sell_side", sw["lows"], "equal_lows", "swing_low")):
        for g in _cluster(pts, 0.18 * a):
            if g["count"] >= 2:
                out.append({"kind": eq_name, "side": kind, "price": g["price"] if kind == "buy_side" else g["low"],
                            "count": g["count"], "age_bars": len(d) - 1 - g["last_i"]})
            elif len(d) - 1 - g["last_i"] <= 60:
                out.append({"kind": one_name, "side": kind, "price": g["price"] if kind == "buy_side" else g["low"],
                            "count": 1, "age_bars": len(d) - 1 - g["last_i"]})
    return out


def session_of(hour: int) -> str:
    for name, a, b in SESSIONS_UTC:
        if a <= hour < b:
            return name
    return "off_hours"


def session_levels(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    out: List[Dict[str, Any]] = []
    last_day = df.index[-1].normalize()
    prev = df[(df.index >= last_day - pd.Timedelta(days=1)) & (df.index < last_day)]
    if not prev.empty:
        out += [{"kind": "prev_day_high", "side": "buy_side", "price": float(prev["high"].max()), "count": 1},
                {"kind": "prev_day_low", "side": "sell_side", "price": float(prev["low"].min()), "count": 1}]
    today = df[df.index >= last_day]
    asia = today[(today.index.hour >= 0) & (today.index.hour < 7)]
    if len(asia) >= 3 and df.index[-1].hour >= 7:
        out += [{"kind": "asia_high", "side": "buy_side", "price": float(asia["high"].max()), "count": 1},
                {"kind": "asia_low", "side": "sell_side", "price": float(asia["low"].min()), "count": 1}]
    return out


def round_levels(price: float) -> List[Dict[str, Any]]:
    if price <= 0:
        return []
    step = 10 ** (int(math.floor(math.log10(price))) - 1) / 2 * 10
    step = step if step > 0 else 1
    lo = math.floor(price / step) * step
    return [{"kind": "round_below", "side": "sell_side", "price": lo, "count": 1},
            {"kind": "round_above", "side": "buy_side", "price": lo + step, "count": 1}]


def detect_sweeps(df: pd.DataFrame, levels: List[Dict[str, Any]], a: float, lookback: int = 10) -> List[Dict[str, Any]]:
    """A sweep: a recent bar pokes through a liquidity level and closes back inside it."""
    if len(df) < lookback + 2 or a <= 0:
        return []
    d = df.iloc[-lookback:]
    n = len(df)
    out = []
    for lv in levels:
        p = lv["price"]
        for j in range(len(d)):
            bar = d.iloc[j]
            ago = len(d) - 1 - j
            if lv["side"] == "buy_side" and bar["high"] > p + 0.02 * a and bar["close"] < p:
                # a later close back above the level cancels the idea of a completed raid
                if (d["close"].iloc[j + 1:] > p).any():
                    continue
                out.append({"id": f"B{round(p, 4)}@{int(d.index[j].timestamp())}", "bias": "bearish", "level": p,
                            "level_kind": lv["kind"], "bars_ago": ago, "wick_atr": round((bar["high"] - p) / a, 2),
                            "displacement_atr": round((p - float(d["close"].iloc[-1])) / a, 2)})
            elif lv["side"] == "sell_side" and bar["low"] < p - 0.02 * a and bar["close"] > p:
                if (d["close"].iloc[j + 1:] < p).any():
                    continue
                out.append({"id": f"S{round(p, 4)}@{int(d.index[j].timestamp())}", "bias": "bullish", "level": p,
                            "level_kind": lv["kind"], "bars_ago": ago, "wick_atr": round((p - bar["low"]) / a, 2),
                            "displacement_atr": round((float(d["close"].iloc[-1]) - p) / a, 2)})
    seen, uniq = set(), []
    for s in sorted(out, key=lambda s: s["bars_ago"]):
        if s["id"] not in seen:
            seen.add(s["id"])
            uniq.append(s)
    return uniq[:4]


def htf_bias(df: pd.DataFrame) -> Dict[str, Any]:
    if len(df) < 55:
        return {"dir": "unknown"}
    c = df["close"]
    e20, e50 = _ema(c, 20).iloc[-1], _ema(c, 50).iloc[-1]
    a = atr(df) or 1e-9
    return {"dir": "up" if c.iloc[-1] > e20 > e50 else "down" if c.iloc[-1] < e20 < e50 else "mixed",
            "slope_atr": round(float((_ema(c, 20).iloc[-1] - _ema(c, 20).iloc[-6]) / a), 2)}


def snapshot(candles: Any, symbol: str, tf: str, bid: float, ask: float, digits: int = 5,
             htf: Optional[Any] = None, n_candles: int = 14) -> Dict[str, Any]:
    df = to_df(candles)
    if len(df) < 30:
        return {"symbol": symbol, "tf": tf, "error": "not enough candles"}
    a = atr(df)
    price = (bid + ask) / 2 if bid and ask else float(df["close"].iloc[-1])
    c = df["close"]
    e20, e50 = _ema(c, 20), _ema(c, 50)
    er = efficiency_ratio(c)
    atr_series = pd.Series(df["high"] - df["low"]).rolling(14).mean().dropna()
    pct = float((atr_series <= atr_series.iloc[-1]).mean()) if len(atr_series) > 20 else 0.5
    raw = liquidity_pools(df, a) + session_levels(df)
    sweeps = detect_sweeps(df, raw, a)
    levels = [dict(lv) for lv in raw] + round_levels(price)
    for lv in levels:
        lv["dist_atr"] = round((lv["price"] - price) / a, 2) if a else 0
        lv["price"] = round(lv["price"], digits)
    for s in sweeps:
        s["level"] = round(s["level"], digits)
    near = sorted(levels, key=lambda lv: abs(lv["dist_atr"]))[:10]
    last = df.iloc[-n_candles:]
    snap = {
        "symbol": symbol, "tf": tf, "price": round(price, digits), "bid": round(bid, digits), "ask": round(ask, digits),
        "spread_atr": round((ask - bid) / a, 3) if a and ask and bid else 0.0, "atr": round(a, digits),
        "trend": {"dir": "up" if price > e20.iloc[-1] > e50.iloc[-1] else "down" if price < e20.iloc[-1] < e50.iloc[-1] else "mixed",
                  "ema20": round(float(e20.iloc[-1]), digits), "ema50": round(float(e50.iloc[-1]), digits),
                  "slope_atr": round(float((e20.iloc[-1] - e20.iloc[-6]) / a), 2) if a else 0.0},
        "efficiency": round(er, 2), "regime": "trending" if er > 0.35 else "choppy" if er < 0.18 else "transitional",
        "volatility": "high" if pct > 0.8 else "low" if pct < 0.25 else "normal",
        "session": session_of(df.index[-1].hour), "levels": sorted(near, key=lambda lv: lv["price"]),
        "sweeps": sweeps, "range20": {"high": round(float(df["high"].iloc[-20:].max()), digits),
                                      "low": round(float(df["low"].iloc[-20:].min()), digits)},
        "candles": [[int(t.timestamp()), round(r.open, digits), round(r.high, digits), round(r.low, digits), round(r.close, digits)]
                    for t, r in last.iterrows()],
    }
    if htf is not None:
        snap["htf"] = htf_bias(to_df(htf))
    return snap


def fingerprint(snap: Dict[str, Any]) -> str:
    """Coarse state signature used to decide whether the world changed enough to be worth thinking about."""
    if "error" in snap or not snap.get("atr"):
        return "na"
    cell = round(snap["price"] / (snap["atr"] * 0.5))
    return f"{cell}|{','.join(s['id'] for s in snap['sweeps'])}|{snap['session']}"
