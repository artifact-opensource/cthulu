# Cthulu RPC Server

Lightweight HTTP-based RPC server for programmatic control of Cthulu at runtime.

![Version](https://img.shields.io/badge/Version-6.0.0-4B0082?style=flat-square)
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=flat-square&logo=calendar)
![Security](https://img.shields.io/badge/Security-Hardened-brightgreen?style=flat-square)

## Quick Start

```powershell
# Place a BUY order
$body = '{"symbol":"BTCUSD#","side":"BUY","volume":0.01}'
Invoke-RestMethod -Uri "http://127.0.0.1:8278/trade" -Method POST -Body $body -ContentType "application/json"

# Place a SELL order
$body = '{"symbol":"BTCUSD#","side":"SELL","volume":0.01}'
Invoke-RestMethod -Uri "http://127.0.0.1:8278/trade" -Method POST -Body $body -ContentType "application/json"

# Check health
Invoke-RestMethod -Uri "http://127.0.0.1:8278/health" -Method GET
```

## Configuration

Enable in `config.json` or any mindset config:

```json
{
  "rpc": {
    "enabled": true,
    "host": "127.0.0.1",
    "port": 8278,
    "token": "your-secure-token-here",
    "security": {
      "rate_limit": {
        "requests_per_minute": 60,
        "trades_per_minute": 10,
        "burst_limit": 10,
        "max_volume_per_minute": 10.0,
        "adaptive_enabled": true
      },
      "ip_whitelist": ["127.0.0.1", "::1"],
      "ip_blacklist": [],
      "audit_enabled": true,
      "audit_log_path": "logs/rpc_audit.log"
    }
  }
}
```

**IMPORTANT:** RPC must be explicitly enabled. Default is `false`.

## Security Features (v6.0.0)

### Intelligent Rate Limiting

- **Per-minute limits**: Configurable requests and trades per minute
- **Burst protection**: Prevents rapid-fire request floods
- **Volume limits**: Caps total trading volume per minute
- **Adaptive scaling**: Automatically adjusts limits based on client behavior
- **Auto-blacklisting**: Repeated violations trigger temporary bans

### IP Access Control

- **Whitelist mode**: Only specified IPs can access
- **Blacklist support**: Block known bad actors
- **Private network detection**: Automatic handling of local IPs
- **Dynamic blacklisting**: Abusive IPs auto-blocked

### Request Validation

- **Symbol validation**: Pattern matching for valid symbols
- **Volume bounds**: Min/max volume enforcement
- **Payload sanitization**: XSS/injection prevention
- **Size limits**: Maximum request body size enforced

### Audit Logging

- **All requests logged**: Full audit trail with timestamps
- **Security events**: Rate limits, auth failures, blocked IPs
- **Sensitive field redaction**: Tokens/passwords never logged
- **Separate audit log**: `logs/rpc_audit.log`

### TLS Support (Optional)

```json
{
  "rpc": {
    "security": {
      "tls_enabled": true,
      "tls_cert_path": "/path/to/cert.pem",
      "tls_key_path": "/path/to/key.pem"
    }
  }
}
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/trade` | Submit a trade order |
| GET | `/provenance` | Query order audit trail |
| GET | `/ops/status` | Get system status (mode, connector, positions) |
| GET | `/ops/runbook?name=...` | Get runbook excerpt |
| GET | `/ops/audit?limit=50` | Get recent audit entries |
| POST | `/ops/command` | Submit an operational command (two-step confirm) |

Note: The RPC server accepts an optional `ops_controller` in `run_rpc_server(..., ops_controller=your_controller)` which will be used to execute `ops/command` requests.
| GET | `/health` | Server health check |
| GET | `/status` | Trading system status |

### Trade Request Format

```json
{
  "symbol": "BTCUSD#",
  "side": "BUY",
  "volume": 0.01,
  "confidence": 0.8,
  "sl_pips": 50,
  "tp_pips": 100
}
```

### Trade Response Format

```json
{
  "status": "OK",
  "ticket": 600315175,
  "price": 87588.60,
  "volume": 0.01,
  "signal_id": "rpc_manual_uuid123"
}
```

### Error Responses

| Status | Meaning |
|--------|---------|
| 400 | Bad request - invalid payload |
| 401 | Unauthorized - invalid/missing token |
| 403 | Forbidden - IP blocked or risk rejected |
| 413 | Payload too large |
| 429 | Rate limited - too many requests |
| 500 | Server error |

## Rate Limit Response

When rate limited, the response includes:

```json
{
  "error": "Per-minute limit exceeded (60/60)"
}
```

## Security Statistics

Query via Python:

```python
from cthulu.rpc.server import get_rpc_security_stats, scan_rpc_dependencies

# Get security stats
stats = get_rpc_security_stats()
print(f"Total clients: {stats['rate_limiter']['total_clients']}")
print(f"Blacklisted: {stats['rate_limiter']['blacklisted_count']}")

# Scan for vulnerable dependencies
vulns = scan_rpc_dependencies()
for v in vulns:
    print(f"[{v['severity']}] {v['package']}: {v['cve']}")
```

## Stress Testing via RPC

The monitoring directory includes scripts for RPC-based stress testing:

```powershell
# Run full stress test (120 minutes)
.\monitoring\run_stress.ps1 -DurationMinutes 120 -InjectionMode realistic

# Inject a single signal
python monitoring\inject_signals.py --symbol BTCUSD# --side BUY --volume 0.05 --count 1
```

## Integration Points

RPC integrates with:

1. **RiskEvaluator** - All trades checked before execution
2. **AdaptiveDrawdownManager** - Position sizing adjusted dynamically
3. **Provenance Tracking** - Full audit trail for each order
4. **Prometheus Metrics** - Trade counts exported
5. **Security Manager** - Rate limiting, IP control, auditing

## Full Documentation

See [docs/development_log/rpc.md](../docs/development_log/rpc.md) for complete API reference.

## Security Best Practices

1. **Always use a strong token**: 32+ character random string
2. **Keep whitelist minimal**: Only add IPs that need access
3. **Enable audit logging**: For compliance and forensics
4. **Monitor rate limits**: Watch for abuse patterns
5. **Review dependencies**: Run `scan_rpc_dependencies()` periodically
6. **Use TLS in production**: If exposing beyond localhost

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "RPC down" in inject logs | Check RPC is enabled in config and Cthulu is running |
| "Connection refused" | Verify port 8278 is not blocked and server is listening |
| "Duplicate order" warning | Each request needs unique signal_id (auto-generated) |
| "Risk rejected" | Check spread limits and position limits in config |
| "Rate limited" | Wait for cooldown or reduce request frequency |
| "IP not in whitelist" | Add your IP to `security.ip_whitelist` |
| "Blacklisted" | Wait for blacklist expiry or clear via restart |
