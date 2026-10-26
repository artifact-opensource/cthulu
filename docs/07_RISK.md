---
title: RISK MANAGEMENT
description: Risk management configuration and stop-loss strategies for Cthulu trading system
tags: [risk-management, stop-loss, position-sizing]
sidebar_position: 7
version: 6.0.0
---

![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--17-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white) 


## Overview

> This document describes the risk-management features in Cthulu and how the system adapts position sizing and stop-loss placement to account conditions.

### Key Features (v6.0.0)

- **Performance-Based Sizing**: Adjusts position size based on recent win rate
- **Centralized Position Sizing**: Full audit trail with `PositionSizeDecision` dataclass
- **Strict Quality Gate**: Only GOOD/PREMIUM entries execute
- **Momentum-Aware Scaling**: Profit scaler detects momentum to let winners run
- **Drawdown Halt**: Automatic trading halt at configurable drawdown threshold

### Configuration

Key configuration entries (in `config.json` under `risk`):

```json
{
  "risk": {
    "max_position_size": 2.0,
    "default_position_size": 0.01,
    "max_daily_loss": 5.0,
    "max_positions_per_symbol": 3,
    "max_total_positions": 4,
    "position_size_pct": 10.0,
    "use_kelly_sizing": true,
    "emergency_stop_loss_pct": 12.0,
    "circuit_breaker_enabled": true,
    "circuit_breaker_threshold_pct": 7.0,
    "performance_based_sizing": true,
    "min_risk_reward_ratio": 1.5,
    "drawdown_halt_percent": 40.0
  }
}
```

### Position Sizing Pipeline (v6.0.0)

All position size adjustments are now centralized with full audit trail:

```python
@dataclass
class PositionSizeDecision:
    base_size: float                      # From RiskEvaluator
    adjustments: List[Tuple[str, float]]  # (reason, multiplier)
    final_size: float
    reasoning: str                        # Full audit string
```

**Adjustment Sources:**
1. **Entry Quality** - GOOD/PREMIUM multiplier (0.85-1.0)
2. **Loss Curve** - Adaptive loss curve adjustment
3. **Cognition** - AI/ML signal enhancement multiplier
4. **Performance** - Win-rate based adjustment (if enabled)

**Example Log Output:**
```
💰 Position sizing: 0.10 × (entry_quality(good)=0.85 × cognition=1.10) → 0.09
```

---

## Stop-Loss Management

Key configuration entries (in `config_schema.py` under `risk`):

- `emergency_stop_loss_pct` (float): default emergency stop used when adopting external trades (percent, e.g. `8.0`).
- `sl_balance_thresholds` (mapping): relative SL thresholds mapped to balance buckets. Example:

```json
"sl_balance_thresholds": {
  "tiny": 0.01,
  "small": 0.02,
  "medium": 0.05,
  "large": 0.05
}
```

- `sl_balance_breakpoints` (list): numeric breakpoints that map to the thresholds. Example: `[1000.0, 5000.0, 20000.0]`.

Behavior summary:

- When placing a new order (or when applying SL during adoption), Cthulu calls `position.risk_manager.suggest_sl_adjustment(...)` with the account balance and proposed SL.
- If the proposed SL is wider than a computed relative threshold, the `risk_manager` returns an `adjusted_sl` nearer to market and suggests target timeframes and a trading mindset (`scalping`, `short-term`, `swing`).
- The `ExecutionEngine` and `PositionManager` will apply the adjusted SL automatically and attach the suggestion to order/position metadata.

Operational guidance:

- For small accounts (<= 1k), thresholds are tight so Cthulu will favor scalping timeframes (`M1`, `M5`, `M15`) and small SLs.
- For larger accounts (> $20k), the threshold remains conservative at 5% to prevent excessive risk on losing trades.
- **Critical Fix (v5.1):** The 'large' account threshold was corrected from 0.25 (25%) to 0.05 (5%) to prevent catastrophic losses on large accounts. See `docs/STOP_LOSS_BUG_FIX.md` for details.

Additional safety features:

- **Execution Engine Cap:** The execution engine enforces a default maximum stop loss of 10% with a hard cap at 15%, providing an additional safety layer beyond the configured thresholds.
- **Balance Category Thresholds:**
  - **Tiny** (≤ $1,000): 1% stop loss
  - **Small** ($1,001 - $5,000): 2% stop loss
  - **Medium** ($5,001 - $20,000): 5% stop loss
  - **Large** (> $20,000): 5% stop loss

Future improvements:

- Symbol-specific pip scaling and lot-size-aware distance calculations.
- Volatility-based dynamic thresholds using recent ATR.




