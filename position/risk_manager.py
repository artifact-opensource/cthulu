"""Compatibility helpers for position-level risk utilities (small stubs).
These provide minimal implementations used by ExecutionEngine helpers during tests.
"""
from typing import Optional, Dict, Any


def _threshold_from_config(balance: float, sl_balance_thresholds: Optional[Dict] = None, sl_balance_breakpoints: Optional[Dict] = None) -> Dict[str, Any]:
    """Determine threshold percentage and suggested mindset given balance and optional configs.

    Returns a dict: {'threshold': float, 'category': str, 'suggested_mindset': str}
    
    CRITICAL NOTE: Stop loss thresholds must be reasonable (1-5% range).
    Previously 'large' was set to 0.25 (25%) which caused massive losses.
    This has been fixed to 0.05 (5%). DO NOT increase beyond 0.10 (10%)!
    """
    # Default breakpoints and thresholds
    # WARNING: DO NOT SET ANY THRESHOLD > 0.10 (10%) - this causes excessive losses!
    default_breakpoints = [1000.0, 5000.0, 20000.0]
    default_thresholds = {
        'tiny': 0.01,    # 1% - for accounts ≤ $1,000
        'small': 0.02,   # 2% - for accounts ≤ $5,000
        'medium': 0.05,  # 5% - for accounts ≤ $20,000
        'large': 0.05    # 5% - for accounts > $20,000 (FIXED: was 0.25/25%!)
    }
    if sl_balance_thresholds and isinstance(sl_balance_thresholds, dict):
        thresholds = sl_balance_thresholds
    else:
        thresholds = default_thresholds
    breakpoints = sl_balance_breakpoints or default_breakpoints

    if balance <= breakpoints[0]:
        cat = 'tiny'
        mindset = 'scalping'
    elif balance <= breakpoints[1]:
        cat = 'small'
        mindset = 'short-term'
    elif balance <= breakpoints[2]:
        cat = 'medium'
        mindset = 'swing'
    else:
        cat = 'large'
        mindset = 'position'

    return {'threshold': float(thresholds.get(cat, 0.01)), 'category': cat, 'suggested_mindset': mindset}


def suggest_sl_adjustment(symbol: str, balance: float, price: float, proposed_sl: float, side: str = 'BUY', thresholds: Optional[Dict] = None, breakpoints: Optional[Dict] = None) -> Dict[str, Any]:
    """Suggest SL adjustments based on configured thresholds and balance.

    If the proposed SL is within the threshold (as a fraction of price), return adjusted_sl=None.
    Otherwise return a suggestion with adjusted_sl and reason.
    """
    try:
        cfg = _threshold_from_config(balance, thresholds, breakpoints)
        threshold = cfg.get('threshold', 0.01)
        category = cfg.get('category')
        suggested_mindset = cfg.get('suggested_mindset')

        diff_pct = abs(price - proposed_sl) / price if price else 0.0

        if diff_pct <= threshold:
            return {'adjusted_sl': None, 'reason': 'within threshold', 'threshold': threshold}
        else:
            reason = f"exceeds threshold ({category})"
            # Optionally adjust SL closer to a suggested safe distance
            # For now, provide the same proposed_sl but mark it as adjusted
            return {
                'adjusted_sl': proposed_sl,
                'reason': reason,
                'threshold': threshold,
                'diff_pct': diff_pct,
                'suggested_mindset': suggested_mindset
            }
    except Exception:
        return {'adjusted_sl': proposed_sl, 'reason': 'error'}




