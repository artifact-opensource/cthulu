# Cthulu Training Roadmap: From Data Collection to Trading Monster

This document outlines the comprehensive training plan for evolving Cthulu into an absolute trading monster. Now that trade collection is robust and non-blocking, we can execute this plan systematically.

## Phase 1: Data Collection Validation (Current State)

### Trade Event Bus Architecture
The new `observability/trade_event_bus.py` provides:
- **Non-blocking event collection** via background thread + queue
- **Multiple event types**: TRADE_OPENED, TRADE_CLOSED, TRADE_ADOPTED, SIGNAL_*, etc.
- **Multi-consumer dispatch**: MetricsCollector, ComprehensiveCollector, TrainingDataLogger, Database, MLCollector
- All trade sources now publish events:
  - System trades (Cthulu's own signals)
  - RPC trades (external API calls)
  - Adopted trades (user's manual trades)

### Verification Steps
```bash
# Run with ML collection enabled
python -m cthulu --config config.json --enable-ml

# Check event bus stats
python -c "from observability.trade_event_bus import get_event_bus; print(get_event_bus().get_stats())"

# View collected training data
ls training/data/raw/
```

---

## Phase 2: Data Accumulation (1-2 Weeks)

### Goals
- Collect 500+ trades across different market conditions
- Capture regime changes (trending, ranging, volatile)
- Include both wins and losses for balanced training

### Data Sources
1. **Live Trading Data** (primary)
   - Real execution data with actual slippage
   - True market impact
   - Location: `training/data/raw/*.jsonl.gz`

2. **Backtesting Data** (supplementary)
   - Run backtests across historical periods
   - Generate synthetic trades with realistic conditions
   - Location: `backtesting/results/`

3. **Manual Trade Adoption**
   - Cthulu learns from user's manual trades too
   - Provides diverse trading styles in the dataset

### Data Collection Config
```json
{
  "ml": {
    "enabled": true,
    "training_data": {
      "enabled": true,
      "batch_size": 100,
      "compress": true
    }
  }
}
```

---

## Phase 3: Feature Engineering (Days 1-3)

### Core Features
| Category | Features |
|----------|----------|
| Price Action | close, open, high, low, body_pct, wick_ratio |
| Momentum | RSI, MACD, MACD_signal, ROC_5, ROC_10 |
| Volatility | ATR, BB_width, BB_position, realized_vol |
| Trend | ADX, EMA_fast/slow_ratio, slope_20 |
| Volume | volume_ratio, VWAP_distance, tick_volume |
| Time | hour_of_day, day_of_week, session (Asian/EU/US) |
| Regime | trending/ranging/volatile classification |

### Target Variables
1. **Classification Targets**
   - `outcome`: WIN/LOSS/BREAKEVEN
   - `profit_tier`: 0 (loss), 1 (small win), 2 (medium win), 3 (large win)
   - `direction_1bar`, `direction_5bar`, `direction_10bar`

2. **Regression Targets**
   - `pnl_pct`: Percentage return
   - `max_favorable_excursion`: Best price reached
   - `max_adverse_excursion`: Worst price reached
   - `hold_duration`: Time in trade

### Feature Engineering Script
```python
# training/features/engineer.py
from training.instrumentation import MLDataCollector
from cognition.training_logger import TrainingDataLogger

# Load raw data
# Transform to features
# Save to training/data/processed/
```

---

## Phase 4: Model Training (Days 4-7)

### Model Architecture Options

#### Option A: LightGBM (Recommended for Start)
- Fast training
- Handles missing values
- Feature importance built-in
- Low latency inference

```python
# training/models/lightgbm_trainer.py
import lightgbm as lgb

params = {
    'objective': 'multiclass',  # For profit_tier
    'num_class': 4,
    'metric': 'multi_logloss',
    'learning_rate': 0.05,
    'num_leaves': 31,
    'feature_fraction': 0.8,
    'bagging_fraction': 0.8,
    'verbosity': -1
}
```

#### Option B: Neural Network (For Advanced Features)
- Handles temporal sequences
- Can incorporate attention for regime detection
- More complex but potentially more powerful

```python
# training/models/neural_trader.py
import torch
import torch.nn as nn

class TradingTransformer(nn.Module):
    # Multi-head attention for market context
    # LSTM for sequence modeling
    # MLP head for prediction
```

### Training Pipeline
1. Load processed features from `training/data/processed/`
2. Time-based train/validation/test split
3. Cross-validation with walk-forward analysis
4. Hyperparameter optimization (Optuna)
5. Model selection based on:
   - Win rate improvement
   - Profit factor
   - Sharpe ratio simulation

---

## Phase 5: Model Integration (Days 8-10)

### Cognition Engine Enhancement
The existing `cognition/engine.py` provides the integration point:

```python
# cognition/engine.py - Already exists, extend:
class CognitionEngine:
    def enhance_signal(self, signal_direction, signal_confidence, symbol, market_data):
        # Load trained model
        # Extract features from market_data
        # Get model prediction
        # Return confidence adjustment and size multiplier
```

### Integration Points
1. **Signal Confidence Adjustment**
   - Model predicts probability of success
   - Adjusts strategy confidence before execution

2. **Position Sizing**
   - Higher confidence → larger position
   - Lower confidence → smaller position or skip

3. **Entry Quality Filter**
   - Model scores potential entries
   - Only execute high-quality setups

---

## Phase 6: Validation & Shadow Mode (Days 11-14)

### Shadow Testing
```bash
# Run in advisory mode - signals logged but not executed
python -m cthulu --config config.json --advisory
```

### Metrics to Track
- **Model Accuracy**: Predicted vs actual outcomes
- **Signal Quality**: Win rate of model-enhanced signals
- **Profit Factor**: Gross profit / Gross loss
- **Sharpe Ratio**: Risk-adjusted returns
- **Max Drawdown**: Worst peak-to-trough decline

### A/B Testing Framework
```python
# Compare:
# A: Original strategy (baseline)
# B: Strategy + ML enhancement

# Track side-by-side performance
# Gradual rollout based on results
```

---

## Phase 7: Production Deployment (Days 15+)

### Deployment Stages
1. **Stage 1**: Advisory only (Discord alerts)
2. **Stage 2**: Small position sizing (25% normal)
3. **Stage 3**: Medium sizing (50% normal)
4. **Stage 4**: Full deployment (100%)

### Monitoring & Alerting
- Model drift detection
- Performance degradation alerts
- Automatic fallback to rule-based mode

### HuggingFace Integration
```bash
# Push trained models to HuggingFace
# Repository: https://huggingface.co/amuzetnoM/CTHULU

# Model artifacts:
# - LightGBM model: cthulu_lgb_v1.joblib
# - Feature scaler: cthulu_scaler_v1.joblib
# - Config: model_config.json
```

---

## Phase 8: Continuous Improvement

### Automated Retraining Pipeline
```python
# training/pipeline/auto_retrain.py
class AutoRetrainPipeline:
    def check_drift(self):
        # Monitor prediction distribution
        # Compare to training distribution
    
    def retrain_if_needed(self):
        # Trigger retraining if drift detected
        # Validate new model before deployment
    
    def update_production(self):
        # Hot-swap model in running system
        # Zero-downtime deployment
```

### Performance Optimization Loop
1. Collect new trading data
2. Analyze failure modes
3. Add new features if needed
4. Retrain model
5. Validate improvement
6. Deploy if better

---

## Key Configuration Settings

### config.json ML Section
```json
{
  "ml": {
    "enabled": true,
    "model_path": "training/models/production/",
    "training_data": {
      "enabled": true,
      "batch_size": 100,
      "compress": true
    },
    "inference": {
      "enabled": true,
      "confidence_threshold": 0.6,
      "max_adjustment": 0.3
    }
  },
  "cognition": {
    "enabled": true,
    "signal_enhancement": true,
    "position_sizing": true,
    "exit_signals": true
  }
}
```

---

## Timeline Summary

| Phase | Duration | Focus |
|-------|----------|-------|
| 1. Data Validation | Day 1 | Verify event bus working |
| 2. Data Accumulation | Days 2-14 | Collect 500+ trades |
| 3. Feature Engineering | Days 15-17 | Build feature pipeline |
| 4. Model Training | Days 18-24 | Train & optimize models |
| 5. Integration | Days 25-27 | Connect to Cognition Engine |
| 6. Validation | Days 28-35 | Shadow mode testing |
| 7. Deployment | Day 36+ | Gradual rollout |
| 8. Optimization | Ongoing | Continuous improvement |

---

## Commands Reference

```bash
# Enable ML collection
python -m cthulu --config config.json --enable-ml

# Export training data
python -c "from integrations.ml_exporter import MLDataExporter; e=MLDataExporter(); e.export_training_data()"

# Train model (when ready)
python training/train_model.py --config training/config.yaml

# Run validation
python training/validate_model.py --model models/latest --data data/test

# Push to HuggingFace (optional)
cd training/models/production
huggingface-cli upload amuzetnoM/CTHULU ./
```

---

## Next Immediate Steps

1. **Verify Event Bus** - Confirm events are being published
2. **Run Live Collection** - Start accumulating real trade data
3. **Monitor Metrics** - Watch comprehensive_metrics.csv growth
4. **Prepare Feature Pipeline** - Set up feature engineering scripts

The foundation is now solid. Time to feed the beast and train it into a trading monster! 🐙
