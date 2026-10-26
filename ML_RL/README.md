# Cthulu ML/RL Pipeline

![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white)
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--17-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
![Models Trained](https://img.shields.io/badge/Models_Trained-3-00FF00?style=for-the-badge&labelColor=0D1117&logo=brain&logoColor=white)

> A lightweight, fast, and reliable ML pipeline for Cthulu trading system.

## Training Status (2026-01-17)

| Component | Status | Accuracy/Reward | Data Used |
|-----------|--------|-----------------|-----------|
| Feature Pipeline | ✅ Trained | 31 features | 2,845 bars |
| Price Predictor | ✅ Trained | 37.4% acc | 2,224 samples |
| RL Position Sizer | ✅ Trained | 4,852 reward | 1,736 episodes |
| Tier Optimizer | ⏳ Waiting | - | Needs closed trades |
| LLM Training Data | ✅ Prepared | 6,056 samples | 181K events |

### Data Sources Used
- **OHLCV Data**: 2,845 GOLD# M30 bars from MT5 (quality: 99%)
- **Database**: 66 trades, 878 signals
- **Event Logs**: 35,873 ML events + 145,769 cognition events

## Overview

The ML pipeline provides intelligent augmentation to Cthulu's rule-based trading system:

- **Feature Pipeline**: Robust feature engineering with 31 features across 7 categories
- **Price Predictor**: Softmax-based direction forecasting
- **Tier Optimizer**: ML-enhanced profit scaling optimization
- **RL Position Sizer**: Hybrid Q-Learning + PPO for position sizing
- **LLM Analysis**: Local LLM for market narrative generation
- **MLOps**: Model versioning, drift detection, automated retraining

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    ML PIPELINE ARCHITECTURE                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │ Feature Pipeline │───►│ Price Predictor │                    │
│  │   (31 features)  │    │   (Softmax NN)  │                    │
│  └────────┬────────┘    └────────┬────────┘                    │
│           │                      │                              │
│           ▼                      ▼                              │
│  ┌─────────────────┐    ┌─────────────────┐                    │
│  │  Tier Optimizer │    │ RL Position Sizer│                    │
│  │  (Gradient-free)│    │ (Q-Learn + PPO) │                    │
│  └────────┬────────┘    └────────┬────────┘                    │
│           │                      │                              │
│           └──────────┬───────────┘                              │
│                      ▼                                          │
│  ┌─────────────────────────────────────────┐                   │
│  │              MLOps Layer                 │                   │
│  │  • Model Registry & Versioning          │                   │
│  │  • Drift Detection (Feature/Prediction) │                   │
│  │  • Automated Retraining Triggers        │                   │
│  └─────────────────────────────────────────┘                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Start

### Training All Models

```bash
python -m training.train_models --mode all
```

### Training Individual Components

```bash
# Train price predictor
python -m training.train_models --mode predictor --epochs 100

# Enhance tier optimizer
python -m training.train_models --mode tier_optimizer

# Train RL position sizer
python -m training.train_models --mode rl_sizer --episodes 1000

# Fit feature pipeline only
python -m training.train_models --mode features --data-path path/to/data.csv
```

## Components

### 1. Feature Pipeline (`feature_pipeline.py`)

Extracts 31 features across 7 categories:

| Category | Features | Description |
|----------|----------|-------------|
| **Momentum** | 9 | Multi-timeframe momentum, recent returns |
| **Volatility** | 4 | ATR ratio, Bollinger bands, range position |
| **Volume** | 3 | Volume ratios, trend, spike detection |
| **Structure** | 3 | Higher highs/lows, swing position |
| **Indicator** | 6 | RSI, MACD, ADX with slopes |
| **Time** | 3 | Hour (sin/cos), day of week |
| **Regime** | 3 | Trend strength, choppiness, mean reversion |

```python
from training.feature_pipeline import get_feature_pipeline

pipeline = get_feature_pipeline()
features = pipeline.extract(market_data)
print(f"Features: {features.feature_names}")
```

### 2. RL Position Sizer (`rl_position_sizer.py`)

Hybrid Q-Learning + PPO for optimal position sizing:

**Actions:**
- SKIP (0x)
- MICRO (0.25x)
- SMALL (0.50x)
- STANDARD (1.0x)
- MODERATE (1.25x)
- AGGRESSIVE (1.5x)

**State Features:**
- Trend strength, volatility, momentum
- Signal confidence, entry quality
- Current exposure, win rate, drawdown
- Risk constraints

```python
from training.rl_position_sizer import get_rl_position_sizer

sizer = get_rl_position_sizer()
action, multiplier, details = sizer.get_sizing_recommendation(
    trend_strength=0.7,
    volatility=0.5,
    momentum=0.3,
    signal_confidence=0.8,
    entry_quality=0.75,
    risk_reward=2.0,
    current_exposure=0.05,
    recent_win_rate=0.55,
    current_drawdown=0.03,
    max_position_pct=0.1,
    remaining_risk=0.8
)
print(f"Recommended: {action.name} @ {multiplier:.2f}x")
```

### 3. LLM Analysis (`llm_analysis.py`)

Local LLM integration for market narratives:

```python
from training.llm_analysis import get_llm_analyzer, MarketContext

analyzer = get_llm_analyzer()

context = MarketContext(
    symbol="BTCUSD",
    timeframe="M30",
    current_price=95000.0,
    price_change_pct=1.5,
    trend_direction="up",
    trend_strength=0.7,
    volatility="medium",
    key_levels={"support": 93000, "resistance": 97000},
    indicators={"rsi": 65, "macd": 0.002, "adx": 35},
    recent_patterns=["higher_high", "bullish_engulfing"]
)

narrative = analyzer.generate_market_narrative(context)
print(narrative.content)
```

### 4. MLOps (`mlops.py`)

Model lifecycle management:

```python
from training.mlops import get_model_registry, get_drift_detector

# Model registry
registry = get_model_registry()
model_id = registry.register(
    model_type="cthulu-predictor",  # Format: cthulu-[component]-v[version]
    version="v5.3.0",
    metrics={"accuracy": 0.65},
    ...
)

# Promote to production
registry.promote_to_production(model_id)

# Drift detection
detector = get_drift_detector()
detector.set_baseline(feature_stats, prediction_dist, accuracy)
report = detector.detect_drift(model_id)
if report.triggered:
    print(f"Drift detected: {report.drift_type.value}")
```

## Directory Structure

```
training/
├── README.md                  # This file
├── data/
│   ├── raw/                   # Raw event logs
│   ├── processed/             # Cleaned datasets
│   ├── metrics/               # Performance metrics
│   └── models/                # Saved models
├── feature_pipeline.py        # Feature engineering
├── instrumentation.py         # Event logging
├── llm_analysis.py           # LLM market analysis
├── mlops.py                  # Model versioning & drift
├── rl_position_sizer.py      # RL position sizing
├── tier_optimizer.py         # Profit tier optimization
└── train_models.py           # Training orchestration
```

## Design Principles

1. **Rule-First**: ML enhances but never overrides rule-based decisions
2. **Simple**: Prefer lightweight models (trees, shallow NNs)
3. **Explainable**: All decisions must be auditable
4. **Versioned**: Full model lineage tracking
5. **Robust**: Graceful degradation when ML unavailable

## Integration with Trading Loop

The ML components integrate at specific points:

1. **Pre-Signal**: Feature extraction
2. **Signal Enhancement**: Price predictor confidence adjustment
3. **Position Sizing**: RL sizer recommendation
4. **Exit Management**: Tier optimizer for profit scaling
5. **Post-Trade**: Experience logging for retraining

## Performance Considerations

- Feature extraction: ~5ms per bar
- Price prediction: ~1ms inference
- RL sizing: ~2ms per decision
- LLM analysis: ~100ms (local), ~500ms (deterministic fallback)

## Retraining Schedule

| Component | Trigger | Frequency |
|-----------|---------|-----------|
| Feature Pipeline | Data drift > 30% | Weekly |
| Price Predictor | Accuracy drop > 10% | Daily |
| Tier Optimizer | 50+ new outcomes | Continuous |
| RL Sizer | 100+ new trades | Daily |

---

**Cthulu ML Pipeline v6.0.0**
*Intelligence that enhances, never replaces.*





