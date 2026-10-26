┌──────────────────────────────────────────────────────────────────────────────┐
│                        CTHULU ML/RL ARCHITECTURE                             │
└──────────────────────────────────────────────────────────────────────────────┘

                           ┌─────────────────────┐
                           │    MARKET DATA      │
                           │   (MT5/Broker)      │
                           └──────────┬──────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         DATA COLLECTION LAYER                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────────┐              ┌──────────────────┐                     │
│   │  MLDataCollector │              │  TrainingLogger  │                     │
│   │  (ML_RL/instr.py)│              │  (cognition/)    │                     │
│   └────────┬─────────┘              └────────┬─────────┘                     │
│            │                                  │                              │
│            ▼                                  ▼                              │
│   ┌──────────────────┐              ┌──────────────────┐    ┌────────────┐   │
│   │ ML_RL/data/raw/  │              │cognition/data/raw│    │ cthulu.db  │   │
│   │ 184 files, 805KB │              │ 385 files, 1.4MB │    │  (SQLite)  │   │
│   └──────────────────┘              └──────────────────┘    └────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         FEATURE ENGINEERING                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                    ┌─────────────────────────────┐                           │
│                    │     FeaturePipeline         │                           │
│                    │  (ML_RL/feature_pipeline.py)│                           │
│                    └─────────────┬───────────────┘                           │
│                                  │                                           │
│          ┌───────────┬───────────┼───────────┬───────────┐                   │
│          ▼           ▼           ▼           ▼           ▼                   │
│    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│    │Technical │ │  Price   │ │  Volume  │ │ Multi-TF │ │  Trend   │          │
│    │Indicators│ │ Patterns │ │ Analysis │ │ Features │ │ Strength │          │
│    │RSI,MACD  │ │momentum  │ │          │ │          │ │          │          │
│    │BB,ATR    │ │volatility│ │          │ │          │ │          │          │
│    └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│                                  │                                           │
│                                  ▼                                           │
│                    ┌─────────────────────────────┐                           │
│                    │   50+ Engineered Features   │                           │
│                    └─────────────────────────────┘                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                      │
                  ┌───────────────────┼───────────────────┐
                  ▼                   ▼                   ▼
┌─────────────────────┐ ┌─────────────────────┐ ┌─────────────────────┐
│   PRICE PREDICTOR   │ │   RL POSITION SIZER │ │   TIER OPTIMIZER    │
├─────────────────────┤ ├─────────────────────┤ ├─────────────────────┤
│                     │ │                     │ │                     │
│  Softmax Classifier │ │  Hybrid Agent:      │ │  Bayesian Optimizer │
│                     │ │  • Q-Learning       │ │                     │
│  Outputs:           │ │  • PPO Policy       │ │  Optimizes:         │
│  • UP probability   │ │                     │ │  • scale_factor     │
│  • DOWN probability │ │  Actions:           │ │  • tier_count (1-5) │
│  • SIDEWAYS prob    │ │  • 0.25x to 2.0x    │ │  • profit_targets   │
│                     │ │  • Position mult    │ │                     │
│  Example:           │ │                     │ │  Tiers:             │
│  UP=0.60            │ │  Reward:            │ │  T1: 25% @ 0.5%     │
│  DOWN=0.30          │ │  • PnL-based        │ │  T2: 25% @ 1.0%     │
│  SIDE=0.10          │ │  • Risk-adjusted    │ │  T3: 25% @ 1.5%     │
│                     │ │  • Drawdown penalty │ │  T4: 25% @ 2.0%     │
│                     │ │                     │ │                     │
└─────────┬───────────┘ └─────────┬───────────┘ └─────────┬───────────┘
          │                       │                       │
          └───────────────────────┼───────────────────────┘
                                  ▼
                    ┌─────────────────────────────┐
                    │      TRADING DECISION       │
                    │  • Direction (from PP)      │
                    │  • Size (from RL)           │
                    │  • Exit tiers (from TO)     │
                    └─────────────┬───────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           LLM ANALYSIS                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│                    ┌─────────────────────────────┐                           │
│                    │        LLMAnalyzer          │                           │
│                    │   (ML_RL/llm_analyzer.py)   │                           │
│                    └─────────────┬───────────────┘                           │
│                                  │                                           │
│          ┌───────────────────────┼───────────────────────┐                   │
│          ▼                       ▼                       ▼                   │
│   ┌──────────────┐      ┌──────────────┐      ┌──────────────┐               │
│   │   Market     │      │    Trade     │      │     Risk     │               │
│   │  Narrative   │      │  Rationale   │      │  Assessment  │               │
│   └──────────────┘      └──────────────┘      └──────────────┘               │
│                                                                              │
│   Backend: Local Ollama (qwen2.5:3b / llama3.2:3b)                           │
│   Fallback: Template-based generation                                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                              MLOps                                           │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────┐              │
│  │ Model Registry │    │ Drift Detector │    │ Auto Retrainer │              │
│  ├────────────────┤    ├────────────────┤    ├────────────────┤              │
│  │• Version track │    │• KS-test       │    │• Trigger on    │              │
│  │• Metadata      │───▶│• Feature drift ───▶│  drift detect  │              │
│  │• Promote/arch  │    │• Alerts        │    │• Auto-train    │              │
│  └────────────────┘    └────────────────┘    └────────────────┘              │
│                                                                              │
│  Storage: ML_RL/models/registry/                                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                         STORAGE SUMMARY                                      │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ML_RL/                                                                      │
│  ├── data/                                                                   │
│  │   ├── raw/              184 files    805 KB   Event logs                  │
│  │   ├── training/         469 files    1.7 MB   Training data               │
│  │   ├── tier_optimizer/     1 file       7 KB   Optimizer state             │
│  │   └── metrics/                                Performance logs            │
│  ├── models/                                                                 │
│  │   ├── rl/                                     RL sizer model              │
│  │   └── registry/                               Model registry              │
│  ├── feature_pipeline.py                                                     │
│  ├── rl_position_sizer.py                                                    │
│  ├── llm_analyzer.py                                                         │
│  ├── mlops.py                                                                │
│  └── train_models.py                                                         │
│                                                                              │
│  cognition/                                                                  │
│  ├── data/raw/             385 files    1.4 MB   Decision logs               │
│  ├── price_predictor.py                                                      │
│  ├── tier_optimizer.py                                                       │
│  └── engine.py                                                               │
│                                                                              │
│  TOTAL: ~21 MB                                                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────┐
│                           CLI COMMANDS                                       │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Data Management:                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  python scripts/data_cli.py status         # Storage summary         │    │
│  │  python scripts/data_cli.py health         # Endpoint health         │    │
│  │  python scripts/data_cli.py cleanup --days 30   # Cleanup old        │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  Training:                                                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐    │
│  │  python -m ML_RL.train_models --component all       # Train all      │    │
│  │  python -m ML_RL.train_models --component predictor # Price only     │    │
│  │  python -m ML_RL.train_models --component rl        # RL sizer       │    │
│  │  python -m ML_RL.train_models --component optimizer # Tier opt       │    │
│  └──────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘

---

# ML Flow: Two Modes
1. LIVE TRADING MODE (Data Collection)

┌─────────────────────────────────────────────────────────────────────┐
│                    LIVE TRADING - DATA COLLECTION                   │
└─────────────────────────────────────────────────────────────────────┘

  MT5/Broker ──► Market Data ──► Trading Loop ──► Execute Orders
       │              │              │                  │
       │              ▼              ▼                  ▼
       │     ┌────────────────┐  ┌────────────────┐  ┌──────────┐
       │     │MLDataCollector │  │TrainingLogger  │  │cthulu.db │
       │     │(ML_RL/instr.py)│  │(cognition/)    │  │ (SQLite) │
       │     └───────┬────────┘  └───────┬────────┘  └────┬─────┘
       │             │                   │                │
       │             ▼                   ▼                ▼
       │     ML_RL/data/raw/     cognition/data/raw/   trades,
       │     *.jsonl.gz          *.jsonl.gz            signals
       │     - order_request     - decisions           positions
       │     - execution         - predictions
       │     - market_snapshot   - outcomes
       │
       └──► NO TRAINING HAPPENS - JUST COLLECTING DATA


2. MODEL TRAINING MODE (Offline)

┌─────────────────────────────────────────────────────────────────────┐
│                    OFFLINE MODE - MODEL TRAINING                    │
└─────────────────────────────────────────────────────────────────────┘

  Historical Data Sources:
  ├── ML_RL/data/raw/*.jsonl.gz      (collected events)
  ├── cognition/data/raw/*.jsonl.gz  (decision logs)
  ├── cthulu.db (trades table)       (trade history)
  └── CSV files (optional)           (OHLCV data)
           │
           ▼
  ┌─────────────────────────────────────────────────────────────────┐
  │                   python -m ML_RL.train_models                  │
  │                                                                 │
  │  1. Load Data                                                   │
  │     └── HistoricalDataManager OR synthetic data                 │
  │                                                                 │
  │  2. Fit Feature Pipeline                                        │
  │     └── Compute 50+ features, normalize, save scaler            │
  │                                                                 │
  │  3. Train Price Predictor                                       │
  │     └── Softmax classifier: UP/DOWN/SIDEWAYS                    │
  │     └── Saves: ML_RL/data/models/price_predictor.json           │
  │                                                                 │
  │  4. Enhance Tier Optimizer                                      │
  │     └── Bayesian optimization on scaling outcomes               │
  │     └── Saves: ML_RL/data/tier_optimizer/optimizer_state.json   │
  │                                                                 │
  │  5. Train RL Sizer                                              │
  │     ├── Offline: Replay historical trades                       │
  │     └── Simulated: Random episodes if no data                   │
  │     └── Saves: ML_RL/models/rl/rl_sizer.json                    │
  │                                                                 │
  │  6. Register Models                                             │
  │     └── MLOps registry with versioning                          │
  └─────────────────────────────────────────────────────────────────┘
           │
           ▼
  Models ready for next live trading session



# Commands:

- **Full pipeline**
python -m ML_RL.train_models --mode all           

-  **Just price predictor**
python -m ML_RL.train_models --mode predictor

-**Just RL**
python -m ML_RL.train_models --mode rl_sizer      

python -m ML_RL.train_models --mode tier_optimizer