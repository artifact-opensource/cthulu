import json
from integrations.discord_notifier import (
    DiscordNotifier,
    NotificationChannel,
)


class FakeResponse:
    status = 204

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_signal_notification_includes_confluence_details(monkeypatch):
    notifier = DiscordNotifier(signals_webhook="https://example.invalid/webhook")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(
        "integrations.discord_notifier.urllib.request.urlopen",
        fake_urlopen,
    )

    notification_queued = notifier.notify_signal_quality(
        symbol="OILCash",
        direction="BUY",
        confidence=0.82,
        strategy="StrategySelectorAdapter",
        indicators={"RSI": 54.2},
        confluence_quality="good",
        confluence_score=78,
        confluence_reasons=["trend aligned", "momentum confirmed"],
        entry_price=103.72,
        stop_loss=103.50,
        take_profit=104.16,
        risk_reward=2.0,
        timeframe="M15",
    )

    assert notification_queued
    queued = notifier._queues[NotificationChannel.SIGNALS].get_nowait()[2]
    assert notifier._send_webhook(
        notifier.webhooks[NotificationChannel.SIGNALS],
        [queued],
    )

    assert captured["url"] == "https://example.invalid/webhook"
    embed = captured["payload"]["embeds"][0]
    assert embed["title"] == "🟢 OILCash · BUY setup"
    assert embed["color"] == 0x00FF00
    fields = {field["name"]: field["value"] for field in embed["fields"]}
    assert fields["Entry Confluence"] == "**GOOD** · `78/100`"
    assert fields["Why it qualifies"] == "• trend aligned\n• momentum confirmed"
    assert fields["Entry"] == "`103.72000`"
    assert fields["Stop Loss"] == "`103.50000`"
    assert fields["Take Profit"] == "`104.16000`"
    assert fields["Risk / Reward"] == "`1:2.00`"
    assert fields["Timeframe"] == "`M15`"
    assert fields["RSI"] == "`54.2000`"


def test_signal_webhook_configuration_enables_discord_notifier():
    notifier = DiscordNotifier(signals_webhook="configured")

    assert notifier.enabled
    assert notifier.webhooks[NotificationChannel.SIGNALS] == "configured"
