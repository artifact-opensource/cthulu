---
title: DEPLOYMENT
description: Current Windows install, startup, monitoring, and recovery guidance for Cthulu
tags: [deployment, windows, setup, monitoring]
sidebar_position: 9
---

# Deployment

The current documented deployment is the **interactive Windows launcher** with a locally installed MetaTrader 5 terminal. Use the [Quick Start](02_QUICKSTART.md) for the full first-run workflow.

The Docker, Linux, NSSM, Task Scheduler, and old `python -m Cthulu --no-prompt` recipes in earlier versions are not the current setup procedure. Do not use them as a production service configuration.

## Install and configure

1. Install the MetaTrader 5 terminal separately and confirm the intended account is available.
2. Install Cthulu using the per-user MSI, or from a source checkout run:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\installer\cthulu_first_run_setup.ps1
   ```

3. Enter the MT5 account number, password, broker server, and risk limits in the first-run wizard. The terminal path is optional.
4. If enabling the optional Agent LLM overlay, configure the Cloudflare account ID, AI Gateway ID, API token, and model in the wizard.
5. Review the saved settings and the [live-trading warning](02_QUICKSTART.md#3-enter-account-risk-and-optional-agent-settings).
6. Double-click `Cthulu Launcher.bat` or use the installed **Cthulu Launcher** shortcut. The launcher checks dependencies and then prompts for execution mode and trading mode.

The wizard installs/checks dependencies and writes local configuration; it does **not** start Cthulu. The repository launcher by itself is not a replacement for the first-run wizard. Build the MSI only when needed; it requires the .NET 8 SDK and `.\installer\Build-Msi.ps1`.

## Choose modes

Select **Agentic** or **Legacy** first, then **Single**, **Multi**, or **HFT**:

- **Agentic** runs the Legacy engine and Agent runtime together. Each has its own risk checks.
- **Legacy** keeps the Legacy engine as the trader. The Agent dashboard starts, but Agent order placement and management are blocked.
- **Single** uses `config.json`.
- **Multi** uses `config_multi.json` and its configured portfolio/risk limits without a launcher-imposed mindset override.
- **HFT** uses `config.json`, M1 data, and broker-universe scanning after a safety preflight. It can be selected under either execution mode.

The current HFT preflight is live-account-only. It requires trading permission, available tradable symbols, stop protection on existing orders and positions, at most 10 active orders, and aggregate stop risk no higher than 5%. The HFT Agent profile caps risk at 1% per entry, 5% aggregate open risk, and 10 active orders; configured limits may be stricter. Configured Agent daily-loss and drawdown halts are not disabled by HFT. HFT is not a demo-account test mode.

## Runtime monitoring

The dashboard starts with each normal startup mode. Use its **Overview** and **Settings** pages to inspect the Agent, configuration, and service controls. By default, the dashboard is available only from the local device. Enabling Local network or Tailscale access requires a dashboard token; keep that token private.

The supervisor retries the Agent process after unexpected exits with backoff. It does not supervise or restart the Legacy trading engine. If the Agent/dashboard restarts, refresh the dashboard page after the service returns. Check the latest files in `logs\` for failures:

| Log | Purpose |
|---|---|
| `Cthulu_setup_*.log` | First-run/dependency setup |
| `Cthulu_*.out.log`, `Cthulu_*.err.log` | Legacy engine/startup output |
| `Cthulu_agent_*.log` | Agent process output |
| `Cthulu_agent_supervisor.log` | Agent restart and supervisor history |
| HFT preflight logs under `logs\` | HFT startup checks and block reasons |

## Stop, restart, and recovery

- **Kill and stay down** in the launcher or dashboard writes the persistent kill-switch state and stops Cthulu services.
- **Restart services** in Dashboard Settings restarts the saved mode/configuration; HFT repeats its preflight.
- To resume after a kill, explicitly start the launcher and choose a mode.

Stopping Cthulu does not close open MT5 positions or cancel pending broker orders. Check and manage those in MT5. The kill switch is not a log purge, database reset, loss-history reset, or clean-account operation.

## Pre-live checklist

- Confirm the MT5 account, broker server, terminal, and trading permission.
- Verify the active `config.json` / `config_multi.json` and risk thresholds.
- Confirm whether the selected mode allows Agent orders. The setup wizard writes `LIVE_RUN_CONFIRM=1`, and Agent autonomy defaults to `autonomous`.
- Store `.env` and `cthulu_agent\.env.agent` securely. Windows ACLs restrict access to the current user and LocalSystem; these files are not encrypted.
- Verify dashboard access mode and token before enabling remote access.
- Monitor the initial session and keep MT5 available. Never assume a process restart closed broker-side exposure.

For normal first-run setup, refer to the [Quick Start](02_QUICKSTART.md). For Agent behavior and dashboard security, see the [Agent guide](../cthulu_agent/README.md).
