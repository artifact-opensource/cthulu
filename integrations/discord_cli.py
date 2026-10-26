"""
Discord Notification CLI Tool

Test and manage Discord notifications for Cthulu trading system.

Usage:
    python -m integrations.discord_cli test --channel alerts
    python -m integrations.discord_cli test --all
    python -m integrations.discord_cli status
    python -m integrations.discord_cli demo
"""

import os
import sys
import argparse
import time
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()


def get_notifier():
    """Get configured Discord notifier"""
    from integrations.discord_notifier import DiscordNotifier, NotificationChannel
    
    notifier = DiscordNotifier(
        alerts_webhook=os.getenv('DISCORD_WEBHOOK_ALERTS', ''),
        health_webhook=os.getenv('DISCORD_WEBHOOK_HEALTH', ''),
        signals_webhook=os.getenv('DISCORD_WEBHOOK_SIGNALS', ''),
        enabled=True
    )
    return notifier


def cmd_status(args):
    """Show Discord notification configuration status"""
    print("\n" + "=" * 60)
    print("Discord Notification Configuration Status")
    print("=" * 60)
    
    webhooks = {
        'Alerts': os.getenv('DISCORD_WEBHOOK_ALERTS', ''),
        'Health': os.getenv('DISCORD_WEBHOOK_HEALTH', ''),
        'Signals': os.getenv('DISCORD_WEBHOOK_SIGNALS', ''),
    }
    
    for name, url in webhooks.items():
        status = "✅ Configured" if url else "❌ Not configured"
        masked = url[:50] + "..." if url and len(url) > 50 else url or "(empty)"
        print(f"\n{name}:")
        print(f"  Status: {status}")
        if url:
            print(f"  URL: {masked}")
    
    print("\n" + "-" * 60)
    print("Notification Settings:")
    print(f"  Notify Trades: {os.getenv('DISCORD_NOTIFY_TRADES', 'true')}")
    print(f"  Notify Adoptions: {os.getenv('DISCORD_NOTIFY_ADOPTIONS', 'true')}")
    print(f"  Notify Risk: {os.getenv('DISCORD_NOTIFY_RISK', 'true')}")
    print(f"  Min P&L to Notify: ${os.getenv('DISCORD_MIN_PNL_NOTIFY', '0')}")
    print("=" * 60 + "\n")


def cmd_test(args):
    """Send test notifications"""
    from integrations.discord_notifier import NotificationChannel
    
    notifier = get_notifier()
    
    channel_map = {
        'alerts': NotificationChannel.ALERTS,
        'health': NotificationChannel.HEALTH,
        'signals': NotificationChannel.SIGNALS,
    }
    
    if args.all:
        channels = list(channel_map.values())
    elif args.channel:
        channels = [channel_map.get(args.channel.lower())]
        if not channels[0]:
            print(f"Unknown channel: {args.channel}")
            print(f"Available: {', '.join(channel_map.keys())}")
            return 1
    else:
        print("Specify --channel <name> or --all")
        return 1
    
    print("\nSending test notifications...")
    for channel in channels:
        print(f"  Testing {channel.value}...", end=" ")
        if notifier.send_test_notification(channel):
            print("✅ Sent")
        else:
            print("❌ Failed (check webhook URL)")
    
    print("\nDone!")
    return 0


def cmd_demo(args):
    """Send demo notifications of each type"""
    from integrations.discord_notifier import NotificationChannel
    
    notifier = get_notifier()
    notifier.start()
    
    print("\n" + "=" * 60)
    print("Sending Demo Notifications")
    print("=" * 60)
    
    # Demo trade opened
    print("\n1. Trade Opened notification...")
    notifier.notify_trade_opened(
        ticket=123456,
        symbol="EURUSD",
        side="BUY",
        volume=0.10,
        price=1.08550,
        sl=1.08350,
        tp=1.08950,
        source="system"
    )
    time.sleep(2)
    
    # Demo trade closed (profit)
    print("2. Trade Closed (profit) notification...")
    notifier.notify_trade_closed(
        ticket=123456,
        symbol="EURUSD",
        side="BUY",
        volume=0.10,
        entry_price=1.08550,
        exit_price=1.08750,
        pnl=20.00,
        duration_seconds=3600,
        exit_reason="Take Profit"
    )
    time.sleep(2)
    
    # Demo trade closed (loss)
    print("3. Trade Closed (loss) notification...")
    notifier.notify_trade_closed(
        ticket=123457,
        symbol="GBPUSD",
        side="SELL",
        volume=0.05,
        entry_price=1.26800,
        exit_price=1.26950,
        pnl=-7.50,
        duration_seconds=1800,
        exit_reason="Stop Loss"
    )
    time.sleep(2)
    
    # Demo trade adopted
    print("4. Trade Adopted notification...")
    notifier.notify_trade_adopted(
        ticket=123458,
        symbol="USDJPY",
        side="BUY",
        volume=0.20,
        price=149.50
    )
    time.sleep(2)
    
    # Demo risk alert
    print("5. Risk Alert notification...")
    notifier.notify_risk_alert(
        alert_type="Max Drawdown",
        message="Daily drawdown limit approaching threshold",
        current_value=0.045,
        threshold=0.06
    )
    time.sleep(2)
    
    # Demo system health
    print("6. System Health notification...")
    notifier.notify_system_health(
        status="Warning",
        message="MT5 connection latency increased",
        details={
            "Latency": "250ms",
            "Threshold": "100ms",
            "Action": "Monitoring"
        }
    )
    time.sleep(2)
    
    # Demo session summary
    print("7. Session Summary notification...")
    notifier.notify_session_summary(
        wins=8,
        losses=3,
        total_pnl=156.50,
        trade_count=11,
        win_rate=0.727,
        avg_win=25.50,
        avg_loss=-12.33,
        best_trade=45.00,
        worst_trade=-18.50
    )
    time.sleep(2)
    
    # Demo model performance
    print("8. Model Performance notification...")
    notifier.notify_model_performance(
        model_name="Price Predictor",
        accuracy=0.68,
        predictions=150,
        drift_detected=False
    )
    time.sleep(2)
    
    # Demo portfolio snapshot
    print("9. Portfolio Snapshot notification...")
    notifier.notify_portfolio_snapshot(
        open_positions=3,
        total_exposure=15000.0,
        unrealized_pnl=45.20,
        margin_used=500.0,
        free_margin=9500.0,
        equity=10045.20
    )
    time.sleep(2)
    
    # Demo signal quality
    print("10. Signal Quality notification...")
    notifier.notify_signal_quality(
        symbol="EURUSD",
        direction="BUY",
        confidence=0.85,
        strategy="Trend Following",
        indicators={
            "RSI": 32.5,
            "MACD": 0.0015,
            "ADX": 28.5
        }
    )
    time.sleep(2)
    
    # Demo regime change
    print("11. Regime Change notification...")
    notifier.notify_regime_change(
        symbol="EURUSD",
        old_regime="Ranging",
        new_regime="Trending",
        confidence=0.82
    )
    time.sleep(2)
    
    # Demo milestone
    print("12. Milestone notification...")
    notifier.notify_milestone(
        milestone_type="New Account High",
        message="Account equity reached a new all-time high!",
        value=10500.00
    )
    
    # Wait for queue to flush
    print("\nWaiting for notifications to send...")
    time.sleep(10)
    
    print("\n" + "=" * 60)
    print(f"Demo complete! Stats: {notifier.get_stats()}")
    print("=" * 60 + "\n")
    
    notifier.stop()
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Cthulu Discord Notification CLI',
        epilog="""
Commands:
  status    Show configuration status
  test      Send test notification to channel(s)
  demo      Send demo notifications of each type

Examples:
  python -m integrations.discord_cli status
  python -m integrations.discord_cli test --channel alerts
  python -m integrations.discord_cli test --all
  python -m integrations.discord_cli demo
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Status command
    subparsers.add_parser('status', help='Show configuration status')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Send test notification')
    test_parser.add_argument('--channel', choices=['alerts', 'health', 'signals'],
                            help='Channel to test')
    test_parser.add_argument('--all', action='store_true',
                            help='Test all channels')
    
    # Demo command
    subparsers.add_parser('demo', help='Send demo notifications')
    
    args = parser.parse_args()
    
    if args.command == 'status':
        return cmd_status(args)
    elif args.command == 'test':
        return cmd_test(args)
    elif args.command == 'demo':
        return cmd_demo(args)
    else:
        parser.print_help()
        return 0


if __name__ == '__main__':
    sys.exit(main())
