# Changelog

## [6.0.0] - 2026-03-10

### K9: The Cognition Kube — Cthulu Goes Alive

#### Tentacle/Arm System (K1-K8)
- **K1-K8 Tentacles:** 8 indicators × 8 timeframes × 4 symbols = 256 sensor configurations
- Each tentacle scans a single timeframe with RSI, MACD, Bollinger, EMA/SMA crossovers, ATR, volume, OBV, ADX
- Sub-40ms scan latency per tentacle — faster than market microstructure noise
- Consensus scoring: UNANIMOUS (8/8), STRONG (7/8), DOMINANT (5-6), MAJORITY (4)

#### K9 Brain — Dual-Hemisphere Cognitive Architecture
- **Left hemisphere:** Technical analysis, pattern recognition, quantitative signals
- **Right hemisphere:** Macro regime detection, sentiment analysis, market intelligence
- **PUP (Probabilistic Uncertainty Principle):** Confidence quantification — trades only fire on high-certainty convergence
- **Rationale Engine:** Every signal generates a plain-English explanation of WHY

#### Multi-Symbol Orchestration
- Concurrent GOLD, BTC, OIL, EUR analysis with per-symbol risk budgets
- Session-aware scheduling (Asian/London/New York)
- MarketIntelligence: VIX, Fear-Greed Index, DXY correlation tracking
- IntelligentSizer: Half-Kelly criterion position sizing with regime adjustment

#### Risk Management Evolution
- Daily loss halt (protects capital automatically)
- Shadow position adoption (picks up orphaned trades)
- Per-symbol exposure limits with portfolio-level correlation checks
- Drawdown circuit breaker

#### Infrastructure
- Bridge protocol fixes, GOLD/OIL symbol mapping
- IOC filling mode for execution
- Webhook DB server with tick persistence
- Linux daemon with systemd management (cthulu-daemon)
- Oversight system: 15-minute autonomous health reports

#### Architecture Philosophy
> "Alive vs artificial — live systems need the ENTIRE system to work or face death. Artificial is modular. Cthulu is designed alive."

The tentacle architecture is biomimetic. K1-K8 are sensory tentacles that read the market across timeframes. K9 is the brain that synthesizes all signals into a single decision. No tentacle acts alone. No trade fires without K9 consensus.

---

## [1.0.0] - 2026-01-09

### Initial Release - Clean Rule-Based Implementation

#### Core Features
- **Signal Engine**: Multi-strategy signal generation with proper SMA/EMA calculations
- **Dynamic SLTP**: ATR-based with initial, breakeven, and trailing modes
- **Strategy Selector**: Regime-aware strategy selection (7 strategies)
- **Entry Confluence**: S/R, momentum, timing, and structure scoring
- **Risk Management**: Position sizing, exposure limits, drawdown protection

#### Strategies
- SMA Crossover (10/30) with continuation signals
- EMA Crossover (12/26) with continuation signals  
- Momentum Breakout with RSI confirmation
- Scalping with fast EMA and RSI extremes
- Mean Reversion with Bollinger Bands
- Trend Following with ADX filter
- RSI Reversal at extreme levels

#### Position Management
- Trade adoption for external positions
- Automatic SL/TP application on adoption
- Position lifecycle tracking
- Magic number management

#### Exit Strategies
- Dynamic trailing stop with protective mode
- Partial profit taking at levels
- Time-based exit (24h max hold, weekend close)

#### Infrastructure
- MT5 connector with retry logic
- SQLite persistence layer
- Data layer with caching
- Liquidity/spread filters
- Trade monitoring

### Technical Notes
- Built from windows-ml branch as foundation
- Removed all ML/AI components for pure rule-based operation
- Clean separation of concerns across modules
- Proper symbol propagation (no more "UNKNOWN")
- ATR-based calculations throughout
