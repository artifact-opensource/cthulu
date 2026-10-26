# Cthulu ML/RL Data System Map

**Version:** 6.0.0  
**Last Updated:** 2026-01-17  
**Total Data Storage:** ~21.5 MB (excluding venv)

---

## 📊 Data Endpoints Overview

### 1. Primary Databases

| Database | Path | Size | Purpose |
|----------|------|------|---------|
| `cthulu.db` | `./cthulu.db` | 0.93 MB | Main trade/signal SQLite database |
| `cthulu_ultra_aggressive.db` | `./Cthulu_ultra_aggressive.db` | 14.23 MB | Ultra-aggressive strategy database |
| `cthulu_aggressive.db` | `./cthulu_aggressive.db` | 0.09 MB | Aggressive strategy database |
| `cthulu_balanced.db` | `./cthulu_balanced.db` | 0.10 MB | Balanced strategy database |
| `cthulu_conservative.db` | `./cthulu_conservative.db` | 0.10 MB | Conservative strategy database |
| `herald.db` | `./data/herald.db` | 0.04 MB | Herald messaging database |
| `temp_prov.db` | `./temp_prov.db` | 0.09 MB | Temporary provenance tracking |

### 2. Vector Databases

| Database | Path | Size | Purpose |
|----------|------|------|---------|
| `cthulu_memory` | `./vectors/cthulu_memory/` | ~0.9 MB | Vector Studio semantic search |
| `vector_fallback.db` | `./data/vector_fallback.db` | 0.02 MB | Fallback vector storage |
| `handbook_fallback.db` | `./vectors/mql5_handbook/handbook_fallback.db` | 0.89 MB | MQL5 handbook vectors |

---

## 📁 Data Directories

### ML_RL Data (`ML_RL/data/`)
**Total: 654 files, 2.52 MB**

| Subdirectory | Files | Size | Description |
|--------------|-------|------|-------------|
| `raw/` | 184 | 0.79 MB | JSONL.gz event logs (orders, executions, snapshots) |
| `training/` | 469 | 1.73 MB | Training data and test event logs |
| `tier_optimizer/` | 1 | 0.01 MB | Tier optimizer state (`optimizer_state.json`) |
| `metrics/` | 0 | 0 MB | Performance metrics (empty) |
| `models/` | - | - | Trained model artifacts |

### Cognition Data (`cognition/data/`)
**Total: 385 files, 1.44 MB**

| Subdirectory | Files | Size | Description |
|--------------|-------|------|-------------|
| `raw/` | 385 | 1.44 MB | Decision logs (JSONL.gz) |
| `models/` | 0 | 0 MB | Cognition model artifacts |
| `tier_optimizer/` | 0 | 0 MB | Legacy tier optimizer state |

### Other Data Directories

| Directory | Files | Size | Description |
|-----------|-------|------|-------------|
| `news/cache/` | 1 | <0.01 MB | News API cache (`news_manager.json`) |
| `vectors/` | 2 | 0.9 MB | Vector database files |
| `data/` | 8 | 0.14 MB | Misc data (drawings, herald DB) |
| `backtesting/reports/` | 18 | 0.04 MB | Backtest result reports |

---

## 🔄 Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CTHULU DATA FLOW                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐           │
│  │  MT5/Market │────►│  Trading Loop   │────►│  Execution      │           │
│  │    Data     │     │  (core/)        │     │  Engine         │           │
│  └─────────────┘     └────────┬────────┘     └────────┬────────┘           │
│                               │                       │                     │
│                               ▼                       ▼                     │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      DATA LAYER (integrations/data_layer.py)        │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │   SQLite     │  │ Vector Studio│  │  ML Instrumentation      │  │   │
│  │  │  (cthulu.db) │  │ (vectors/)   │  │  (ML_RL/data/raw/)       │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      COGNITION ENGINE                                │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │  Training    │  │    Tier      │  │  Decision Logs           │  │   │
│  │  │   Logger     │  │  Optimizer   │  │  (cognition/data/raw/)   │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                         ML PIPELINE                                  │   │
│  ├─────────────────────────────────────────────────────────────────────┤   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│  │  │  MLOps       │  │   RL Sizer   │  │  Feature Pipeline        │  │   │
│  │  │  Registry    │  │   Models     │  │  Normalization           │  │   │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📝 Data Writers & Collectors

### 1. MLDataCollector (`ML_RL/instrumentation.py`)
- **Output:** `ML_RL/data/raw/events.{timestamp}.jsonl.gz`
- **Rotation:** 10MB per file
- **Events:** `order_request`, `execution`, `market_snapshot`
- **Mode:** Non-blocking background writer thread

### 2. CognitionInstrumentation (`cognition/instrumentation.py`)
- **Output:** `cognition/data/raw/events.{timestamp}.jsonl.gz`
- **Rotation:** 10MB per file
- **Events:** Decision logs, signal evaluations
- **Mode:** Non-blocking background writer thread

### 3. TrainingLogger (`cognition/training_logger.py`)
- **Output:** `cognition/data/decisions_{session}.jsonl[.gz]`
- **Format:** JSONL (optionally gzipped)
- **Content:** Full decision records for ML training

### 4. TierOptimizer State
- **ML_RL:** `ML_RL/data/tier_optimizer/optimizer_state.json`
- **Cognition:** `cognition/data/tier_optimizer/optimizer_state.json`

### 5. Model Artifacts
- **Feature Pipeline:** `ML_RL/data/models/feature_pipeline.json`
- **Price Predictor:** `ML_RL/data/models/price_predictor.json`
- **RL Sizer:** `ML_RL/models/rl/rl_sizer.json`
- **MLOps Registry:** `ML_RL/models/registry/registry.json`

### 6. SQLite Database (`persistence/database.py`)
- **Tables:** trades, signals, metrics, positions
- **Connection:** WAL mode, 30s timeout
- **Concurrent access:** Supported via WAL

### 7. Vector Studio (`integrations/vector_studio.py`)
- **Output:** `./vectors/cthulu_memory/`
- **Mode:** Async writes with fallback
- **Content:** Semantic embeddings for trades/signals

### 8. News Cache (`news/cache.py`)
- **Output:** `news/cache/news_manager.json`
- **TTL:** 300 seconds default
- **Content:** Cached API responses

---

## 🔗 Configuration Paths

| Config | Path | Description |
|--------|------|-------------|
| Main Config | `config.json` | Primary system configuration |
| Example Config | `config.example.json` | Template configuration |
| Symbols | `config/symbols.json` | Trading symbols configuration |
| Indicators | `monitoring/indicator_config.json` | Indicator monitoring config |
| Auto-tune | `configs/auto_tune/*.json` | Auto-tune parameter sets |

---

## 📊 Data Consolidation Analysis

### Current State
- **Duplication:** ML_RL and cognition both have separate event logging
- **Redundancy:** Two tier optimizer states exist
- **Fragmentation:** Raw events split across directories

### Consolidation Opportunities

| Current | Consolidated | Benefit |
|---------|--------------|---------|
| `ML_RL/data/raw/` + `cognition/data/raw/` | Single `data/events/` | Unified event stream |
| 2x tier optimizer states | Single state in ML_RL | No divergence |
| Multiple strategy DBs | Single DB with strategy tags | Easier querying |

### Do NOT Consolidate
- **SQLite DB** - Keep separate for strategy isolation
- **Vector DB** - Different semantic spaces
- **Model artifacts** - Version-controlled separately

---

## 🛠️ CLI Commands Reference

```bash
# Data storage CLI (to be implemented)
python -m cthulu data status          # Show storage usage
python -m cthulu data cleanup         # Remove old event logs
python -m cthulu data export          # Export data for training
python -m cthulu data health          # Check all endpoints

# Existing database commands
python scripts/db_health_check.py --db cthulu.db
python scripts/purge_provenance.py --db cthulu.db --days 30
python scripts/query_provenance.py --db cthulu.db
```

---

## 📈 Health Check Endpoints

| Endpoint | Check | Status |
|----------|-------|--------|
| `cthulu.db` | Write test | ✅ |
| `ML_RL/data/raw/` | Directory writable | ✅ |
| `cognition/data/raw/` | Directory writable | ✅ |
| `vectors/cthulu_memory/` | DB accessible | ✅ |
| `news/cache/` | Cache readable | ✅ |

---

## 📦 Backup Recommendations

### High Priority (Daily)
- `cthulu.db` - Main trade database
- `ML_RL/data/tier_optimizer/optimizer_state.json`
- `config.json`

### Medium Priority (Weekly)
- `ML_RL/data/models/` - Trained models
- `vectors/` - Vector embeddings
- `cognition/data/raw/` - Decision logs

### Low Priority (Monthly)
- `ML_RL/data/raw/` - Event logs (can regenerate)
- `backtesting/reports/` - Report archive

---

**Last audit:** 2026-01-17T12:00:00Z
