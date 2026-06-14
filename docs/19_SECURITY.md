---
title: SECURITY
description: Security guidelines for Cthulu including credential management, API security, network protection, and access control
tags: [security, credentials, api-security, access-control]
sidebar_position: 19
version: 6.0.0
---

![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117&logo=git&logoColor=white) 
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar&logoColor=white)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white) 

## Table of Contents
- [Credential Management](#credential-management)
- [API Security](#api-security)
- [Network Security](#network-security)
- [Data Protection](#data-protection)
- [Access Control](#access-control)
- [Monitoring & Auditing](#monitoring--auditing)
- [Security Checklist](#security-checklist)

---

## Credential Management

### Environment Variable Overrides

**Cthulu v4.0.0 implements secure environment variable overrides:**

- **Individual Field Control**: Each MT5 credential can be overridden individually via environment variables
- **Runtime Priority**: Environment variables always take precedence over config file values
- **No Placeholder Dependencies**: Removed insecure FROM_ENV placeholders that could expose credential locations

```bash
# Secure credential override (recommended)
export MT5_LOGIN=12345678
export MT5_PASSWORD=secure_password
export MT5_SERVER=Broker-Live

# Config file can contain dummy values or be empty
# Environment variables will override at runtime
```

**Security Benefits:**
- Credentials never stored in config files
- Environment variables are process-isolated
- No risk of accidental credential commits
- Supports containerized deployments with secret injection

### Encrypted Storage

For production environments, encrypt sensitive configuration:

```python
from cryptography.fernet import Fernet
import os
import json

class SecureConfig:
    """Encrypted configuration manager."""
    
    def __init__(self, key_file='config.key'):
        self.key_file = key_file
        self.cipher = self._load_or_create_key()
    
    def _load_or_create_key(self):
        """Load existing key or create new one."""
        if os.path.exists(self.key_file):
            with open(self.key_file, 'rb') as f:
                key = f.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_file, 'wb') as f:
                f.write(key)
            os.chmod(self.key_file, 0o600)  # Read/write owner only
        
        return Fernet(key)
    
    def encrypt_config(self, config_dict):
        """Encrypt configuration dictionary."""
        json_str = json.dumps(config_dict)
        encrypted = self.cipher.encrypt(json_str.encode())
        return encrypted
    
    def decrypt_config(self, encrypted_data):
        """Decrypt configuration."""
        decrypted = self.cipher.decrypt(encrypted_data)
        return json.loads(decrypted.decode())
    
    def save_secure_config(self, config_dict, filename='config.enc'):
        """Save encrypted configuration."""
        encrypted = self.encrypt_config(config_dict)
        with open(filename, 'wb') as f:
            f.write(encrypted)
        os.chmod(filename, 0o600)
    
    def load_secure_config(self, filename='config.enc'):
        """Load encrypted configuration."""
        with open(filename, 'rb') as f:
            encrypted = f.read()
        return self.decrypt_config(encrypted)

# Usage
secure_config = SecureConfig()

# Encrypt and save
config = {
    'mt5': {
        'login': 12345678,
        'password': 'secret_password',
        'server': 'Broker-Demo'
    }
}
secure_config.save_secure_config(config)

# Load securely
config = secure_config.load_secure_config()
```

### Key Rotation

Implement periodic key rotation:

```python
import datetime

class KeyRotation:
    """Manage credential rotation."""
    
    def __init__(self, rotation_days=90):
        self.rotation_days = rotation_days
        self.last_rotation_file = '.last_rotation'
    
    def should_rotate(self):
        """Check if keys should be rotated."""
        if not os.path.exists(self.last_rotation_file):
            return True
        
        with open(self.last_rotation_file, 'r') as f:
            last_rotation = datetime.datetime.fromisoformat(f.read())
        
        days_since = (datetime.datetime.now() - last_rotation).days
        return days_since >= self.rotation_days
    
    def mark_rotated(self):
        """Record rotation timestamp."""
        with open(self.last_rotation_file, 'w') as f:
            f.write(datetime.datetime.now().isoformat())
    
    def rotate_password(self):
        """Rotate MT5 password."""
        if self.should_rotate():
            # Generate new password
            new_password = self._generate_secure_password()
            
            # Update in broker account (manual step)
            print("⚠️  Update password in MT5 terminal:")
            print(f"New password: {new_password}")
            
            # Update in configuration
            # ... update config ...
            
            self.mark_rotated()
    
    def _generate_secure_password(self, length=20):
        """Generate cryptographically secure password."""
        import secrets
        import string
        
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()"
        return ''.join(secrets.choice(alphabet) for _ in range(length))
```

---

## API Security

### Rate Limiting

Protect against API abuse:

```python
from cthulu.utils.rate_limiter import SlidingWindowRateLimiter

# Apply rate limiting to sensitive operations
auth_limiter = SlidingWindowRateLimiter(
    max_calls=5,          # Max 5 auth attempts
    window_seconds=300,   # Per 5 minutes
    name="authentication"
)

def authenticate_user(credentials):
    """Authenticate with rate limiting."""
    if not auth_limiter.allow_request():
        wait_time = auth_limiter.wait_time()
        raise Exception(f"Too many auth attempts. Wait {wait_time:.0f}s")
    
    # Proceed with authentication
    return verify_credentials(credentials)
```

### API Key Management

```python
import hashlib
import secrets

class APIKeyManager:
    """Manage API keys for RPC access."""
    
    def __init__(self, db_path='api_keys.db'):
        self.db = Database(db_path)
        self._init_db()
    
    def _init_db(self):
        """Initialize API keys table."""
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY,
                key_hash TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                permissions TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_used DATETIME,
                expires_at DATETIME
            )
        """)
    
    def generate_key(self, name, permissions=['read'], expires_days=90):
        """Generate new API key."""
        # Generate cryptographically secure key
        api_key = secrets.token_urlsafe(32)
        
        # Hash for storage
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # Store in database
        expires_at = datetime.now() + timedelta(days=expires_days)
        self.db.execute("""
            INSERT INTO api_keys (key_hash, name, permissions, expires_at)
            VALUES (?, ?, ?, ?)
        """, (key_hash, name, json.dumps(permissions), expires_at))
        
        # Return plain key ONCE (never stored)
        return api_key
    
    def validate_key(self, api_key):
        """Validate API key."""
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        result = self.db.execute("""
            SELECT permissions, expires_at
            FROM api_keys
            WHERE key_hash = ?
        """, (key_hash,)).fetchone()
        
        if not result:
            return False
        
        permissions, expires_at = result
        
        # Check expiration
        if datetime.fromisoformat(expires_at) < datetime.now():
            return False
        
        # Update last used
        self.db.execute("""
            UPDATE api_keys
            SET last_used = CURRENT_TIMESTAMP
            WHERE key_hash = ?
        """, (key_hash,))
        
        return json.loads(permissions)
    
    def revoke_key(self, key_hash):
        """Revoke API key."""
        self.db.execute("DELETE FROM api_keys WHERE key_hash = ?", (key_hash,))
```

### Request Validation

```python
from pydantic import BaseModel, validator

class OrderRequest(BaseModel):
    """Validated order request."""
    symbol: str
    side: str
    volume: float
    price: float = None
    
    @validator('symbol')
    def validate_symbol(cls, v):
        """Validate symbol format."""
        if not v or len(v) < 3:
            raise ValueError('Invalid symbol')
        # Check against whitelist
        allowed_symbols = ['EURUSD', 'GBPUSD', 'XAUUSD']
        if v not in allowed_symbols:
            raise ValueError(f'Symbol {v} not allowed')
        return v
    
    @validator('side')
    def validate_side(cls, v):
        """Validate order side."""
        if v not in ['BUY', 'SELL']:
            raise ValueError('Side must be BUY or SELL')
        return v
    
    @validator('volume')
    def validate_volume(cls, v):
        """Validate volume."""
        if v <= 0 or v > 10:
            raise ValueError('Volume must be between 0 and 10')
        return v

# Usage
try:
    request = OrderRequest(
        symbol='EURUSD',
        side='BUY',
        volume=0.1
    )
except ValueError as e:
    logger.error(f"Invalid request: {e}")
```

---

## Network Security

### Firewall Configuration

```bash
# Ubuntu/Debian UFW
sudo ufw enable

# Allow SSH
sudo ufw allow 22/tcp

# Allow RPC (local only)
sudo ufw allow from 127.0.0.1 to any port 8181

# Allow Prometheus (internal network only)
sudo ufw allow from 192.168.1.0/24 to any port 9090

# Deny all other incoming
sudo ufw default deny incoming
sudo ufw default allow outgoing
```

### TLS/SSL for RPC

Enable HTTPS for RPC server:

```python
import ssl
from http.server import HTTPServer, BaseHTTPRequestHandler

def create_secure_server(host='127.0.0.1', port=8181):
    """Create HTTPS server."""
    server = HTTPServer((host, port), RPCHandler)
    
    # Create SSL context
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('server.crt', 'server.key')
    
    # Wrap socket
    server.socket = context.wrap_socket(server.socket, server_side=True)
    
    return server

# Generate self-signed certificate (development only)
# openssl req -x509 -newkey rsa:4096 -keyout server.key -out server.crt -days 365 -nodes
```

### VPN for Remote Access

For remote access, use VPN instead of exposing ports:

```bash
# Install WireGuard
sudo apt install wireguard

# Generate keys
wg genkey | tee privatekey | wg pubkey > publickey

# Configure /etc/wireguard/wg0.conf
[Interface]
PrivateKey = <your_private_key>
Address = 10.0.0.1/24
ListenPort = 51820

[Peer]
PublicKey = <client_public_key>
AllowedIPs = 10.0.0.2/32

# Start VPN
sudo wg-quick up wg0
```

---

## Data Protection

### Database Encryption

Encrypt sensitive data at rest:

```python
from cryptography.fernet import Fernet

class EncryptedDatabase:
    """Database with encrypted fields."""
    
    def __init__(self, db_path, encryption_key):
        self.db = Database(db_path)
        self.cipher = Fernet(encryption_key)
    
    def insert_trade(self, trade):
        """Insert trade with encrypted sensitive fields."""
        # Encrypt sensitive fields
        encrypted_notes = self.cipher.encrypt(
            trade.notes.encode()
        ) if trade.notes else None
        
        self.db.execute("""
            INSERT INTO trades (ticket, symbol, volume, notes_encrypted)
            VALUES (?, ?, ?, ?)
        """, (trade.ticket, trade.symbol, trade.volume, encrypted_notes))
    
    def get_trade(self, ticket):
        """Retrieve trade with decrypted fields."""
        result = self.db.execute("""
            SELECT ticket, symbol, volume, notes_encrypted
            FROM trades WHERE ticket = ?
        """, (ticket,)).fetchone()
        
        if result:
            ticket, symbol, volume, notes_encrypted = result
            
            # Decrypt sensitive fields
            notes = self.cipher.decrypt(notes_encrypted).decode() \
                if notes_encrypted else None
            
            return Trade(
                ticket=ticket,
                symbol=symbol,
                volume=volume,
                notes=notes
            )
```

### Log Sanitization

Prevent sensitive data in logs:

```python
import re
import logging

class SanitizingFormatter(logging.Formatter):
    """Custom formatter that sanitizes sensitive data."""
    
    PATTERNS = [
        (re.compile(r'password["\']?\s*[:=]\s*["\']?([^"\'}\s]+)'), r'password=***'),
        (re.compile(r'api[_-]?key["\']?\s*[:=]\s*["\']?([^"\'}\s]+)'), r'api_key=***'),
        (re.compile(r'token["\']?\s*[:=]\s*["\']?([^"\'}\s]+)'), r'token=***'),
        (re.compile(r'\d{4,}'), r'****'),  # Mask account numbers
    ]
    
    def format(self, record):
        """Format log record with sanitization."""
        original = super().format(record)
        
        # Apply all patterns
        sanitized = original
        for pattern, replacement in self.PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        
        return sanitized

# Configure logger
handler = logging.StreamHandler()
handler.setFormatter(SanitizingFormatter())
logger.addHandler(handler)
```

### Secure File Permissions

```bash
# Set restrictive permissions on sensitive files
chmod 600 .env
chmod 600 config.json
chmod 600 Cthulu.db
chmod 600 *.key

# Set directory permissions
chmod 700 /opt/Cthulu/data
chmod 700 /opt/Cthulu/logs

# Verify permissions
ls -la .env
# Should show: -rw------- (owner read/write only)
```

---

## Access Control

### Role-Based Access Control (RBAC)

```python
from enum import Enum

class Role(Enum):
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"

class Permission(Enum):
    READ_POSITIONS = "read_positions"
    WRITE_POSITIONS = "write_positions"
    MODIFY_CONFIG = "modify_config"
    VIEW_LOGS = "view_logs"

ROLE_PERMISSIONS = {
    Role.ADMIN: [
        Permission.READ_POSITIONS,
        Permission.WRITE_POSITIONS,
        Permission.MODIFY_CONFIG,
        Permission.VIEW_LOGS
    ],
    Role.TRADER: [
        Permission.READ_POSITIONS,
        Permission.WRITE_POSITIONS,
        Permission.VIEW_LOGS
    ],
    Role.VIEWER: [
        Permission.READ_POSITIONS,
        Permission.VIEW_LOGS
    ]
}

def check_permission(user_role: Role, required_permission: Permission):
    """Check if role has permission."""
    permissions = ROLE_PERMISSIONS.get(user_role, [])
    if required_permission not in permissions:
        raise PermissionError(f"Role {user_role} lacks {required_permission}")

# Usage
def close_position(user_role, ticket):
    """Close position with permission check."""
    check_permission(user_role, Permission.WRITE_POSITIONS)
    # Proceed with closing position
    position_manager.close(ticket)
```

### Audit Logging

```python
import logging
from datetime import datetime

class AuditLogger:
    """Security audit logger."""
    
    def __init__(self, log_file='audit.log'):
        self.logger = logging.getLogger('audit')
        handler = logging.FileHandler(log_file)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s'
        ))
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def log_access(self, user, resource, action, result):
        """Log access attempt."""
        self.logger.info(f"ACCESS | {user} | {resource} | {action} | {result}")
    
    def log_config_change(self, user, field, old_value, new_value):
        """Log configuration change."""
        self.logger.info(
            f"CONFIG | {user} | {field} | {old_value} -> {new_value}"
        )
    
    def log_security_event(self, event_type, details):
        """Log security event."""
        self.logger.warning(f"SECURITY | {event_type} | {details}")

# Usage
audit = AuditLogger()
audit.log_access('admin', 'positions', 'close', 'success')
audit.log_security_event('failed_auth', 'Multiple failed login attempts')
```

---

## Monitoring & Auditing

### Security Monitoring

```python
class SecurityMonitor:
    """Monitor security events."""
    
    def __init__(self):
        self.failed_auth_attempts = {}
        self.suspicious_ips = set()
        self.max_failed_attempts = 5
    
    def record_failed_auth(self, user, ip):
        """Record failed authentication."""
        key = (user, ip)
        self.failed_auth_attempts[key] = \
            self.failed_auth_attempts.get(key, 0) + 1
        
        if self.failed_auth_attempts[key] >= self.max_failed_attempts:
            self.suspicious_ips.add(ip)
            self.alert_security_team(
                f"Multiple failed auth attempts from {ip} for user {user}"
            )
    
    def is_ip_suspicious(self, ip):
        """Check if IP is flagged as suspicious."""
        return ip in self.suspicious_ips
    
    def alert_security_team(self, message):
        """Send security alert."""
        # Send email, SMS, or push notification
        logger.critical(f"SECURITY ALERT: {message}")
```

### Regular Security Audits

```bash
#!/bin/bash
# security_audit.sh - Run regular security checks

echo "=== Cthulu Security Audit ==="
echo "Date: $(date)"
echo

# Check file permissions
echo "Checking file permissions..."
find /opt/Cthulu -type f -perm /go+w -ls

# Check for exposed credentials
echo "Checking for exposed credentials..."
grep -r "password\|api_key\|token" /opt/Cthulu/*.json 2>/dev/null || echo "OK"

# Check open ports
echo "Checking open ports..."
sudo netstat -tulpn | grep Cthulu

# Check for updates
echo "Checking for security updates..."
sudo apt list --upgradable 2>/dev/null | grep -i security

# Check logs for suspicious activity
echo "Checking logs for failed auth..."
grep -i "failed\|unauthorized" /opt/Cthulu/logs/*.log | tail -10

echo
echo "=== Audit Complete ==="
```

---

## Security Checklist

### Pre-Deployment

- [ ] All credentials stored in environment variables or encrypted
- [ ] `.env` file in `.gitignore`
- [ ] Secure file permissions (600 for sensitive files)
- [ ] SSL/TLS enabled for RPC
- [ ] Firewall configured
- [ ] Strong passwords (min 20 characters, mixed case, numbers, symbols)
- [ ] API keys rotated regularly
- [ ] Database encryption enabled

### Ongoing Maintenance

- [ ] Security updates applied monthly
- [ ] Credential rotation every 90 days
- [ ] Audit logs reviewed weekly
- [ ] Backups encrypted and tested
- [ ] Access logs monitored
- [ ] Security scans run monthly
- [ ] Dependency vulnerabilities checked

### Incident Response

- [ ] Incident response plan documented
- [ ] Security contacts identified
- [ ] Backup recovery tested
- [ ] Rollback procedure defined
- [ ] Communication plan established

---

## Emergency Procedures

### Security Breach Response

1. **Isolate**:  Immediately disconnect system from network
2. **Assess**: Determine scope of breach
3. **Rotate**: Change all credentials immediately
4. **Review**: Check audit logs for unauthorized access
5. **Restore**: Restore from clean backup if needed
6. **Notify**: Inform relevant parties
7. **Document**: Record incident details

### Credential Compromise

```bash
# Emergency credential rotation script
#!/bin/bash

echo "⚠️  EMERGENCY CREDENTIAL ROTATION"
read -p "Continue? (yes/no): " confirm

if [ "$confirm" = "yes" ]; then
    # Generate new credentials
    NEW_PASS=$(openssl rand -base64 24)
    
    echo "New password: $NEW_PASS"
    echo "1. Update password in MT5 terminal"
    echo "2. Update .env file"
    echo "3. Restart Cthulu"
    echo "4. Verify connection"
fi
```

---

## Tools & Resources

### Security Scanning

```bash
# Install security scanners
pip install safety bandit

# Scan dependencies for vulnerabilities
safety check

# Static code analysis for security issues
bandit -r /opt/Cthulu -f json -o security_report.json

# Check for secrets in git history
pip install detect-secrets
detect-secrets scan > .secrets.baseline
```

### Recommended Reading

- OWASP Top 10: https://owasp.org/www-project-top-ten/
- CIS Benchmarks: https://www.cisecurity.org/cis-benchmarks/
- NIST Cybersecurity Framework: https://www.nist.gov/cyberframework

---

**Last Updated**: December 2024  
**Version**: 3.3.1




