---
title: QUICK START
description: Current Windows installation, first-run setup, and launcher choices for Cthulu
tags: [quickstart, installation, setup, getting-started]
sidebar_position: 2
---

# Quick Start

This guide covers the current Windows setup and launcher flow. For a concise project overview, see the [root README](../readme.md).

## 1. Install prerequisites

- Windows and a MetaTrader 5 terminal installed separately.
- An MT5 demo account for normal initial testing. HFT is an exception: its current preflight requires a real MT5 account.
- Internet access for the installer/setup wizard to bootstrap Python or install dependencies.

Python 3.10 or later is required. The first-run wizard attempts to install Python 3.12 through `winget` if needed. If `winget` is unavailable, install Python manually and rerun setup.

## 2. Run first-run setup

### From the MSI

Double-click `Cthulu-Setup.msi`. On the Finish page, leave **Open Cthulu first-run setup** selected. If you skip it, open **Cthulu Setup** from the Start Menu. The MSI also creates a **Cthulu Launcher** Start Menu shortcut and desktop shortcut.

### From a source checkout

Run this from the repository root; the wizard can bootstrap Python, create `.venv`, and install the project requirements:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\installer\cthulu_first_run_setup.ps1
```

The batch launcher is not the first-run credential wizard. `Cthulu Launcher.bat` checks/installs dependencies and opens the menus, but requires the first-run configuration files to exist. Running `scripts\setup.ps1` alone does not collect the account details or create those files.

### Build an MSI from source

With the .NET 8 SDK installed, run:

```powershell
.\installer\Build-Msi.ps1
```

The result is `installer\dist\Cthulu-Setup.msi`. The build excludes local credentials, runtime configs, databases, logs, tests, and the nested `resource_aggregator` repository.

## 3. Enter account, risk, and optional Agent settings

The wizard requires an MT5 account number, password, and broker server. The terminal executable path is optional. Install and log in to the MT5 terminal separately.

The default risk values are percentages of account equity:

| Setting | Default |
|---|---:|
| Maximum risk per trade | 0.5% |
| Daily-loss stop | 2% |
| Drawdown halt | 10% |
| Maximum simultaneous positions | 3 |

Daily-loss and drawdown values of `0` disable their respective stop. Review these limits before starting any mode.

The Agent LLM overlay is optional. To configure it during setup, enable the Cloudflare AI Gateway option and enter:

- Cloudflare account ID
- AI Gateway ID (default: `default`)
- Cloudflare API token
- Model (default: `@cf/qwen/qwen3-30b-a3b-fp8`)
- Optional base URL override (leave blank to use the account default)

The wizard stores Legacy settings in `config.json`, `config_multi.json`, and the root `.env`; Agent settings and the optional LLM key are stored in `cthulu_agent\.env.agent`. Windows ACLs restrict those environment files to the current user and LocalSystem, but the values are not encrypted. Do not commit or share them.

**Important live-trading behavior:** setup does not start Cthulu, but it writes `LIVE_RUN_CONFIRM=1` for the Agent. Agent autonomy defaults to `autonomous`. When you later choose Agentic on a real MT5 account, the Agent can place orders without an additional per-order confirmation. Use a demo account for Single/Multi testing and change the Agent autonomy/confirmation setting if that is not intended.

## 4. Start from the launcher

Double-click `Cthulu Launcher.bat`, or select the installed **Cthulu Launcher** shortcut. The launcher checks dependencies and then shows two sequential menus:

1. **Kill and stay down**, **Agentic**, **Legacy**, or **Exit**.
2. After choosing Agentic or Legacy: **Single**, **Multi**, **HFT**, or **Exit**.

The two menu choices are independent:

| Menu | Choice | Effect |
|---|---|---|
| Execution | **Agentic** | Starts the Legacy engine and Agent runtime together. Both may act under their separate risk checks. |
| Execution | **Legacy** | Legacy is the active trading owner. The Agent dashboard runtime starts, but Agent order placement and management are blocked. |
| Trading | **Single** | Uses `config.json`. |
| Trading | **Multi** | Uses `config_multi.json`; the Legacy engine uses the configured ultra-aggressive mindset for this launcher mode. |
| Trading | **HFT** | Uses `config.json`, M1 data, and broker-universe scanning after a safety preflight. Choose Agentic first if Agent trading should be active in HFT. |

### HFT preflight and risk

The current HFT startup requires a **real** MT5 account with trading enabled. It blocks startup if no tradable symbols are available, an existing position/order lacks a stop loss, risk cannot be calculated, aggregate stop risk exceeds 5%, or active orders exceed 10. Consequently, the current HFT launcher rejects demo accounts.

The HFT Agent profile caps risk at 1% per entry, 5% aggregate open risk, and 10 active orders; configured settings can impose stricter caps. HFT does not disable the Agent's configured daily-loss or drawdown halts. Treat HFT as live high-risk trading, not as the demo-test option.

## 5. Dashboard controls and stopping

The launcher opens the Agent dashboard and starts a supervisor that retries the Agent process after unexpected exits. The supervisor does not restart the Legacy engine. If the dashboard service restarts, the browser may briefly disconnect.

From **Dashboard → Settings → Cthulu services**:

- **Kill and stay down** sets a persistent stop marker and stops Cthulu/Agent services.
- **Restart services** starts the last-saved execution mode and trading mode again; HFT repeats its preflight.

You can also select **Kill and stay down** from the launcher's first menu. To resume, explicitly launch Cthulu and choose a mode. Stopping services does not close broker positions or cancel pending orders. Check them in MT5. The launcher does not clear logs, databases, trading history, or daily-loss state.

## Troubleshooting

| Symptom | Check |
|---|---|
| Launcher says configuration is missing | Complete the first-run wizard; the dependency script alone does not create the MT5/Agent configuration. |
| Python or dependency setup fails | Install Python 3.10+ (Python 3.12 is the setup bootstrap default), then rerun the wizard. Check the latest `logs\Cthulu_setup_*.log`. |
| MT5 cannot connect | Verify the terminal is installed, account number/password/server are correct, and the selected account is available in MT5. |
| HFT startup is blocked | HFT needs a real account, MT5 trading permission, available tradable symbols, protected existing orders/positions, and exposure under its preflight caps. Read the HFT preflight log. |
| Kill switch remains active | Start the launcher and explicitly choose a mode to resume. Do not delete the marker as a substitute for checking why services stopped. |
| Service or dashboard exits | Review `logs\Cthulu_agent_supervisor.log` and the latest `Cthulu_*.err.log` / `Cthulu_agent_*.err.log`. |

For Agent controls, provider setup, and dashboard security, see the [Agent README](../cthulu_agent/README.md). For risk concepts, see [Risk Management](07_RISK.md).
