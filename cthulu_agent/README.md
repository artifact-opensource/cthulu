# Cthulu Agent

The Agent is a journaling, self-reviewing trading runtime with a live dashboard. It can connect to MetaTrader 5 or the built-in paper market and runs beside the Legacy engine.

## Run it

For the full Windows trading system, complete [first-run setup](../docs/02_QUICKSTART.md) and launch `Cthulu Launcher.bat` from the repository root. Choose **Agentic** or **Legacy**, then **Single**, **Multi**, or **HFT**. The Agent dashboard runtime starts in both execution modes; Agent order placement and management are enabled only in Agentic mode.

For a direct Agent-only development run, use the repository virtual environment from the repository root:

```powershell
.\.venv\Scripts\python.exe .\run_agent.py --open
```

This command runs the Agent runtime/dashboard only; it does not start the Legacy trading engine or replace the full-system launcher. Run the Agent tests with the same interpreter:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s cthulu_agent\tests
```

Configure **Cloudflare AI Gateway** in the first-run wizard or Agent **Settings**. The default model is `@cf/ibm-granite/granite-4.0-h-micro`; the gateway ID defaults to `default`. Supply a Cloudflare account ID and API token, use **Find models** if configuring through Settings, and save the configuration. The Agent starts on the paper broker unless `BROKER=mt5` is configured; its MT5 adapter uses the account configured for Cthulu.

The first-run wizard writes `LIVE_RUN_CONFIRM=1` for the Agent, while Agent autonomy defaults to `autonomous`. Agentic startup can therefore place orders on the configured live account without separate per-order confirmation. Review the [Quick Start risk warning](../docs/02_QUICKSTART.md#3-enter-account-risk-and-optional-agent-settings) and test Single/Multi on a demo account.

The project requirements include `numpy` and `pandas`; live MT5 use also requires the MetaTrader 5 terminal and its Python package. No Node build step is required.

## The loop
Every cycle the agent **observes** (cheap, no LLM), then, when something is worth thinking about, it runs **plan → reason → adjust → execute → reflect**:

* **Plan** (periodically): focus, bias per symbol, levels to watch, todos.
* **Reason**: reads snapshots (trend, regime, liquidity pools, sweeps, sessions), its open book, todos, playbook and recent journal, and proposes up to three actions: `place_limit`, `place_stop`, `place_market`, `modify_order`, `cancel_order`, `modify_position`, `close_position` (partial allowed), todos, or `hold`.
* **Adjust**: if the risk engine rejects something, the model gets the reasons and one chance to fix it.
* **Execute**: every action passes the deterministic risk engine, then the autonomy mode (observe / ask me / autonomous).
* **Reflect**: compares what happened with what it expected; sets when to look next.

LLM calls are gated (market change, open book, schedule, per-hour cap) so a free model is not hammered.
Cloudflare Workers AI calls use the OpenAI-compatible AI Gateway endpoint. Granite 4.0 H-Micro (`@cf/ibm-granite/granite-4.0-h-micro`) is currently listed at $0.017/M input tokens and $0.112/M output tokens, roughly one-third the Neuron cost of the previous Qwen3 30B-A3B model. Workers AI includes a shared free allocation of 10,000 Neurons per account per day, resetting at 00:00 UTC; heavy use can still exhaust it. Model availability and pricing can change, so check [Cloudflare Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/). If a response is empty or truncated, the client retries with progressively larger generation budgets and reports the final model/token usage on failure.

## How it learns
* Everything is written to SQLite (`data/agent.db`): journal (full-text searchable), todos, trades, equity, chat.
* Operational errors are delivered as dashboard notifications, not journal entries. Legacy `system` journal rows and their local Discord outbox records are purged when the journal opens; raw feed and provider diagnostics remain in server logs, not dashboard content.
* The **playbook** holds skills (liquidity sweep reversal, equal-level raids, session-open fakeouts, trend pullback limits, position management, news stand-down, scaling ladder). Seeded skills start on *probation* with low confidence.
* Each closed trade is attributed to the skills it cited. Confidence is computed from results (expectancy in R, sample size). Automatic rules demote or retire skills with enough bad evidence and only results can promote.
* After each closed trade the model reviews the *process* and may edit skill text (versioned). Every 8 trades a **meta review** looks at stats, lessons and the scaling ladder and may add, edit or retire skills, add experiments as todos, and update its own scaling and process notes.
* The model can never grant itself more risk: confidence feeds the risk multiplier, and the multiplier is computed by code.

## Scaling tiny to large
Risk per trade is a percentage of equity set by tier (seed 2% → capital 0.25%), multiplied by a drawdown throttle and by the confidence of the cited skill, then capped by `RISK_MAX_PER_TRADE_PCT`. It never rises to recover losses. Tier limits also cap open positions, resting orders and total open risk. On very small accounts the broker's minimum lot can exceed the risk budget; the engine then rejects the trade rather than over-risk.

## Guardrails (code, not prompts)
Stop loss on every entry; stops may only be **tightened**; limit/stop orders must be on the correct side of price; min reward:risk; ATR-based stop and entry sanity; spread filter; daily-loss and drawdown halts; observed-symbol eligibility; world-feed stand-down. Settings expose hard caps for total active orders (positions plus pending orders), per-symbol positions/orders, pending orders, and aggregate open risk; account-tier limits can be stricter. `AGENT_ENTRY_MODE` can allow adaptive, market-only, or pending-only entries. A live real-money MT5 account is forced to *ask me* mode unless `LIVE_RUN_CONFIRM=1`.

The selectable Agent risk profiles are conservative, balanced, aggressive, ultra-aggressive, and HFT. `AGENT_SYMBOLS=*` discovers broker symbols that are tradable, have fresh quotes and usable M1 history, and pass `AGENT_SYMBOL_MAX_SPREAD_PCT`; `AGENT_SYMBOL_SCAN_LIMIT` rotates a bounded market subset into each reasoning pass while account-wide positions and pending orders remain in risk accounting.

A manual daily-loss reset snapshots the trade-ID high-water mark, so broker timestamps ahead of the machine clock cannot keep an old closed loss in the new baseline. Trades already open at reset remain included when they close; trade history is never deleted.

The Agent loads dynamic SL/TP settings from the same config selected by the launcher. In Agentic mode it manages all broker positions (including external or otherwise unjournaled positions), adds configured initial protection only when SL/TP is missing, and only tightens an existing stop. Legacy mode uses the base Cthulu position manager for the same all-position protection.

## Strategy and execution controls
The Settings page offers Agentic reasoning profiles (`adaptive`, `trend_following`, `mean_reversion`, `momentum_breakout`, `scalping`, and `liquidity_sweep`). These guide the agent's analysis; they are not separately running legacy strategy classes and do not replace risk checks. The Agentic strategy profile and entry mode are included in each reasoning context, and entry mode is enforced by code. Before holding, the agent evaluates confirmed sweep/reclaim retracements and aligned-trend pullback limits; corroborated setups with less than 1 ATR displacement may qualify. An order is staged only when its evidence, stop, target, expiry, and risk checks support it; the agent never forces a trade.

The legacy engine has its own `sma_crossover`, `ema_crossover`, `scalping`, `momentum_breakout`, `mean_reversion`, `trend_following`, and `rsi_reversal` strategies, plus `conservative`, `balanced`, `aggressive`, `ultra_aggressive`, and `high_frequency` mindsets. The Legacy loop continues to run its configured strategy and risk workflow in both execution modes. Agentic mode does not execute those legacy classes or import their risk presets; it receives the latest Legacy indicator, signal, confluence, regime, and score snapshots through a small shared SQLite bridge.

## Execution mode
The Settings page has one shared `CTHULU_EXECUTION_MODE` switch:

* **Agentic** runs the Legacy loop and the Agentic runtime in parallel. Legacy trades continue through the existing Cthulu risk and execution workflow; the agent may also enter and manage shared-account positions under its own risk checks.
* **Legacy** runs the Legacy loop and blocks Agentic order placement and management.

The switch is stored in the shared project-root `.env` and read for every execution decision, independently of the Agent's separate settings file. An already-running process observes a change without a restart. Enabling Agentic mode can adopt existing positions. Disabling Agentic actions requires a connected, flat account with no pending orders. The agent can manage external positions when `AGENT_MANAGE_FOREIGN=true`; symbol aliases resolve the configured watchlist to broker symbols.

The Windows **Cthulu Launcher** first asks for **Agentic** or **Legacy**, then **Single**, **Multi**, or **HFT**. It starts the Legacy engine and Agent supervisor/dashboard. In Agentic mode, both the Legacy loop and Agent can act under their separate risk checks. In Legacy mode, Agent trading is blocked while the dashboard remains available. Multi-symbol startup uses `config_multi.json` and the configured ultra-aggressive Legacy mindset. Startup and service output is written under `logs/`.

HFT is a trading mode beneath either execution mode, not a separate third startup owner. It uses `config.json`, M1 data, dynamic broker-universe scanning, and a safety preflight. The current preflight requires a real MT5 account with trading enabled, tradable symbols, stop protection on existing positions and orders, no more than 10 active orders, and calculated aggregate stop risk at or below 5%; it rejects demo accounts. The HFT Agent profile caps risk at 1% per entry, 5% aggregate open risk, and 10 active orders. Configured daily-loss and peak-drawdown halts remain active in HFT mode.

The launcher opens the dashboard and starts an Agent supervisor that retries the Agent process with backoff after an unexpected exit. It does not supervise or restart the Legacy engine. Dashboard Settings provides **Kill and stay down** and **Restart services**. The kill switch stops Cthulu services but does not close broker positions, cancel pending orders, purge logs, or reset account history.

## World feed
Cthulu includes native, read-only public data feeds; no aggregator service or extra package is required:

* CoinGecko Bitcoin USD spot price and 24-hour change.
* FRED US 10-year Treasury yield, broad dollar index, and WTI spot price.
* BBC World and Business RSS headlines/summaries for geopolitical and macro context. These are headline feeds, not exhaustive coverage or a substitute for market data.

Snapshots are cached in the existing SQLite agent database and refreshed together every 30 minutes by default. Failed feeds retain their last good value and report a stale/error status and data timestamp. The Overview now displays the World Brief, native source values, and feed/digest errors. A failed brief digestion is reported and retried with bounded backoff instead of waiting silently for the next feed refresh. Provider availability, publication delays, and rate limits can change; these indicators are context, not trading signals or guarantees.

Set `WORLD_NATIVE_ENABLED=false` to disable native pulls. An optional custom pull feed can still be configured with `WORLD_API_URL` and `WORLD_API_PATHS`; POST JSON to `/api/world/ingest` for push ingestion. Data is shrunk, summarized into themes and event risk, journaled, and marked untrusted in every prompt.

## Discord trading journal
To enable Discord journal delivery, set `DISCORD_TRADING_JOURNAL_WEBHOOK_URL` in the Agent environment (for example, `cthulu_agent/.env.agent`). Leave it unset to disable delivery. For existing forum threads, set `DISCORD_WORLD_BRIEF_THREAD_ID` and `DISCORD_TRADING_JOURNAL_THREAD_ID` to their numeric IDs; the same forum webhook will post World Briefs and session journals into their respective threads. Without thread IDs, `DISCORD_TRADING_JOURNAL_FORUM_MODE=true` retains the behavior of creating a dated forum thread for each scheduled post. Discord receives the latest World Brief hourly and journal summaries five minutes before and at the close of the Asia (00:00–07:00 UTC), London (07:00–12:00 UTC), and New York (12:00–21:00 UTC) sessions. These are Discord-only schedules: they do not change World feed fetches, digestion, trading cycles, or local journal writes. Posts are stored in a SQLite outbox and retried with backoff; repeated scheduler checks do not duplicate a scheduled post. Existing local journal entries are not replayed as a startup catch-up. Embeds include recent journal context and clickable TradingView chart links. They are journal notes, not execution confirmations; chart links do not trigger trades. Mentions are suppressed, and the webhook URL is never included in messages or logs. Rotate any webhook URL that has been exposed, then configure its replacement locally.

## Security
The dashboard can place trades and write API keys, so it binds to localhost by default, checks the `Host` and `Origin` headers, requires JSON content types, and refuses a non-loopback bind without `DASHBOARD_TOKEN`. API keys are only ever written to `.env` (mode 600) and never returned by the API.

The Settings page offers three dashboard access modes:

* **This device only** binds to loopback.
* **Local network** binds to network interfaces and prints private LAN URLs at startup.
* **Tailscale** binds only to the IPv4 address returned by the installed, connected Tailscale CLI (`tailscale ip -4`) and prints that URL at startup.

Changing the mode requires restarting the agent. The first time a remote mode is enabled, Cthulu generates a strong `DASHBOARD_TOKEN`, saves it in `.env`, and presents it once for copying. Enter that token on each remote device before using the API, chat, or controls. Keep the token private; remote access is not intended to be unauthenticated.

The agent does not expose a general-purpose shell. Its MT5 terminal can be checked or launched with `/app status` and `/app launch mt5`; to close it, pause first and explicitly confirm with `/app close mt5 confirm`. Closing is graceful and never force-terminates the terminal. Trading actions use the MT5 broker API and continue through the deterministic risk engine.

## Important
* `AGENT_MANAGE_FOREIGN=true` (default) lets it manage positions and orders opened by anything else, including the Legacy bot. Run only one Legacy loop per account; Agentic mode is designed for the Agentic runtime and one selected Legacy loop to operate together.
* Test on a demo account first. Nothing here guarantees profit.

## Tests
`python -m unittest cthulu_agent.tests.test_agent` (needs no network; uses a local fake LLM and the paper broker).
