# Cognition
> Soul of Cthulu



 ![Version](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
 ![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white) 
 ![Last Commit](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?branch=main&style=for-the-badge&logo=github&labelColor=0D1117&color=6A00FF)

**AI/ML Integration Layer for Intelligent Trading**

---

## Implementation Status

| Module | Status | Description |
|--------|--------|-------------|
| **Market Regime Classifier** | ✅ IMPLEMENTED | Bull/Bear/Sideways/Volatile/Choppy detection |
| **Price Predictor** | ✅ IMPLEMENTED | Softmax/Argmax direction forecasting |
| **Sentiment Analyzer** | ✅ IMPLEMENTED | News/calendar/fear-greed integration |
| **Exit Oracle** | ✅ IMPLEMENTED | High-confluence exit signals |
| **Order Block Detector** | ✅ IMPLEMENTED | ICT methodology - institutional supply/demand zones |
| **Session ORB Detector** | ✅ IMPLEMENTED | Opening Range Breakout for London/NY sessions |
| **Cognition Engine** | ✅ IMPLEMENTED | Central orchestration layer |

---

## Quick Start

```python
from cthulu.cognition import CognitionEngine, get_cognition_engine

# Initialize engine
engine = get_cognition_engine()

# Analyze market
state = engine.analyze('BTCUSD', market_data)
print(f"Regime: {state.regime.regime.value}")
print(f"Prediction: {state.prediction.direction.value}")
print(f"Sentiment: {state.sentiment.direction.value}")

# Enhance signals
enhancement = engine.enhance_signal('long', 0.75, 'BTCUSD', market_data)
adjusted_confidence = 0.75 * enhancement.confidence_multiplier
adjusted_size = lot_size * enhancement.size_multiplier

# Get exit signals
exits = engine.get_exit_signals(positions, market_data, indicators)
for exit in exits:
    if exit.urgency.value in ('close_now', 'emergency'):
        close_position(exit.ticket, exit.recommended_close_pct)
```

---

## Module Overview

### 1. Market Regime Classifier
Detects current market conditions using softmax probability distribution.

**Regimes:** BULL, BEAR, SIDEWAYS, VOLATILE, CHOPPY

**Features Extracted:**
- Trend strength (ADX-based)
- Price momentum (multi-timeframe ROC)
- Volatility ratio (ATR/price)
- Volume trend
- Structure score (higher highs/lower lows)
- Range bound score (BB %B variance)

```python
from cthulu.cognition import classify_regime

state = classify_regime(market_data)
print(f"Regime: {state.regime.value} ({state.confidence:.0%})")
print(f"Probabilities: {state.probabilities}")
```

### 2. Price Predictor
Direction forecasting with trainable softmax classifier.

**Output:** LONG, SHORT, NEUTRAL with probabilities

**Features (12):**
- Multi-timeframe momentum (3)
- ATR ratio
- RSI normalized
- Volume ratio
- Range position
- Recent returns (5)

```python
from cthulu.cognition import predict_direction

prediction = predict_direction(market_data)
if prediction.is_actionable:
    print(f"Direction: {prediction.direction.value}")
    print(f"Expected move: {prediction.expected_move_pct:.2f}%")
```

### 3. Sentiment Analyzer
Aggregates news, calendar, and fear/greed indicators.

**Sources:**
- News headlines (keyword analysis)
- Economic calendar events
- Fear & Greed proxy

```python
from cthulu.cognition import get_sentiment

sentiment = get_sentiment('BTCUSD')
if sentiment.suggests_caution:
    print("Warning: High-impact event upcoming")
```

### 4. Exit Oracle
High-confluence exit signals using multiple reversal detectors.

**Detectors:**
- Trend Flip (25%): EMA crossover
- RSI Reversal (20%): From extremes
- MACD Crossover (15%)
- Bollinger Band (15%)
- Profit Giveback (15%)
- Volume Climax (10%)

**Urgency Levels:**
- HOLD: < 0.55 confluence
- SCALE_OUT: 0.55-0.74
- CLOSE_NOW: 0.75-0.89
- EMERGENCY: >= 0.90

```python
from cthulu.cognition import evaluate_exits

signals = evaluate_exits(positions, market_data, indicators)
for sig in signals:
    print(f"[{sig.urgency.value}] Close {sig.recommended_close_pct}% of #{sig.ticket}")
```

### 5. Order Block Detector (ICT Methodology)
Detects institutional order blocks based on Inner Circle Trader concepts.

**Concepts:**
- **Break of Structure (BOS):** Price closes beyond prior swing high/low
- **Change of Character (ChoCH):** Failure to continue trend
- **Order Block:** Last opposing candle before structure break
- **Mitigation:** When price returns to fill the zone

**Usage:**
```python
from cthulu.cognition import get_cognition_engine

engine = get_cognition_engine()

# Get order block signals
signal = engine.get_order_block_signal(market_data, current_price, atr)
if signal:
    print(f"Order Block {signal['direction']}: {signal['reason']}")
    print(f"Entry: {signal['entry_price']}, SL: {signal['stop_loss']}")

# Get active order blocks
active_obs = engine.get_active_order_blocks()
for ob in active_obs:
    print(f"{ob.block_type.value}: {ob.low:.2f} - {ob.high:.2f}")
```

### 6. Session ORB Detector (Opening Range Breakout)
Detects opening range breakouts for major trading sessions.

**Sessions:**
- **London:** 08:00-08:30 UTC
- **New York:** 13:30-14:00 UTC
- **Asian:** 00:00-00:30 UTC (optional)

**Logic:**
1. Define opening range (high/low) during first 30 minutes
2. Wait for breakout above high (bullish) or below low (bearish)
3. Execute trade with SL at opposite range boundary

**Usage:**
```python
from cthulu.cognition import get_cognition_engine

engine = get_cognition_engine()

# Get ORB signal
signal = engine.get_session_orb_signal(market_data, current_price, atr)
if signal:
    print(f"ORB {signal['direction']}: {signal['reason']}")
    print(f"Range: {signal['range_low']:.2f} - {signal['range_high']:.2f}")

# Get all structure signals (OB + ORB combined)
signals = engine.get_structure_signals(market_data, current_price, atr)
for sig in signals:
    print(f"[{sig['source']}] {sig['direction']}: {sig['reason']}")
```

---

## ML Pipeline (Legacy)

Purpose: A lightweight, fast, and reliable ML pipeline for Cthulu.

High-level layout:

- data/raw: raw event logs (JSONL/Parquet) produced by instrumentation
- data/processed: cleaned datasets and labeled examples for training
- features: feature engineering scripts
- training: training scripts and model evaluation
- serving: model serving and signal notifier (Discord)
- monitoring: drift detectors, model health monitors
- utils: helpers, schema definitions

Architecture:
1. Instrumentation to capture order, execution, and market snapshots.
2. Offline experiments (simple tree model like LightGBM/XGBoost) predicting short-term probability of positive returns for 1-5 bar horizons.
3. Shadow / advisory mode: model outputs are recorded and sent to Discord (via webhook) as "signals" in advisory mode only.
4. If approval and performance: advisory -> gated advisory filters -> advisory+small position sizing -> production.

Design principles: simple, explainable, versioned, and auditable. Keep processing fast and robust; favor lightweight models initially.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    COGNITION ENGINE                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Regime    │  │   Price     │  │  Sentiment  │         │
│  │ Classifier  │  │ Predictor   │  │  Analyzer   │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                 │
│         └────────────────┼────────────────┘                 │
│                          │                                  │
│  ┌─────────────┐  ┌──────┴──────┐  ┌─────────────┐         │
│  │Order Block  │  │    Exit     │  │ Session ORB │         │
│  │ Detector    │  │   Oracle    │  │  Detector   │         │
│  │   (ICT)     │  │             │  │(London/NY)  │         │
│  └──────┬──────┘  └─────────────┘  └──────┬──────┘         │
│         │                                  │                 │
│         └──────────────────────────────────┘                 │
│                          │                                  │
│              get_structure_signals()                        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│  analyze() → CognitionState                                 │
│  enhance_signal() → SignalEnhancement                       │
│  get_exit_signals() → List[ExitSignal]                      │
│  get_order_block_signal() → Optional[Dict]                  │
│  get_session_orb_signal() → Optional[Dict]                  │
│  get_structure_signals() → List[Dict]                       │
│  should_trade() → (bool, reason)                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Integration with Trading Loop

The Cognition Engine integrates at key points:

1. **Pre-Signal**: `should_trade()` - Check if conditions allow trading
2. **Signal Enhancement**: `enhance_signal()` - Adjust confidence/size
3. **Strategy Selection**: `get_strategy_affinity()` - Weight by regime
4. **Exit Management**: `get_exit_signals()` - High-confluence exits

---

## Training the Price Predictor

```python
from cthulu.cognition import get_cognition_engine

engine = get_cognition_engine()

# Train on historical data
result = engine.train_predictor(
    market_data,
    epochs=100,
    batch_size=32,
    move_threshold_pct=0.1
)

print(f"Accuracy: {result.accuracy:.2%}")
print(f"Final loss: {result.final_loss:.4f}")
```

---

### 7. Chart Manager (Visual Reasoning Layer)
Dynamic zone and level management - represents how Cthulu "sees" the chart.

**Architecture:**
- **Read Layer (Sync):** Fast, thread-safe reads for real-time decision making
- **Write Layer (Async):** Non-blocking zone creation/updates via background thread
- **Event System:** Callbacks for zone touches, breaks, rejections

**Zone Types:**
- Order Blocks (bullish/bearish)
- ORB High/Low
- Support/Resistance
- Fair Value Gaps (FVG)
- Trend Lines & Channels
- Fibonacci levels
- VWAP & Point of Control

**Zone Lifecycle:**
```
PENDING → ACTIVE → TESTED → WEAKENED → BROKEN/MITIGATED/EXPIRED
```

**Usage:**
```python
from cthulu.cognition import get_chart_manager

cm = get_chart_manager()

# Get zone analysis for entry decision
analysis = cm.get_zones_for_entry('BTCUSD', 'long', current_price, atr)
print(f"Zone score: {analysis['zone_score']:.2%}")
print(f"Supporting zones: {len(analysis['supporting_zones'])}")
print(f"Warnings: {analysis['warnings']}")

# Get key levels for S/R
levels = cm.get_key_levels('BTCUSD', current_price)
print(f"Support: {levels['support']}")
print(f"Resistance: {levels['resistance']}")

# Get R:R context from zone structure
rr = cm.get_risk_reward_context('BTCUSD', entry_price, 'long')
print(f"Suggested SL: {rr['suggested_sl']}, TP: {rr['suggested_tp']}")
print(f"R:R Ratio: {rr['rr_ratio']:.2f}")
```

**Integration with Entry Confluence:**
The Chart Manager automatically syncs with order_blocks.py, session_orb.py, and structure_detector.py. Zone analysis is incorporated into the confluence scoring.

---

## Files

| File | Description |
|------|-------------|
| `engine.py` | Central CognitionEngine orchestration |
| `regime_classifier.py` | Market regime detection |
| `price_predictor.py` | Direction forecasting |
| `sentiment_analyzer.py` | News/calendar integration |
| `exit_oracle.py` | Exit signal generation |
| `order_blocks.py` | ICT Order Block detection (BOS/ChoCH) |
| `session_orb.py` | Session-based Opening Range Breakout |
| `chart_manager.py` | Dynamic zone/level tracking & visual reasoning |
| `tier_optimizer.py` | ML-based tier optimization |
| `instrumentation.py` | Event logging for ML training |

---

<div align="center">

**Cognition: The Soul of Cthulu**

*"Intelligence is the ability to adapt to change."* - Stephen Hawking

</div>

