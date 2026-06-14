# Cthulhu Backtester (Web Dashboard)

![Version](https://img.shields.io/badge/Version-3.3_APEX-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
![Status](https://img.shields.io/badge/Status-Live_Prototype-10b981?style=for-the-badge&labelColor=0D1117)
![AI](https://img.shields.io/badge/Powered_By-Gemini_2.5-4285F4?style=for-the-badge&labelColor=0D1117&logo=google&logoColor=white)

> The official web-based simulation engine and dashboard for the Cthulhu Algorithmic Trading Framework.

---

## 1. System Overview

This application serves as the **frontend interface** and **client-side simulator** for the Cthulhu Trading System. It allows quantitative traders to:
1.  **Ingest Data**: Upload CSV files containing OHLCV market data.
2.  **Configure Strategies**: Set parameters for Moving Average Crossover, Capital, Risk, and Execution settings.
3.  **Run Simulations**: Execute backtests locally in the browser using a high-performance TypeScript engine.
4.  **Optimize Parameters**: Perform grid-search optimization to find the best performing Moving Average periods.
5.  **AI Analysis**: Generate institutional-grade performance reports using **Google Gemini 2.5 Flash**.
6.  **Broadcast Signals**: Relay generated trade signals to external execution engines (MT5) via Webhooks.

---

## 2. Web Application Features

### ⚡ Core Simulation Engine
-   **Client-Side Execution**: Runs entirely in the browser (Zero-Latency).
-   **Vectorized-like Performance**: Capable of processing thousands of candles in milliseconds (FAST mode).
-   **Execution Modeling**: Simulates Commission and Slippage to provide realistic Net PnL.

### 🧠 Advanced Strategy Modules
-   **Ensemble Logic**: Implements a **Consensus Voting System** running three parallel strategies (Core, Fast, Slow). Trades are taken only when the weighted vote confidence exceeds a user-defined threshold.
-   **ML / Risk Filter**:
    -   **Regime Detection**: Uses RSI and Relative Volume to identify favorable market conditions.
    -   **Dynamic Slippage**: Models liquidity by adjusting slippage based on volume (High Vol = Low Slippage).
    -   **Selection Policies**: Supports `ARGMAX` (Greedy) or `SOFTMAX` (Probabilistic) trade selection.

### 📡 Live Operations (MT5 Bridge)
-   **Webhook Relay**: Capability to broadcast specific trade signals to a configurable HTTP endpoint.
-   **Integration**: Designed to connect with MetaTrader 5 (via Python Bridge) or other execution servers.

### 🤖 AI Analyst (Gemini Integration)
-   **Generative Reporting**: Converts raw backtest metrics into a rich, styled HTML report.
-   **Scoring System**: Automatically grades strategies (A+ to F) based on Sharpe Ratio and Risk-Adjusted Returns.
-   **Tactical Feedback**: Provides specific, actionable recommendations to improve strategy parameters.
-   **Tech**: Powered by `@google/genai` using the `gemini-2.5-flash` model for high-speed inference.

### 🛠 Parameter Optimization
-   **Grid Search**: Automatically iterates through ranges of parameters.
    -   *Fast MA*: Start, End, Step.
    -   *Slow MA*: Start, End, Step.
-   **Objective Function**: Optimizes for **Profit Factor** (Gross Profit / Gross Loss).
-   **Safety Mechanisms**: Iteration capping (max 5000) to prevent browser UI freezing.

### 📊 Visualization & Metrics
-   **Cinematic Dashboard**: Full-width, dark-mode UI designed for high-resolution displays.
-   **Interactive Chart (D3.js)**:
    -   Dual-axis plotting (Price vs Equity).
    -   Trade Markers (Green = Buy, Red = Sell).
    -   Hover tooltips for trade details.
-   **Key Performance Indicators**:
    -   Sharpe Ratio, Max Drawdown, Win Rate, Profit Factor.

---

## 3. Configuration & Setup

### Environment Variables
To enable the AI features, you must provide your Google Gemini API Key via environment variables.
The app expects: `process.env['API_KEY']`.

### Webhook Configuration
To use the "Broadcast" feature:
1.  Go to the **Execution** tab.
2.  Select **Data Source: MT5 Webhook Relay**.
3.  Check **Enable Outbound Signals**.
4.  Enter the URL of your local execution server (e.g., `http://localhost:8080/signal`).

### Data Source
The application accepts CSV files. Ensure your data follows this schema:
```csv
Date,Open,High,Low,Close,Volume
2023-01-01 00:00,1.0500,1.0550,1.0490,1.0520,1000
2023-01-01 01:00,1.0520,1.0560,1.0510,1.0540,1500
...
```
*Note: The parser supports various date formats (ISO8601, etc).*

---

## 4. Tech Stack

-   **Framework**: Angular 21+ (Zoneless, Signals)
-   **Language**: TypeScript 5.2+
-   **Styling**: Tailwind CSS (Dark Mode optimized)
-   **Charts**: D3.js v7
-   **AI SDK**: `@google/genai`

---

*Cthulhu Backtester Web Dashboard - v3.3*