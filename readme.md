# Cthulu

Cthulu is an automated trading system for MetaTrader 5. It has two execution modes:

- **Legacy** — the established strategy and risk-management engine.
- **Agentic** — the Legacy engine runs alongside an LLM-guided Agent runtime, with deterministic risk checks on Agent actions.

The Windows launcher asks for an execution mode and then a trading mode. These are separate choices; **HFT is a trading mode, not a third execution mode**.

> **Trading risk:** Automated trading can lose money. Use a demo account for Single and Multi testing, review every risk setting, and do not rely on past results or AI output as a guarantee of performance.

## Windows installation and first run

MetaTrader 5 must be installed separately. The Cthulu installer does not install the MT5 terminal.

### Use the MSI

1. Double-click `Cthulu-Setup.msi` and complete the per-user installation.
2. On the Finish page, leave **Open Cthulu first-run setup** selected, or open **Cthulu Setup** from the Start Menu later.
3. Complete the wizard and select **Install & save setup**. The wizard installs the project dependencies and writes the local configuration; it does **not** start Cthulu or place trades.
4. When ready, choose **Open launcher**, or use the **Cthulu Launcher** desktop/Start Menu shortcut.

The MSI installs under `%LOCALAPPDATA%\Programs\Cthulu`. It contains no account credentials or local runtime data.

### Set up from a source checkout

From the repository root, run the same first-run wizard:

```powershell
git clone https://github.com/amuzetnoM/cthulu.git
Set-Location cthulu
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -File .\installer\cthulu_first_run_setup.ps1
```

The wizard can install Python 3.12 through `winget` if Python is missing, then creates `.venv` and installs `requirements.txt`. Python 3.10 or later is required. If `winget` is unavailable, install Python manually and rerun setup.

The repository's `Cthulu Launcher.bat` is the double-click startup entry point **after first-run setup**. It installs/checks Python dependencies before showing its menus, but it does not collect MT5 credentials or create the first-run configuration. Running `scripts\setup.ps1` alone is not a substitute for the first-run wizard.

### Build the MSI

To build the installer from a Windows checkout, install the .NET 8 SDK and run:

```powershell
.\installer\Build-Msi.ps1
```

The output is `installer\dist\Cthulu-Setup.msi`. The build stages tracked application files and excludes local environment files, runtime configs, databases, logs, tests, and the nested `resource_aggregator` repository.

## What first-run setup configures

The wizard requires an MT5 account number, password, and broker server. An MT5 terminal path is optional. Use a demo account for normal initial testing.

Risk inputs are percentages of account equity. The defaults are **0.5% maximum risk per trade**, **2% daily-loss stop**, **10% drawdown halt**, and **3 maximum simultaneous positions**. A daily-loss or drawdown value of `0` disables that stop.

The Agent LLM overlay is optional. When enabled, enter a Cloudflare account ID, AI Gateway ID (defaults to `default`), API token, and model. The default model is `@cf/qwen/qwen3-30b-a3b-fp8`; the base URL may be left blank. Model availability and pricing can change; check [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/).

Setup writes `config.json`, `config_multi.json`, the root `.env`, and `cthulu_agent\.env.agent`. The environment files contain secrets and are ACL-restricted to the current Windows user and LocalSystem; they are not encrypted. Never commit or share them.

**Review this before launching:** the wizard writes `LIVE_RUN_CONFIRM=1` to the Agent environment. The Agent's default autonomy is `autonomous`, so a later Agentic launch on an MT5 account can place orders without a separate per-order confirmation. The setup wizard itself does not trade. Use a demo account for Single/Multi testing, and change the Agent autonomy or confirmation setting if you do not want autonomous live orders.

## Start Cthulu

Double-click `Cthulu Launcher.bat` (or the installed **Cthulu Launcher** shortcut). The launcher runs dependency setup, then presents:

1. **Kill and stay down**, **Agentic**, **Legacy**, or **Exit**.
2. After choosing Agentic or Legacy: **Single**, **Multi**, **HFT**, or **Exit**.

### Execution mode

| Choice | Behavior |
|---|---|
| **Agentic** | Starts the Legacy engine and Agent runtime together. The Legacy engine continues to use its configured strategy and risk checks; the Agent can also place/manage orders under its own risk checks. |
| **Legacy** | The Legacy engine is the active trading owner. The Agent dashboard runtime is still started, but Agent order placement and management are blocked. |

### Trading mode

| Choice | Configuration and behavior |
|---|---|
| **Single** | Uses `config.json`. |
| **Multi** | Uses `config_multi.json`; the Legacy engine uses its configured ultra-aggressive mindset for this launcher mode. |
| **HFT** | Uses `config.json`, M1 data, and broker-universe scanning. HFT runs only after a safety preflight. It is available under either execution choice: select **Agentic**, then **HFT**, to enable Agent trading in HFT mode. |

**HFT is a live-account mode in the current launcher:** preflight requires a real MT5 account with trading enabled, tradable symbols, protected existing positions/orders, no more than 10 active orders, and calculated aggregate stop risk at or below 5%. A demo account is rejected by this preflight. The HFT Agent profile caps risk at 1% per entry, 5% aggregate open risk, and 10 active orders; configured risk limits may be stricter. HFT does not disable the configured Agent daily-loss or drawdown halts.

## Dashboard, restart, and kill switch

The launcher opens the Agent dashboard and starts its supervisor. If the Agent process exits unexpectedly, the supervisor retries it with a backoff; the Legacy trading process is not restarted by that Agent supervisor. The dashboard may briefly disconnect during a restart.

From the dashboard, open **Settings → Cthulu services**:

- **Kill and stay down** activates a persistent kill switch and stops Cthulu and Agent service processes.
- **Restart services** reruns the saved execution/trading-mode selection. HFT startup repeats its safety preflight.

The launcher also offers the kill switch as its first menu choice. To resume after a kill, explicitly start the launcher and choose a mode. Stopping services does **not** close open positions or cancel broker-side pending orders; check and manage them in MT5. The kill switch does not purge logs, databases, trade history, or daily-loss state.

The dashboard binds to this device by default. Remote access requires a dashboard token; see the [Agent guide](cthulu_agent/README.md) before changing network access.

## Local files and logs

| Path | Purpose |
|---|---|
| `config.json` | Single-symbol and HFT Legacy configuration |
| `config_multi.json` | Multi-symbol configuration |
| `.env` | Shared Legacy credentials and saved launcher mode |
| `cthulu_agent\.env.agent` | Agent credentials, risk settings, and optional LLM settings |
| `.cthulu.killswitch` | Persistent stop marker; removed only when a launcher explicitly resumes |
| `logs\` | Setup, startup, engine, Agent, and HFT preflight logs |
| `data\agent.db` | Agent journal and runtime database |

If startup fails, check the latest relevant file in `logs\`. Setup failures are written to `Cthulu_setup_*.log`; regular engine output uses `Cthulu_*.out.log` and `Cthulu_*.err.log`; Agent output and restart history are recorded in `Cthulu_agent_*.log` and `Cthulu_agent_supervisor.log`.

## Documentation

- [Quick Start](docs/02_QUICKSTART.md) — current first-run and launcher workflow
- [Agent guide](cthulu_agent/README.md) — Agent behavior, Cloudflare configuration, risk controls, and dashboard
- [Risk management](docs/07_RISK.md)
- [Mindsets](docs/06_MINDSETS.md)
- [Deployment notes](docs/09_DEPLOYMENT.md)
- [Architecture](docs/04_ARCHITECTURE.md)
- [Interactive system map](tools/system_map.html) and [map guide](tools/SYSTEM_MAP_GUIDE.md)
- [Changelog](docs/Changelog/CHANGELOG.md)

## License and disclaimer

Cthulu is distributed under the [GNU Affero General Public License v3.0](LICENSE). It is provided without warranties and is not financial advice. You are responsible for your account, credentials, risk settings, and all trading decisions.
