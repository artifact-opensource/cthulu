---
title: FEATURES GUIDE
description: Comprehensive guide to Cthulu's advanced trading strategies, next-generation indicators, and dynamic strategy selection system
tags: [features, strategies, indicators, dynamic-selection, SAFE]
slug: /docs/features
sidebar_position: 5
version: 6.0.0
---
````
_________   __  .__          .__         
\_   ___ \_/  |_|  |__  __ __|  |  __ __ 
/    \  \/\   __\  |  \|  |  \  | |  |  \
\     \____|  | |   Y  \  |  /  |_|  |  /
 \______  /|__| |___|  /____/|____/____/ 
        \/           \/                  
````    

 ![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white)
 ![Last Update](https://img.shields.io/badge/Last_Update-2026--01--17-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
 ![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?branch=main&style=for-the-badge&logo=github&labelColor=0D1117&color=6A00FF)


## Overview

> This document describes the major features of the Cthulu trading system — a cutting-edge, multi-strategy autonomous trading platform with dynamic strategy selection, next-generation indicators, and the revolutionary **SAFE (Set And Forget Engine)** architecture.

### SAFE: Set And Forget Engine

👾 Cthulu v5.3.0 "EVOQUE" continues the SAFE paradigm with enhanced quality controls:
- **S**mart strategy selection with intelligent fallback
- **A**daptive to all market conditions (ranging, trending, volatile)
- **F**ully autonomous signal generation without manual intervention
- **E**xpert-level risk management with survival mode protection
- **NEW:** Strict quality gate - only GOOD/PREMIUM entries execute
- **NEW:** Momentum-aware profit scaling - let winners run

## Table of Contents

1. [Trading Strategies (7 Active)](#trading-strategies)
2. [Next-Generation Indicators](#next-generation-indicators)
3. [Dynamic Strategy Selection](#dynamic-strategy-selection)
4. [Multi-Strategy Fallback](#multi-strategy-fallback)
5. [Entry Quality Gate (v5.3.0)](#entry-quality-gate)
6. [Ultra-Aggressive Mode](#ultra-aggressive-mode)
7. [Equity Curve Management](#equity-curve-management)
8. [Exit Management System](#exit-management-system)
9. [Adaptive Loss Curve](#adaptive-loss-curve)
10. [Confluence Exit Manager](#confluence-exit-manager)
11. [Micro Account Protection](#micro-account-protection)
12. [Profit Scaling System](#profit-scaling-system)
13. [Adaptive Account Manager](#adaptive-account-manager)
14. [Liquidity Trap Detection](#liquidity-trap-detection)
15. [SPARTA Mode](#sparta-mode-battle-testing)
15. [Create Your Own Mode](#create-your-own-mode)
16. [Real-Time Observability](#real-time-observability)
17. [Configuration Guide](#configuration-guide)
18. [Usage Examples](#usage-examples)
19. [Performance Tuning](#performance-tuning)

---

## Trading Strategies

Cthulu v5.3.0 includes **7 active trading strategies**, each optimized for specific market conditions:

| Strategy | Type | Best Regime | Signal Speed | Crossover Required |
|----------|------|-------------|--------------|-------------------|
| RSI Reversal | Reversal | REVERSAL, VOLATILE | Instant | ❌ No |
| EMA Crossover | Trend | TRENDING | Fast | ✅ Yes |
| SMA Crossover | Trend | TRENDING_WEAK | Medium | ✅ Yes |
| Momentum Breakout | Breakout | VOLATILE_BREAKOUT | Medium | ❌ No |
| Scalping | Mean Reversion | RANGING_TIGHT | Ultra-Fast | ✅ Yes |
| Mean Reversion | Reversal | RANGING | Fast | ❌ No |
| Trend Following | Trend | TRENDING_STRONG | Slow | ❌ No |

### 1. RSI Reversal Strategy

**Purpose**: Trade immediately on RSI extremes without waiting for crossovers
**Optimal Timeframes**: M5, M15, M30
**Key Innovation**: No crossover dependency — signals fire instantly on RSI direction change

**Configuration Example**:
```json
{
  "type": "rsi_reversal",
  "params": {
    "rsi_period": 14,
    "rsi_extreme_oversold": 25,
    "rsi_extreme_overbought": 85,
    "atr_multiplier": 1.5,
    "risk_reward_ratio": 2.0,
    "cooldown_bars": 2,
    "symbol": "BTCUSD#"
  }
}
```

**Signal Logic**:
- **LONG**: Previous RSI ≤ oversold threshold AND current RSI > previous RSI AND RSI < 50
- **SHORT**: Previous RSI ≥ overbought threshold AND current RSI < previous RSI AND RSI > 50

**When to Use**:
- Volatile markets with frequent overbought/oversold conditions
- When crossover strategies are too slow
- Crypto markets with high RSI oscillation

---

### 2. EMA Crossover Strategy

**Purpose**: Faster reaction to price changes for day trading
**Optimal Timeframes**: M15, M30, H1
**Key Features**:
- Uses Exponential Moving Averages (EMA) instead of Simple Moving Averages
- Faster signal generation due to exponential weighting
- Tighter stops (1.5x ATR vs 2.0x ATR)
- Higher confidence scores (0.75 vs 0.70)

**Configuration Example**:
```json
{
  "type": "ema_crossover",
  "params": {
    "fast_period": 9,
    "slow_period": 21,
    "atr_period": 14,
    "atr_multiplier": 1.5,
    "risk_reward_ratio": 2.5
  }
}
```

**When to Use**:
- Trending markets
- Day trading sessions
- When you need faster entries than SMA

---

### 2. Momentum Breakout Strategy

**Purpose**: Capture explosive moves with momentum confirmation
**Optimal Timeframes**: M15, H1, H4
**Key Features**:
- Breakout detection from consolidation zones
- Volume spike confirmation (1.5x average)
- RSI momentum validation
- Aggressive take profit (3.0x risk-reward ratio)
- High confidence signals (0.80)

**Configuration Example**:
```json
{
  "type": "momentum_breakout",
  "params": {
    "lookback_period": 20,
    "rsi_threshold": 55,
    "atr_multiplier": 1.5,
    "volume_multiplier": 1.5,
    "risk_reward_ratio": 3.0
  }
}
```

**Entry Conditions**:
- **Long**: Price breaks above recent high + RSI > 55 + Volume spike
- **Short**: Price breaks below recent low + RSI < 45 + Volume spike

**When to Use**:
- Volatile markets
- After consolidation periods
- Breakout trading sessions

---

### 3. Scalping Strategy

**Purpose**: Ultra-fast M1/M5 trading with tight stops
**Optimal Timeframes**: M1, M5
**Key Features**:
- Ultra-tight stops (1.0x ATR)
- Fast EMAs (5/10 crossover)
- RSI oversold/overbought recovery
- Spread filter (max 2 pips)
- Quick profit targets (2.0x R:R)
- Highest confidence (0.85)

**Configuration Example**:
```json
{
  "type": "scalping",
  "params": {
    "fast_ema": 5,
    "slow_ema": 10,
    "rsi_period": 7,
    "rsi_oversold": 25,
    "rsi_overbought": 75,
    "atr_multiplier": 1.0,
    "risk_reward_ratio": 2.0,
    "spread_limit_pips": 2.0
  }
}
```

**Entry Conditions**:
- **Long**: EMA5 crosses above EMA10 + RSI recovering from oversold (25-60)
- **Short**: EMA5 crosses below EMA10 + RSI recovering from overbought (40-75)
- **Filter**: Spread must be < 2 pips

**When to Use**:
- Ranging markets
- High liquidity sessions (London/NY overlap)
- Low spread periods
- Fast-paced trading

---

### 4. Mean Reversion Strategy

**Purpose**: Profit from price returning to mean in ranging markets
**Optimal Timeframes**: M15, M30, H1
**Key Features**:
- Bollinger Band bounce detection
- RSI divergence confirmation
- Tight stops near band edges
- Conservative risk-reward ratio (2.0x)
- Medium confidence signals (0.70)

**Configuration Example**:
```json
{
  "type": "mean_reversion",
  "params": {
    "bollinger_period": 20,
    "bollinger_std": 2.0,
    "rsi_period": 14,
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "atr_multiplier": 1.0,
    "risk_reward_ratio": 2.0
  }
}
```

**Entry Conditions**:
- **Long**: Price touches lower Bollinger Band + RSI oversold (< 30)
- **Short**: Price touches upper Bollinger Band + RSI overbought (> 70)
- **Filter**: ADX < 25 (ranging market confirmation)

**When to Use**:
- Sideways/ranging markets
- Low volatility periods
- After strong directional moves (correction trades)
- When ADX indicates weak trend

---

### 5. Trend Following Strategy

**Purpose**: Ride strong trends with ADX confirmation
**Optimal Timeframes**: H1, H4, D1
**Key Features**:
- ADX trend strength validation
- Supertrend direction confirmation
- Wider stops for trend continuation
- Higher risk-reward ratio (3.0x)
- High confidence signals (0.80)

**Configuration Example**:
```json
{
  "type": "trend_following",
  "params": {
    "adx_period": 14,
    "adx_threshold": 25,
    "supertrend_period": 10,
    "supertrend_multiplier": 3.0,
    "atr_multiplier": 2.0,
    "risk_reward_ratio": 3.0
  }
}
```

**Entry Conditions**:
- **Long**: ADX > 25 + Supertrend bullish + Price above VWAP
- **Short**: ADX > 25 + Supertrend bearish + Price below VWAP
- **Filter**: Strong trend confirmation from multiple indicators

**When to Use**:
- Strong trending markets
- High ADX readings
- After trend establishment
- Longer timeframe trading

---

## Next-Generation Indicators

### 1. Supertrend Indicator

**Purpose**: Clear trend identification with dynamic support/resistance
**Type**: Trend-following

**How It Works**:
- Combines ATR with price action
- Provides dynamic support/resistance levels
- Clear directional signals (1 = bullish, -1 = bearish)
- Never whipsaws in strong trends

**Usage**:
```python
from cthulu.indicators.supertrend import Supertrend

indicator = Supertrend(period=10, multiplier=3.0)
result = indicator.calculate(data)

# Access values
supertrend_value = result['supertrend']
direction = result['supertrend_direction']  # 1 or -1
signal = result['supertrend_signal']  # Entry signals
```

**Interpretation**:
- Direction = 1: Bullish trend, use as trailing stop (below price)
- Direction = -1: Bearish trend, use as trailing stop (above price)
- Signal = 2: Strong buy signal (direction changed to 1)
- Signal = -2: Strong sell signal (direction changed to -1)

---

### 2. VWAP (Volume Weighted Average Price)

**Purpose**: Institutional-grade price analysis
**Type**: Volume-based

**How It Works**:
- Calculates average price weighted by volume
- Includes standard deviation bands
- Used by institutions for execution benchmarking
- Resets daily for intraday VWAP

**Usage**:
```python
from cthulu.indicators.vwap import VWAP

indicator = VWAP(std_dev_multiplier=2.0)
result = indicator.calculate(data)

# Access values
vwap = result['vwap']
upper_band = result['vwap_upper']  # 2x std dev
lower_band = result['vwap_lower']  # 2x std dev
```

**Trading Rules**:
- **Buy**: Price bounces from VWAP support (lower bands)
- **Sell**: Price rejects from VWAP resistance (upper bands)
- **Trend**: Price consistently above VWAP = bullish trend
- **Mean Reversion**: Price far from VWAP = expect return

**Anchored VWAP**:
Calculate VWAP from significant events (earnings, major news):
```python
from cthulu.indicators.vwap import AnchoredVWAP

indicator = AnchoredVWAP(anchor_index=50)  # Start from bar 50
result = indicator.calculate(data)
```

---

### 3. VPT (Volume Price Trend)

**Purpose**: Measure volume-weighted price momentum
**Type**: Volume-momentum hybrid

**How It Works**:
- Combines price change with volume
- Cumulative indicator showing buying/selling pressure
- Positive VPT = buying pressure, Negative VPT = selling pressure
- Crosses above/below zero signal trend changes

**Usage**:
```python
from cthulu.indicators.volume_indicators import VPT

indicator = VPT()
result = indicator.calculate(data)

# Access values
vpt = result['vpt']  # Cumulative VPT value
vpt_signal = result['vpt_signal']  # 1, 0, -1 signals
```

**Trading Rules**:
- **Buy**: VPT crosses above zero + increasing volume
- **Sell**: VPT crosses below zero + increasing volume
- **Divergence**: Price up, VPT down = bearish divergence
- **Confirmation**: VPT confirms price direction with volume

---

### 4. Volume Oscillator

**Purpose**: Identify volume momentum and trend strength
**Type**: Volume momentum

**How It Works**:
- Compares short-term vs long-term volume moving averages
- Positive values = increasing volume (bullish)
- Negative values = decreasing volume (bearish)
- Centerline crossovers signal volume trend changes

**Usage**:
```python
from cthulu.indicators.volume_indicators import VolumeOscillator

indicator = VolumeOscillator(short_period=5, long_period=10)
result = indicator.calculate(data)

# Access values
oscillator = result['volume_oscillator']
signal = result['volume_oscillator_signal']  # 1, 0, -1
histogram = result['volume_histogram']
```

**Trading Rules**:
- **Buy**: Oscillator crosses above zero + price confirmation
- **Sell**: Oscillator crosses below zero + price confirmation
- **Strength**: High positive values = strong buying interest
- **Weakness**: High negative values = strong selling interest

---

### 5. Price Volume Trend (PVT)

**Purpose**: Cumulative volume-price relationship analysis
**Type**: Volume-price accumulation

**How It Works**:
- Accumulates price changes weighted by volume
- Shows institutional accumulation/distribution
- Rising PVT = accumulation, Falling PVT = distribution
- Similar to On-Balance Volume but uses percentage changes

**Usage**:
```python
from cthulu.indicators.price_volume_trend import PriceVolumeTrend

indicator = PriceVolumeTrend()
result = indicator.calculate(data)

# Access values
pvt = result['pvt']  # Cumulative PVT value
pvt_signal = result['pvt_signal']  # Trend signals
```

**Trading Rules**:
- **Buy**: PVT rising + price rising = strong accumulation
- **Sell**: PVT falling + price falling = strong distribution
- **Divergence**: Price up, PVT down = potential reversal
- **Breakouts**: PVT breakouts often precede price breakouts

---

## Dynamic Strategy Selection

### Overview

The **StrategySelector** automatically chooses the best strategy based on:
1. Market regime (trending, ranging, volatile, consolidating)
2. Individual strategy performance
3. Strategy-regime affinity
4. Confidence scores

### Market Regime Detection

**Regimes Identified (10 Total)**:
- **TRENDING_UP_STRONG**: Strong uptrend (ADX > 30, positive returns > 1%)
- **TRENDING_UP_WEAK**: Weak uptrend (ADX 20-30, positive returns 0.5-1%)
- **TRENDING_DOWN_STRONG**: Strong downtrend (ADX > 30, negative returns > 1%)
- **TRENDING_DOWN_WEAK**: Weak downtrend (ADX 20-30, negative returns 0.5-1%)
- **RANGING_TIGHT**: Tight sideways movement (ADX < 20, BB width < 1%)
- **RANGING_WIDE**: Wide ranging (ADX < 20, BB width 1-2%)
- **VOLATILE_BREAKOUT**: High volatility breakout (ATR spike, volume surge)
- **VOLATILE_CONSOLIDATION**: High volatility consolidation (ATR high, narrow BB)
- **CONSOLIDATING**: Low volatility (narrow BB bands, low ADX < 15)
- **REVERSAL**: Trend reversal signals (ADX turning, momentum divergence)

**Detection Logic**:
```python
# Factors used:
- ADX value (trend strength)
- 20-period returns (direction)
- ATR ratio (volatility)
- Bollinger Band width (range compression)
```

### Strategy Affinity Matrix

Each strategy has optimal performance in certain regimes (0.0-1.0 scale):

| Strategy | Strong Up | Weak Up | Strong Down | Weak Down | Tight Range | Wide Range | Breakout | Consolidation | Consolidating | Reversal |
|----------|-----------|---------|-------------|-----------|-------------|------------|----------|---------------|---------------|----------|
| **SMA Crossover** | 0.90 | 0.85 | 0.90 | 0.85 | 0.30 | 0.40 | 0.60 | 0.50 | 0.40 | 0.70 |
| **EMA Crossover** | 0.95 | 0.90 | 0.95 | 0.90 | 0.40 | 0.50 | 0.70 | 0.60 | 0.50 | 0.75 |
| **Momentum Breakout** | 0.80 | 0.70 | 0.80 | 0.70 | 0.50 | 0.60 | 0.95 | 0.80 | 0.30 | 0.85 |
| **Scalping** | 0.60 | 0.65 | 0.60 | 0.65 | 0.95 | 0.85 | 0.40 | 0.50 | 0.70 | 0.55 |
| **Mean Reversion** | 0.40 | 0.45 | 0.40 | 0.45 | 0.95 | 0.85 | 0.50 | 0.70 | 0.90 | 0.80 |
| **Trend Following** | 0.98 | 0.90 | 0.98 | 0.90 | 0.20 | 0.30 | 0.80 | 0.40 | 0.30 | 0.50 |
| **RSI Reversal** ⭐ | 0.50 | 0.60 | 0.50 | 0.60 | 0.90 | 0.85 | 0.70 | **0.95** | 0.85 | **0.98** |

⭐ **RSI Reversal**: Highest affinity for REVERSAL and VOLATILE_CONSOLIDATION regimes

### Performance Tracking

For each strategy, the system tracks:
- **Win Rate**: % of winning trades
- **Profit Factor**: Total profit / Total loss
- **Recent Performance**: Last 50 signals
- **Average Confidence**: Mean confidence score
- **Signal Count**: Total signals generated

### Selection Algorithm

**Weighted Score Calculation**:
```
Total Score = (Performance × 0.4) + (Regime Affinity × 0.4) + (Confidence × 0.2)
```

**Performance Score** (0-1):
```
= (Win Rate × 0.5) + (min(Profit Factor/2, 1) × 0.3) + (Recent Performance × 0.2)
```

**Best Strategy**: Highest total score wins

### Multi-Strategy Fallback

The fallback mechanism dramatically increases signal generation by trying multiple strategies:

**How It Works**:
1. Primary strategy (highest score) is tried first
2. If no signal, calculate scores for all remaining strategies
3. Try top 3 alternatives in descending score order
4. First strategy to generate a valid signal wins
5. Attribution logged for performance tracking

**Code Flow**:
```python
def generate_signal(data, bar):
    # 1. Select primary strategy
    primary = self.select_strategy(data)
    signal = primary.on_bar(bar)
    
    # 2. If no signal, try fallbacks
    if signal is None:
        scores = self._calculate_all_scores(data)
        sorted_strategies = sorted(scores.items(), key=lambda x: x[1]['total'], reverse=True)
        
        for name, score in sorted_strategies[:3]:
            if name != primary.name:
                fallback = self.strategies[name]
                signal = fallback.on_bar(bar)
                if signal:
                    logger.info(f"Fallback signal from {name} (score={score['total']:.3f})")
                    return signal
    
    return signal
```

**Benefits**:
- **No missed opportunities**: Even if scalping needs a crossover, RSI Reversal can fire
- **Regime adaptability**: Different strategies catch different conditions
- **Performance tracking**: Attribution enables strategy optimization
- **Configurable depth**: Adjust fallback count (default: 3)

### Usage Example

```python
from cthulu.strategy.strategy_selector import StrategySelector

# Create strategies
strategies = [
    EmaCrossover(config1),
    MomentumBreakout(config2),
    ScalpingStrategy(config3),
    RsiReversalStrategy(config4) 
]

# Initialize selector
selector = StrategySelector(strategies=strategies, config={
    'regime_check_interval': 180,  # Check every 3 minutes
    'min_strategy_signals': 5,
    'performance_weight': 0.35,
    'regime_weight': 0.35,
    'confidence_weight': 0.30
})

# Generate signal (auto-selects best strategy with fallback)
signal = selector.generate_signal(data, latest_bar)

# Record outcome for learning
selector.record_outcome('rsi_reversal', 'win', 150.0)

# Get performance report
report = selector.get_performance_report()
```

---

## Ultra-Aggressive Mode

### Configuration: `config_ultra_aggressive.json`

**Key Differences from Standard Aggressive**:

| Parameter | Standard Aggressive | Ultra-Aggressive |
|-----------|-------------------|------------------|
| **Position Size %** | 10% | 15% |
| **Max Positions** | 6 | 10 |
| **Confidence Threshold** | 0.35 | 0.25 |
| **Poll Interval** | 30s | 15s |
| **Strategy Type** | Single | Dynamic (4 strategies) |
| **Max Daily Loss** | $250 | $500 |

**Enabled Strategies** (All 4):
1. EMA Crossover (fast periods: 8/21)
2. Momentum Breakout (lookback: 15)
3. Scalping (very tight: 5/10 EMAs)
4. SMA Crossover (backup: 5/13)

**Exit Strategies** (More aggressive):
- **Adverse Movement**: 0.5% threshold (vs 1.0%), 30s window (vs 60s)
- **Time-Based**: 8 hours max hold (vs 24 hours)
- **Profit Target**: 1.5% target (vs 2.0%), 50% partial close
- **Trailing Stop**: 1.5x ATR (vs 2.0x), activates at 0.5% profit

**New Indicators**:
- RSI (14 and 7 periods for multi-timeframe)
- Supertrend (10 period, 3.0 multiplier)
- VWAP (2.0 std dev bands)

**Features Enabled**:
- ML instrumentation: `true`
- Adaptive parameters: `true`
- Multi-timeframe analysis: `true`

---

## Configuration Guide

### Complete Dynamic Strategy Configuration

```json
{
  "strategy": {
    "type": "dynamic",
    "dynamic_selection": {
      "enabled": true,
      "regime_check_interval": 180,
      "min_strategy_signals": 3,
      "performance_weight": 0.4,
      "regime_weight": 0.4,
      "confidence_weight": 0.2
    },
    "strategies": [
      {
        "type": "ema_crossover",
        "params": {
          "fast_period": 8,
          "slow_period": 21,
          "atr_multiplier": 1.2,
          "risk_reward_ratio": 3.0
        }
      },
      {
        "type": "momentum_breakout",
        "params": {
          "lookback_period": 15,
          "rsi_threshold": 50,
          "volume_multiplier": 1.3
        }
      },
      {
        "type": "scalping",
        "params": {
          "fast_ema": 5,
          "slow_ema": 10,
          "spread_limit_pips": 2.0
        }
      }
    ]
  },
  "indicators": [
    {"type": "rsi", "params": {"period": 14}},
    {"type": "rsi", "params": {"period": 7}},
    {"type": "supertrend", "params": {"period": 10, "multiplier": 3.0}},
    {"type": "vwap", "params": {"std_dev_multiplier": 2.0}},
    {"type": "macd", "params": {"fast_period": 12, "slow_period": 26}},
    {"type": "bollinger", "params": {"period": 20, "std_dev": 2.0}},
    {"type": "adx", "params": {"period": 14}}
  ]
}
```

---

## Usage Examples

### 1. Run with Ultra-Aggressive Configuration

```bash
# Interactive mode
python -m Cthulu --config config_ultra_aggressive.json

# Automated mode (headless)
python -m Cthulu --config config_ultra_aggressive.json --skip-setup --no-prompt

# Dry-run (no real trades)
python -m Cthulu --config config_ultra_aggressive.json --dry-run

# Debug mode
python -m Cthulu --config config_ultra_aggressive.json --log-level DEBUG
```

### 2. Monitor Dynamic Strategy Selection

The system logs strategy selection decisions:

```
INFO: Market regime detected: TRENDING_UP (ADX=32.5, Returns=2.34%, Vol=1.12)
INFO: Selected strategy: ema_crossover (score=0.856, perf=0.823, regime=0.950, conf=0.750)
INFO:   momentum_breakout: total=0.812, perf=0.765, regime=0.800
INFO:   scalping: total=0.634, perf=0.700, regime=0.600
```

### 3. Track Strategy Performance

```bash
# View performance report in logs
grep "Recorded" Cthulu.log | tail -20

# Example output:
# Recorded win for ema_crossover: $152.30 (WinRate=68.42%)
# Recorded loss for momentum_breakout: $-48.20 (WinRate=62.50%)
```

### 4. Test Individual Strategies

```python
from cthulu.strategy.ema_crossover import EmaCrossover
from cthulu.strategy.momentum_breakout import MomentumBreakout

# Test EMA strategy
ema_strategy = EmaCrossover(config={
    'params': {'fast_period': 9, 'slow_period': 21}
})

# Test Momentum strategy
momentum_strategy = MomentumBreakout(config={
    'params': {'lookback_period': 20, 'rsi_threshold': 55}
})
```

---

## Performance Tuning

### 1. Strategy Selection Tuning

**Adjust Weights** for different trading styles:

```json
// Conservative (rely more on performance)
{
  "performance_weight": 0.6,
  "regime_weight": 0.3,
  "confidence_weight": 0.1
}

// Aggressive (adapt faster to regime)
{
  "performance_weight": 0.3,
  "regime_weight": 0.5,
  "confidence_weight": 0.2
}
```

**Regime Check Interval**:
- Fast adaptation: 120-180 seconds
- Balanced: 300 seconds (5 minutes)
- Slow/stable: 600+ seconds

### 2. Scalping Optimization

For best scalping performance:
- Use M1 or M5 timeframes
- Trade during high liquidity (London/NY overlap)
- Monitor spread (must be < 2 pips)
- Use tight risk management (1.0x ATR stops)

```json
{
  "trading": {
    "timeframe": "TIMEFRAME_M5",
    "poll_interval": 10
  },
  "risk": {
    "position_size_pct": 5.0,  // Smaller size for scalping
    "max_positions_per_symbol": 3
  }
}
```

### 3. Breakout Trading Optimization

For momentum breakouts:
- Use H1 or H4 for better breakouts
- Increase volume multiplier for stronger confirmation
- Use wider stops for volatile instruments

```json
{
  "params": {
    "lookback_period": 20,
    "volume_multiplier": 2.0,  // Stronger confirmation
    "atr_multiplier": 2.0       // Wider stops
  }
}
```

---

## Best Practices

### 1. Start Conservative

Begin with:
- Single strategy mode
- Lower position sizes (5%)
- Higher confidence thresholds (0.40+)
- Dry-run mode for 1 week

### 2. Gradually Increase Aggression

After successful testing:
- Enable dynamic strategy selection
- Increase position sizes
- Lower confidence threshold
- Add more concurrent positions

### 3. Monitor Performance

Track these metrics:
- Overall win rate (target: 55%+)
- Profit factor (target: 1.5+)
- Strategy selection accuracy
- Regime detection accuracy

### 4. Adjust Based on Market

- **Trending**: Favor EMA/SMA crossover strategies
- **Ranging**: Enable scalping strategy
- **Volatile**: Use momentum breakout
- **Low Volume**: Increase spread limits or pause

---

## Troubleshooting

### Issue: Strategy switches too frequently

**Solution**: Increase `regime_check_interval` and `min_strategy_signals`

### Issue: Low win rate in scalping

**Solution**: 
- Check spread (must be < 2 pips)
- Verify trading during high liquidity periods
- Tighten RSI thresholds (25/75 → 20/80)

### Issue: Breakout strategy triggers too early

**Solution**:
- Increase `volume_multiplier` (1.5 → 2.0)
- Raise `rsi_threshold` (55 → 60)
- Increase `lookback_period` (20 → 30)

---

## Desktop GUI Interface

### Overview
Cthulu includes a comprehensive desktop GUI (`python -m Cthulu --gui`) that provides real-time monitoring and manual trading capabilities.

### Features

#### Live Trade Monitoring
- **Real-time Positions**: View all open positions with ticket numbers, symbols, sides, volumes, current prices, and P&L
- **Automatic Updates**: Refreshes every 2 seconds with latest market data
- **Alternating Rows**: Improved readability with color-coded rows

#### Detailed Trade History
- **Database-Driven**: Pulls complete trade records from SQLite database
- **Comprehensive Details**: Shows entry/exit times, prices, volumes, P&L, and trade status
- **Historical Records**: Displays up to 50 most recent trades, ordered by entry time
- **Status Tracking**: OPEN, CLOSED, CANCELLED status with exit reasons

#### Performance Dashboard
- **Key Metrics**: Total trades, win rate, net profit, profit factor, max drawdown, Sharpe ratio
- **Real-time Updates**: Metrics update from performance logs
- **Strategy Info**: Current active strategy and detected market regime

#### Manual Trading
- **Order Placement**: GUI interface for placing manual trades
- **Risk Validation**: Orders validated against risk limits before submission
- **RPC Integration**: Uses internal HTTP API for order execution

### Usage
```bash
# Launch GUI
python -m Cthulu --gui

# Or run full system with GUI
python -m Cthulu --config config.json
```

### Configuration
The GUI automatically connects to the running Cthulu instance and displays data from:
- `Cthulu.db` - Trade database
- `Cthulu.log` - Live log updates
- `logs/latest_summary.txt` - Performance metrics
- `logs/strategy_info.txt` - Strategy status

---

## Autonomous Position Management

### Overview

Cthulu v6.0.0 provides revolutionary **autonomous position management** that creates self-managing trades. This is the core of the **SAFE (Set And Forget Engine)** paradigm.

The system comprises four interconnected modules:
1. **ProfitScaler** - Tiered partial profit taking
2. **MicroAccountProtection** - Intelligent DCA (Dollar Cost Averaging)
3. **AdaptiveDrawdownManager** - Dynamic drawdown state management
4. **EquityCurveManager** - Trailing equity protection

### How They Work Together

```
Signal Generated → Position Opened → ProfitScaler monitors
                                          ↓
                        Profit grows → Take partial (25%, 35%, 50%)
                        Profit shrinks → MicroAccountProtection evaluates DCA
                                          ↓
                        Market adverse → AdaptiveDrawdownManager adjusts risk
                        Equity drops → EquityCurveManager protects capital
```

---

## Profit Scaling System

### Purpose
Automatically lock in profits at tiered milestones while letting winners run.

### Tier Configuration

**Standard Account Tiers** (Balance ≥ $100):
| Tier | Profit Threshold | Close % | Move SL | Trail % |
|------|------------------|---------|---------|---------|
| 1 | 30% of position | 25% | To Breakeven | 50% |
| 2 | 60% of position | 35% | To Breakeven | 60% |
| 3 | 100% of position | 50% | To Breakeven | 70% |

**Micro Account Tiers** (Balance < $100 - SPARTA Mode):
| Tier | Profit Threshold | Close % | Move SL | Trail % |
|------|------------------|---------|---------|---------|
| 1 | 15% of position | 30% | To Breakeven | 40% |
| 2 | 30% of position | 40% | To Breakeven | 50% |
| 3 | 50% of position | 50% | To Breakeven | 60% |

### How It Works

1. **Position Registered**: When a trade opens, ProfitScaler begins monitoring
2. **Profit Calculation**: Continuously calculates unrealized P&L percentage
3. **Tier Evaluation**: Checks if profit threshold is reached
4. **Partial Close**: Executes partial position close via ExecutionEngine
5. **SL Adjustment**: Moves stop-loss to breakeven after first tier
6. **Trailing**: Implements trailing stop at configured percentage

### Emergency Profit Lock

If unrealized profit exceeds **10% of account balance**, ProfitScaler triggers **emergency profit lock**:
- Immediately closes 50% of position
- Moves SL to breakeven
- Logs as emergency action

### ML-Powered Tier Optimization

The system learns optimal tier configurations from historical outcomes:
- Records every scaling action and its result
- Adjusts tier thresholds based on what maximizes total profit
- Adapts to account size and instrument volatility

### Configuration

```json
{
  "profit_scaling": {
    "enabled": true,
    "micro_account_threshold": 100.0,
    "min_profit_amount": 0.10,
    "emergency_lock_threshold_pct": 0.10,
    "tiers": [
      {"profit_threshold_pct": 0.30, "close_pct": 0.25, "move_sl_to_entry": true, "trail_pct": 0.50},
      {"profit_threshold_pct": 0.60, "close_pct": 0.35, "move_sl_to_entry": true, "trail_pct": 0.60},
      {"profit_threshold_pct": 1.00, "close_pct": 0.50, "move_sl_to_entry": true, "trail_pct": 0.70}
    ]
  }
}
```

---

## MicroAccountProtection (Intelligent DCA)

### Purpose
Provides intelligent averaging-down capabilities for adverse positions, especially critical for micro accounts where a single bad trade could devastate the balance.

### DCA Logic

The system evaluates positions for potential averaging opportunities:

1. **Entry Conditions**:
   - Position is in loss (negative floating P&L)
   - Loss percentage exceeds configurable threshold
   - Market shows favorable re-entry signals
   - Account has sufficient margin

2. **Volume Calculation**:
   - New entry volume = Original volume × DCA multiplier (default: 0.5)
   - Never exceeds remaining margin safety limits

3. **Re-entry Timing**:
   - Waits for price to stabilize (configurable bars)
   - Confirms with indicator convergence
   - Validates against risk parameters

### Configuration

```json
{
  "micro_account_protection": {
    "enabled": true,
    "balance_threshold": 100.0,
    "dca_enabled": true,
    "dca_loss_threshold_pct": 2.0,
    "dca_max_entries": 3,
    "dca_volume_multiplier": 0.5,
    "emergency_stop_pct": 10.0
  }
}
```

### Safety Rails

- **Maximum DCA Entries**: Limited to 3 additional entries per position
- **Margin Check**: Always validates sufficient free margin
- **Emergency Stop**: Closes everything if drawdown exceeds threshold
- **Cooldown Period**: Minimum time between DCA entries

---

## Adaptive Drawdown Management

### Purpose
Dynamically adjusts trading behavior based on current drawdown state, implementing survival strategies when capital is at risk.

### Drawdown States

| State | Drawdown % | Position Multiplier | Max Positions | Confidence Required |
|-------|------------|--------------------:|:-------------:|:-------------------:|
| NORMAL | 0-5% | 1.0x | 10 | 0.25 |
| CAUTION | 5-10% | 0.75x | 7 | 0.35 |
| WARNING | 10-20% | 0.5x | 5 | 0.50 |
| DANGER | 20-35% | 0.25x | 3 | 0.70 |
| CRITICAL | 35-50% | 0.1x | 1 | 0.85 |
| SURVIVAL | 50-90% | 0.05x | 1 | 0.95 |
| RECOVERY | Recovering | 0.6x | 4 | 0.45 |

### State Transitions

```
NORMAL → CAUTION → WARNING → DANGER → CRITICAL → SURVIVAL
                                                    ↓
                                              RECOVERY (climbing back)
```

### SURVIVAL Mode

When drawdown exceeds 50%, the system enters **SURVIVAL MODE**:

- **Position Size**: Micro-lots only (0.01)
- **Max Positions**: 1 only
- **Confidence Required**: 95%+ (near-certain signals only)
- **Risk:Reward Minimum**: 5:1
- **Allowed Strategies**: High-probability only (trend_following)
- **Session Filter**: High liquidity periods only (London/NY)
- **Wider Stops**: 2x normal ATR multiplier

### Win/Lose Streak Adjustment

The system tracks consecutive wins/losses and adjusts accordingly:

- **4+ Wins**: Position size +20% (anti-martingale)
- **3+ Losses**: Position size -20%
- **4+ Losses**: Position size -40%

### Configuration

```json
{
  "adaptive_drawdown": {
    "enabled": true,
    "trailing_lock_pct": 0.5,
    "thresholds": {
      "caution": 5.0,
      "warning": 10.0,
      "danger": 20.0,
      "critical": 35.0,
      "survival": 50.0
    }
  }
}
```

---

## Equity Curve Management

### Purpose
Monitors the equity curve trajectory and implements trailing profit protection to prevent giving back gains.

### Key Metrics Tracked

- **Peak Balance**: Highest balance achieved
- **Peak Equity**: Highest equity achieved
- **Trailing Equity High**: High watermark for profit locking
- **Locked Profit Amount**: Gains that must be protected
- **Equity Velocity**: Rate of change ($/minute)
- **Equity Momentum**: Acceleration of equity change

### Trailing Equity Protection

Once account gains exceed **5% of initial balance**, the system starts locking profits:

1. **New High**: When equity makes new high, lock 50% of the new gain
2. **Protection Trigger**: If current profit drops below 50% of locked amount, trigger protective actions
3. **Actions**: Tighten stops, move to breakeven, partial close recommendations

### Equity States

| State | Description | Action |
|-------|-------------|--------|
| ASCENDING | Equity rising steadily | Allow larger positions |
| DESCENDING | Equity falling | Reduce position sizes |
| CONSOLIDATING | Sideways movement | Normal trading |
| BREAKOUT_UP | Breaking to new highs | Slightly larger positions |
| BREAKDOWN | Breaking to new lows | Defensive mode |
| RECOVERY | Recovering from drawdown | Gradual size increase |

### Protection Levels

| Equity vs Peak | Level | Actions |
|----------------|-------|---------|
| >90% | Normal | Full trading |
| 80-90% | WARNING | Reduce size 50%, tighten stops |
| 70-80% | DANGER | Reduce size 75%, partial close 50% |
| 50-70% | CRITICAL | Minimal size, close 75%, breakeven all |
| <50% | EMERGENCY | Close all positions |

### Configuration

```json
{
  "equity_curve_management": {
    "enabled": true,
    "trailing_lock_pct": 0.5,
    "profit_lock_threshold": 5.0,
    "equity_warning_pct": 90.0,
    "equity_danger_pct": 80.0,
    "equity_critical_pct": 70.0,
    "equity_emergency_pct": 50.0
  }
}
```

---

## Exit Management System

### Architecture Overview

Cthulu v5.1 "Apex" implements a **multi-layered exit management system** that coordinates multiple exit strategies with intelligent priority adjustment. The system is designed around the principle: **"Don't hope for recovery - that's market prediction."**

### Exit Strategy Hierarchy

| Layer | Strategy | Priority | Purpose |
|-------|----------|----------|---------|
| 1 | SurvivalModeExit | 100 | Emergency capital protection |
| 2 | AdaptiveLossExit | 90 | Non-linear loss tolerance enforcement |
| 3 | MicroAccountProtection | 80 | Micro account profit protection |
| 4 | ConfluenceExitManager | 75 | Multi-indicator reversal detection |
| 5 | AdverseMovementExit | 70 | Sudden adverse movement response |
| 6 | StopLoss | 65 | Traditional stop loss |
| 7 | ProfitScalingExit | 60 | Tiered profit taking |
| 8 | TakeProfit | 55 | Traditional take profit |
| 9 | TimeBasedExit | 45 | Time-based position management |
| 10 | TrailingStop | 40 | Dynamic trailing stop |

### Priority Adjustment System

The ExitCoordinator dynamically adjusts strategy priorities based on:

- **High Volatility**: +10 priority to StopLoss, AdverseMovement
- **Wide Spreads**: -5 priority to all exits (costly to close)
- **News Events**: +15 priority to all exits
- **Market Close**: +20 priority to TimeBasedExit
- **Near Profit Target**: +15 priority to TakeProfit, ProfitTarget
- **Long Hold Time**: +10 priority to TimeBasedExit
- **Deep Loss (-2%+)**: +20 priority to StopLoss

---

## Adaptive Loss Curve

### Philosophy

**Linear loss tolerance is dangerous for micro accounts.** Recovery from a 50% loss requires a 100% gain. The AdaptiveLossCurve implements hyperbolic/softmax-based scaling that enforces tighter stops on smaller accounts.

### Mathematical Foundation

The curve uses a hybrid hyperbolic-softmax function:

```
loss_rate = interpolate(anchor_points) * softmax_smooth(balance)

Where:
- softmax_weight = 1 / (1 + exp(-k * (x - 0.5)))
- k = hyperbolic_steepness (default: 2.5)
```

### Loss Tolerance Table

| Account Balance | Max Daily Loss | Max Per-Trade Loss | Rate |
|-----------------|----------------|--------------------:|-----:|
| $5 | $0.50 | $0.25 | 10% |
| $10 | $0.80 | $0.40 | 8% |
| $25 | $1.50 | $0.75 | 6% |
| $50 | $2.50 | $1.25 | 5% |
| $100 | $3.00 | $1.50 | 3% |
| $250 | $6.25 | $3.12 | 2.5% |
| $500 | $10.00 | $5.00 | 2% |
| $1,000 | $20.00 | $10.00 | 2% |
| $5,000 | $75.00 | $37.50 | 1.5% |

### Recovery Mode

When drawdown exceeds 20% from peak, the system enters **Recovery Mode**:
- Loss tolerance reduced by 50%
- More conservative position sizing
- Exits recovery only when balance fully recovers

### Usage

```python
from cthulu.exit import AdaptiveLossCurve, create_adaptive_loss_curve

# Create curve with defaults
curve = AdaptiveLossCurve()

# Get max loss for $50 account
max_loss = curve.get_max_loss(50.0)  # Returns $1.25

# Check if position should close
should_close, reason = curve.should_close_for_loss(
    balance=50.0,
    unrealized_pnl=-1.50  # $1.50 loss
)
# Returns (True, "Loss $1.50 exceeds adaptive limit $1.25 (3.0%)")

# Get stop distance
stop_distance = curve.get_stop_distance(
    balance=100.0,
    entry_price=88000,
    lot_size=0.01,
    pip_value=10.0
)
```

### Configuration

```json
{
  "adaptive_loss_curve": {
    "base_loss_rate": 0.03,
    "hyperbolic_steepness": 2.5,
    "softmax_temperature": 50.0,
    "min_loss_floor": 0.10,
    "max_loss_cap_pct": 0.15,
    "per_trade_multiplier": 0.5,
    "recovery_mode_drawdown_pct": 0.20,
    "recovery_mode_loss_reduction": 0.5,
    "tier_anchors": {
      "5.0": 0.10,
      "50.0": 0.05,
      "100.0": 0.03,
      "500.0": 0.02,
      "1000.0": 0.02
    }
  }
}
```

---

## Confluence Exit Manager

### Philosophy

**Exit when multiple indicators AGREE on reversal, not when hoping for recovery.** The ConfluenceExitManager tracks positions and generates high-confidence exit signals based on multi-indicator confluence.

### Signal Classification

| Classification | Confluence Score | Action | Urgency |
|----------------|------------------|--------|--------:|
| HOLD | < 0.55 | Continue | 0 |
| SCALE_OUT | 0.55 - 0.74 | Partial close (30-50%) | 60 |
| CLOSE_NOW | 0.75 - 0.89 | Full close | 85 |
| EMERGENCY | ≥ 0.90 | Immediate full close | 100 |

### Indicator Weights

| Indicator | Weight | Detection |
|-----------|-------:|-----------|
| Trend Flip (EMA) | 25% | Fast EMA crosses slow EMA against position |
| RSI Divergence | 20% | RSI drops from overbought (longs) or rises from oversold (shorts) |
| MACD Crossover | 15% | MACD crosses signal line against position |
| Bollinger Breach | 15% | Price at/beyond band in profit direction |
| Price Action | 15% | 50%+ profit giveback from peak |
| Volume Spike | 10% | 2x+ volume with profit = distribution |

### Confluence Scoring

```
weighted_score = Σ(indicator_weight × strength × confidence)
normalized_score = weighted_score / total_weights

# Bonus for multiple agreeing indicators
if agreeing >= 3: score × 1.2
if agreeing >= 4: score × 1.1
```

### Example Scenario

**Long BTC @ $88,000 with $50 unrealized profit:**

1. RSI drops from 78 → 72 (reversal_down, strength=0.6, confidence=0.8)
2. MACD just crossed below signal (reversal_down, strength=0.7, confidence=0.75)
3. Price gave back 40% of peak profit (strength=0.4, confidence=0.7)

**Calculation:**
```
rsi_contribution = 0.20 × 0.6 × 0.8 = 0.096
macd_contribution = 0.15 × 0.7 × 0.75 = 0.079
price_action = 0.15 × 0.4 × 0.7 = 0.042

total = 0.217 / 1.0 = 0.217 (3 indicators)
with_bonus = 0.217 × 1.2 = 0.26

Classification: HOLD (needs more confluence)
```

### Position Tracking

The manager maintains real-time tracking per position:

```python
TrackedPosition:
  ticket: int          # Position ID
  entry_price: float   # Entry price
  entry_time: datetime # When opened
  current_price: float # Current market price
  unrealized_pnl: float # Current P&L
  max_favorable: float # Peak profit achieved
  max_adverse: float   # Max drawdown experienced
  holding_bars: int    # Bars since entry
```

### Usage

```python
from cthulu.exit import ConfluenceExitManager, ExitClassification

manager = ConfluenceExitManager()

# Track a position
manager.track_position(
    ticket=123456,
    symbol='BTCUSD#',
    side='BUY',
    entry_price=88000,
    volume=0.01
)

# Evaluate for exit
recommendation = manager.evaluate_exit(
    ticket=123456,
    current_price=88500,
    indicators={
        'rsi': 72, 'rsi_prev': 78,
        'macd': -0.5, 'macd_signal': -0.3, 'macd_prev': -0.2,
        'ema_fast': 88400, 'ema_slow': 88500,
        'bb_upper': 89000, 'bb_lower': 87000,
        'volume': 1500, 'volume_avg': 800
    },
    account_balance=100.0
)

if recommendation:
    if recommendation.classification == ExitClassification.CLOSE_NOW:
        print(f"CLOSE position: {recommendation.reason}")
        print(f"Indicators agreeing: {recommendation.indicators_agreeing}")
```

### Configuration

```json
{
  "confluence_exit": {
    "scale_out_threshold": 0.55,
    "close_now_threshold": 0.75,
    "rsi_overbought": 70,
    "rsi_oversold": 30,
    "rsi_divergence_threshold": 5.0
  }
}
```

---

## Adaptive Account Manager

### Philosophy

**Account size dictates trading style.** A $5 account cannot trade like a $5,000 account. The AdaptiveAccountManager implements phase-based account lifecycle management with dynamic timeframe selection.

### Account Phases

| Phase | Balance Range | Max Lot | Timeframe | Risk/Trade | R:R Min |
|-------|---------------|---------|-----------|------------|---------|
| **MICRO** | $0-25 | 0.01 | Scalp (M1-M5) | 10% | 1.5 |
| **SEED** | $25-100 | 0.02 | Scalp/Intraday | 5% | 1.8 |
| **GROWTH** | $100-500 | 0.05 | Intraday | 3% | 2.0 |
| **ESTABLISHED** | $500-2000 | 0.10 | Intraday/Swing | 2% | 2.0 |
| **MATURE** | $2000+ | 0.50 | Swing/Position | 1% | 2.5 |
| **RECOVERY** | Any (20%+ DD) | 0.01 | Scalp | 2% | 1.2 |

### Dynamic Timeframe Selection

The system automatically selects optimal timeframes based on:

1. **Account Phase**: Smaller accounts use faster timeframes for quick profits
2. **Market Volatility**: High volatility → shorter timeframes
3. **Recovery Mode**: Forces scalp timeframes for quick wins
4. **Balance Progress**: As balance grows, timeframes extend

### Argmax Decision Making

Phase selection uses argmax scoring over multiple factors:

```
score(phase) = balance_fit + drawdown_adjustment + performance_momentum

best_phase = argmax(scores)
```

**Scoring Factors**:
- Balance fit: 50-70 points (primary)
- Drawdown adjustment: +15 for conservative phases if DD > 15%
- Performance momentum: +10 if win rate > 60%

### Trade Frequency Limits

Each phase has built-in frequency limits:

| Phase | Max Trades/Hour | Min Trade Interval |
|-------|----------------:|-------------------:|
| MICRO | 10 | 60s |
| SEED | 8 | 120s |
| GROWTH | 6 | 180s |
| ESTABLISHED | 4 | 300s |
| MATURE | 3 | 600s |
| RECOVERY | 15 | 30s |

### Integration with Trading Loop

The AdaptiveAccountManager integrates at three points:

1. **Pre-Signal Validation**: Checks phase limits and validates signal confidence
2. **Position Sizing**: Adjusts lot size based on phase config
3. **Timeframe Selection**: Returns optimal MT5 timeframe constant

### Usage

```python
from cthulu.risk import AdaptiveAccountManager, create_adaptive_account_manager

# Create manager
manager = create_adaptive_account_manager()

# Update with current balance
phase_config = manager.update(balance=29.0, equity=29.5)

# Check if can trade
can_trade, reason = manager.can_open_trade()

# Validate signal
is_valid, reason = manager.validate_signal(confidence=0.7, risk_reward=1.8)

# Get position size
lot_size = manager.get_position_size(
    entry_price=88000,
    stop_loss=87500
)

# Get optimal timeframe
timeframe = manager.get_optimal_timeframe(market_volatility=0.5)
```

### Configuration

```json
{
  "adaptive_account_manager": {
    "phase_thresholds": {
      "micro": 25,
      "seed": 100,
      "growth": 500,
      "established": 2000
    },
    "recovery_threshold": 0.20
  }
}
```

### Status Report

Get comprehensive status:

```python
status = manager.get_status_report()
# Returns:
# {
#   'phase': 'seed',
#   'balance': 29.81,
#   'drawdown_pct': 1.76,
#   'in_recovery': False,
#   'timeframe': 'scalp',
#   'can_trade': True,
#   'trades_today': 5,
#   'win_rate': 60.0
# }
```

---

## Liquidity Trap Detection

### Purpose
Detects market manipulation patterns and protects against stop hunts, fakeouts, and sudden regime changes.

### Trap Types Detected

#### 1. Stop Hunt Detection
**Signature**: Price spikes beyond recent swing high/low, then quickly reverses
- Monitors swing highs/lows
- Detects wick-to-body ratio anomalies
- Confidence: 85%

#### 2. Fakeout Detection
**Signature**: Breakout on low volume
- Price breaks above/below consolidation
- Volume < 70% of average
- Confidence: 70%

#### 3. Volume Divergence
**Signature**: Large price move without volume confirmation
- Range > 1.5x average
- Volume < 50% of average
- Confidence: 65%

#### 4. Regime Flip
**Signature**: Sudden trend reversal
- First half trending one direction
- Second half trending opposite
- Magnitude > 50% of first move
- Confidence: 75%

### Trading Recommendations

When trap detected:
- **Stop Hunt (Bearish)**: Consider short entry at rejection level
- **Stop Hunt (Bullish)**: Consider long entry at rejection level
- **Fakeout**: Fade the move
- **Volume Divergence**: Wait 3 bars for confirmation
- **Regime Flip**: Follow the new direction

### Market Flip Protection

For open positions, the system monitors for:
- **Momentum Flip**: RSI crossing from overbought to oversold (or vice versa)
- **Volume Surge**: 2x average volume against position direction
- **Automatic Exit**: Triggered when flip conditions met

### Configuration

```json
{
  "liquidity_trap_detection": {
    "enabled": true,
    "spike_threshold_pct": 0.3,
    "reversal_bars": 3,
    "volume_divergence_mult": 0.5,
    "fakeout_volume_mult": 0.7,
    "trap_cooldown_minutes": 30
  }
}
```

---

## SPARTA Mode (Battle Testing)

### Purpose
Special configuration for testing system resilience under extreme conditions with micro capital.

### Philosophy
> "This is Sparta! We fight not for survival but to grow no matter the odds."

### Configuration

SPARTA Mode activates when:
- Account balance < $100
- OR explicit `config_battle_test.json` loaded

### Key Differences

| Parameter | Normal | SPARTA |
|-----------|--------|--------|
| Profit Tiers | Standard | Aggressive (faster taking) |
| DCA | Conservative | Intelligent averaging |
| Max Loss | 10% daily | 5% per trade |
| Confidence | 0.25 | 0.15 (more signals) |
| Position Size | Risk-based | Micro-lots only |
| Targets | Standard | Quick scalps |

### Battle Test Metrics

During SPARTA mode, additional metrics tracked:
- Recovery time from adverse moves
- DCA effectiveness
- Profit locking success rate
- Maximum consecutive losses survived

---

## Create Your Own Mode

### Purpose
Full customization of strategy selection and parameters for advanced users.

### Available Strategies

| Strategy | Code | Type |
|----------|------|------|
| RSI Reversal | `rsi_reversal` | Reversal |
| EMA Crossover | `ema_crossover` | Trend |
| SMA Crossover | `sma_crossover` | Trend |
| Momentum Breakout | `momentum_breakout` | Breakout |
| Scalping | `scalping` | Mean Reversion |
| Mean Reversion | `mean_reversion` | Reversal |
| Trend Following | `trend_following` | Trend |

### Configuration Example

```json
{
  "strategy": {
    "type": "custom",
    "custom_selection": {
      "strategies": ["rsi_reversal", "ema_crossover", "scalping"],
      "primary": "rsi_reversal",
      "fallback_enabled": true,
      "fallback_order": ["ema_crossover", "scalping"]
    }
  }
}
```

### Dynamic vs Custom

| Feature | Dynamic | Custom |
|---------|---------|--------|
| Strategy Selection | Automatic | Manual |
| All Strategies | ✅ All 7 | ✅ Your choice |
| Regime Detection | ✅ | ✅ |
| Performance Tracking | ✅ | ✅ |
| Fallback Order | Score-based | Config-based |

---

## Real-Time Observability

### Dashboard

The live dashboard (`observability/reporting/dashboard.html`) provides:

**Charts**:
- Equity curve over time
- Win rate by strategy
- Drawdown visualization
- P&L distribution

**Benchmarking Tables**:
- Performance metrics
- Strategy comparison
- Risk-adjusted returns
- Statistical analysis

### Metrics Collection

Three CSV files are continuously updated:

1. **comprehensive_metrics.csv**: All trading metrics
2. **indicator_metrics.csv**: Technical indicator values
3. **system_health.csv**: System performance metrics

### Prometheus Integration

Metrics exported to Prometheus for external monitoring:
- Trade counts by status
- P&L by strategy
- Latency measurements
- System health indicators

---

## Conclusion

Cthulu v6.0.0 is a **market-destroying beast** with:

✅ **7 Active Strategies** with intelligent selection
✅ **SAFE Engine** for autonomous operation
✅ **Profit Scaling** with ML-optimized tiers
✅ **Intelligent DCA** for adverse conditions
✅ **Adaptive Drawdown** with survival mode
✅ **Equity Protection** with profit locking
✅ **Trap Detection** against manipulation
✅ **SPARTA Mode** for battle testing
✅ **Create Your Own** full customization
✅ **Real-Time Dashboard** with benchmarking

The system is designed to be a **Set And Forget Engine** - configure once, let it trade autonomously, and watch it adapt to any market condition.

**Remember**: *"An apex predator doesn't react to the market - it dominates it."*




