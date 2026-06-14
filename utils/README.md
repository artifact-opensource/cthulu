# Utility Modules

![Version](https://img.shields.io/badge/Version-6.0.0-4B0082?style=flat-square)
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=flat-square&logo=calendar)

## Overview

Infrastructure components providing reliability, performance, and fault tolerance across the Cthulu trading system.

## Module Components

```
utils/
├── __init__.py           # Module exports
├── circuit_breaker.py    # Fault tolerance pattern
├── rate_limiter.py       # Request throttling
├── cache.py              # Smart caching with TTL
├── health_monitor.py     # System health tracking
└── retry.py              # Exponential backoff retry
```

## Quick Reference

| Component | Purpose | Use When |
|-----------|---------|----------|
| **Circuit Breaker** | Prevent cascading failures | External service calls |
| **Rate Limiter** | Control request frequency | API protection |
| **Cache** | Reduce redundant operations | Repeated data access |
| **Health Monitor** | Track component status | Observability |
| **Retry** | Handle transient failures | Network operations |

## Quick Start Examples

### Circuit Breaker

```python
from utils.circuit_breaker import CircuitBreaker

breaker = CircuitBreaker("mt5_api", failure_threshold=5)

@breaker.protect
def get_market_data():
    return connector.get_rates("BTCUSD#")
```

### Rate Limiter

```python
from utils.rate_limiter import TokenBucketRateLimiter

limiter = TokenBucketRateLimiter(rate=10, capacity=20)

if limiter.allow_request():
    execute_request()
else:
    time.sleep(limiter.wait_time())
```

### Cache

```python
from utils.cache import SmartCache

cache = SmartCache(max_size=100, default_ttl=60)

data = cache.get("BTCUSD_data")
if data is None:
    data = fetch_data()
    cache.set("BTCUSD_data", data, ttl=60)
```

### Health Monitor

```python
from utils.health_monitor import HealthMonitor, HealthStatus

monitor = HealthMonitor()
monitor.register_component("mt5_connector")
monitor.update_health("mt5_connector", HealthStatus.HEALTHY, "Connected")
```

### Retry

```python
from utils.retry import retry_with_backoff

@retry_with_backoff(max_attempts=3, base_delay=1.0)
def connect_to_service():
    return service.connect()
```

## Use Cases in Cthulu

### 1. MT5 Connection Protection

```python
# Circuit breaker for MT5 operations
mt5_breaker = CircuitBreaker("mt5", failure_threshold=3)

# Rate limiter for API calls
mt5_limiter = TokenBucketRateLimiter(rate=50, capacity=100)

# Retry for connection
@retry_with_backoff(max_attempts=5)
@mt5_breaker.protect
def safe_connect():
    if not mt5_limiter.allow_request():
        time.sleep(mt5_limiter.wait_time())
    return mt5.initialize()
```

### 2. Market Data Caching

```python
# Cache market data
market_cache = SmartCache(max_size=100, default_ttl=60)

def get_cached_rates(symbol, timeframe):
    key = f"{symbol}_{timeframe}"
    
    data = market_cache.get(key)
    if data is None:
        data = connector.get_rates(symbol, timeframe, 500)
        market_cache.set(key, data, ttl=60)
    
    return data
```

### 3. RPC Server Protection

```python
# Rate limiting per client
rpc_limiter = SlidingWindowRateLimiter(
    max_requests=60,
    window_seconds=60
)

@app.route('/trade', methods=['POST'])
def place_trade():
    client_ip = request.remote_addr
    
    if not rpc_limiter.allow_request(client_id=client_ip):
        return jsonify({"error": "Rate limit exceeded"}), 429
    
    # Process trade...
```

### 4. Health Monitoring

```python
# Initialize health monitor
health = HealthMonitor()
health.register_component("mt5_connector")
health.register_component("database")
health.register_component("execution_engine")

# Update in trading loop
def trading_loop():
    if connector.is_connected():
        health.update_health("mt5_connector", HealthStatus.HEALTHY)
    else:
        health.update_health("mt5_connector", HealthStatus.UNHEALTHY)
```

## Configuration

### Complete Utilities Configuration

```json
{
  "utilities": {
    "circuit_breaker": {
      "mt5_connector": {
        "failure_threshold": 5,
        "timeout_seconds": 60
      },
      "news_api": {
        "failure_threshold": 3,
        "timeout_seconds": 300
      }
    },
    "rate_limiter": {
      "mt5_api": {
        "algorithm": "token_bucket",
        "rate": 50,
        "capacity": 100
      },
      "rpc_server": {
        "algorithm": "sliding_window",
        "max_requests": 60,
        "window_seconds": 60
      }
    },
    "cache": {
      "market_data": {
        "max_size": 100,
        "default_ttl": 60
      },
      "indicators": {
        "max_size": 200,
        "default_ttl": 300
      }
    },
    "retry": {
      "max_attempts": 5,
      "base_delay": 1.0,
      "max_delay": 30.0
    }
  }
}
```

## Testing

```bash
# Run utility tests
python -m pytest tests/unit/test_utils.py -v

# Test circuit breaker
python -m pytest tests/unit/test_circuit_breaker.py -v

# Test rate limiter
python -m pytest tests/unit/test_rate_limiter.py -v
```

## Performance Impact

| Component | Memory | CPU | Latency |
|-----------|--------|-----|---------|
| Circuit Breaker | < 1KB | Negligible | < 1μs |
| Rate Limiter | < 5KB | Negligible | < 1μs |
| Cache | ~1KB/item | Low | < 1μs |
| Health Monitor | < 10KB | Negligible | < 1μs |
| Retry | Minimal | Variable | Depends on backoff |

## Best Practices

### Circuit Breaker
- Set thresholds to 3-5 failures
- Choose timeout based on service recovery (30-120s)
- Monitor state transitions
- Alert on circuit opens

### Rate Limiter
- Choose algorithm based on traffic pattern
- Set limits with safety margin
- Return 429 status with Retry-After header
- Implement client-side backoff

### Cache
- Set TTL based on data volatility
- Target 80%+ hit rate
- Monitor cache size
- Use pattern-based invalidation

### Health Monitor
- Check critical components frequently (5-10s)
- Define clear health thresholds
- Expose `/health` endpoint
- Include metrics in responses

### Retry
- Retry only transient errors
- Limit attempts to 3-5
- Use exponential backoff
- Add jitter to prevent thundering herd

## Troubleshooting

### Circuit Opens Frequently
- Threshold too low - increase failure_threshold
- Underlying service unstable - investigate root cause
- Network issues - check connectivity

### Rate Limit Hit Often
- Limits too strict - increase rate/capacity
- Burst traffic - use token bucket algorithm
- Multiple clients - implement per-client limiting

### Cache Hit Rate Low
- TTL too short - increase default_ttl
- Keys not reused - review access patterns
- Cache too small - increase max_size

### Health Checks Timing Out
- Check intervals too frequent - increase interval
- Component slow - optimize component
- Network latency - adjust timeouts

## Dependencies

- Standard library only (no external dependencies)
- Optional: `prometheus_client` for metrics export

## Related Documentation

- [Utilities Guide](../docs/UTILITIES.md) - Complete guide
- [Performance Tuning](../docs/PERFORMANCE_TUNING.md) - Optimization
- [Security](../docs/SECURITY.md) - Security patterns
- [Architecture](../docs/ARCHITECTURE.md) - System design

## See Also

- [Risk Module](../risk/README.md)
- [Position Module](../position/README.md)
- [RPC Server](../rpc/README.md)

---

**Module Version:** 6.0.0  
**Last Updated:** 2026-01-06
