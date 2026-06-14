## Trading Metrics
> Operational Guide

Purpose
- Provide a compact, production-grade reference for metrics, collection, alerting, visualization, and remediation for the Cthulu trading system.
- Goals: actionable alerts, reproducible collection, clear ownership, and data for continuous tuning.

Principles (always)
- Actionable: every alert has a clear owner and remediation step.
- Automated: metric collection and reporting are automated end-to-end.
- Surgical: metrics are precise (definition, collection point, frequency, threshold).
- Versioned & Testable: schema and alert rules are checked into repo and exercised in staging.

Metric taxonomy (high level)
1. Real-time Health & Process
2. Signals & Acceptance
3. Orders & Execution
4. Trade Performance & Risk
5. Errors & Observability

For each metric use this compact template: Definition • Collection point • Frequency • Alert • Recommended action

1) Real-time Health & Process
- Process Alive
  - Definition: PID present and responsive (heartbeat ≤ poll_interval).
  - Collection: process heartbeat metric and system process poll every 30s.
  - Alert: missing > 30s → pager.
  - Action: restart process, inspect logs, escalate if restart loops.
- MT5 Connectivity
  - Definition: connector.get_account_info() OK and trade_allowed==True.
  - Collection: check each loop.
  - Alert: >3 consecutive failures → pager.
  - Action: failover connector, network check, restart adapter.
- Loop Cycle Time
  - Definition: iteration duration (start→end).
  - Collection: log at INFO and expose histogram.
  - Alert: p95 > 2× poll_interval for >3 cycles → alert.
  - Action: profile loop work, backpressure nonessential tasks.

2) Signals & Acceptance
- Signals Generated (sg_total)
  - Definition: count of strategy signals (labels: strategy, symbol, side).
  - Collection: emitted at signal generation (INFO + metric increment).
  - Frequency: realtime.
  - Why: baseline for activity; too low/too high → tuning.
- Signals Accepted (sa_total); Acceptance Rate = SA/SG
  - Definition: signals approved by RiskEvaluator.
  - Collection: increment at approve with position_size label.
  - Alert: Acceptance rate < 0.05 or > 0.5 sustained → investigate.
  - Action: review risk parameters, balance constraints, or strategy threshold.

3) Orders & Execution
- Orders Placed (orders_total)
  - Definition: market orders sent (labels: reason, symbol, strategy).
  - Collection: on execution_engine.place_order return; persist order_id.
  - Why: verifies end-to-end execution.
- Execution Latency (order_latency_seconds)
  - Definition: time from OrderRequest to MT5 ack.
  - Collection: histogram; report p50/p95/p99.
  - Alert: p95 > 0.5s → investigate network/MT5/CPU.
  - Action: retry logic, batching, failover to alternate endpoint.
- Slippage (slippage_ticks, slippage_value)
  - Definition: executed_price - requested_price normalized to ticks.
  - Collection: record per order and aggregate.
  - Alert: avg slippage > symbol tolerance or sudden spike.
  - Action: switch to limit orders, reduce size, change venue.

4) Trade Performance & Risk
- Win Rate & PnL (trade_pnl)
  - Definition: net P&L per trade/day/strategy/symbol, with sample size.
  - Collection: persisted on trade close; produce rolling 1h/24h/7d.
  - Use: compute expectancy, Sharpe-like stats, Sortino.
- MAE / MFE
  - Definition: worst/best excursion while trade open.
  - Collection: PositionTracker samples while open.
  - Use: calibrate stops and take-profit.
- Average Trade Duration
  - Definition: entry→exit; distribution informs poll frequency.
- Fill Rate / Rejects
  - Definition: fraction of orders rejected or partially filled.
  - Alert: sudden drop in fill rate or increase in rejects.

5) Errors & Observability
- Error Rate & Unique Stack Traces
  - Definition: ERROR events and distinct traces in rolling windows (1/5/60 min).
  - Collection: log tail or structured logging pipeline.
  - Alert: any ERROR with traceback in last 5 minutes → pager; >1 error/min sustained → page.
  - Action: capture full trace, link to loop number, create incident.

Data Sources & Storage
- Primary: logs (Cthulu.log), Signals DB, Orders/Trades DB, PositionTracker snapshots, MT5 connector responses.
- Storage schema (minimum)
  - signals(id, ts, strategy, symbol, side, confidence, accepted)
  - orders(id, signal_id, ts_request, ts_ack, request_price, execution_price, volume, status, latency_ms)
  - trades(id, order_id, entry_ts, exit_ts, entry_price, exit_price, pnl, mae, mfe)
- Time-series: export to Prometheus (preferred) or CSV / Influx as fallback.

Collection & Aggregation
- Recommended: python prometheus_client + lightweight collector reading logs & DB every minute; expose metrics on /metrics.
- Logging: structured JSON logs with fields (ts, level, loop_id, component).
- Batch: aggregate hourly and persist to long-term store for backtesting and A/B analysis.

Suggested metric names & labels (examples)
- cthulu_process_alive{host, component}
- cthulu_signal_generated_total{strategy,symbol,side}
- cthulu_signals_accepted_total{strategy}
- cthulu_order_placed_total{strategy,symbol,status}
- cthulu_order_latency_seconds (histogram)
- cthulu_slippage_ticks (histogram)
- cthulu_trade_pnl{strategy,symbol}
- cthulu_error_counter{component,trace_hash}

Thresholds & Alerting (defaults; tune per strategy/symbol)
- Connectivity: MT5 disconnects >3 attempts → pager
- Errors: any exception trace in 5 minutes → pager
- Acceptance rate: SA/SG < 0.05 or > 0.5 → investigate
- Latency: p95 > 500 ms → alert
- Slippage: avg > configured tolerance per-symbol → alert
- Drawdown: cumulative daily loss > max_daily_loss → emergency shutdown

Dashboards (must-have panels)
- System Health: process, loop latency, MT5 connectivity, last signal/order timestamps
- Signal Funnel: SG → SA → OP → Filled/Rejected with rates & counts
- Execution: latency percentiles, slippage distribution, fill rate
- P&L & Risk: rolling PnL, avg trade PnL, win rate, MAE/MFE histograms, exposure by symbol
- Incident timeline: errors with link to logs and loop_id

Tuning & Remediation (mapping metrics → actions)
- Low SG: lower signal thresholds, shorten lookback, enable test-mode strategies.
- Low SA/SG: review risk limits, balance, or overly strict rules.
- High Latency/Slippage: investigate network, execution engine, batch sizes; consider limit orders.
- Large MAE: increase stop distance or reduce position size; use scaling exits if MFE >> TP.

Experimentation & Continuous Validation
- A/B tests: parallel instances with parameter variants; compare SG/SA/OP/PnL windows with statistical tests.
- Shadow mode: dry_run=True to gather signals and executions without risk.
- Golden-run: require 1h+ runtime with no uncaught exceptions and stable core metrics before promoting to production.

Automated SYSTEM_REPORT checklist (included in SYSTEM_REPORT.md)
- Process Alive timestamp
- Last Signal Generated ts
- Last Order Placed ts
- Rolling 1h stats: SG, SA, OP, WinRate, AvgPnL, p95 Latency, AvgSlippage
- Top-3 errors last 24h with links

Implementation notes (quick)
- Emit metrics at source (signal generator, risk manager, execution engine).
- Store events in DB with unique ids to correlate signal→order→trade.
- Use histogram buckets for latency/slippage and export percentiles in dashboards.
- Keep alert rules in repo (Terraform/Prometheus rules) and test them in staging.

Ownership & Runbooks
- Each alert has an owner and a short runbook (one-liner + required logs/queries).
- Maintain a “playbook” for emergency shutdown and restart procedures.

Appendix: minimal Prometheus labels to include
- host, region, instance, strategy, symbol, side, loop_id

This document is intentionally executable: convert these templates into code + alert rules, commit to CI, and validate with synthetic runs before enabling production alerts.