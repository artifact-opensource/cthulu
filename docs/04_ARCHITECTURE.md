---
title: ARCHITECTURE
description: Technical architecture and system design of the Cthulu multi-strategy autonomous trading platform
tags: [architecture, system-design, technical-overview]
sidebar_position: 4
version: 6.0.0
---

![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white)
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white)

### High-Level System Overview

```mermaid
graph TB
    subgraph "User Interface Layer"
        GUI[Desktop GUI<br/>Tkinter Dashboard]
        RPC[RPC Server<br/>HTTP API]
    end

    subgraph "Core Trading Engine"
        ORCH[Multi-Strategy<br/>Orchestrator]
        STRAT[Strategy Engine<br/>6 Strategies]
        EXEC[Execution Engine<br/>Order Management]
    end

    subgraph "Intelligence Layer"
        IND[Indicator Library<br/>12 Indicators]
        REGIME[Regime Detection<br/>10 States]
        NEWS[News Integration<br/>FRED, TradingEconomics]
    end

    subgraph "Data & Persistence"
        DATA[Data Layer<br/>OHLCV Processing]
        DB[SQLite Database<br/>Trade History]
        CACHE[Cache Layer<br/>Performance]
    end

    subgraph "Risk & Position Management"
        RISK[Risk Manager<br/>Position Sizing]
        POS[Position Manager<br/>Lifecycle]
        EXIT[Exit Strategies<br/>4 Types]
    end

    subgraph "External Services"
        MT5[MetaTrader 5<br/>Broker]
        PROM[Prometheus<br/>Metrics]
    end

    GUI --> ORCH
    RPC --> ORCH
    ORCH --> REGIME
    REGIME --> STRAT
    STRAT --> IND
    STRAT --> NEWS
    STRAT --> EXEC
    EXEC --> RISK
    RISK --> MT5
    EXEC --> POS
    POS --> EXIT
    EXIT --> MT5
    DATA --> MT5
    IND --> DATA
    POS --> DB
    EXEC --> DB
    ORCH --> PROM
    DATA --> CACHE

    style ORCH fill:#00ff88,stroke:#00cc6a,color:#000
    style MT5 fill:#00aaff,stroke:#0088cc,color:#000
    style DB fill:#ffaa00,stroke:#dd8800,color:#000
```

> 🧭 Interactive system map available: `docs/SYSTEM_MAP.html` (local draft in `_dev/system_map.html`)

### Component Architecture

```mermaid
flowchart LR
    ORCH["Multi-Strategy Orchestrator<br/>(__main__.py)<br/>11-step trading loop"]
    CONFIG["Configuration<br/>(config/)<br/>Wizard + Schema"]
    LOGGING["Logging System<br/>(observability/)<br/>JSON + Metrics"]
    MT5["MT5 Connector<br/>(connector/)<br/>- Reconnection<br/>- Rate limiting<br/>- Health check"]
    RISK["Risk Manager<br/>(risk/)<br/>- Position size<br/>- Daily limits<br/>- Approval"]
    DATA["Data Layer<br/>(data/)<br/>- OHLCV norm<br/>- Caching<br/>- Resampling"]
    IND["Indicator Library<br/>(indicators/)<br/>RSI, MACD, BB, Stoch<br/>ADX, Supertrend, VWAP"]
    STRAT["Strategy Engine<br/>(strategy/)<br/>- 7 Strategies<br/>- Regime Detection<br/>- Selection"]
    EXEC["Execution Engine<br/>(execution/)<br/>- Idempotent orders<br/>- ML instrumentation<br/>- Reconciliation"]
    POS["Position Mgmt<br/>(position/)<br/>- Tracking<br/>- Adoption<br/>- P&L calc"]
    EXIT["Exit Strategies<br/>(exit/)<br/>- Trailing stop<br/>- Time-based<br/>- Profit target"]
    DB["Persistence<br/>(database/)<br/>- SQLite trades<br/>- Signals<br/>- Metrics"]
    OBS["Observability<br/>(monitoring/)<br/>- Trade monitor<br/>- Health checks<br/>- Prometheus"]
    GUI["Desktop GUI<br/>(ui/)<br/>- Trade history<br/>- Live monitor<br/>- Metrics dash"]
    RPC["RPC Server<br/>(rpc/)<br/>- HTTP API<br/>- Manual trading<br/>- REST endpoints"]

    ORCH --> CONFIG
    ORCH --> LOGGING
    CONFIG --> MT5
    CONFIG --> RISK
    LOGGING --> MT5
    LOGGING --> RISK
    MT5 --> DATA
    RISK --> DATA
    MT5 --> IND
    RISK --> IND
    DATA --> STRAT
    IND --> STRAT
    DATA --> EXEC
    IND --> EXEC
    STRAT --> POS
    EXEC --> POS
    STRAT --> EXIT
    EXEC --> EXIT
    POS --> DB
    EXIT --> DB
    POS --> OBS
    EXIT --> OBS
    DB --> GUI
    OBS --> GUI
    DB --> RPC
    OBS --> RPC

    style ORCH fill:#00ff88,stroke:#00cc6a,color:#000
    style MT5 fill:#00aaff,stroke:#0088cc,color:#000
    style DB fill:#ffaa00,stroke:#dd8800,color:#000
```

### Core Runtime Flow (strategy → execution → position → exit → persistence)

```mermaid
flowchart TD
    SignalGen[Strategy Engine<br/>Signal Generation]
    Exec[Execution Engine<br/>Order Submission]
    Position[Position Manager<br/>Track & P&L]
    Exit[Exit Strategies<br/>Stop/TP/Trailing/Time]
    Persist[Persistence<br/>Signal/Order/Trade Storage]

    SignalGen --> Exec
    Exec --> Position
    Position --> Exit
    Exit --> Persist
    Exec --> Persist
```

## Autonomous Trading Flow

### Trading Loop Sequence

```mermaid
sequenceDiagram
    participant User
    participant Orchestrator
    participant MT5
    participant Strategy
    participant Risk
    participant Execution
    participant Position

    User->>Orchestrator: Start Trading

    loop Every Trading Cycle
        Orchestrator->>MT5: Check Connection
        MT5-->>Orchestrator: Status OK

        Orchestrator->>MT5: Fetch Market Data
        MT5-->>Orchestrator: OHLCV Data

        Orchestrator->>Strategy: Detect Market Regime
        Strategy-->>Orchestrator: Regime Classification

        Orchestrator->>Strategy: Analyze & Generate Signal
        Strategy-->>Orchestrator: Trade Signal (BUY/SELL/HOLD)

        alt Signal is BUY or SELL
            Orchestrator->>Risk: Validate Trade
            Risk-->>Orchestrator: Risk Approved + Position Size

            Orchestrator->>Execution: Execute Order
            Execution->>MT5: Place Order
            MT5-->>Execution: Order Filled
            Execution-->>Orchestrator: Execution Result

            Orchestrator->>Position: Track New Position
            Position-->>Orchestrator: Position Registered
        end

        Orchestrator->>Position: Check Existing Positions
        Position->>Position: Evaluate Exit Conditions

        alt Exit Condition Met
            Position->>Execution: Close Position
            Execution->>MT5: Close Order
            MT5-->>Execution: Position Closed
        end

        Orchestrator->>Orchestrator: Update Metrics
        Orchestrator->>User: Log Status
    end
```

### Detailed Trading Flow

```mermaid
flowchart LR
    START([Start System])
    INIT[Initialize Components]
    CONFIG[Load Configuration]
    MT5CONN[Connect MT5]
    COMPONENTS[Setup Modules]

    LOOP_START{Main Trading Loop}
    HEALTH[Step 1: Connection Health]
    SYNC[Step 2: Position Sync]
    FETCH[Step 3: Market Data Fetch]
    IND[Step 4: Calculate Indicators]
    ENTRY[Step 5: Entry Signal]
    RISK_CHECK[Step 6: Risk Approval]
    EXECUTE[Step 7: Execute Entry]
    EXIT_CHECK[Step 8: Exit Signal Check]
    EXIT_EXEC[Step 9: Execute Exit]
    PERSIST[Step 10: Persistence & Metrics]
    SLEEP[Sleep Interval]

    SHUTDOWN[Shutdown: Close Connections & Save]
    END([End])

    START --> INIT
    INIT --> CONFIG
    CONFIG --> MT5CONN
    MT5CONN --> COMPONENTS
    COMPONENTS --> LOOP_START

    LOOP_START --> HEALTH
    HEALTH --> SYNC
    SYNC --> FETCH
    FETCH --> IND
    IND --> ENTRY
    ENTRY --> RISK_CHECK
    RISK_CHECK --> EXECUTE
    EXECUTE --> EXIT_CHECK
    EXIT_CHECK --> EXIT_EXEC
    EXIT_EXEC --> PERSIST
    PERSIST --> SLEEP
    SLEEP --> LOOP_START

    LOOP_START --> SHUTDOWN
    SHUTDOWN --> END

    style START fill:#00ff88,stroke:#00cc6a,color:#000
    style END fill:#ff4444,stroke:#cc0000,color:#fff
    style LOOP_START fill:#ffaa00,stroke:#dd8800,color:#000
```

## Data Flow

```mermaid
flowchart LR
    MT5[MT5 Terminal]
    CONN[MT5 Connector]
    DATA[Data Layer]
    IND[Indicators]
    STRAT[Strategy Engine]
    SIGNAL[Trade Signal]

    MT5 -->|Historical Data| CONN
    CONN -->|OHLCV| DATA
    DATA -->|Normalized DataFrame| IND
    IND -->|Technical Values| STRAT
    STRAT -->|Analysis| SIGNAL

    style MT5 fill:#00aaff,stroke:#0088cc,color:#000
    style SIGNAL fill:#00ff88,stroke:#00cc6a,color:#000
```

---

## Monitoring & Deployment Recommendations

**Short-term (30–60 min validation)**
- Run Cthulu locally using an aggressive mindset config and debug logging:
```bash
python -m Cthulu --config configs/mindsets/aggressive/config_aggressive_h1.json --symbol "GOLD#m" --skip-setup --no-prompt --log-level DEBUG
```
- Tail logs and watch for messages:
  - `Adopted trade:`
  - `Set SL/TP for #`
  - `SL/TP verification failed`
  - `Failed to select symbol`

**Production (recommended)**
- Containerize with Docker, expose Prometheus metrics (use `observability/prometheus.py`).
- Use orchestration (Compose/K8s) with health probes and restart policies.
- Centralized logging and alerting (Prometheus + Alertmanager; Slack/PagerDuty for critical alerts).

Choose: (A) 30–60 minute live terminal monitoring, or (B) start containerizing + add Prometheus endpoint and alert rules.

---

## Trade Decision Flow

```mermaid
flowchart LR
    START([Market Data Arrives])
    FETCH[Fetch OHLCV Data]
    NORM[Normalize DataFrame]
    IND[Calculate Indicators]
    subgraph INDICATORS["Technical Indicators"]
        RSI[RSI]
        MACD[MACD]
        BB[Bollinger Bands]
        ADX[ADX]
        ATR[ATR]
    end
    REGIME[Detect Market Regime]
    SELECT[Select Strategy]
    ANALYZE[Strategy Analysis]
    SIGNAL{Signal Generated?}
    RISK_CHECK[Risk Validation]
    SIZE[Calculate Position Size]
    SLTP[Calculate SL/TP]
    APPROVE{Risk Approved?}
    EXECUTE[Execute Order]
    TRACK[Track Position]
    MONITOR[Monitor Exits]
    REJECT[Reject Trade]
    END([Continue Loop])

    START --> FETCH
    FETCH --> NORM
    NORM --> IND
    IND --> RSI
    IND --> MACD
    IND --> BB
    IND --> ADX
    IND --> ATR
    RSI --> REGIME
    MACD --> REGIME
    BB --> REGIME
    ADX --> REGIME
    ATR --> REGIME
    REGIME --> SELECT
    SELECT --> ANALYZE
    ANALYZE --> SIGNAL
    SIGNAL -->|Yes| RISK_CHECK
    SIGNAL -->|No| END
    RISK_CHECK --> SIZE
    SIZE --> SLTP
    SLTP --> APPROVE
    APPROVE -->|Yes| EXECUTE
    APPROVE -->|No| REJECT
    EXECUTE --> TRACK
    TRACK --> MONITOR
    MONITOR --> END
    REJECT --> END

    style START fill:#00ff88,stroke:#00cc6a,color:#000
    style EXECUTE fill:#00aaff,stroke:#0088cc,color:#000
    style REJECT fill:#ff4444,stroke:#cc0000,color:#fff
```

## Strategy Selection Logic

```mermaid
flowchart TD
    START([Begin Strategy Selection])
    REGIME[Analyze Market Regime]
    TRENDING{Trending<br/>ADX > 25?}
    VOLATILE{Volatile<br/>ATR High?}
    RANGING{Ranging<br/>BB Tight?}

    RSI_REV[RSI Reversal<br/>Strategy]
    EMA[EMA Crossover<br/>Strategy]
    SMA[SMA Crossover<br/>Strategy]
    MOM[Momentum Breakout<br/>Strategy]
    SCALP[Scalping<br/>Strategy]
    MEAN[Mean Reversion<br/>Strategy]
    TREND[Trend Following<br/>Strategy]

    FALLBACK{Primary<br/>Signal?}
    TRY_ALT[Try Alternative<br/>Strategies]
    NO_SIGNAL[No Signal]

    START --> REGIME
    REGIME --> TRENDING
    TRENDING -->|Yes, Strong| TREND
    TRENDING -->|Yes, Weak| EMA
    TRENDING -->|No| VOLATILE
    VOLATILE -->|Yes| MOM
    VOLATILE -->|No| RANGING
    RANGING -->|Tight| SCALP
    RANGING -->|Normal| MEAN
    RANGING -->|Wide| SMA

    RSI_REV --> FALLBACK
    EMA --> FALLBACK
    SMA --> FALLBACK
    MOM --> FALLBACK
    SCALP --> FALLBACK
    MEAN --> FALLBACK
    TREND --> FALLBACK

    FALLBACK -->|No| TRY_ALT
    FALLBACK -->|Yes| END([Generate Signal])
    TRY_ALT -->|Up to 3 more| FALLBACK
    TRY_ALT -->|Exhausted| NO_SIGNAL
    NO_SIGNAL --> END

    style START fill:#00ff88,stroke:#00cc6a,color:#000
    style END fill:#00aaff,stroke:#0088cc,color:#000
    style NO_SIGNAL fill:#ffaa00,stroke:#dd8800,color:#000
```

## Exit Strategy Priority Flow

```mermaid
flowchart LR
    START([Monitor Positions])
    CHECK[Check All Open Positions]

    subgraph EXITS["Exit Strategy Evaluation (Priority Order)"]
        P90[Priority 90<br/>Adverse Movement<br/>Emergency Exit]
        P50[Priority 50<br/>Time-Based Exit<br/>Max Hold Time]
        P40[Priority 40<br/>Profit Target<br/>Take Profit]
        P25[Priority 25<br/>Trailing Stop<br/>Lock Profits]
    end

    EXEC{Exit<br/>Triggered?}
    CLOSE[Close Position]
    UPDATE[Update P&L]
    LOG[Log Exit Event]
    PERSIST[Save to Database]
    CONTINUE[Continue Monitoring]

    START --> CHECK
    CHECK --> P90
    P90 -->|Check| P50
    P50 -->|Check| P40
    P40 -->|Check| P25
    P90 --> EXEC
    P50 --> EXEC
    P40 --> EXEC
    P25 --> EXEC
    EXEC -->|Yes| CLOSE
    EXEC -->|No| CONTINUE
    CLOSE --> UPDATE
    UPDATE --> LOG
    LOG --> PERSIST
    PERSIST --> CONTINUE
    CONTINUE --> START

    style P90 fill:#ff4444,stroke:#cc0000,color:#fff
    style P50 fill:#ffaa00,stroke:#dd8800,color:#000
    style P40 fill:#00ff88,stroke:#00cc6a,color:#000
    style P25 fill:#00aaff,stroke:#0088cc,color:#000
```

## Multi-Strategy Ensemble Architecture

```mermaid
flowchart TB
    subgraph ENSEMBLE["Strategy Ensemble"]
        direction LR
        S1[RSI Reversal]
        S2[EMA Crossover]
        S3[SMA Crossover]
        S4[Momentum]
        S5[Scalping]
        S6[Mean Reversion]
        S7[Trend Following]
    end

    subgraph PERF["Performance Tracking"]
        WIN[Win Rate]
        PF[Profit Factor]
        SHARPE[Sharpe Ratio]
        DD[Drawdown]
    end

    subgraph REGIME["Regime Detection"]
        TREND_D[Trending]
        RANGE_D[Ranging]
        VOLAT_D[Volatile]
        BREAKOUT[Breakout]
        REVERSAL[Reversal]
    end

    SELECTOR[Dynamic Strategy Selector]
    ACTIVE[Active Strategy]
    SIGNAL[Trade Signal]

    S1 --> PERF
    S2 --> PERF
    S3 --> PERF
    S4 --> PERF
    S5 --> PERF
    S6 --> PERF
    S7 --> PERF

    PERF --> SELECTOR
    REGIME --> SELECTOR
    SELECTOR --> ACTIVE
    ACTIVE --> SIGNAL

    style SELECTOR fill:#00ff88,stroke:#00cc6a,color:#000
    style ACTIVE fill:#00aaff,stroke:#0088cc,color:#000
    style SIGNAL fill:#ffaa00,stroke:#dd8800,color:#000
```

## Risk Management Flow

```mermaid
flowchart LR
    SIGNAL[Trade Signal Received]

    subgraph CHECKS["Risk Validation Checks"]
        BAL[Check Account Balance]
        DAILY[Check Daily Loss Limit]
        POS_COUNT[Check Position Count]
        EXPO[Check Symbol Exposure]
        MARGIN[Check Margin Available]
    end

    SIZE[Calculate Position Size]

    subgraph SIZING["Sizing Methods"]
        PCT[% of Balance]
        KELLY[Kelly Criterion]
        FIXED[Fixed Lot Size]
        VOL[Volatility-Based]
    end

    SL[Calculate Stop Loss]
    TP[Calculate Take Profit]

    APPROVE{All Checks<br/>Passed?}
    EXEC[Approve Execution]
    REJECT[Reject Trade]
    LOG[Log Decision]

    SIGNAL --> CHECKS
    BAL --> SIZE
    DAILY --> SIZE
    POS_COUNT --> SIZE
    EXPO --> SIZE
    MARGIN --> SIZE

    SIZE --> PCT
    SIZE --> KELLY
    SIZE --> FIXED
    SIZE --> VOL

    PCT --> SL
    KELLY --> SL
    FIXED --> SL
    VOL --> SL

    SL --> TP
    TP --> APPROVE

    APPROVE -->|Yes| EXEC
    APPROVE -->|No| REJECT

    EXEC --> LOG
    REJECT --> LOG

    style APPROVE fill:#ffaa00,stroke:#dd8800,color:#000
    style EXEC fill:#00ff88,stroke:#00cc6a,color:#000
    style REJECT fill:#ff4444,stroke:#cc0000,color:#fff
```

---

## Component Responsibilities

### Core Components

**MT5Connection** (`core/connection.py`)
- Establish and maintain MT5 terminal connection
- Handle reconnection logic
- Provide account and terminal information
- Manage symbol data access
- Health monitoring

**RiskManager** (`core/risk_manager.py`)
- Calculate position sizes based on risk percentage
- Compute stop loss and take profit levels
- Enforce trading limits (max positions, daily loss)
- Track daily P&L
- Validate margin requirements

**TradeManager** (`core/trade_manager.py`)
- Execute market orders (buy/sell)
- Close existing positions
- Modify position SL/TP
- Track all bot positions
- Handle order errors and retries

### Strategy Components

**BaseStrategy** (`strategies/base_strategy.py`)
- Abstract base class for all strategies
- Common functionality (data fetching, ATR calculation)
- Strategy execution framework
- Signal management

**SimpleMovingAverageCross** (`strategies/simple_ma_cross.py`)
- MA crossover signal detection
- Entry/exit logic
- Filter application
- Position management

### Utility Components

**Config** (`utils/config.py`)
- Load YAML configuration
- Access configuration values
- Validate settings
- Save configuration changes

**Logger** (`utils/logger.py`)
- Console and file logging
- Color-coded output
- Trade-specific logging
- Error tracking

## Safety Features

### Multi-Layer Risk Protection

1. Configuration Level
   - Risk per trade limit (default: 1%)
   - Max concurrent positions (default: 3)
   - Max daily loss (default: 5%)

2. Pre-Trade Checks
   - Connection validation
   - Trading hours filter
   - Spread limit check
   - Margin sufficiency
   - Account trading status

3. Position Level
   - Automatic stop loss on every trade
   - Take profit for profit targets
   - ATR-based SL sizing
   - Risk/reward ratio enforcement

4. Daily Tracking
   - Daily P&L monitoring
   - Automatic trading halt at loss limit
   - Position count enforcement

## Extensibility Points

### Adding New Strategies

```python
from strategies.base_strategy import BaseStrategy

class MyCustomStrategy(BaseStrategy):
    def analyze(self, df):
        # Your analysis logic
        return signal_dict

    def should_close_position(self, position, df):
        # Your exit logic
        return (should_close, reason)
```

### Adding New Indicators

```python
# indicators/custom.py
def my_indicator(df, period=14):
    # Calculate indicator
    return indicator_values
```

### Integration Points
- gold_standard Integration (import signals, regime detection)
- External Data Sources (sentiment, news, alternative data)
- Machine Learning (feature extraction, prediction integration)

## Testing Strategy

### Unit Tests
- Component isolation testing
- Mock MT5 API responses
- Risk calculation verification

### Integration Tests
- Full strategy execution
- Multi-component interaction
- Error handling scenarios

### Backtesting
- Historical data replay
- Performance metrics
- Optimization runs

## Deployment Architecture

```
Development Environment
├── Local Python venv
├── Demo MT5 account
├── File-based configuration
└── Console logging

Production Environment (Future)
├── Dedicated server/VPS
├── Live MT5 account
├── Database configuration
├── Remote logging (e.g., Elasticsearch)
├── Monitoring dashboard
└── Alert system
```

## Future Architecture Evolution

### Phase 2: Multi-Strategy
```
Cthulu Bot
├── Strategy Manager
│   ├── MA Crossover
│   ├── RSI + MACD
│   ├── Bollinger Breakout
│   └── Pattern Recognition
└── Regime Detector
    └── Strategy Router
```

### Phase 3: ML Integration
```
Cthulu Bot
├── Feature Engine
├── ML Model Manager
│   ├── Random Forest
│   ├── Gradient Boosting
│   └── Ensemble
└── Prediction Service
```

### Phase 4: Multi-Asset
```
Cthulu Bot
├── Asset Manager
│   ├── XAUUSD (Gold)
│   ├── EURUSD (Forex)
│   └── BTCUSD (Crypto)
├── Portfolio Manager
└── Correlation Engine
```

---

```mermaid
flowchart TD
    subgraph Orchestration
        O1["__main__.py loop"]
    end
    A["MT5 Connector<br/>(MT5Connector / mt5)"]
    B["Data Layer<br/>(DataLayer.normalize_rates)"]
    C["Indicators<br/>(RSI, MACD, Bollinger, Stochastic, ADX)"]
    D["Strategy<br/>(SmaCrossover / Strategy.on_bar)"]
    E["Risk Manager<br/>(RiskManager.approve)"]
    F["Execution Engine<br/>(ExecutionEngine.place_order)"]
    G["MT5<br/>(order_send) & Order Result"]
    H["Position Manager<br/>(PositionManager.track_position / monitor_positions)"]
    I["Exit Strategies<br/>(Adverse, TimeBased, ProfitTarget, TrailingStop)"]
    J["Persistence<br/>(Database.record_trade, record_signal, update_trade_exit)"]
    K["Metrics<br/>(MetricsCollector)"]
    L["Health & Reconnect checks<br/>(MT5Connector.is_connected, reconnect)"]
    M["Trade Adoption<br/>(TradeManager.scan_and_adopt → PositionManager.add_position)"]

    O1 --> A
    O1 --> B
    O1 --> C
    O1 --> D
    O1 --> E
    O1 --> F
    O1 --> H
    O1 --> I
    O1 --> J
    O1 --> K
    O1 --> L
    O1 --> M

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H --> I
    I -- "Position close" --> F
    H --> J
    F --> J
    H --> K
    J --> K
    A --> L
    L --> H
    A --> M
```

---

**Current Status:** Production-ready v6.0.0, upgrade implementation and additional research in-progess.
**Architecture:** Fully modular, extensible, enterprise-grade with 6 strategies and 12 indicators  
**Next Steps:** Performance optimization and advanced monitoring enhancements
