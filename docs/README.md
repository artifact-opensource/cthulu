# Cthulu-RB (Rule-Based)

> **Rule-Based Autonomous Trading System**  
> Version: 1.0.0  
> Branch: windows (rule-based)

## Overview

Cthulu-RB is a clean, rule-based implementation of the Cthulu trading system. It focuses on:
- **Proper signal generation** with SMA/EMA crossovers and continuation signals
- **Dynamic SL/TP management** that actually works with proper mode transitions
- **ATR-based calculations** for volatility-adaptive trading
- **Multi-strategy selection** based on market regime

## Quick Start

```bash
# Ensure .env file has MT5 credentials
python -m cthulu_rb
```

## Architecture

```
cthulu-rb/
├── core/           # Bootstrap, trading loop, signal engine
├── strategy/       # SMA, EMA, Momentum, Scalping, Mean Reversion, Trend Following
├── risk/           # Dynamic SLTP, position sizing, drawdown management
├── position/       # Trade manager, adoption, lifecycle
├── execution/      # Order execution engine
├── exit/           # Trailing stop, partial profits, time-based exits
├── cognition/      # Entry confluence filter
├── connector/      # MT5 connection
├── data/           # Market data layer with caching
├── indicators/     # ATR, RSI, MACD, Bollinger Bands, etc.
├── filters/        # Liquidity and spread filters
├── monitoring/     # Trade monitoring, metrics
└── persistence/    # SQLite database
```

## Key Features

### Signal Generation
- **SMA Crossover**: 10/30 period with continuation signals
- **EMA Crossover**: 12/26 period (MACD-style)
- **Momentum Breakout**: High/Low breakout with RSI confirmation
- **Scalping**: Fast EMA with RSI overbought/oversold
- **Mean Reversion**: Bollinger Band bounce
- **Trend Following**: MA alignment with ADX filter
- **RSI Reversal**: RSI extreme levels

### Dynamic SL/TP Modes
1. **Initial**: ATR-based SL (2x) and TP (4x) on trade entry
2. **Breakeven**: Move SL to entry + buffer when profit > 1 ATR
3. **Trailing**: Lock 50%+ of profits when profit > 1.5 ATR

### Entry Confluence
- Support/Resistance proximity scoring
- Momentum alignment check
- Session timing evaluation
- Market structure analysis

## Configuration

See `config.json` for all configurable parameters:
- `symbol`: Trading instrument (e.g., "GOLDm#")
- `timeframe`: Chart timeframe (M1, M5, M15, H1, etc.)
- `risk`: Position sizing and limits
- `dynamic_sltp`: ATR multipliers for SL/TP
- `entry_confluence`: Scoring weights and thresholds
- `strategy_selector`: Enabled strategies and weights

## Environment Variables

Create `.env` file:
```
MT5_LOGIN=your_login
MT5_PASSWORD=your_password
MT5_SERVER=your_server
```

## Logs

All logs are written to console with timestamps and levels:
- `INFO`: Normal operations
- `WARNING`: Non-critical issues
- `ERROR`: Failures that need attention

## Database

SQLite database (`cthulu.db`) stores:
- Trade history
- Signal records
- Performance metrics
