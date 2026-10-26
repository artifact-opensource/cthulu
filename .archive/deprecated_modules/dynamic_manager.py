"""Lightweight dynamic position manager.

Designed for per-loop fast evaluation of open positions. It computes a small
rolling volatility estimate (approx ATR) using recent price ticks obtained via
`connector.get_recent_ticks()` if available, or falls back to simple price deltas.

API:
- evaluate(position: PositionInfo, connector, config) -> dict(action suggestions)

Suggestions include: `adjust_sl` (new SL price), `adjust_tp`, `mindset`, and `reason`.

The implementation is intentionally conservative and fast: no heavy numpy/pandas
use and minimal I/O. It is safe to call every loop; callers should enforce
rate-limits on actual order modifications.
"""
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

# Fast, dependency-free approximate ATR using recent ticks

def _approx_atr_from_ticks(price_history: "list[float]") -> Optional[float]:
    if not price_history or len(price_history) < 2:
        return None
    # True range approximated by successive absolute differences
    trs = [abs(price_history[i] - price_history[i-1]) for i in range(1, len(price_history))]
    # Return simple moving average
    return sum(trs) / len(trs) if trs else None


def evaluate(position, connector, config: Dict[str, Any]) -> Dict[str, Any]:
    """Evaluate a `PositionInfo` and return suggestion dict.

    position: PositionInfo
    connector: connector object (should provide `get_recent_ticks(symbol, seconds)` or `symbol_info_tick`)
    config: dict containing 'risk' and dynamic manager knobs
    """
    # Default response
    res: Dict[str, Any] = {
        "adjust_sl": None,
        "adjust_tp": None,
        "reason": "no_action",
        "mindset": None,
        "relative_atr": None,
    }

    try:
        symbol = position.symbol
        current_price = float(position.current_price or position.open_price)
        side = position.side or "BUY"

        # Get short history (best-effort): prefer connector.get_recent_ticks
        price_history = []
        try:
            if hasattr(connector, 'get_recent_ticks'):
                # get ticks for last 60 seconds
                ticks = connector.get_recent_ticks(symbol, seconds=60)
                # ticks expected as list of dicts with 'price'
                price_history = [float(t['price']) for t in ticks][-30:]
            else:
                # fallback: use the current_price repeated (no vol)
                price_history = [current_price]
        except Exception:
            # fallback to single price
            price_history = [current_price]

        atr = _approx_atr_from_ticks(price_history)
        res['relative_atr'] = (atr / current_price) if (atr and current_price) else None

        # Determine current SL distance in relative terms
        sl = position.stop_loss or None
        if sl and current_price:
            sl_dist = abs(current_price - sl)
            sl_rel = sl_dist / current_price
        else:
            sl_rel = None

        # Use risk thresholds for decision; conservative defaults
        risk = config.get('risk', {}) if isinstance(config, dict) else {}
        # pick a target atr multiplier (how many ATRs as SL)
        atr_multiplier = float(risk.get('dynamic_atr_multiplier', 3.0))
        max_rel_for_atr = float(risk.get('max_rel_sl', 0.25))

        # If we have ATR and sl_rel, consider tightening if SL >> atr*multiplier
        if atr and sl_rel is not None:
            target_rel = (atr * atr_multiplier) / current_price
            # bound target_rel by max_rel_for_atr
            if target_rel > max_rel_for_atr:
                target_rel = max_rel_for_atr

            if sl_rel > target_rel * 1.2:
                # propose tightened SL
                if side == 'BUY':
                    new_sl = current_price - (target_rel * current_price)
                else:
                    new_sl = current_price + (target_rel * current_price)
                res.update({
                    'adjust_sl': float(new_sl),
                    'reason': f'tighten_sl: sl_rel={sl_rel:.4f} target={target_rel:.4f}',
                    'mindset': 'scalping' if target_rel < 0.02 else 'short-term'
                })
                return res

        # If no SL present, suggest a SL based on ATR
        if not sl and atr:
            target_rel = min((atr * atr_multiplier) / current_price, float(risk.get('max_rel_sl', 0.25)))
            if side == 'BUY':
                new_sl = current_price - (target_rel * current_price)
            else:
                new_sl = current_price + (target_rel * current_price)
            res.update({
                'adjust_sl': float(new_sl),
                'reason': 'add_sl_based_on_atr',
                'mindset': 'scalping' if target_rel < 0.02 else 'short-term'
            })
            return res

        # No action
        return res

    except Exception as e:
        return {"adjust_sl": None, "adjust_tp": None, "reason": f"error:{e}", "mindset": None}




