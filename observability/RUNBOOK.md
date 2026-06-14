# Observability Runbook

Purpose: Document critical metrics, alert thresholds, and step-by-step playbooks to triage and remediate key incidents for Cthulu.

> Location: `cthulu/observability`

---

## Incident Priorities
- P0 — Production trading stopped, severe loss or connectivity outage to MT5.
- P1 — Orders failing at high rate, DB write errors, or missing metrics ingestion.
- P2 — Performance degradations, metric anomalies, non-critical errors.

---

## Critical Metrics & Recommended Alerts
(Use Prometheus expressions and alert rules as guidance)

1. MT5 Connector Health
   - Metric: `mt5_connector_up{instance=~".*"}` (gauge, 1 = up)
   - Alert: `mt5_down` if `mt5_connector_up == 0` for 2m → P0
   - Play: verify network, restart connector, fallback to advisory/dry-run, notify ops.

2. Order Failure Rate
   - Metric: `orders_failed_total` and `orders_submitted_total`
   - Alert: `order_failure_rate_high` if `rate(orders_failed_total[5m]) / rate(orders_submitted_total[5m]) > 0.05` for 5m → P1
   - Play: inspect failures, confirm rejection reasons, pause live execution if > X and notify.

3. Execution Latency
   - Metric: `exec_latency_seconds` (histogram)
   - Alert: `high_execution_latency` if `histogram_quantile(0.95, sum(rate(exec_latency_seconds_bucket[5m])) by (le)) > 1.0`s → P1
   - Play: capture recent traces, check MT5, network, or execution queue backlog.

4. Unexpected Position Changes
   - Metric: `positions_changed_total` by reason/state
   - Alert: `unexpected_position_change` if an out-of-band close or large P&L movement occurs → P0/P1 depending magnitude
   - Play: reconcile DB, check MT5 fills, freeze trading loop if necessary.

5. DB Write Errors & Transaction Failures
   - Metric: `db_write_errors_total`
   - Alert: `db_write_errors` if `increase(db_write_errors_total[5m]) > 0` → P1
   - Play: check DB health, free disk, WAL status, restart DB process or failover.

6. Daily Loss Circuit Breaker
   - Metric: `daily_loss_usd` (derived)
   - Alert: `daily_loss_threshold_exceeded` if `daily_loss_usd > config.daily_loss_threshold` → P0
   - Play: Immediately stop live trading, notify ops, run postmortem.

7. ML Drift Warning (informational)
   - Metric: `model_input_drift_score` (KL-divergence or PSI)
   - Alert: `model_drift_high` if score > configured threshold for 24h → P2
   - Play: snapshot inputs, notify ML team, schedule re-eval.

---

## Example Prometheus Alert (YAML snippet)

```
- alert: mt5_down
  expr: mt5_connector_up == 0
  for: 2m
  labels:
    severity: critical
  annotations:
    summary: "MT5 connector down"
    description: "The MT5 connector has been down for > 2m"
```

---

## Playbooks (short)

P0 (MT5 down / trading stopped):
1. Confirm `mt5_connector_up` and network (ping/connect). Check MT5 broker status.
2. Check connector logs and recent errors.
3. If restart allowed: restart connector process using systemctl/nssm or container restart.
4. If restart fails or repeated, set system to `advisory/dry-run` and escalate to on-call.
5. Communicate on Ops channel (Discord/Slack) with incident note.

P1 (Order failures / DB errors):
1. Inspect `orders_failed_total` with labels; identify cause (reject, insufficient funds, rate-limit).
2. Pause execution if failure persists > threshold.
3. If DB write errors: check disk, WAL, replicas; failover to read-only if needed.
4. Escalate to devs if failures cannot be quickly mitigated.

P2 (Drift / Performance):
1. Collect diagnostics and recent metrics.
2. Notify ML owner and schedule deeper analysis.

---

## Alerting & Escalation (Discord)
- Primary channel: `#ops-cthulu` (read-only for bots). Use direct mention for P0.
- Alert message must include: timestamp, metric, instance, last 5 logs snippet, link to runbook section.
- For P0/P1: open an incident thread and tag the on-call person. Use the `incident` message template.

---

## Runbook Operations (Maintenance tasks)
- Weekly: Verify metrics ingestion pipeline and scrape targets.
- Monthly: Review alert thresholds and false positive rate.
- Quarterly: Run chaos test for MT5 connector in staging (simulate failures and ensure failover).

---

## Notes & Next steps
- Add Prometheus alert rules and basic automation to send to Discord webhooks.
- Consider adding a light-weight automation to convert P0 alerts into incident tickets with required fields (time, impact, owner).

---

*This is a living document — adjust thresholds and steps based on operational experience.*