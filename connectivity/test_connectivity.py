#!/usr/bin/env python3
"""
Test script for connectivity modules (RPC and Webhook).
This script demonstrates basic functionality without integrating into the main system.
"""
import time
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from connectivity.rpc import RPCServer, RPCClient, RPCError
from connectivity.webhook import WebhookServer, WebhookClient, WebhookError


def test_rpc():
    """Test RPC server and client."""
    print("\n" + "="*50)
    print("Testing RPC Module")
    print("="*50)
    
    # Define test handlers
    def get_status(params):
        return {
            'status': 'running',
            'version': '5.2.0',
            'uptime': 12345
        }
    
    def add_numbers(params):
        a = params.get('a', 0)
        b = params.get('b', 0)
        return {'result': a + b}
    
    # Start server
    print("\n1. Starting RPC server on port 9001...")
    server = RPCServer(host='127.0.0.1', port=9001)
    server.register_method('get_status', get_status)
    server.register_method('add', add_numbers)
    server.start()
    time.sleep(1)  # Give server time to start
    
    # Test client
    print("\n2. Creating RPC client...")
    client = RPCClient(host='127.0.0.1', port=9001, timeout=5.0)
    
    # Test ping
    print("\n3. Testing connection...")
    if client.ping():
        print("   ✓ Server is reachable")
    else:
        print("   ✗ Server is not reachable")
        return False
    
    # Test method calls
    print("\n4. Testing RPC method calls...")
    
    try:
        # Call get_status
        result = client.call('get_status', {})
        print(f"   ✓ get_status: {result}")
        
        # Call add
        result = client.call('add', {'a': 5, 'b': 3})
        print(f"   ✓ add(5, 3): {result}")
        
        # Test non-existent method
        try:
            client.call('non_existent', {})
            print("   ✗ Should have raised error for non-existent method")
        except RPCError as e:
            print(f"   ✓ Correctly handled non-existent method: {e}")
    
    except Exception as e:
        print(f"   ✗ Error during RPC calls: {e}")
        return False
    
    # Get stats
    print("\n5. Server statistics:")
    stats = server.get_stats()
    for key, value in stats.items():
        print(f"   - {key}: {value}")
    
    # Stop server
    print("\n6. Stopping RPC server...")
    server.stop()
    time.sleep(0.5)
    print("   ✓ RPC server stopped")
    
    return True


def test_webhook():
    """Test webhook server and client."""
    print("\n" + "="*50)
    print("Testing Webhook Module")
    print("="*50)
    
    # Track received webhooks
    received_webhooks = []
    
    # Define test handlers
    def handle_event(payload, headers):
        received_webhooks.append(payload)
        event_type = payload.get('type', 'unknown')
        print(f"   [Server] Received event: {event_type}")
        return {
            'status': 'processed',
            'event_id': len(received_webhooks)
        }
    
    def handle_alert(payload, headers):
        message = payload.get('message', 'no message')
        print(f"   [Server] Received alert: {message}")
        return {'acknowledged': True}
    
    # Start server
    print("\n1. Starting webhook server on port 8080...")
    server = WebhookServer(host='127.0.0.1', port=8080)
    server.register_handler('/events', handle_event)
    server.register_handler('/alerts', handle_alert)
    server.start()
    time.sleep(1)  # Give server time to start
    
    # Test client
    print("\n2. Creating webhook client...")
    client = WebhookClient(
        url='http://127.0.0.1:8080/events',
        timeout=5.0
    )
    
    # Test webhooks
    print("\n3. Testing webhook sending...")
    
    try:
        # Send single webhook
        response = client.send({
            'type': 'test_event',
            'data': 'test data',
            'timestamp': time.time()
        })
        print(f"   ✓ Single webhook sent: {response}")
        
        # Send batch webhooks
        payloads = [
            {'type': 'batch_event_1', 'value': 100},
            {'type': 'batch_event_2', 'value': 200},
            {'type': 'batch_event_3', 'value': 300}
        ]
        results = client.send_batch(payloads)
        print(f"   ✓ Batch webhooks sent: {len(results)} responses")
        
        # Test async sending
        client.send_async({
            'type': 'async_event',
            'message': 'fire and forget'
        })
        print("   ✓ Async webhook sent (fire-and-forget)")
        time.sleep(0.5)  # Give async call time to complete
    
    except WebhookError as e:
        print(f"   ✗ Error during webhook calls: {e}")
        return False
    
    # Test alerts endpoint
    print("\n4. Testing different endpoint...")
    alert_client = WebhookClient(url='http://127.0.0.1:8080/alerts')
    try:
        response = alert_client.send({
            'message': 'Test alert',
            'severity': 'info'
        })
        print(f"   ✓ Alert sent: {response}")
    except WebhookError as e:
        print(f"   ✗ Error sending alert: {e}")
    
    # Get stats
    print("\n5. Server statistics:")
    stats = server.get_stats()
    for key, value in stats.items():
        print(f"   - {key}: {value}")
    
    print(f"\n6. Total webhooks received: {len(received_webhooks)}")
    
    # Stop server
    print("\n7. Stopping webhook server...")
    server.stop()
    time.sleep(0.5)
    print("   ✓ Webhook server stopped")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "#"*50)
    print("# Connectivity Module Test Suite")
    print("#"*50)
    
    rpc_success = test_rpc()
    webhook_success = test_webhook()
    
    print("\n" + "="*50)
    print("Test Summary")
    print("="*50)
    print(f"RPC Module:     {'✓ PASSED' if rpc_success else '✗ FAILED'}")
    print(f"Webhook Module: {'✓ PASSED' if webhook_success else '✗ FAILED'}")
    print("="*50)
    
    if rpc_success and webhook_success:
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed!")
        return 1


if __name__ == '__main__':
    sys.exit(main())
