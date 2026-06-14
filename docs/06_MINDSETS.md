---
title: MINDSETS GUIDE
description: Mindsets guide covering Conservative, Balanced, Aggressive, and Ultra-Aggressive trading configurations
tags: [conservative, balanced, aggressive, ultra-aggressive, hft, scalping]
sidebar_position: 6
version: 6.0.0
---

![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white)
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white)

## Overview

This document describes the four supported mindsets: Conservative, Balanced, Aggressive, and Ultra-Aggressive. The Ultra-Aggressive section below contains the exact, existing configuration from the repository. The other three sections are included as templates and summaries and currently require verification against authoritative source values before being treated as canonical.

If you have the verified parameter sets for Conservative, Balanced, and Aggressive, please provide them and I will merge them into these sections verbatim. Alternatively, you can approve the proposed templates below, and I will mark them as confirmed.

---

## Conservative

Purpose: Risk-averse trading with strict thresholds, small position sizes, and limited concurrency. Intended for capital preservation and low volatility.

Status: CONFIGURATION REQUIRED — Please provide verified parameters or approve the template below.

Configuration template (replace placeholder/null values with verified numbers):

```json
{
  "risk": {
    "position_size_pct": null,
    "max_daily_loss": null,
    "max_positions_per_symbol": null,
    "max_total_positions": null
  },
  "trading": {
    "poll_interval": null,
    "confidence_threshold": null,
    "adx_threshold": null
  },
  "strategy": {
    "type": "conservative",
    "fallback_enabled": null,
    "max_fallback_attempts": null
  }
}
```

Best practices:
1. Use strict stop-loss and position sizing.
2. Test on low-leverage/demo accounts.
3. Prefer longer timeframes (e.g., M30, H1).

---

## Balanced

Purpose: A middle-ground profile balancing frequency and risk. Suited for general-purpose deployment.

Status: CONFIGURATION REQUIRED — Please provide verified parameters or approve the template below.

Configuration template:

```json
{
  "risk": {
    "position_size_pct": null,
    "max_daily_loss": null,
    "max_positions_per_symbol": null,
    "max_total_positions": null
  },
  "trading": {
    "poll_interval": null,
    "confidence_threshold": null,
    "adx_threshold": null
  },
  "strategy": {
    "type": "balanced",
    "fallback_enabled": null,
    "max_fallback_attempts": null
  }
}
```

Best practices:
1. Monitor performance and adjust position sizing.
2. Use a mix of short and medium timeframes (e.g., M15, M30).
3. Validate on paper trading before scaling.

---

## Aggressive

Purpose: Increased frequency and position sizing relative to Balanced, with higher risk tolerance and faster execution.

Status: CONFIGURATION REQUIRED — Please provide verified parameters or approve the template below.

Configuration template:

```json
{
  "risk": {
    "position_size_pct": null,
    "max_daily_loss": null,
    "max_positions_per_symbol": null,
    "max_total_positions": null
  },
  "trading": {
    "poll_interval": null,
    "confidence_threshold": null,
    "adx_threshold": null
  },
  "strategy": {
    "type": "aggressive",
    "fallback_enabled": null,
    "max_fallback_attempts": null
  }
}
```

Best practices:
1. Have strict monitoring and alerts.
2. Use leverage only if risk limits are enforced.
3. Prefer M5–M15 timeframes for higher signal density.

---

## Ultra-Aggressive

The Ultra-Aggressive mode is designed for experienced traders who want maximum trading frequency and opportunity capture. This mode operates with relaxed thresholds, higher position limits, and faster polling intervals.

⚠️ **Warning**: This mode involves significantly higher risk. Only use with proper risk management and adequate capital.

### Risk Parameters

```json
{
  "risk": {
    "position_size_pct": 15.0,
    "max_daily_loss": 500.0,
    "max_positions_per_symbol": 10,
    "max_total_positions": 10
  }
}
```

### Trading Parameters

```json
{
  "trading": {
    "poll_interval": 15,
    "confidence_threshold": 0.15,
    "adx_threshold": 15
  }
}
```

### Strategy Configuration

Enable all 7 strategies with fallback mechanism:

```json
{
  "strategy": {
    "type": "dynamic",
    "fallback_enabled": true,
    "max_fallback_attempts": 3
  }
}
```

## Best Practices (Ultra-Aggressive)

1. **Start Small**: Begin with lower position sizes until you validate performance  
2. **Monitor Closely**: Watch the system during initial deployment  
3. **Set Hard Limits**: Always configure max daily loss limits  
4. **Use on Demos First**: Test thoroughly on demo accounts before going live

## Performance Expectations (Ultra-Aggressive)

- **Signal Frequency**: High - multiple signals per hour  
- **Win Rate**: Target 60-70%  
- **Risk/Reward**: Typically 1:1.5 to 1:2  
- **Drawdown**: Expect higher volatility and drawdown

## Recommended Timeframes

- Conservative: M30, H1  
- Balanced: M15, M30  
- Aggressive: M5, M15  
- Ultra-Aggressive: M5, M15, M30

See [FEATURES_GUIDE.md](FEATURES_GUIDE.md) for complete strategy details.

---

Action required: provide verified parameter sets for Conservative, Balanced, and Aggressive, or approve the template values to finalize this document.
