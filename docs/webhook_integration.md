# Webhook → DB → EA Poller Integration

This document explains how to use the included lightweight webhook DB server together with an MQL5 EA that polls for jobs and acts on them.

Components
- scripts/webhook_db_server.py — Python server that stores webhooks in `data/webhooks.db`.
- integrations/webhook_poller/WebhookPoller.mq5 — MQL5 EA that polls `/next_job` and executes BUY/SELL commands.

Server endpoints
- POST /webhook — send JSON payload to enqueue a job. Example body:
  {
    "command": "BUY",
    "symbol": "EURUSD",
    "volume": 0.1,
    "price": 0,
    "order_type": "market",  # or "limit"/"stop"
    "sl": 0,
    "tp": 0
  }
  Returns: `{ "id": <int> }`

- POST /publish_tick — EA or data publisher posts tick JSON: `{ "symbol":"EURUSD", "bid":1.23, "ask":1.234, "volume":100, "time":"..." }`.
  Returns: `{ "id": <int> }`

- POST /publish_bar — Publisher posts completed bar JSON: `{ "symbol":"EURUSD", "timeframe":"M1", "time":"...", "open":1.23, "high":1.25, "low":1.22, "close":1.24, "volume":123 }`.
  Returns: `{ "id": <int> }`

- GET /latest_bars?symbol=EURUSD&tf=M1&count=10 — returns the most recent bars as JSON: `{ "bars": [ {time, open, high, low, close, volume}, ... ] }`.

- GET /next_job — EA polls this, server returns plaintext: `<id>|<CMD>|<SYMBOL>|<VOLUME>|<PRICE>|<SL>|<TP>|<ORDERTYPE>`.
  If no job is pending server replies with HTTP 204 No Content.

- POST /ack?id=<id> — EA calls this after successful execution to mark the job as done.

MT5 (EA) setup
1. Copy `integrations/webhook_poller/WebhookPoller.mq5` into your `MQL5/Experts` folder inside the MetaTrader data directory.
2. In MT5: Tools → Options → Expert Advisors → add `http://127.0.0.1:9002` (or the server URL) to **Allow WebRequest for listed URL**. Restart terminal if needed.
3. Attach EA to a chart and set `ServerUrl` to your webhook server address (default: `http://127.0.0.1:9002`).

Security notes
- Whitelist only trusted URLs in MT5 WebRequest.
- Protect the webhook endpoint (e.g., restrict source, add HMAC token) before exposing to the internet.
- Use HTTPS for remote servers (you will need to add the HTTPS URL to the MT5 WebRequest whitelist).

Running the demo
1. Start the webhook server:
   ```bash
   python3 scripts/webhook_db_server.py --host 0.0.0.0 --port 9002
   ```
2. Ensure MT5 terminal can call the server (whitelist the URL), attach the EA.
3. Send a test webhook:
   ```bash
   curl -X POST http://127.0.0.1:9002/webhook -d '{"command":"BUY","symbol":"EURUSD","volume":0.01}' -H 'Content-Type: application/json'
   ```
4. EA will poll `/next_job`, execute the order, then call `/ack?id=<id>` to complete the job.

Troubleshooting
- If EA returns `WebRequest` failures, ensure the URL is whitelisted and reachable from the terminal. If MT5 runs under Wine, ensure network loopback works and the server binds to 0.0.0.0 or the appropriate host.
- Inspect `data/webhooks.db` with `sqlite3 data/webhooks.db 'select * from webhooks;'` to see queued jobs.

