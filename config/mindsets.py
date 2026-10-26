"""
Trading Mindsets / Risk Profiles

Provides preset configurations for different trading styles:
- AGGRESSIVE: Higher risk, faster entries, tighter stops
- BALANCED: Default moderate risk/reward settings  
- CONSERVATIVE: Lower risk, wider stops, stricter filters

Usage:
    from cthulu.config.mindsets import MINDSETS, apply_mindset
    
    # Apply a mindset to your config
    config = apply_mindset(base_config, "balanced")
    
    # Or use CLI: python -m herald --mindset balanced
"""

from typing import Dict, Any
from copy import deepcopy


# Aggressive profile: higher risk tolerance, faster signals
AGGRESSIVE = {
    "name": "aggressive",
    "description": "Higher risk, faster entries, tighter stops. For experienced traders.",
    
    "risk": {
        "max_position_size": 1.0,         # Up to 1 lot per position
        "default_position_size": 0.05,    # Default 0.05 lots
        "position_size_pct": 5.0,         # 5% of equity per trade
        "max_daily_loss": 100.0,          # $100 daily loss limit
        "max_positions_per_symbol": 2,    # Allow 2 positions per symbol
        "max_total_positions": 5,         # Allow up to 5 total positions
        "use_kelly_sizing": True,         # Use Kelly criterion
        "emergency_stop_loss_pct": 8.0,   # 8% emergency stop
        "circuit_breaker_enabled": True,
        "circuit_breaker_threshold_pct": 5.0,  # 5% circuit breaker
    },
    
    "strategy": {
        "sma_crossover": {
            "short_window": 5,            # Fast: 5-period SMA
            "long_window": 15,            # Slow: 15-period SMA
            "atr_period": 10,             # Faster ATR
            "atr_multiplier": 1.5,        # Tighter stops
            "risk_reward_ratio": 2.5,     # Higher R:R target
        }
    },
    
    "trading": {
        "poll_interval": 30,              # Check every 30 seconds
        "lookback_bars": 300,             # Less historical data
    },
    
    "confidence_threshold": 0.5,          # Lower confidence required
}


# Balanced profile: moderate risk/reward
BALANCED = {
    "name": "balanced",
    "description": "Moderate risk, balanced approach. Recommended for most users.",
    
    "risk": {
        "max_position_size": 0.5,         # Up to 0.5 lots per position
        "default_position_size": 0.02,    # Default 0.02 lots
        "position_size_pct": 2.0,         # 2% of equity per trade
        "max_daily_loss": 50.0,           # $50 daily loss limit
        "max_positions_per_symbol": 1,    # 1 position per symbol
        "max_total_positions": 3,         # Allow up to 3 total positions
        "use_kelly_sizing": False,        # Fixed sizing
        "emergency_stop_loss_pct": 5.0,   # 5% emergency stop
        "circuit_breaker_enabled": True,
        "circuit_breaker_threshold_pct": 3.0,  # 3% circuit breaker
    },
    
    "strategy": {
        "sma_crossover": {
            "short_window": 10,           # Fast: 10-period SMA
            "long_window": 30,            # Slow: 30-period SMA
            "atr_period": 14,             # Standard ATR
            "atr_multiplier": 2.0,        # Standard stops
            "risk_reward_ratio": 2.0,     # 2:1 R:R
        }
    },
    
    "trading": {
        "poll_interval": 60,              # Check every minute
        "lookback_bars": 500,             # Standard history
    },
    
    "confidence_threshold": 0.6,          # Moderate confidence required
}


# Conservative profile: lower risk, stricter filters
CONSERVATIVE = {
    "name": "conservative",
    "description": "Lower risk, wider stops, stricter entry filters. Capital preservation focus.",
    
    "risk": {
        "max_position_size": 0.2,         # Up to 0.2 lots per position
        "default_position_size": 0.01,    # Default 0.01 lots
        "position_size_pct": 1.0,         # 1% of equity per trade
        "max_daily_loss": 25.0,           # $25 daily loss limit
        "max_positions_per_symbol": 1,    # 1 position per symbol
        "max_total_positions": 2,         # Allow up to 2 total positions
        "use_kelly_sizing": False,        # Fixed sizing
        "emergency_stop_loss_pct": 3.0,   # 3% emergency stop
        "circuit_breaker_enabled": True,
        "circuit_breaker_threshold_pct": 2.0,  # 2% circuit breaker
    },
    
    "strategy": {
        "sma_crossover": {
            "short_window": 20,           # Fast: 20-period SMA (slower signals)
            "long_window": 50,            # Slow: 50-period SMA
            "atr_period": 20,             # Longer ATR period
            "atr_multiplier": 2.5,        # Wider stops
            "risk_reward_ratio": 1.5,     # Conservative R:R
        }
    },
    
    "trading": {
        "poll_interval": 120,             # Check every 2 minutes
        "lookback_bars": 750,             # More historical data
    },
    
    "confidence_threshold": 0.75,         # Higher confidence required
}


# All available mindsets
MINDSETS: Dict[str, Dict[str, Any]] = {
    "aggressive": AGGRESSIVE,
    "balanced": BALANCED, 
    "conservative": CONSERVATIVE,
}


# Ultra-Aggressive profile: very high-frequency, dynamic strategy mix
ULTRA_AGGRESSIVE = {
    "name": "ultra_aggressive",
    "description": "Ultra-Aggressive: dynamic strategy selector + scalping/day strategies for experienced traders.",
    "risk": {
        "max_position_size": 2.0,
        "default_position_size": 0.1,
        "position_size_pct": 15.0,
        "max_daily_loss": 500.0,
        "max_positions_per_symbol": 3,
        "max_total_positions": 10,
        "use_kelly_sizing": True,
        "emergency_stop_loss_pct": 12.0,
        "circuit_breaker_enabled": True,
        "circuit_breaker_threshold_pct": 7.0,
        "max_spread_points": 5000.0,
        "max_spread_pct": 0.05
    }, 
    # Provide a full strategy replacement for dynamic mode
    "strategy_full": {
        "type": "dynamic",
        "dynamic_selection": {
            "enabled": True,
            "regime_check_interval": 120,
            "min_strategy_signals": 2,
            "performance_weight": 0.35,
            "regime_weight": 0.35,
            "confidence_weight": 0.30
        },
        "strategies": [
            {"type": "rsi_reversal", "params": {"rsi_period": 14, "rsi_extreme_oversold": 32, "rsi_extreme_overbought": 78, "atr_multiplier": 1.0, "risk_reward_ratio": 2.5, "cooldown_bars": 3}},
            {"type": "ema_crossover", "params": {"fast_period": 8, "slow_period": 21, "atr_period": 14, "atr_multiplier": 1.2, "risk_reward_ratio": 3.0}},
            {"type": "scalping", "params": {"fast_ema": 5, "slow_ema": 10, "rsi_period": 7, "rsi_oversold": 20, "rsi_overbought": 80, "rsi_long_max": 65, "rsi_short_min": 35, "atr_multiplier": 0.8, "risk_reward_ratio": 2.5}},
            {"type": "momentum_breakout", "params": {"lookback_period": 15, "rsi_threshold": 45, "atr_multiplier": 1.3, "risk_reward_ratio": 3.5}},
            {"type": "mean_reversion", "params": {"ma_period": 20, "bb_std": 2.0, "rsi_period": 14, "rsi_oversold": 35, "rsi_overbought": 65, "atr_multiplier": 1.0, "risk_reward_ratio": 2.0}},
            {"type": "trend_following", "params": {"fast_ma": 20, "slow_ma": 50, "adx_period": 14, "adx_threshold": 18, "atr_multiplier": 1.5, "risk_reward_ratio": 2.5}},
            {"type": "sma_crossover", "params": {"fast_period": 5, "slow_period": 13, "atr_period": 14, "atr_multiplier": 1.5, "risk_reward_ratio": 2.5}}
        ]
    },
    "trading": {
        "poll_interval": 15,
        "lookback_bars": 500,
        "symbol": "BTCUSD#",
        "timeframe": "TIMEFRAME_M15"
    },
    "indicators": [
        {"type": "rsi", "params": {"period": 14}},
        {"type": "rsi", "params": {"period": 7}},
        {"type": "macd", "params": {"fast_period": 12, "slow_period": 26, "signal_period": 9}},
        {"type": "bollinger", "params": {"period": 20, "std_dev": 2.0}},
        {"type": "adx", "params": {"period": 14}},
        {"type": "supertrend", "params": {"period": 10, "multiplier": 3.0}},
        {"type": "vwap", "params": {"std_dev_multiplier": 2.0}}
    ],
    "confidence_threshold": 0.25
}

# expose ultra aliases
MINDSETS.update({"ultra_aggressive": ULTRA_AGGRESSIVE, "ultra": ULTRA_AGGRESSIVE})


def apply_mindset(config: Dict[str, Any], mindset_name: str) -> Dict[str, Any]:
    """
    Apply a mindset preset to a configuration.
    
    The mindset values override the base config values.
    MT5 credentials and other non-mindset settings are preserved.
    
    Args:
        config: Base configuration dictionary
        mindset_name: One of "aggressive", "balanced", "conservative"
        
    Returns:
        New configuration dict with mindset applied
        
    Raises:
        ValueError: If mindset_name is not recognized
    """
    mindset_name = mindset_name.lower()
    
    if mindset_name not in MINDSETS:
        available = ", ".join(MINDSETS.keys())
        raise ValueError(f"Unknown mindset '{mindset_name}'. Available: {available}")
    
    mindset = MINDSETS[mindset_name]
    result = deepcopy(config)
    
    # Apply risk settings
    if "risk" in mindset:
        if "risk" not in result:
            result["risk"] = {}
        result["risk"].update(mindset["risk"])
    
    # Apply strategy settings
    if "strategy" in mindset:
        strategy_type = result.get("strategy", {}).get("type", "sma_crossover")
        if strategy_type in mindset["strategy"]:
            if "strategy" not in result:
                result["strategy"] = {"type": strategy_type, "params": {}}
            if "params" not in result["strategy"]:
                result["strategy"]["params"] = {}
            result["strategy"]["params"].update(mindset["strategy"][strategy_type])

    # Allow a mindset to supply a full strategy replacement (useful for dynamic selectors)
    if "strategy_full" in mindset:
        # Replace the full strategy section with the provided structure
        result["strategy"] = deepcopy(mindset["strategy_full"])
    
    # Apply trading settings
    if "trading" in mindset:
        if "trading" not in result:
            result["trading"] = {}
        result["trading"].update(mindset["trading"])

    # Apply indicators if provided by the mindset
    if "indicators" in mindset:
        # Replace or set indicators list
        result["indicators"] = deepcopy(mindset["indicators"])
    
    # Store confidence threshold
    if "confidence_threshold" in mindset:
        result["confidence_threshold"] = mindset["confidence_threshold"]
    
    # Mark which mindset was applied
    result["_mindset"] = mindset_name
    
    return result


def get_mindset_info(mindset_name: str) -> Dict[str, Any]:
    """
    Get information about a specific mindset.
    
    Args:
        mindset_name: Mindset name
        
    Returns:
        Mindset configuration dict
    """
    mindset_name = mindset_name.lower()
    if mindset_name not in MINDSETS:
        raise ValueError(f"Unknown mindset: {mindset_name}")
    return MINDSETS[mindset_name]


def list_mindsets() -> Dict[str, str]:
    """
    List available mindsets with descriptions.
    
    Returns:
        Dict of mindset_name -> description
    """
    return {name: m["description"] for name, m in MINDSETS.items()}




