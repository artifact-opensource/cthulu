---
title: INTRODUCTION
description: Current overview of Cthulu's Windows runtime, execution modes, trading modes, and safety controls
tags: [trading, mt5, execution-modes, risk-management]
sidebar_position: 1
---

# Introduction

Cthulu is an automated trading system for MetaTrader 5. The Windows launcher has **two independent choices**:

1. **Execution mode:** Agentic or Legacy.
2. **Trading mode:** Single, Multi, or HFT.

HFT is not a third execution mode. It is selected after Agentic or Legacy, so an operator can run Agentic HFT or Legacy HFT.

> **Trading risk:** Automated trading can lose money. The first-run wizard enables the Agent's live confirmation flag. Review [the Quick Start safety notes](02_QUICKSTART.md#3-enter-account-risk-and-optional-agent-settings) before launching on a real account.

## Execution modes

| Choice | Behavior |
|---|---|
| **Agentic** | Runs the Legacy engine and the Agent runtime together. The Legacy strategy continues under its own risk checks; the Agent can also place or manage orders under separate deterministic risk checks. |
| **Legacy** | The Legacy engine owns trading. The Agent dashboard runtime still starts, but Agent order placement and management are blocked. |

The Agent may manage broker positions beyond those it opened, including positions opened by the Legacy engine or another tool. Use one Legacy loop per account and review `AGENT_MANAGE_FOREIGN` before startup.

## Trading modes

| Choice | Configuration | Behavior |
|---|---|---|
| **Single** | `config.json` | Runs the standard single-symbol configuration. |
| **Multi** | `config_multi.json` | Runs the multi-symbol configuration; the launcher selects the configured ultra-aggressive Legacy mindset. |
| **HFT** | `config.json` | Uses M1 data and broker-universe scanning after an HFT safety preflight. |

Current HFT preflight requires a real MT5 account with trading enabled, tradable symbols, stop protection on existing positions and orders, no more than 10 active orders, and calculated aggregate stop risk at or below 5%. The preflight rejects demo accounts. The HFT Agent profile caps risk at 1% per entry, 5% aggregate open risk, and 10 active orders; configured limits may be stricter. Configured daily-loss and drawdown halts remain active.

## Startup and dashboard

For normal Windows use, complete the [first-run setup](02_QUICKSTART.md) and start `Cthulu Launcher.bat`. It presents the execution-mode menu first, followed by the trading-mode menu. The MSI installs **Cthulu Setup** and **Cthulu Launcher** shortcuts; the repository launcher is intended for use after first-run setup.

Each normal mode starts the Agent dashboard runtime. The Agent supervisor retries the Agent process after an unexpected exit, but does not supervise or restart the Legacy engine. A dashboard restart can briefly disconnect the browser. The Settings page provides **Kill and stay down** and **Restart services** controls.

The kill switch persistently stops Cthulu services; it does not close positions or cancel pending orders at the broker, delete logs, clear databases, or reset daily-loss history. Inspect open orders in MT5 and use the explicit launcher flow to resume.

## First-run configuration and live trading

The setup wizard requires an MT5 account number, password, and broker server. It writes `config.json`, `config_multi.json`, `.env`, and `cthulu_agent\.env.agent`, and does not start Cthulu.

Default risk values are 0.5% maximum risk per trade, 2% daily-loss stop, 10% drawdown halt, and 3 maximum simultaneous positions. Daily-loss and drawdown values of `0` disable the corresponding stop.

The optional Agent LLM integration uses Cloudflare AI Gateway. The default model is `@cf/qwen/qwen3-30b-a3b-fp8`; the account ID, gateway ID, API token, model, and optional base URL are entered in the wizard or Agent Settings.

The wizard writes `LIVE_RUN_CONFIRM=1` into the Agent environment. Agent autonomy defaults to `autonomous`; therefore, a later Agentic launch can place live orders without a separate per-order confirmation. Use a demo account for Single/Multi testing and change the autonomy/confirmation settings if autonomous live order placement is not intended. Current HFT preflight requires a real account.

## Further reading

- [Quick Start](02_QUICKSTART.md) — installation, setup, launch, HFT preflight, and troubleshooting
- [Root README](../readme.md) — project overview and Windows operator instructions
- [Agent guide](../cthulu_agent/README.md) — Agent controls, provider setup, risk checks, and dashboard access
- [Risk management](07_RISK.md)
- [Deployment](09_DEPLOYMENT.md)
- [Architecture overview](../OVERVIEW.md)
- [System map guide](../tools/SYSTEM_MAP_GUIDE.md)
