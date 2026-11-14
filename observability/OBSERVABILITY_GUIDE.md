# Cthulu Observability Guide

This guide covers the current Windows launcher, dashboard, and log files. The older direct-CLI stress-test and RPC order-injection instructions have been removed; an RPC trade request can place a real MT5 order and must not be used as a health check.

## Normal startup

1. Complete [first-run setup](../docs/02_QUICKSTART.md).
2. Double-click `Cthulu Launcher.bat`.
3. Choose **Agentic** or **Legacy**, then **Single**, **Multi**, or **HFT**.
4. Monitor the Agent dashboard and the current session's logs.

Use a demo account for Single/Multi testing. The current HFT preflight requires a real account and applies live exposure checks; see the [Quick Start HFT section](../docs/02_QUICKSTART.md#hft-preflight-and-risk).

## Dashboard and recovery

The dashboard starts with both execution modes. **Overview** and **Settings** provide runtime state and service controls. **Kill and stay down** persistently stops Cthulu services; **Restart services** starts the saved mode/configuration again. HFT startup repeats its preflight.

The Agent supervisor retries an unexpectedly stopped Agent process with backoff. It does not supervise or restart the Legacy engine. If the dashboard disconnects, check the supervisor log and refresh the browser after the service returns.

The dashboard binds to the local device by default. Remote access requires a dashboard token. Do not expose the dashboard or its token as a monitoring shortcut.

## Log locations

Logs are written under `logs\`:

| Log | Purpose |
|---|---|
| `Cthulu_setup_*.log` | First-run and dependency setup |
| `Cthulu_*.out.log` / `Cthulu_*.err.log` | Legacy engine and startup output |
| `Cthulu_agent_*.log` | Agent process output |
| `Cthulu_agent_supervisor.log` | Agent supervisor and restart history |
| HFT preflight logs | HFT checks and startup block reasons |

Tail the supervisor log from the repository root in PowerShell:

```powershell
Get-Content .\logs\Cthulu_agent_supervisor.log -Tail 100 -Wait
```

Inspect the latest relevant log before restarting. A restart is not a reset: it does not clear logs, databases, trade history, or daily-loss state, and it does not close positions or cancel pending orders at the broker.

## Safety

- Never use a trade-placement endpoint or test-trade helper as a monitoring probe.
- Keep MT5 credentials, Cloudflare keys, and dashboard tokens private.
- The setup wizard writes `LIVE_RUN_CONFIRM=1`; Agent autonomy defaults to `autonomous`. Review the [live-trading warning](../docs/02_QUICKSTART.md#3-enter-account-risk-and-optional-agent-settings) before enabling Agentic mode on a real account.
- If Cthulu is stopped, inspect open positions and pending orders in MT5.
