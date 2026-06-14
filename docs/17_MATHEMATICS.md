---
title: MATHEMATICS
description: "Mathematical foundations for Cthulu: risk, sizing, BOS/ChoCH detection, multi-RRR exits and performance optimization."
tags: [mathematics, risk-management, position-sizing, exit-strategies]
sidebar_position: 17
version: 6.0.0
---

![](https://img.shields.io/badge/Version-2.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white)

# MATHEMATICS

This document records the mathematical foundations and practical formulas used by Cthulu for position sizing, risk management, entry confluence, BOS/ChoCH detection, profit-scaling / multi-RRR exits and their performance implications. 

## 1. Notation & Units
- P: current market price
- SL: stop-loss price
- TP: take-profit price
- Q: trade quantity (lots)
- R: risk per trade in account currency
- B: account balance/equity
- r: fractional risk per trade (r = R / B)
- pip_value: value per pip for the instrument
- ATR(N): Average True Range over N bars
- σ: volatility estimate (e.g., ATR or realized volatility)
- k: Kelly fraction (optional)

All monetary math assumes consistent base currency; convert where necessary.

## 2. Position Sizing & Risk
Goal: select Q such that the maximum loss if SL is hit equals target risk R.

1) Distance to SL (in price units):

    d = abs(P - SL)

2) Risk per unit of quantity (account currency per lot):

    risk_per_lot = d * pip_value

3) Quantity (lots):

    Q = R / risk_per_lot = (r * B) / (d * pip_value)

Edge cases & guards:
- Minimum tick/volume increments must be respected.
- Round Q down to allowed step sizes.
- If Q < Q_min set Q = 0 (trade rejected).
- If d is near zero use fallback (reject or widen SL).

Volatility scaling (adaptive sizing):

    target_distance = α * ATR(N)   (α e.g., 0.6.0.0)
    enforce SL distance >= min_tick * factor

Where ATR(N) = EMA(TrueRange, N)

Kelly-derived approach (aggressive):

    k = (W * (avg_win/avg_loss) - (1 - W)) / (avg_win/avg_loss)
    fraction = max(0, f * k)  (f conservative fraction e.g., 0.25)

But Kelly is volatile; prefer fixed fractional risk with caps.

## 3. Risk Manager Unified Design (math summary)
Unify both risk implementations under a single API:
- Inputs: proposals (signal_id, suggested Q, suggested SL, suggested TP, confidence)
- Policy checks:
  - Max open positions constraint (global and instrument-level).
  - Exposure cap: sum(|notional|) <= exposure_limit.
  - Correlation adjustment: scale risk when correlated positions present.
  - Drawdown-based scaling: reduce r when drawdown > threshold.

Mathematically:

    allowed_r = base_r * drawdown_factor * correlation_factor

Where drawdown_factor ∈ (0,1], correlation_factor ≤ 1.

## 4. Entry Confluence Scoring (signal queue timing)
Confluence score S combines independent evidence sources; compute as weighted normalized sum:

    S = Σ w_i * norm(e_i)

- e_i: evidence metric i (indicator value, pattern strength, liquidity filter, time-of-day multiplier)
- w_i: weight for evidence i (sum to 1)
- norm(): scale evidence to [0,1] using historic percentiles or tanh normalization

To avoid immediate execution before confluence completes, introduce a short confirmation window Δt (number of bars or seconds) and hold signal in a queue. Only execute if S >= threshold_T within confirmation window; otherwise cancel or downgrade.

Dynamic thresholds:

    T = base_T * (1 - conf_modifier * overall_confidence)

Where conf_modifier increases with regime clarity (e.g., ADX) and volatility.

## 5. BOS / ChoCH Detection (break of structure & change of character)
Purpose: detect structural market shifts to confirm higher-probability entries.

Basic algorithm (discrete-time):
1. Identify swing highs/lows using pivot detection (sensitivity parameter s)
2. Maintain last N pivots: {p_1..p_n} with timestamps.
3. Break-of-Structure (BOS): new pivot high > previous pivot high (for uptrend) or new pivot low < previous pivot low (for downtrend).

Mathematical check:

    BOS_up = (pivot_high_new > max(pivot_high_history))
    BOS_down = (pivot_low_new < min(pivot_low_history))

Change-of-Character (ChoCH): transition where structure direction flips; detected when price closes beyond a pivot in opposite direction and subsequent price action fails to confirm. Use a confirmation candle count m.

Scoring: give BOS/ChoCH high weight in confluence S (e.g., w_BOS = 0.30).

Parameters to expose:
- pivot_lookback (bars)
- min_pivot_distance (pips) to avoid noise
- confirmation_candles m

## 6. Multi-RRR Exit Structure (replace simple scaling)
Goal: deploy staggered TPs that capture different RRRs.

Example config: RRR targets = [1.0, 2.0, 4.0] with fractions [0.4, 0.35, 0.25] of initial Q.

For each TP_i:

    TP_price_i = entry_price ± RRR_i * d   (sign depends on long/short)
    close Q_i when price reaches TP_price_i

Dynamic management: once first TP fills, optionally move SL to breakeven + buffer; allow remaining legs to scale out or trail.

Profit scaling math (for partial closes):

    Q_remaining := Q_remaining - Q_i
    new_SL := max(old_SL, entry_price + breakeven_buffer)  (for long)

Avoid immediate scale-outs on small moves: require a minimum price move (e.g., 0.5*ATR) before applying partial close.

## 7. Execution, Slippage & Latency Considerations
Model slippage as expected cost per trade s (pips) and add to order price estimation.

Expected PnL per trade (taking slippage into account):

    E[PnL] = W * avg_win - (1-W) * avg_loss - slippage_cost

Where avg_win/loss include slippage and commission.

Include latency multiplier for market orders; for market-if-touched use limit-based execution where feasible.

## 8. Performance Metrics & Backtest Statistics
Compute and track:
- Net profit, CAGR
- Win rate W
- Profit factor = gross_profit / gross_loss
- Expectancy = W * avg_win - (1-W) * avg_loss
- Sharpe ratio (annualized): (mean_return / std_return) * sqrt(252)
- Sortino ratio (downside risk)
- Max drawdown & recovery time
- Calmar ratio

Use walk-forward testing and out-of-sample validation to avoid overfitting.

## 9. Optimization Objective & Parameter Spaces
Define objective(s): maximize risk-adjusted return such as Sharpe or maximize CAGR subject to max_drawdown < threshold.

Parameter examples to optimize:
- ATR multiplier α for SL sizing
- base_r (risk fraction)
- entry_threshold T
- confluence weights w_i
- pivot sensitivity s and confirmation m
- RRR tier values and fractions

Optimization approaches:
- Random search / grid search (fast, parallelizable)
- Bayesian optimization (e.g., Optuna) for efficient scanning
- Evolutionary strategies for discrete complex spaces

Constraints: penalize solutions that violate exposure or produce unrealistic trade counts (regularization).

## 10. Backtesting & Validation Workflow
1. Run backtest with baseline parameters for N years.
2. Compute performance metrics and stability diagnostics (Monte Carlo resampling of returns, slippage sensitivity).
3. Run parameter optimization (constrained) on in-sample period.
4. Validate best parameter set on out-of-sample period (walk-forward).
5. If stable, deploy to paper/live with reduced sizing and monitoring.

Example commands (placeholders):

    python cthulu/backtest.py --config configs/backtest.yaml --from 2018-01-01 --to 2024-01-01
    python cthulu/optimizer.py --space configs/opt_space.yaml --trials 200

## 12. Implementation Checklist (short)
- [ ] Unify risk manager code paths into single risk module API
- [ ] Implement confirmation window for confluence scoring
- [ ] Add BOS/ChoCH detector and expose parameters
- [ ] Replace simple scaling with multi-RRR exit legs and partial close logic
- [ ] Add slippage/latency modeling in order engine
- [ ] Run optimizer and perform walk-forward validation

## 13. References & Further Reading
- Kelly criterion and fractional Kelly
- ATR-based volatility position sizing
- Walk-forward optimization best practices
- HNSW & FlatIndex design notes (Hektor)


---

Appendix: Quick formulas

- Position size: Q = (r * B) / (d * pip_value)
- Distance: d = |P - SL|
- Confluence score: S = Σ w_i * norm(e_i)
- Expectancy: E = W * avg_win - (1-W) * avg_loss


