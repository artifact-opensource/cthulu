# Discord Notification Integration

Cthulu integrates with Discord for real-time trading alerts and system notifications.

## Quick Start

1. **Create Discord Webhooks**
   - Go to your Discord server → Server Settings → Integrations → Webhooks
   - Create 3 webhooks in the "Cthulu" category:
     - `alerts` - Trade executions, risk alerts, adoptions
     - `health` - Session summaries, model performance
     - `signals` - High-confidence signals, regime changes

2. **Configure Environment**
   Add webhook URLs to `.env`:
   ```bash
   DISCORD_WEBHOOK_ALERTS=https://discord.com/api/webhooks/...
   DISCORD_WEBHOOK_HEALTH=https://discord.com/api/webhooks/...
   DISCORD_WEBHOOK_SIGNALS=https://discord.com/api/webhooks/...
   ```

3. **Test Connection**
   ```bash
   python -m integrations.discord_cli status
   python -m integrations.discord_cli test --all
   ```

## Channels

### Alerts Channel
Real-time trading events and system alerts:

| Notification | Description | Priority |
|-------------|-------------|----------|
| Trade Opened | Entry with symbol, direction, size, SL/TP | HIGH |
| Trade Closed | Exit with P&L, duration, reason | HIGH |
| Trade Adopted | Manual trade taken over by Cthulu | HIGH |
| Risk Alert | Drawdown, margin, position limits | CRITICAL |
| System Health | Connection failures, API errors | CRITICAL |

### Health Channel
Daily digests and system status:

| Notification | Description | Frequency |
|-------------|-------------|-----------|
| Session Summary | Win/loss, total P&L, trade count | End of session |
| Model Performance | ML accuracy, drift warnings | Daily |
| Portfolio Snapshot | Open positions, exposure, equity | Configurable |

### Signals Channel
Trading signals and market conditions:

| Notification | Description | Priority |
|-------------|-------------|----------|
| Signal Quality | High-confidence setups detected | MEDIUM |
| Regime Change | Market condition shifts | MEDIUM |
| Milestone | Profit targets hit, new highs | HIGH |

## Configuration Options

```json
{
  "discord": {
    "enabled": true,
    "webhook_alerts": "",
    "webhook_health": "",
    "webhook_signals": "",
    "notify_trades": true,
    "notify_adoptions": true,
    "notify_risk": true,
    "min_pnl_notify": 0
  }
}
```

Environment variable equivalents:
```bash
DISCORD_NOTIFY_TRADES=true
DISCORD_NOTIFY_ADOPTIONS=true
DISCORD_NOTIFY_RISK=true
DISCORD_MIN_PNL_NOTIFY=0
```

## CLI Commands

```bash
# Check configuration status
python -m integrations.discord_cli status

# Test specific channel
python -m integrations.discord_cli test --channel alerts

# Test all channels
python -m integrations.discord_cli test --all

# Send demo notifications (all types)
python -m integrations.discord_cli demo
```

## Rate Limiting

The notifier respects Discord's rate limits:
- 25 requests per minute per webhook (leaving headroom)
- Up to 5 embeds per message (batched automatically)
- Messages are queued and processed asynchronously

## Programmatic Usage

```python
from integrations.discord_notifier import get_discord_notifier

notifier = get_discord_notifier()

# Trade notifications
notifier.notify_trade_opened(
    ticket=123456,
    symbol="EURUSD",
    side="BUY",
    volume=0.10,
    price=1.08550,
    sl=1.08350,
    tp=1.08950
)

# Risk alerts
notifier.notify_risk_alert(
    alert_type="Max Drawdown",
    message="Daily drawdown limit reached",
    current_value=0.06,
    threshold=0.06
)

# Session summary
notifier.notify_session_summary(
    wins=8,
    losses=3,
    total_pnl=156.50,
    trade_count=11,
    win_rate=0.727
)
```

## Integration with Event Bus

The Discord notifier automatically subscribes to the Trade Event Bus when initialized during system bootstrap. All trade events are forwarded to Discord based on configuration.

Events captured:
- `TRADE_OPENED` → Trade Opened notification
- `TRADE_CLOSED` → Trade Closed notification  
- `TRADE_ADOPTED` → Trade Adopted notification
- `RISK_LIMIT_HIT` → Risk Alert notification
- `DRAWDOWN_EVENT` → Risk Alert notification

## Troubleshooting

### Notifications not sending
1. Check webhook URLs are correct: `python -m integrations.discord_cli status`
2. Test webhook connectivity: `python -m integrations.discord_cli test --all`
3. Check logs for rate limit warnings

### Missing notifications
1. Verify `notify_trades`, `notify_risk` settings
2. Check `min_pnl_notify` threshold
3. Ensure webhooks are in correct channels

### Rate limited
- System automatically handles rate limits
- Check `get_stats()` for dropped notification count
- Consider increasing `batch_interval` if volume is high
