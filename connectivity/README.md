# Connectivity Module

External communication layer for Cthulu Trading System.

## Overview

The `connectivity` module provides two communication protocols:
- **RPC**: JSON-RPC 2.0 over TCP for remote procedure calls
- **Webhook**: HTTP webhooks for event-driven communication

## Installation

No additional dependencies required beyond Python standard library.

## RPC Module

### RPC Server

```python
from connectivity.rpc import RPCServer

# Define handler functions
def get_status(params):
    return {
        'status': 'running',
        'balance': 10000.00,
        'positions': 3
    }

def execute_trade(params):
    symbol = params.get('symbol')
    direction = params.get('direction')
    # Execute trade logic
    return {'ticket': 12345, 'status': 'executed'}

# Create and configure server
server = RPCServer(host='0.0.0.0', port=9001)
server.register_method('get_status', get_status)
server.register_method('execute_trade', execute_trade)

# Start server
server.start()

# Server runs in background thread
# Stop when done
# server.stop()
```

### RPC Client

```python
from connectivity.rpc import RPCClient

# Create client
client = RPCClient(host='localhost', port=9001, timeout=10.0)

# Call remote methods
status = client.call('get_status', {})
print(status)
# {'status': 'running', 'balance': 10000.00, 'positions': 3}

# Call with parameters
result = client.call('execute_trade', {
    'symbol': 'EURUSD',
    'direction': 'buy',
    'lot_size': 0.1
})
print(result)
# {'ticket': 12345, 'status': 'executed'}

# Fire-and-forget (no response)
client.call_async('log_event', {'event': 'system_startup'})

# Check connection
if client.ping():
    print("Server is reachable")
```

### RPC Features

- JSON-RPC 2.0 compliant
- TCP socket communication
- Multi-threaded request handling
- Automatic retry logic
- Request/response logging
- Connection pooling support
- Timeout handling

## Webhook Module

### Webhook Server

```python
from connectivity.webhook import WebhookServer

# Define handler functions
def handle_trading_signal(payload, headers):
    signal = payload.get('signal')
    symbol = payload.get('symbol')
    # Process trading signal
    return {'status': 'signal_received'}

def handle_alert(payload, headers):
    alert_type = payload.get('type')
    message = payload.get('message')
    # Process alert
    return {'status': 'alert_processed'}

# Create server with signature verification
server = WebhookServer(
    host='0.0.0.0',
    port=8080,
    secret_key='your-secret-key-here'  # Optional
)

# Register handlers
server.register_handler('/trading/signal', handle_trading_signal)
server.register_handler('/alerts/*', handle_alert)  # Wildcard support

# Start server
server.start()

# Server runs in background thread
# Stop when done
# server.stop()
```

### Webhook Client

```python
from connectivity.webhook import WebhookClient

# Create client with signature
client = WebhookClient(
    url='https://example.com/webhook',
    secret_key='your-secret-key-here',  # Optional
    timeout=10.0,
    retry_count=3
)

# Send webhook
response = client.send({
    'event': 'trade_executed',
    'symbol': 'EURUSD',
    'ticket': 12345,
    'profit': 25.50
})

# Send asynchronously (fire-and-forget)
client.send_async({
    'event': 'heartbeat',
    'timestamp': 1234567890
})

# Send batch
payloads = [
    {'event': 'trade1', 'symbol': 'EURUSD'},
    {'event': 'trade2', 'symbol': 'GBPUSD'},
    {'event': 'trade3', 'symbol': 'USDJPY'}
]
results = client.send_batch(payloads, parallel=True)

# Test connection
if client.test_connection():
    print("Webhook endpoint is reachable")
```

### Webhook Features

- HTTP POST webhooks
- Path-based routing
- Wildcard path matching
- HMAC-SHA256 signature verification
- Health check endpoint
- Automatic retry logic
- Batch sending (sequential or parallel)
- Custom headers support

## Security

### RPC Security

- Use firewalls to restrict access to RPC ports
- Consider implementing authentication in handlers
- Run on internal networks only
- Use TLS/SSL proxies for internet exposure

### Webhook Security

- Use `secret_key` for signature verification
- Validate payload structure in handlers
- Implement rate limiting
- Use HTTPS in production
- Verify signatures on server side

## Error Handling

Both modules provide custom exceptions:

```python
from connectivity.rpc import RPCError
from connectivity.webhook import WebhookError

try:
    result = client.call('some_method', {})
except RPCError as e:
    print(f"RPC error: {e}")

try:
    response = webhook_client.send({'event': 'test'})
except WebhookError as e:
    print(f"Webhook error: {e}")
```

## Configuration Examples

### RPC Server Configuration

```python
server = RPCServer(
    host='0.0.0.0',          # Listen on all interfaces
    port=9001,               # RPC port
    max_connections=10,      # Max concurrent connections
    buffer_size=4096         # Socket buffer size
)
```

### RPC Client Configuration

```python
client = RPCClient(
    host='localhost',        # Server host
    port=9001,              # Server port
    timeout=10.0,           # Request timeout (seconds)
    retry_count=3,          # Retry attempts
    retry_delay=1.0,        # Delay between retries
    buffer_size=4096        # Socket buffer size
)
```

### Webhook Server Configuration

```python
server = WebhookServer(
    host='0.0.0.0',                      # Listen on all interfaces
    port=8080,                           # HTTP port
    secret_key='your-secret-key-here'    # HMAC signature key
)
```

### Webhook Client Configuration

```python
client = WebhookClient(
    url='https://example.com/webhook',   # Webhook endpoint
    secret_key='your-secret-key-here',   # HMAC signature key
    timeout=10.0,                        # Request timeout
    retry_count=3,                       # Retry attempts
    retry_delay=1.0,                     # Delay between retries
    headers={'X-Custom': 'value'}        # Custom headers
)
```

## Integration with Cthulu

These modules are standalone and don't modify any system files. To integrate:

1. Import the required classes:
   ```python
   from connectivity.rpc import RPCServer, RPCClient
   from connectivity.webhook import WebhookServer, WebhookClient
   ```

2. Initialize in your bootstrap or main loop

3. Register handlers for your specific use cases

4. Start servers during system initialization

5. Use clients to communicate with external services

## Threading

Both servers run in daemon threads and are non-blocking:
- Servers can be started and will run in the background
- Main application continues execution
- Servers automatically stop when main application exits
- **Note**: Daemon threads may be forcibly terminated on exit. For graceful shutdown, explicitly call `server.stop()` before application exit to ensure all active requests are completed.

## Logging

Both modules use Python's standard logging:

```python
import logging

# Configure logging level
logging.getLogger('connectivity.rpc').setLevel(logging.DEBUG)
logging.getLogger('connectivity.webhook').setLevel(logging.INFO)
```

## Examples

### Complete RPC Example

```python
from connectivity.rpc import RPCServer, RPCClient
import time

# Server side
def add(params):
    a = params.get('a', 0)
    b = params.get('b', 0)
    return {'result': a + b}

server = RPCServer(port=9001)
server.register_method('add', add)
server.start()

# Client side
client = RPCClient(port=9001)
result = client.call('add', {'a': 5, 'b': 3})
print(result)  # {'result': 8}

server.stop()
```

### Complete Webhook Example

```python
from connectivity.webhook import WebhookServer, WebhookClient

# Server side
def handle_event(payload, headers):
    event_type = payload.get('type')
    print(f"Received event: {event_type}")
    return {'processed': True}

server = WebhookServer(port=8080)
server.register_handler('/events', handle_event)
server.start()

# Client side
client = WebhookClient(url='http://localhost:8080/events')
response = client.send({'type': 'test', 'data': 'hello'})
print(response)  # {'status': 'success', ...}

server.stop()
```

## License

Part of Cthulu Trading System v5.2.0
