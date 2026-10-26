# Advisory Manager


 ![Version](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
 ![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white) 


---

## Overview

The Advisory Manager provides **safe deployment testing modes** for Cthulu without executing real trades. It is designed for **validation and testing**, not live trading cognition.

## Modes

### Advisory Mode (Paper Trading)
- **Purpose**: Signal logging without execution
- **Use Case**: Validate signal generation logic
- **Behavior**: Records all signals and order intentions to ML collector
- **Risk**: Zero - no orders placed

### Ghost Mode (Micro-Testing)
- **Purpose**: Tiny test trades to validate live plumbing
- **Use Case**: Verify execution engine connectivity
- **Behavior**: Places minimal lot size orders with strict caps
- **Risk**: Controlled - max trades and duration enforced

### Production Mode
- **Purpose**: Normal operation
- **Behavior**: Orders proceed through standard execution
- **Risk**: Full - standard risk management applies

## Configuration

```json
{
  "advisory": {
    "enabled": false,
    "mode": "advisory",
    "ghost_lot_size": 0.01,
    "ghost_max_trades": 5,
    "ghost_max_duration": 3600,
    "log_only": false
  }
}
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | false | Enable advisory/ghost modes |
| `mode` | string | "advisory" | Mode: advisory, ghost, production |
| `ghost_lot_size` | float | 0.01 | Lot size for ghost trades |
| `ghost_max_trades` | int | 5 | Maximum ghost trades allowed |
| `ghost_max_duration` | int | 3600 | Ghost window duration (seconds) |
| `log_only` | bool | false | Log without any execution |

## When to Use

### Advisory Mode
- Testing new signal generators
- Validating indicator calculations
- Paper trading strategy variants
- Pre-production validation

### Ghost Mode
- Verifying broker connectivity
- Testing execution engine plumbing
- Validating order flow end-to-end
- Post-deployment sanity checks

### Production Mode
- Live trading (advisory disabled)
- Standard operation

## Safety Features

1. **Trade Caps**: Ghost mode enforces strict maximum trades
2. **Time Windows**: Ghost mode auto-expires after duration
3. **Async Processing**: Ghost orders queued for background processing
4. **ML Recording**: All decisions recorded for analysis

## Integration

The Advisory Manager integrates with:
- **Execution Engine**: Intercepts order requests
- **ML Collector**: Records all advisory events
- **Signal Pipeline**: Validates signals without execution

## Important Notes

> ⚠️ **Advisory is NOT a decision enhancer** - it's for testing and validation only.

> ⚠️ **Ghost mode uses real funds** - ensure caps are appropriate for your account.

> ⚠️ **Production mode bypasses advisory** - orders execute normally.

---

<div align="center">

**Cthulu Trading System** · v6.0.0

</div>
