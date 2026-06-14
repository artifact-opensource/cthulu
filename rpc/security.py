"""
RPC Security Hardening Module

Provides:
- Intelligent rate limiting with adaptive thresholds
- IP-based access control with whitelist/blacklist
- Request validation and sanitization
- TLS configuration helpers
- Dependency scanning utilities
- Audit logging for all RPC operations
"""

import hashlib
import hmac
import json
import logging
import os
import re
import ssl
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger('cthulu.rpc.security')


class ThreatLevel(Enum):
    """Threat classification levels."""
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class RateLimitAction(Enum):
    """Actions when rate limit is exceeded."""
    REJECT = "reject"
    QUEUE = "queue"
    THROTTLE = "throttle"
    BLACKLIST = "blacklist"


@dataclass
class RateLimitConfig:
    """Configuration for intelligent rate limiting."""
    # Base limits
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_limit: int = 10
    burst_window_seconds: float = 1.0
    
    # Trading-specific limits
    trades_per_minute: int = 10
    trades_per_hour: int = 100
    max_volume_per_minute: float = 10.0  # Max total volume per minute
    
    # Adaptive settings
    adaptive_enabled: bool = True
    scale_down_threshold: float = 0.8  # Reduce limits at 80% utilization
    scale_up_threshold: float = 0.3    # Increase limits at 30% utilization
    min_scale_factor: float = 0.5
    max_scale_factor: float = 2.0
    
    # Penalty settings
    violation_threshold: int = 5       # Violations before blacklist
    violation_decay_minutes: int = 60  # Time for violations to decay
    blacklist_duration_minutes: int = 30
    
    # Action on limit exceed
    exceed_action: RateLimitAction = RateLimitAction.REJECT


@dataclass 
class SecurityConfig:
    """Comprehensive RPC security configuration."""
    # Authentication
    require_auth: bool = True
    token_hash_algorithm: str = "sha256"
    token_min_length: int = 32
    
    # IP Access Control
    ip_whitelist: List[str] = field(default_factory=lambda: ["127.0.0.1", "::1"])
    ip_blacklist: List[str] = field(default_factory=list)
    allow_private_networks: bool = True
    
    # TLS Configuration
    tls_enabled: bool = False
    tls_cert_path: Optional[str] = None
    tls_key_path: Optional[str] = None
    tls_min_version: str = "TLSv1.2"
    
    # Request Validation
    max_request_size_bytes: int = 65536  # 64KB
    max_symbol_length: int = 20
    allowed_symbols_pattern: str = r"^[A-Z0-9#]+$"
    max_volume: float = 100.0
    min_volume: float = 0.01
    
    # Rate Limiting
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    
    # Audit
    audit_enabled: bool = True
    audit_log_path: str = "logs/rpc_audit.log"
    audit_sensitive_fields: List[str] = field(default_factory=lambda: ["password", "token", "secret"])


@dataclass
class ClientState:
    """Track state for each client/IP."""
    ip: str
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    request_times: List[datetime] = field(default_factory=list)
    trade_times: List[datetime] = field(default_factory=list)
    trade_volumes: List[float] = field(default_factory=list)
    violations: int = 0
    last_violation: Optional[datetime] = None
    blacklisted_until: Optional[datetime] = None
    threat_level: ThreatLevel = ThreatLevel.NONE
    scale_factor: float = 1.0


class IntelligentRateLimiter:
    """
    Adaptive rate limiter with trading-aware throttling.
    
    Features:
    - Per-client tracking with memory decay
    - Burst detection and prevention
    - Volume-based limiting for trades
    - Adaptive scaling based on system load
    - Automatic blacklisting for abuse
    """
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.clients: Dict[str, ClientState] = {}
        self.lock = RLock()
        self._global_request_count = 0
        self._last_cleanup = datetime.now()
        
    def check_request(self, client_ip: str, is_trade: bool = False, volume: float = 0.0) -> Tuple[bool, str]:
        """
        Check if request should be allowed.
        
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        with self.lock:
            self._cleanup_old_data()
            
            client = self._get_or_create_client(client_ip)
            now = datetime.now()
            
            # Check blacklist
            if client.blacklisted_until and now < client.blacklisted_until:
                remaining = (client.blacklisted_until - now).total_seconds()
                return False, f"Blacklisted for {remaining:.0f}s more"
            elif client.blacklisted_until:
                # Blacklist expired
                client.blacklisted_until = None
                client.violations = max(0, client.violations - 2)
            
            # Decay violations over time
            if client.last_violation:
                decay_time = timedelta(minutes=self.config.violation_decay_minutes)
                if now - client.last_violation > decay_time:
                    client.violations = max(0, client.violations - 1)
                    client.last_violation = now if client.violations > 0 else None
            
            # Calculate effective limits with scaling
            effective_rpm = int(self.config.requests_per_minute * client.scale_factor)
            effective_rph = int(self.config.requests_per_hour * client.scale_factor)
            effective_burst = int(self.config.burst_limit * client.scale_factor)
            
            # Check burst limit (requests in last burst_window)
            burst_cutoff = now - timedelta(seconds=self.config.burst_window_seconds)
            burst_count = sum(1 for t in client.request_times if t > burst_cutoff)
            if burst_count >= effective_burst:
                self._record_violation(client)
                return False, f"Burst limit exceeded ({burst_count}/{effective_burst})"
            
            # Check per-minute limit
            minute_cutoff = now - timedelta(minutes=1)
            minute_count = sum(1 for t in client.request_times if t > minute_cutoff)
            if minute_count >= effective_rpm:
                self._record_violation(client)
                return False, f"Per-minute limit exceeded ({minute_count}/{effective_rpm})"
            
            # Check per-hour limit
            hour_cutoff = now - timedelta(hours=1)
            hour_count = sum(1 for t in client.request_times if t > hour_cutoff)
            if hour_count >= effective_rph:
                self._record_violation(client)
                return False, f"Per-hour limit exceeded ({hour_count}/{effective_rph})"
            
            # Trading-specific checks
            if is_trade:
                trade_minute_count = sum(1 for t in client.trade_times if t > minute_cutoff)
                if trade_minute_count >= self.config.trades_per_minute:
                    self._record_violation(client)
                    return False, f"Trade per-minute limit exceeded ({trade_minute_count}/{self.config.trades_per_minute})"
                
                trade_hour_count = sum(1 for t in client.trade_times if t > hour_cutoff)
                if trade_hour_count >= self.config.trades_per_hour:
                    self._record_violation(client)
                    return False, f"Trade per-hour limit exceeded ({trade_hour_count}/{self.config.trades_per_hour})"
                
                # Volume check
                minute_volume = sum(v for t, v in zip(client.trade_times, client.trade_volumes) if t > minute_cutoff)
                if minute_volume + volume > self.config.max_volume_per_minute:
                    self._record_violation(client)
                    return False, f"Volume limit exceeded ({minute_volume + volume:.2f}/{self.config.max_volume_per_minute})"
                
                # Record trade
                client.trade_times.append(now)
                client.trade_volumes.append(volume)
            
            # Record request
            client.request_times.append(now)
            client.last_seen = now
            self._global_request_count += 1
            
            # Adaptive scaling
            if self.config.adaptive_enabled:
                self._adjust_scale_factor(client)
            
            return True, "OK"
    
    def _get_or_create_client(self, ip: str) -> ClientState:
        """Get or create client state."""
        if ip not in self.clients:
            self.clients[ip] = ClientState(ip=ip)
        return self.clients[ip]
    
    def _record_violation(self, client: ClientState):
        """Record a rate limit violation."""
        client.violations += 1
        client.last_violation = datetime.now()
        
        # Update threat level
        if client.violations >= self.config.violation_threshold:
            client.threat_level = ThreatLevel.HIGH
            # Blacklist
            client.blacklisted_until = datetime.now() + timedelta(
                minutes=self.config.blacklist_duration_minutes
            )
            logger.warning(f"Client {client.ip} blacklisted for {self.config.blacklist_duration_minutes}m "
                          f"after {client.violations} violations")
        elif client.violations >= 3:
            client.threat_level = ThreatLevel.MEDIUM
        elif client.violations >= 1:
            client.threat_level = ThreatLevel.LOW
    
    def _adjust_scale_factor(self, client: ClientState):
        """Dynamically adjust rate limits based on behavior."""
        now = datetime.now()
        minute_cutoff = now - timedelta(minutes=1)
        
        # Calculate utilization
        minute_count = sum(1 for t in client.request_times if t > minute_cutoff)
        utilization = minute_count / self.config.requests_per_minute
        
        # Scale based on utilization
        if utilization > self.config.scale_down_threshold:
            # High utilization - tighten limits
            client.scale_factor = max(
                self.config.min_scale_factor,
                client.scale_factor * 0.9
            )
        elif utilization < self.config.scale_up_threshold and client.violations == 0:
            # Low utilization and good behavior - relax limits
            client.scale_factor = min(
                self.config.max_scale_factor,
                client.scale_factor * 1.1
            )
    
    def _cleanup_old_data(self):
        """Periodically clean up old request data."""
        now = datetime.now()
        if now - self._last_cleanup < timedelta(minutes=5):
            return
        
        self._last_cleanup = now
        hour_cutoff = now - timedelta(hours=2)
        
        for client in self.clients.values():
            client.request_times = [t for t in client.request_times if t > hour_cutoff]
            client.trade_times = [t for t in client.trade_times if t > hour_cutoff]
            # Keep volumes aligned with trade times
            if len(client.trade_volumes) > len(client.trade_times):
                client.trade_volumes = client.trade_volumes[-len(client.trade_times):]
    
    def get_client_stats(self, client_ip: str) -> Dict[str, Any]:
        """Get statistics for a client."""
        with self.lock:
            if client_ip not in self.clients:
                return {"exists": False}
            
            client = self.clients[client_ip]
            now = datetime.now()
            minute_cutoff = now - timedelta(minutes=1)
            
            return {
                "exists": True,
                "ip": client.ip,
                "first_seen": client.first_seen.isoformat(),
                "last_seen": client.last_seen.isoformat(),
                "requests_last_minute": sum(1 for t in client.request_times if t > minute_cutoff),
                "trades_last_minute": sum(1 for t in client.trade_times if t > minute_cutoff),
                "violations": client.violations,
                "threat_level": client.threat_level.name,
                "scale_factor": client.scale_factor,
                "blacklisted": client.blacklisted_until is not None and now < client.blacklisted_until
            }
    
    def get_global_stats(self) -> Dict[str, Any]:
        """Get global rate limiter statistics."""
        with self.lock:
            return {
                "total_clients": len(self.clients),
                "global_requests": self._global_request_count,
                "blacklisted_count": sum(
                    1 for c in self.clients.values()
                    if c.blacklisted_until and datetime.now() < c.blacklisted_until
                ),
                "high_threat_count": sum(
                    1 for c in self.clients.values()
                    if c.threat_level == ThreatLevel.HIGH
                )
            }


class RequestValidator:
    """Validates and sanitizes RPC requests."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self._symbol_pattern = re.compile(config.allowed_symbols_pattern)
    
    def validate_trade_request(self, payload: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate a trade request payload.
        
        Returns:
            Tuple of (valid: bool, error_message: str, sanitized_payload: dict)
        """
        errors = []
        sanitized = {}
        
        # Symbol validation
        symbol_raw = str(payload.get('symbol', '')).strip()
        symbol = symbol_raw.upper()
        if not symbol_raw:
            errors.append("Missing required field: symbol")
        elif len(symbol) > self.config.max_symbol_length:
            errors.append(f"Symbol too long (max {self.config.max_symbol_length})")
        elif not self._symbol_pattern.match(symbol):
            errors.append(f"Invalid symbol format: {symbol_raw}")
        else:
            sanitized['symbol'] = symbol
        
        # Side validation
        side = payload.get('side', '').upper().strip()
        if side not in ('BUY', 'SELL'):
            errors.append("Side must be 'BUY' or 'SELL'")
        else:
            sanitized['side'] = side
        
        # Volume validation
        try:
            volume = float(payload.get('volume', 0))
            if volume < self.config.min_volume:
                errors.append(f"Volume too small (min {self.config.min_volume})")
            elif volume > self.config.max_volume:
                errors.append(f"Volume too large (max {self.config.max_volume})")
            else:
                sanitized['volume'] = volume
        except (TypeError, ValueError):
            errors.append("Volume must be a valid number")
        
        # Optional price validation
        if 'price' in payload and payload['price'] is not None:
            try:
                price = float(payload['price'])
                if price <= 0:
                    errors.append("Price must be positive")
                else:
                    sanitized['price'] = price
            except (TypeError, ValueError):
                errors.append("Price must be a valid number")
        
        # Optional SL/TP validation
        for field in ('sl', 'tp'):
            if field in payload and payload[field] is not None:
                try:
                    value = float(payload[field])
                    if value < 0:
                        errors.append(f"{field.upper()} cannot be negative")
                    else:
                        sanitized[field] = value
                except (TypeError, ValueError):
                    errors.append(f"{field.upper()} must be a valid number")
        
        # Signal ID sanitization
        if 'signal_id' in payload:
            signal_id = str(payload['signal_id'])[:100]  # Limit length
            signal_id = re.sub(r'[^a-zA-Z0-9_-]', '', signal_id)  # Alphanumeric only
            sanitized['signal_id'] = signal_id
        
        if errors:
            return False, "; ".join(errors), {}
        
        return True, "", sanitized


class IPAccessController:
    """IP-based access control with whitelist/blacklist."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self._whitelist: Set[str] = set(config.ip_whitelist)
        self._blacklist: Set[str] = set(config.ip_blacklist)
        self._dynamic_blacklist: Dict[str, datetime] = {}
        self.lock = Lock()
        
        # Private network ranges (IPv4)
        self._private_ranges = [
            ('10.0.0.0', '10.255.255.255'),
            ('172.16.0.0', '172.31.255.255'),
            ('192.168.0.0', '192.168.255.255'),
            ('127.0.0.0', '127.255.255.255'),
        ]
    
    def is_allowed(self, ip: str) -> Tuple[bool, str]:
        """
        Check if IP is allowed access.
        
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        with self.lock:
            # Check static blacklist first
            if ip in self._blacklist:
                return False, "IP in blacklist"
            
            # Check dynamic blacklist
            if ip in self._dynamic_blacklist:
                expiry = self._dynamic_blacklist[ip]
                if datetime.now() < expiry:
                    return False, "IP temporarily blacklisted"
                else:
                    del self._dynamic_blacklist[ip]
            
            # Check whitelist
            if self._whitelist:
                if ip in self._whitelist:
                    return True, "IP in whitelist"
                
                # Check if private network and allowed
                if self.config.allow_private_networks and self._is_private_ip(ip):
                    return True, "Private network allowed"
                
                return False, "IP not in whitelist"
            
            # No whitelist = allow all non-blacklisted
            return True, "OK"
    
    def _is_private_ip(self, ip: str) -> bool:
        """Check if IP is in private network range."""
        try:
            parts = [int(p) for p in ip.split('.')]
            if len(parts) != 4:
                return False
            
            ip_num = (parts[0] << 24) + (parts[1] << 16) + (parts[2] << 8) + parts[3]
            
            for start, end in self._private_ranges:
                start_parts = [int(p) for p in start.split('.')]
                end_parts = [int(p) for p in end.split('.')]
                
                start_num = (start_parts[0] << 24) + (start_parts[1] << 16) + (start_parts[2] << 8) + start_parts[3]
                end_num = (end_parts[0] << 24) + (end_parts[1] << 16) + (end_parts[2] << 8) + end_parts[3]
                
                if start_num <= ip_num <= end_num:
                    return True
            
            return False
        except Exception:
            return False
    
    def add_to_blacklist(self, ip: str, duration_minutes: int = 30):
        """Dynamically blacklist an IP."""
        with self.lock:
            self._dynamic_blacklist[ip] = datetime.now() + timedelta(minutes=duration_minutes)
            logger.warning(f"IP {ip} dynamically blacklisted for {duration_minutes}m")
    
    def remove_from_blacklist(self, ip: str):
        """Remove IP from dynamic blacklist."""
        with self.lock:
            if ip in self._dynamic_blacklist:
                del self._dynamic_blacklist[ip]
    
    def add_to_whitelist(self, ip: str):
        """Add IP to whitelist."""
        with self.lock:
            self._whitelist.add(ip)
    
    def remove_from_whitelist(self, ip: str):
        """Remove IP from whitelist."""
        with self.lock:
            self._whitelist.discard(ip)


class AuditLogger:
    """Audit logging for RPC operations."""
    
    def __init__(self, config: SecurityConfig):
        self.config = config
        self._audit_logger: Optional[logging.Logger] = None
        self._setup_audit_logger()
    
    def _setup_audit_logger(self):
        """Set up dedicated audit logger."""
        if not self.config.audit_enabled:
            return
        
        try:
            # Ensure log directory exists
            log_path = Path(self.config.audit_log_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Create dedicated audit logger
            self._audit_logger = logging.getLogger('cthulu.rpc.audit')
            self._audit_logger.setLevel(logging.INFO)
            
            # File handler with rotation
            handler = logging.FileHandler(str(log_path), encoding='utf-8')
            handler.setFormatter(logging.Formatter(
                '%(asctime)s [AUDIT] %(message)s',
                datefmt='%Y-%m-%dT%H:%M:%S'
            ))
            
            # Avoid duplicate handlers
            if not self._audit_logger.handlers:
                self._audit_logger.addHandler(handler)
            
        except PermissionError as e:
            logger.error(f"Failed to setup audit logger at '{self.config.audit_log_path}': {e}")
            # Try per-user fallback location
            try:
                fallback_base = Path(os.getenv('LOCALAPPDATA') or Path.home()) / 'cthulu' / 'logs'
                fallback_base.mkdir(parents=True, exist_ok=True)
                fallback_path = fallback_base / Path(self.config.audit_log_path).name
                handler = logging.FileHandler(str(fallback_path), encoding='utf-8')
                handler.setFormatter(logging.Formatter(
                    '%(asctime)s [AUDIT] %(message)s',
                    datefmt='%Y-%m-%dT%H:%M:%S'
                ))
                if not self._audit_logger.handlers:
                    self._audit_logger.addHandler(handler)
                logger.info(f"Switched audit log to user-local path: {fallback_path}")
            except Exception as e2:
                logger.error(f"Fallback audit logger init failed: {e2}")
        except Exception as e:
            logger.error(f"Failed to setup audit logger: {e}")
    
    def log_request(
        self,
        client_ip: str,
        endpoint: str,
        method: str,
        payload: Optional[Dict] = None,
        result: str = "success",
        details: Optional[str] = None
    ):
        """Log an RPC request."""
        if not self._audit_logger:
            return
        
        # Sanitize payload - remove sensitive fields
        sanitized_payload = {}
        if payload:
            for key, value in payload.items():
                if key.lower() in self.config.audit_sensitive_fields:
                    sanitized_payload[key] = "***REDACTED***"
                else:
                    sanitized_payload[key] = value
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "client_ip": client_ip,
            "endpoint": endpoint,
            "method": method,
            "result": result,
            "payload_size": len(json.dumps(payload)) if payload else 0,
        }
        
        if details:
            log_entry["details"] = details
        
        if sanitized_payload:
            log_entry["payload"] = sanitized_payload
        
        self._audit_logger.info(json.dumps(log_entry))
    
    def log_security_event(
        self,
        event_type: str,
        client_ip: str,
        severity: ThreatLevel,
        details: str
    ):
        """Log a security event."""
        if not self._audit_logger:
            return
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "client_ip": client_ip,
            "severity": severity.name,
            "details": details
        }
        
        self._audit_logger.warning(json.dumps(log_entry))


class TLSHelper:
    """Helper for TLS configuration."""
    
    @staticmethod
    def create_ssl_context(config: SecurityConfig) -> Optional[ssl.SSLContext]:
        """Create SSL context for TLS-enabled server."""
        if not config.tls_enabled:
            return None
        
        if not config.tls_cert_path or not config.tls_key_path:
            logger.warning("TLS enabled but cert/key paths not configured")
            return None
        
        try:
            # Map version string to SSL constant
            version_map = {
                "TLSv1.2": ssl.TLSVersion.TLSv1_2,
                "TLSv1.3": ssl.TLSVersion.TLSv1_3,
            }
            
            min_version = version_map.get(config.tls_min_version, ssl.TLSVersion.TLSv1_2)
            
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = min_version
            context.load_cert_chain(config.tls_cert_path, config.tls_key_path)
            
            # Security settings
            context.set_ciphers('ECDHE+AESGCM:DHE+AESGCM:ECDHE+CHACHA20:DHE+CHACHA20')
            context.options |= ssl.OP_NO_COMPRESSION
            
            logger.info(f"TLS context created with min version {config.tls_min_version}")
            return context
            
        except Exception as e:
            logger.error(f"Failed to create TLS context: {e}")
            return None


class DependencyScanner:
    """Scan for known vulnerable dependencies."""
    
    KNOWN_VULNERABILITIES = {
        # Package: [(vulnerable_versions, severity, CVE)]
        "requests": [
            (["<2.31.0"], "HIGH", "CVE-2023-32681"),
        ],
        "urllib3": [
            (["<2.0.6"], "MEDIUM", "CVE-2023-45803"),
        ],
        "cryptography": [
            (["<41.0.0"], "HIGH", "CVE-2023-38325"),
        ],
    }
    
    @staticmethod
    def scan_requirements(requirements_path: str = "requirements.txt") -> List[Dict[str, Any]]:
        """Scan requirements file for known vulnerabilities."""
        vulnerabilities = []
        
        try:
            req_path = Path(requirements_path)
            if not req_path.exists():
                logger.warning(f"Requirements file not found: {requirements_path}")
                return vulnerabilities
            
            with open(req_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse package name and version
                    match = re.match(r'^([a-zA-Z0-9_-]+)([<>=!]+)?(.+)?$', line)
                    if not match:
                        continue
                    
                    package = match.group(1).lower()
                    version_spec = match.group(3) or ""
                    
                    if package in DependencyScanner.KNOWN_VULNERABILITIES:
                        for vuln_versions, severity, cve in DependencyScanner.KNOWN_VULNERABILITIES[package]:
                            vulnerabilities.append({
                                "package": package,
                                "installed_spec": line,
                                "vulnerable_versions": vuln_versions,
                                "severity": severity,
                                "cve": cve,
                                "recommendation": f"Upgrade {package} to latest version"
                            })
            
        except Exception as e:
            logger.error(f"Error scanning dependencies: {e}")
        
        return vulnerabilities
    
    @staticmethod
    def scan_installed() -> List[Dict[str, Any]]:
        """Scan installed packages for vulnerabilities."""
        vulnerabilities = []
        
        try:
            import pkg_resources
            
            for package, vulns in DependencyScanner.KNOWN_VULNERABILITIES.items():
                try:
                    installed = pkg_resources.get_distribution(package)
                    installed_version = installed.version
                    
                    for vuln_versions, severity, cve in vulns:
                        # Check if installed version matches vulnerable pattern
                        for vuln_pattern in vuln_versions:
                            if vuln_pattern.startswith('<'):
                                threshold = vuln_pattern[1:]
                                if pkg_resources.parse_version(installed_version) < pkg_resources.parse_version(threshold):
                                    vulnerabilities.append({
                                        "package": package,
                                        "installed_version": installed_version,
                                        "vulnerable_versions": vuln_versions,
                                        "severity": severity,
                                        "cve": cve,
                                        "recommendation": f"Upgrade {package} to {threshold} or later"
                                    })
                                    
                except pkg_resources.DistributionNotFound:
                    pass
                    
        except ImportError:
            logger.warning("pkg_resources not available for dependency scanning")
        except Exception as e:
            logger.error(f"Error scanning installed packages: {e}")
        
        return vulnerabilities


class RPCSecurityManager:
    """
    Central security manager for RPC operations.
    
    Combines all security components into unified interface.
    """
    
    def __init__(self, config: Optional[SecurityConfig] = None):
        self.config = config or SecurityConfig()
        
        # Initialize components
        self.rate_limiter = IntelligentRateLimiter(self.config.rate_limit)
        self.validator = RequestValidator(self.config)
        self.ip_controller = IPAccessController(self.config)
        self.audit = AuditLogger(self.config)
        self.tls_context = TLSHelper.create_ssl_context(self.config)
        
        logger.info("RPC Security Manager initialized")
    
    def check_request(
        self,
        client_ip: str,
        endpoint: str,
        method: str,
        payload: Optional[Dict] = None,
        is_trade: bool = False,
        volume: float = 0.0
    ) -> Tuple[bool, str]:
        """
        Perform comprehensive security check on request.
        
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # IP access check
        ip_allowed, ip_reason = self.ip_controller.is_allowed(client_ip)
        if not ip_allowed:
            self.audit.log_security_event(
                "IP_BLOCKED", client_ip, ThreatLevel.MEDIUM, ip_reason
            )
            return False, ip_reason
        
        # Rate limit check
        rate_allowed, rate_reason = self.rate_limiter.check_request(
            client_ip, is_trade=is_trade, volume=volume
        )
        if not rate_allowed:
            self.audit.log_security_event(
                "RATE_LIMITED", client_ip, ThreatLevel.LOW, rate_reason
            )
            return False, rate_reason
        
        # Validate payload if trade request
        if is_trade and payload:
            valid, error, _ = self.validator.validate_trade_request(payload)
            if not valid:
                self.audit.log_security_event(
                    "INVALID_REQUEST", client_ip, ThreatLevel.LOW, error
                )
                return False, error
        
        # Log successful request
        self.audit.log_request(
            client_ip, endpoint, method, payload, "allowed"
        )
        
        return True, "OK"
    
    def validate_and_sanitize(self, payload: Dict) -> Tuple[bool, str, Dict]:
        """Validate and sanitize trade payload."""
        return self.validator.validate_trade_request(payload)
    
    def get_security_stats(self) -> Dict[str, Any]:
        """Get comprehensive security statistics."""
        return {
            "rate_limiter": self.rate_limiter.get_global_stats(),
            "tls_enabled": self.tls_context is not None,
            "config": {
                "require_auth": self.config.require_auth,
                "ip_whitelist_count": len(self.config.ip_whitelist),
                "ip_blacklist_count": len(self.config.ip_blacklist),
                "max_request_size": self.config.max_request_size_bytes,
                "rate_limits": {
                    "requests_per_minute": self.config.rate_limit.requests_per_minute,
                    "trades_per_minute": self.config.rate_limit.trades_per_minute,
                    "burst_limit": self.config.rate_limit.burst_limit
                }
            }
        }
    
    def scan_dependencies(self) -> List[Dict]:
        """Scan for dependency vulnerabilities."""
        return DependencyScanner.scan_installed()


# Singleton instance for easy access
_security_manager: Optional[RPCSecurityManager] = None


def get_security_manager(config: Optional[SecurityConfig] = None) -> RPCSecurityManager:
    """Get or create the global security manager instance."""
    global _security_manager
    if _security_manager is None:
        _security_manager = RPCSecurityManager(config)
    return _security_manager


def reset_security_manager():
    """Reset the global security manager (for testing)."""
    global _security_manager
    _security_manager = None
