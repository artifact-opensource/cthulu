"""Risk manager helpers

Provide simple, conservative heuristics to adjust stop-loss/take-profit distances
based on account balance and current price. Also recommend timeframes/mindsets
when required SL distances are too wide for the account size.

This module is intentionally lightweight and rule-based so it can be refined
later with more accurate pip/lot conversions and symbol-specific volatility.
"""
from typing import Optional, Dict, Any, Sequence


def _threshold_from_config(balance: float, thresholds: Optional[Dict[str, float]] = None,
                           breakpoints: Optional[Sequence[float]] = None) -> float:
    """Compute a relative threshold using either provided thresholds/breakpoints
    or fallback heuristics. `breakpoints` is an ascending list of balances that
    map to the ordered values in `thresholds`.
    """
    # If custom thresholds are provided as a mapping label->value and breakpoints
    # provide the numeric ranges, map them accordingly.
    try:
        if thresholds and breakpoints and isinstance(breakpoints, Sequence):
            # thresholds might be a dict with labels, but we treat the values in
            # insertion order by typical callers (yaml/json preserves order in modern Pythons).
            vals = list(thresholds.values())
            # If mismatched lengths, fallback
            if len(vals) == len(breakpoints) + 1:
                # Determine bucket
                for i, bp in enumerate(breakpoints):
                    if balance <= bp:
                        return float(vals[i])
                return float(vals[-1])
    except Exception:
        pass

    # Fallback heuristics
    if balance <= 0:
        return 0.01
    if balance < 1000:
        return 0.01
    if balance < 5000:
        return 0.02
    if balance < 20000:
        return 0.05
    return 0.25


def suggest_sl_adjustment(
    symbol: str,
    balance: float,
    current_price: float,
    proposed_sl: float,
    side: Optional[str] = "BUY",
    thresholds: Optional[Dict[str, float]] = None,
    breakpoints: Optional[Sequence[float]] = None,
) -> Dict[str, Any]:
    """Suggest an adjusted SL if the proposed SL is too wide for the account.

    Accepts optional `thresholds` and `breakpoints` to override default scaling.
    """
    result = {
        "adjusted_sl": None,
        "reason": "",
        "suggested_timeframes": [],
        "suggested_mindset": "",
        "relative_distance": None,
    }

    if current_price is None or proposed_sl is None:
        result["reason"] = "missing price/SL"
        return result

    try:
        dist = abs(proposed_sl - current_price)
        rel = dist / current_price if current_price != 0 else 0.0
        result["relative_distance"] = rel

        threshold = _threshold_from_config(balance, thresholds, breakpoints)

        if rel <= threshold:
            result["reason"] = "within threshold"
            return result

        # Compute adjusted SL nearer to price based on threshold
        if side == "BUY":
            adjusted_price = current_price * (1.0 - threshold)
        else:
            adjusted_price = current_price * (1.0 + threshold)

        # Suggest timeframes and mindset
        if threshold <= 0.02:
            tf = ["M1", "M5", "M15"]
            mindset = "scalping"
        elif threshold <= 0.05:
            tf = ["M15", "M30", "H1"]
            mindset = "short-term"
        else:
            tf = ["H1", "H4", "D1"]
            mindset = "swing"

        result.update({
            "adjusted_sl": float(adjusted_price),
            "reason": f"proposed SL ({rel:.3f} rel) exceeds threshold ({threshold:.3f}) for balance {balance}",
            "suggested_timeframes": tf,
            "suggested_mindset": mindset,
        })
        return result

    except Exception as e:
        result["reason"] = f"error computing suggestion: {e}"
        return result




