---
title: QUICK START
description: Get started with Cthulu trading system - installation, configuration, and first trades
tags: [quickstart, installation, setup, getting-started]
sidebar_position: 2
version: 6.0.0
---

![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white) 

### 1. Initial Setup

```bash
# Clone or update repository
git clone https://github.com/amuzetnoM/Cthulu.git
cd Cthulu

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
```

### 2. Configure Credentials

Edit `.env` file:
```bash
# MetaTrader 5 Credentials
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_broker_server

# Trading Configuration
ACCOUNT_CURRENCY=USD
RISK_PER_TRADE=0.02
MAX_DAILY_LOSS=0.05
```

### 3. Run Setup Wizard

Choose one of two wizards:

#### Interactive Wizard (Recommended for beginners)
```bash
python -m Cthulu --wizard
```
Step-by-step prompts for:
- Trading mindset (aggressive/balanced/conservative)
- Symbol and timeframe
- Risk management
- Strategy selection (single or dynamic)
- Technical indicators

#### NLP Wizard (Advanced - describe in natural language)
```bash
python -m Cthulu --wizard-ai
```
Example input:
```
Aggressive GOLD#m on M15 and H1, 2% risk, $100 max loss
```

### 4. Start Trading

```bash
# Dry run (recommended first)
python -m Cthulu --config config.json --dry-run

# Live trading (requires confirmation)
export LIVE_RUN_CONFIRM=1
python -m Cthulu --config config.json
```



### Features
- Auto-refresh every 2 seconds
- Singleton instance (no duplicates)
- Graceful shutdown
- Log file monitoring

---

## Strategy Modes

### Single Strategy Mode
Choose one strategy:
- **SMA Crossover**: Simple moving average crossover (beginner-friendly)
- **EMA Crossover**: Exponential moving average (responsive)
- **Momentum Breakout**: Price momentum detection (aggressive)
- **Scalping**: Quick trades with tight stops (advanced)

### Dynamic Strategy Selection (New!)
System automatically switches between strategies based on:
- Market regime detection
- Strategy performance tracking
- Real-time conditions
- Confidence scores

Example config:
```json
{
  "strategy": {
    "type": "dynamic",
    "dynamic_selection": {
      "regime_detection_enabled": true,
      "performance_tracking_enabled": true,
      "min_confidence_threshold": 0.6
    },
    "strategies": [
      {"type": "sma_crossover", "params": {"fast_period": 10, "slow_period": 30}},
      {"type": "ema_crossover", "params": {"fast_period": 12, "slow_period": 26}},
      {"type": "momentum_breakout", "params": {"lookback_period": 20}},
      {"type": "scalping", "params": {"quick_period": 5, "trend_period": 20}}
    ]
  }
}
```

---

## Technical Indicators

Add indicators to enhance your strategy:

### Available Indicators
1. **RSI** (Relative Strength Index)
   - Momentum oscillator
   - Default: period=14, overbought=70, oversold=30

2. **MACD** (Moving Average Convergence Divergence)
   - Trend following
   - Default: fast=12, slow=26, signal=9

3. **Bollinger Bands**
   - Volatility indicator
   - Default: period=20, std_dev=2.0

4. **Stochastic**
   - Momentum indicator
   - Default: k=14, d=3, smooth=3

5. **ADX** (Average Directional Index)
   - Trend strength
   - Default: period=14

6. **Supertrend** ⭐ NEW in v4.0.0
   - Trend following
   - Default: atr_period=10, multiplier=3.0

7. **VWAP** ⭐ NEW in v4.0.0
   - Volume weighted average price
   - Intraday trading

Example config:
```json
{
  "indicators": [
    {"type": "supertrend", "params": {"atr_period": 10, "atr_multiplier": 3.0}},
    {"type": "rsi", "params": {"period": 14}},
    {"type": "vwap", "params": {}}
  ]
}
```

---

## Mindset Presets

Pre-configured risk profiles:

### Aggressive
- Position size: 5% per trade
- Max positions: 5
- Daily loss limit: $100
- Faster signals, tighter stops

### Balanced (Recommended)
- Position size: 2% per trade
- Max positions: 3
- Daily loss limit: $50
- Moderate risk/reward

### Conservative
- Position size: 1% per trade
- Max positions: 2
- Daily loss limit: $25
- Wider stops, stricter filters

Apply via CLI:
```bash
python -m Cthulu --config config.json --mindset aggressive
```

Or during wizard setup.

---

## 🔧 Command Line Options

```bash
# Basic
python -m Cthulu --config config.json                    # Start with config

# Wizard
python -m Cthulu --wizard                                 # Interactive setup
python -m Cthulu --wizard-ai                             # NLP-based setup
python -m Cthulu --config config.json --skip-setup       # Skip wizard

# Trading Modes
python -m Cthulu --config config.json --dry-run          # Simulate trades
python -m Cthulu --config config.json --adopt-only       # Only manage existing trades

# Customization
python -m Cthulu --config config.json --mindset aggressive
python -m Cthulu --config config.json --symbol GOLD#m
python -m Cthulu --config config.json --enable-ml        # Enable ML features

# RPC Server
python -m Cthulu --config config.json --enable-rpc       # Enable RPC for GUI
```

---

## Troubleshooting

### MT5 Not Connecting
1. Check `.env` file has correct credentials
2. Verify MT5 terminal is installed and running
3. Check config uses FROM_ENV:
   ```json
   "mt5": {
     "password": "FROM_ENV",
     "server": "FROM_ENV"
   }
   ```

### GUI Issues
- **Dark mode broken**: Update to latest version (fixed)
- **Multiple GUIs**: Update to latest version (singleton pattern added)
- **Can't launch**: Check `logs/gui_stderr.log` for errors

### Configuration Issues
- Run wizard: `python -m Cthulu --wizard`
- Check example: `config.example.json`
- See documentation: `UPGRADE_FIXES.md`

---

## 📚 Additional Resources

- **Full Documentation**: `UPGRADE_GUIDE.md`
- **Fix Details**: `UPGRADE_FIXES.md`
- **Release Notes**: `release_notes/v4.0.0.md`
- **Implementation**: `IMPLEMENTATION_SUMMARY.md`

---


## 💡 Tips

1. **Start with dry-run**: Test your config without risking capital
2. **Use balanced mindset**: Good for most traders
3. **Monitor GUI**: Keep eye on active strategy and regime
4. **Review logs**: Check `Cthulu.log` for detailed activity
5. **Adjust gradually**: Small changes, measure impact

---

## 🆘 Support

- Issues: https://github.com/amuzetnoM/Cthulu/issues
- Discussions: https://github.com/amuzetnoM/Cthulu/discussions

Happy Trading!




