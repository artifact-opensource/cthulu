# Ultra-Aggressive Mindset Configuration

> **v6.0.0** | High-Risk, High-Reward Trading Profile
>
> **Legacy configuration note:** The per-timeframe JSON files below are older configuration presets. The current Windows launcher selects `config.json` for Single/HFT or `config_multi.json` for Multi; it does not select these files directly. Use the first-run wizard and review its risk values before trading.

## Overview

The Ultra-Aggressive mindset is designed for experienced traders who understand and accept higher risk 
in pursuit of larger returns. It combines dynamic strategy selection with aggressive position sizing 
and reduced confirmation thresholds.

## Key Characteristics

| Parameter | Value | Description |
|-----------|-------|-------------|
| **Position Size %** | 15% | Larger equity allocation per trade |
| **Max Daily Loss** | $500 | Higher loss tolerance |
| **Max Positions** | 10 | More concurrent positions allowed |
| **Confidence Threshold** | 0.20-0.35 | Lower barrier for signal acceptance |
| **Kelly Sizing** | Enabled | Dynamic sizing based on win rate |
| **Circuit Breaker** | 7% | Emergency stop threshold |

## Timeframe Configurations

| Timeframe | File | Primary Use |
|-----------|------|-------------|
| **M1** | `config_ultra_aggressive_m1.json` | Scalping, micro-movements |
| **M5** | `config_ultra_aggressive_m5.json` | High-frequency trend capture |
| **M15** | `config_ultra_aggressive_m15.json` | Dynamic strategy selector |
| **M30** | `config_ultra_aggressive_m30.json` | Swing capture |
| **H1** | `config_ultra_aggressive_h1.json` | Medium-term trends |
| **H4** | `config_ultra_aggressive_h4.json` | Position trading |
| **D1** | `config_ultra_aggressive_d1.json` | Long-term trends |

## Strategy Mix

All ultra-aggressive configs use dynamic strategy selection with these strategies:

1. **RSI Reversal** - Extreme overbought/oversold captures
2. **EMA Crossover** - Fast/slow moving average signals
3. **Scalping** - Quick micro-profit captures
4. **Momentum Breakout** - Breakout detection
5. **Mean Reversion** - Bollinger band reversals
6. **Trend Following** - ADX-confirmed trends
7. **SMA Crossover** - Classic crossover signals

## Risk Management

- **Emergency Stop**: 12-18% depending on timeframe
- **Trailing Lock**: Automatic profit protection at 30-65%
- **Adaptive Drawdown**: Three-tier protection (survival/critical/danger)
- **Micro Account Protection**: Tiered profit-taking for small accounts

## Usage

For the current Windows flow, complete the [first-run setup](../../../docs/02_QUICKSTART.md), then start `Cthulu Launcher.bat`. Select **Multi** to use `config_multi.json` and the launcher's configured ultra-aggressive Legacy mindset. The launcher does not use a command-line `--wizard` flow to select one of the per-timeframe JSON files above.

## ⚠️ Warning

This mindset is for **experienced traders only**. The higher risk parameters can lead to 
significant losses. Always:

1. Test on a dedicated MT5 demo account first
2. Use appropriate account sizing
3. Monitor positions actively
4. Have circuit breakers enabled

---
*Part of Cthulu Trading System v6.0.0*
