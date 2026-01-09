#!/usr/bin/env python3
"""
Example integration script for connectivity modules.
This demonstrates how to integrate RPC and Webhook into the main Cthulu system.

DO NOT RUN THIS - It's just an example for reference.
"""
import logging
from connectivity.rpc import RPCServer, RPCClient
from connectivity.webhook import WebhookServer, WebhookClient


def example_rpc_integration():
    """Example of how to integrate RPC server into Cthulu."""
    
    # Define handlers that interact with trading system
    def get_system_status(params):
        """Return current system status."""
        return {
            'status': 'running',
            'mode': 'live',
            'balance': 10000.00,
            'positions': 3,
            'uptime_hours': 24
        }
    
    def get_positions(params):
        """Return open positions."""
        # In real integration, this would query from position manager
        return {
            'positions': [
                {'ticket': 12345, 'symbol': 'EURUSD', 'profit': 25.50},
                {'ticket': 12346, 'symbol': 'GBPUSD', 'profit': -10.20},
                {'ticket': 12347, 'symbol': 'USDJPY', 'profit': 5.00}
            ]
        }
    
    def place_manual_trade(params):
        """Place a manual trade."""
        symbol = params.get('symbol')
        direction = params.get('direction')
        lot_size = params.get('lot_size', 0.1)
        
        # In real integration, this would use ExecutionEngine
        return {
            'success': True,
            'ticket': 12348,
            'message': f'Trade placed: {direction} {lot_size} lots of {symbol}'
        }
    
    def close_position(params):
        """Close a position by ticket."""
        ticket = params.get('ticket')
        
        # In real integration, this would use position manager
        return {
            'success': True,
            'ticket': ticket,
            'message': f'Position {ticket} closed'
        }
    
    # Initialize RPC server
    rpc_server = RPCServer(host='0.0.0.0', port=9001)
    
    # Register all handlers
    rpc_server.register_method('get_status', get_system_status)
    rpc_server.register_method('get_positions', get_positions)
    rpc_server.register_method('place_trade', place_manual_trade)
    rpc_server.register_method('close_position', close_position)
    
    # Start server
    rpc_server.start()
    
    logging.info("RPC server integrated and running on port 9001")
    
    return rpc_server


def example_webhook_integration():
    """Example of how to integrate webhooks into Cthulu."""
    
    # Define webhook handlers
    def handle_trading_signal(payload, headers):
        """Handle external trading signal."""
        signal_type = payload.get('type')  # 'buy' or 'sell'
        symbol = payload.get('symbol')
        confidence = payload.get('confidence', 0.5)
        
        logging.info(f"Received trading signal: {signal_type} {symbol} (confidence: {confidence})")
        
        # In real integration, this would:
        # 1. Validate signal
        # 2. Check risk limits
        # 3. Execute trade via ExecutionEngine
        
        return {
            'status': 'signal_received',
            'action': 'executed' if confidence > 0.7 else 'ignored',
            'reason': 'confidence threshold' if confidence <= 0.7 else 'trade executed'
        }
    
    def handle_risk_alert(payload, headers):
        """Handle risk management alerts."""
        alert_type = payload.get('alert_type')
        severity = payload.get('severity')
        message = payload.get('message')
        
        logging.warning(f"Risk alert: {alert_type} - {message}")
        
        # In real integration, this might:
        # 1. Trigger position closure
        # 2. Pause trading
        # 3. Send notifications
        
        return {'acknowledged': True}
    
    def handle_market_event(payload, headers):
        """Handle market event notifications."""
        event = payload.get('event')
        data = payload.get('data', {})
        
        logging.info(f"Market event: {event}")
        
        # In real integration, this might update market regime
        
        return {'processed': True}
    
    # Initialize webhook server
    webhook_server = WebhookServer(
        host='0.0.0.0',
        port=8080,
        secret_key='your-secure-secret-key-here'  # Use env variable in production
    )
    
    # Register handlers
    webhook_server.register_handler('/trading/signal', handle_trading_signal)
    webhook_server.register_handler('/risk/alert', handle_risk_alert)
    webhook_server.register_handler('/market/event', handle_market_event)
    
    # Start server
    webhook_server.start()
    
    logging.info("Webhook server integrated and running on port 8080")
    
    return webhook_server


def example_webhook_sender():
    """Example of sending webhooks to external services."""
    
    # Initialize webhook client for external service
    external_webhook = WebhookClient(
        url='https://your-monitoring-service.com/webhook',
        secret_key='shared-secret-key',
        timeout=5.0
    )
    
    # Send trade notification
    external_webhook.send({
        'event': 'trade_executed',
        'symbol': 'EURUSD',
        'direction': 'buy',
        'ticket': 12345,
        'profit': 0.0,
        'timestamp': 1234567890
    })
    
    # Send system status updates
    external_webhook.send_async({
        'event': 'heartbeat',
        'status': 'running',
        'timestamp': 1234567890
    })
    
    return external_webhook


def integration_example_in_bootstrap():
    """
    Example of how to integrate into core/bootstrap.py
    
    In CthuluBootstrap.bootstrap() method, add:
    """
    
    # After other components are initialized...
    
    # Initialize RPC server if enabled in config
    # if config.get('rpc', {}).get('enabled', False):
    #     rpc_server = example_rpc_integration()
    #     self.rpc_server = rpc_server
    
    # Initialize webhook server if enabled
    # if config.get('webhook', {}).get('enabled', False):
    #     webhook_server = example_webhook_integration()
    #     self.webhook_server = webhook_server
    
    pass


def config_example():
    """
    Example config.json additions for connectivity modules:
    
    {
        "rpc": {
            "enabled": true,
            "host": "0.0.0.0",
            "port": 9001,
            "max_connections": 10
        },
        "webhook": {
            "enabled": true,
            "host": "0.0.0.0",
            "port": 8080,
            "secret_key": "your-secret-key-from-env"
        },
        "external_webhooks": {
            "monitoring": {
                "enabled": true,
                "url": "https://your-monitoring-service.com/webhook",
                "secret_key": "shared-secret"
            }
        }
    }
    """
    pass


if __name__ == '__main__':
    print("This is an example file for reference only.")
    print("See the comments for integration guidance.")
    print("\nKey integration points:")
    print("1. Add RPC/Webhook initialization in core/bootstrap.py")
    print("2. Register handlers that interact with your trading components")
    print("3. Add configuration options to config.json")
    print("4. Use WebhookClient to send notifications to external services")
    print("\nFor testing, run: python3 connectivity/test_connectivity.py")
