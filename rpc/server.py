"""Lightweight RPC server for controlling Cthulu at runtime.

Provides a minimal POST /trade endpoint protected by a bearer token.
Designed to be local-only (binds to 127.0.0.1 by default) and dependency-free (uses http.server).

Security Features (v6.0.0):
- Intelligent rate limiting with adaptive thresholds
- IP whitelist/blacklist with automatic threat detection
- Request validation and sanitization
- Comprehensive audit logging
- Optional TLS support
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
# Use ThreadingHTTPServer when available to handle concurrent requests without blocking
try:
    from http.server import ThreadingHTTPServer
except Exception:
    ThreadingHTTPServer = HTTPServer
import json
import logging
from urllib.parse import urlparse
from threading import Thread
from typing import Optional, Dict, Any
import socket  # used for request read timeouts and socket exceptions

logger = logging.getLogger('cthulu.rpc')

# Import security manager
try:
    from cthulu.rpc.security import (
        RPCSecurityManager, SecurityConfig, RateLimitConfig,
        get_security_manager, ThreatLevel
    )
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False
    logger.warning("RPC security module not available - running without hardening")


class RPCRequestHandler(BaseHTTPRequestHandler):
    # These class members will be set when the server is created by run_rpc_server
    token: Optional[str] = None
    execution_engine = None
    risk_manager = None
    position_manager = None
    database = None
    security_manager: Optional['RPCSecurityManager'] = None
    security_config: Optional[Dict[str, Any]] = None
    # Optional Ops controller passed by orchestrator to allow safe operational commands
    ops_controller = None
    # Confirmation tokens for two-step command execution: token -> {expires, payload, user}
    confirmation_store: Dict[str, Dict[str, Any]] = {}

    def _send_json(self, status_code: int, payload: dict):
        body = json.dumps(payload).encode('utf-8')
        try:
            self.send_response(status_code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except (ConnectionResetError, BrokenPipeError):
            # Client disconnected early; silently ignore
            pass

    def _unauthorized(self, msg='Unauthorized'):
        self._send_json(401, {'error': msg})

    def _bad_request(self, msg='Bad Request'):
        self._send_json(400, {'error': msg})

    def do_POST(self):
        parsed = urlparse(self.path)
        client_ip = self.client_address[0]
        # Prevent handlers blocking indefinitely when client doesn't send the body
        try:
            # short read timeout to fail quickly and free the worker thread
            self.connection.settimeout(15)
        except Exception:
            # best-effort only
            pass
        logger.debug('RPC request received: %s from %s', parsed.path, client_ip)  # entry log for tracing
        
        # Security check if security manager is available
        if self.security_manager:
            # Read body for security checks
            length = int(self.headers.get('Content-Length', 0))
            
            # Check request size limit
            max_size = self.security_manager.config.max_request_size_bytes
            if length > max_size:
                logger.warning(f"Request too large from {client_ip}: {length} > {max_size}")
                self._send_json(413, {'error': f'Request too large (max {max_size} bytes)'})
                return
            
            # Read body with timeout handling to avoid blocking the worker
            try:
                raw = self.rfile.read(length) if length > 0 else b''
            except socket.timeout:
                logger.warning('RPC request from %s timed out while reading body', client_ip)
                self._send_json(408, {'error': 'Request read timeout'})
                return
            except Exception as e:
                logger.warning('Failed reading request body from %s: %s', client_ip, e)
                self._bad_request('Invalid JSON')
                return

            try:
                payload = json.loads(raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw)
            except Exception as e:
                logger.warning('Invalid JSON from %s: %s', client_ip, e)
                self._bad_request('Invalid JSON')
                return
            
            # Determine volume for rate limiting (robust parsing)
            raw_volume = payload.get('volume', 0)
            try:
                volume = float(raw_volume) if raw_volume is not None and raw_volume != '' else 0.0
            except (TypeError, ValueError):
                volume = 0.0
            
            # Comprehensive security check
            allowed, reason = self.security_manager.check_request(
                client_ip=client_ip,
                endpoint=parsed.path,
                method='POST',
                payload=payload,
                is_trade=(parsed.path == '/trade'),
                volume=volume
            )
            
            if not allowed:
                logger.warning(f"Request blocked from {client_ip}: {reason}")
                # Map validation-type reasons to 400, rate-limit to 429, otherwise 403
                reason_lower = reason.lower() if isinstance(reason, str) else ''
                if 'limit' in reason_lower:
                    status_code = 429
                elif any(k in reason_lower for k in ('missing', 'invalid', 'volume', 'price', 'symbol', 'side')):
                    status_code = 400
                else:
                    status_code = 403
                self._send_json(status_code, {'error': reason})
                return
            
            # Validate and sanitize payload for trade requests
            if parsed.path == '/trade':
                valid, error, sanitized = self.security_manager.validate_and_sanitize(payload)
                if not valid:
                    self._bad_request(error)
                    return
                # Use sanitized payload
                payload = {**payload, **sanitized}
        else:
            # No security manager - original behavior
            length = int(self.headers.get('Content-Length', 0))
            try:
                raw = self.rfile.read(length)
                payload = json.loads(raw.decode('utf-8') if isinstance(raw, (bytes, bytearray)) else raw)
            except Exception as e:
                logger.exception('Failed to parse JSON body')
                self._bad_request('Invalid JSON')
                return
        
        # Allow ops command POSTs in addition to /trade
        if parsed.path == '/ops/command':
            # Authenticate
            auth = self.headers.get('Authorization')
            api_key = self.headers.get('X-Api-Key')
            if self.token:
                if auth and auth.startswith('Bearer '):
                    token = auth.split(' ', 1)[1].strip()
                else:
                    token = api_key
                if not token or token != self.token:
                    self._unauthorized('Invalid or missing API token')
                    if self.security_manager:
                        self.security_manager.audit.log_security_event(
                            "AUTH_FAILED", client_ip, ThreatLevel.MEDIUM if SECURITY_AVAILABLE else None,
                            "Invalid or missing token for ops command"
                        )
                    return

            # Extract command
            cmd = payload.get('command')
            component = payload.get('component')
            params = payload.get('params', {})
            confirm_token = payload.get('confirm_token')
            actor = None
            # Determine actor from Authorization hint or headers if available
            if auth and auth.startswith('Bearer '):
                actor = f"bearer:{auth.split(' ',1)[1][:8]}"
            else:
                actor = client_ip

            # Two-step confirmation: create token if not provided
            if not confirm_token:
                # Create short-lived confirmation token
                import uuid, time
                token_val = f"confirm_{uuid.uuid4().hex[:12]}"
                expires_in = 60
                RPCRequestHandler.confirmation_store[token_val] = {
                    'expires': time.time() + expires_in,
                    'payload': {'command': cmd, 'component': component, 'params': params},
                    'actor': actor,
                }
                if self.security_manager:
                    self.security_manager.audit.log_security_event(
                        "OPS_CMD_PENDING", client_ip, ThreatLevel.MEDIUM if SECURITY_AVAILABLE else None,
                        f"Pending ops command {cmd} on {component} by {actor} (token={token_val[:8]})"
                    )
                self._send_json(200, {'requires_confirmation': True, 'confirm_token': token_val, 'expires_in': expires_in})
                return

            # Confirmation token provided — validate
            store = RPCRequestHandler.confirmation_store.get(confirm_token)
            import time
            if not store:
                self._bad_request('Invalid or expired confirmation token')
                return
            if time.time() > store.get('expires', 0):
                del RPCRequestHandler.confirmation_store[confirm_token]
                self._bad_request('Invalid or expired confirmation token')
                return

            # Execute the command if ops_controller present
            try:
                if not self.ops_controller:
                    self._send_json(501, {'error': 'Ops controller not available on server'})
                    return
                # Perform the command; ops_controller.perform_command returns dict
                res = self.ops_controller.perform_command(cmd, component, params, actor)
                if self.security_manager:
                    self.security_manager.audit.log_security_event(
                        "OPS_CMD_EXECUTED", client_ip, ThreatLevel.MEDIUM if SECURITY_AVAILABLE else None,
                        f"Executed ops command {cmd} on {component} by {actor}"
                    )
                # Remove used token
                try:
                    del RPCRequestHandler.confirmation_store[confirm_token]
                except Exception as e:
                    logger.debug("Failed to remove confirmation token: %s", e, exc_info=True)
                self._send_json(200, {'result': res})
                return
            except Exception as e:
                logger.exception('Failed to execute ops command')
                self._send_json(500, {'error': 'Failed to execute command'})
                return

        if parsed.path != '/trade':
            self._bad_request('Unknown endpoint')
            return

        # Authenticate with Bearer token or X-Api-Key header
        auth = self.headers.get('Authorization')
        api_key = self.headers.get('X-Api-Key')
        if self.token:
            if auth and auth.startswith('Bearer '):
                token = auth.split(' ', 1)[1].strip()
            else:
                token = api_key
            if not token or token != self.token:
                self._unauthorized('Invalid or missing API token')
                if self.security_manager:
                    self.security_manager.audit.log_security_event(
                        "AUTH_FAILED", client_ip, ThreatLevel.MEDIUM if SECURITY_AVAILABLE else None,
                        "Invalid or missing token"
                    )
                return

        # Validate minimal fields
        symbol = payload.get('symbol')
        side = payload.get('side')
        volume = payload.get('volume')
        price = payload.get('price', None)
        sl = payload.get('sl', None)
        tp = payload.get('tp', None)

        if not symbol or side not in ('BUY', 'SELL') or (volume is None):
            self._bad_request('Missing or invalid fields: require symbol, side(BUY/SELL), volume')
            return

        try:
            volume = float(volume)
        except Exception:
            self._bad_request('volume must be numeric')
            return

        # Validate against symbol-specific trading limits (min lot / step) when connector available
        connector = getattr(self.execution_engine, 'connector', None)
        if connector:
            try:
                sym_min = connector.get_min_lot(symbol)
                sym_info = connector.get_symbol_info(symbol) or {}
                sym_step = sym_info.get('volume_step')
            except Exception as e:
                logger.debug('Failed to fetch symbol limits from connector for %s: %s', symbol, e, exc_info=True)
                sym_min = None
                sym_step = None

            # Auto-adjust volume up to symbol min and nearest step when possible
            try:
                if sym_min is not None:
                    minf = float(sym_min)
                    if volume < minf:
                        # keep record of original requested volume
                        payload['requested_volume'] = volume
                        # compute adjusted volume (respect step if available)
                        adjusted = minf
                        if sym_step:
                            try:
                                stepf = float(sym_step)
                                multiplier = round(adjusted / stepf)
                                adjusted = round(max(stepf, multiplier * stepf), 8)
                            except Exception:
                                pass
                        logger.info('Adjusted RPC requested volume for %s: %s -> %s (min=%s, step=%s)', symbol, payload['requested_volume'], adjusted, sym_min, sym_step)
                        volume = float(adjusted)
                # Then ensure volume is a multiple of step (round to nearest valid step)
                if sym_step:
                    try:
                        stepf = float(sym_step)
                        multiplier = round(volume / stepf)
                        adjusted_v = round(max(stepf, multiplier * stepf), 8)
                        if abs(adjusted_v - volume) > 1e-9:
                            payload['requested_volume'] = payload.get('requested_volume', volume)
                            logger.info('Adjusted RPC volume for %s to match step %s: %s -> %s', symbol, sym_step, volume, adjusted_v)
                            volume = float(adjusted_v)
                    except Exception:
                        logger.debug('Failed to validate/round volume step for %s with step=%s', symbol, sym_step, exc_info=True)
            except Exception as e:
                logger.debug('Unexpected error while auto-adjusting volume for %s: %s', symbol, e, exc_info=True)

        # Build OrderRequest lazily to avoid importing heavy modules at module import time
        try:
            from cthulu.execution.engine import OrderRequest, OrderType, OrderStatus, ExecutionResult
        except Exception:
            self._send_json(500, {'error': 'Server misconfiguration: cannot import Execution engine'})
            return

        order_type = OrderType.MARKET if not price else OrderType.LIMIT
        # Generate unique signal_id per request to avoid duplicate detection
        import uuid
        import time
        unique_signal_id = payload.get('signal_id') or f"rpc_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
        order_req = OrderRequest(
            signal_id=unique_signal_id,
            symbol=symbol,
            side=side,
            volume=volume,
            order_type=order_type,
            price=price,
            sl=sl,
            tp=tp,
        )
        # Mark source for provenance
        try:
            order_req.metadata['source'] = 'rpc'
            order_req.metadata['client_ip'] = self.client_address[0]
            # Include any auth token hint (do not store full token)
            auth = self.headers.get('Authorization')
            if auth and auth.startswith('Bearer '):
                order_req.metadata['auth_hint'] = f"bearer:{auth.split(' ',1)[1][:6]}"
        except Exception as e:
            logger.debug("Failed to attach metadata to RPC order: %s", e, exc_info=True)

        # Risk approval (fetch account state if available)
        try:
            account_info = None
            try:
                connector = getattr(self.position_manager, 'connector', None)
                if connector and hasattr(connector, 'get_account_info'):
                    account_info = connector.get_account_info()
            except Exception as e:
                logger.debug("Failed to get account info from connector: %s", e, exc_info=True)
                account_info = None

            # The RiskManager was designed for `Signal` objects with attributes like
            # stop_loss, take_profit, price, confidence etc. Build a small signal-like
            # object from the order request so the approve() call can inspect necessary fields.
            class _SignalLike:
                pass

            signal_like = _SignalLike()
            # Provide fields expected by RiskEvaluator.approve()
            signal_like.symbol = order_req.symbol
            signal_like.price = order_req.price
            signal_like.stop_loss = order_req.sl
            signal_like.take_profit = order_req.tp
            # Normalized attributes
            signal_like.side = order_req.side
            signal_like.confidence = getattr(order_req, 'confidence', 1.0)
            signal_like.action = getattr(order_req, 'order_type', 'manual')
            signal_like.size_hint = getattr(order_req, 'volume', None)
            signal_like.metadata = {}

            logger.debug('Risk approval: starting approve() for %s', order_req.symbol)
            approved, reason, position_size = self.risk_manager.approve(
                signal_like,
                account_info,
                len(self.position_manager.get_positions(symbol=symbol))
            )
            logger.debug('Risk approval: done (approved=%s, reason=%s, pos_size=%s)', approved, reason, position_size)
        except Exception as e:
            logger.exception('Risk manager check failed')
            self._send_json(500, {'error': 'Risk manager error'})
            return

        if not approved:
            logger.info('RPC trade rejected by risk manager: %s', reason)
            self._send_json(403, {'error': 'Risk rejected', 'reason': reason})
            return

        # Overwrite volume with calculated position size if available
        if position_size:
            order_req.volume = position_size

        # Place the order
        try:
            logger.debug('Execution engine: placing order for %s %s %s', order_req.symbol, order_req.side, order_req.volume)
            result = self.execution_engine.place_order(order_req)
            logger.debug('Execution engine: place_order returned: %s', getattr(result, 'status', None))
        except Exception:
            logger.exception('Execution engine error while placing manual order')
            self._send_json(500, {'error': 'Execution failed'})
            return

        if result is None:
            self._send_json(500, {'error': 'Execution returned no result'})
            return

        # If filled, track position and record
        try:
            if result.status == OrderStatus.FILLED:
                tracked = self.position_manager.track_position(result, signal_metadata={})
                # record in DB via TradeRecord
                try:
                    from cthulu.persistence.database import TradeRecord
                    from datetime import datetime as _dt
                    tr = TradeRecord(
                        signal_id='rpc_manual',
                        order_id=result.order_id,
                        symbol=order_req.symbol,
                        side=order_req.side,
                        entry_price=result.fill_price,
                        volume=result.filled_volume,
                        entry_time=_dt.now(),
                    )
                    self.database.record_trade(tr)
                except Exception:
                    logger.exception('Failed to record RPC-placed trade')
                
                # ==========================================================
                # PUBLISH RPC TRADE EVENT TO EVENT BUS (Non-blocking)
                # ==========================================================
                try:
                    from cthulu.observability.trade_event_bus import publish_trade_opened
                    publish_trade_opened(
                        ticket=result.order_id,
                        symbol=order_req.symbol,
                        side=order_req.side,
                        volume=result.filled_volume,
                        price=result.fill_price,
                        stop_loss=order_req.sl,
                        take_profit=order_req.tp,
                        source="rpc",
                        strategy="rpc_manual",
                        signal_id=unique_signal_id,
                        client_ip=self.client_address[0]
                    )
                except Exception as e:
                    logger.debug(f"Event bus publish RPC trade (non-critical): {e}")

        except Exception:
            logger.exception('Failed to track or record RPC trade')

        # Return structured result
        resp = {
            'status': result.status.name,
            'order_id': getattr(result, 'order_id', None),
            'fill_price': getattr(result, 'fill_price', None),
            'filled_volume': getattr(result, 'filled_volume', None),
            'message': getattr(result, 'message', None)
        }

        # Include adjustment metadata when we auto-adjusted volume
        try:
            if payload.get('requested_volume') is not None:
                resp['requested_volume'] = payload.get('requested_volume')
                resp['adjusted_volume'] = volume
            # Also include any engine-level metadata if present
            if hasattr(result, 'metadata') and result.metadata:
                if 'adjusted_from' in result.metadata:
                    resp['adjusted_from'] = result.metadata.get('adjusted_from')
                if 'adjusted_to' in result.metadata:
                    resp['adjusted_to'] = result.metadata.get('adjusted_to')
        except Exception:
            logger.debug('Failed to attach adjustment metadata to response', exc_info=True)

        self._send_json(200, resp)

    def do_GET(self):
        parsed = urlparse(self.path)
        # Handle Ops API GET endpoints (/ops/status, /ops/runbook, /ops/audit)
        if parsed.path.startswith('/ops/'):
            # Authenticate
            auth = self.headers.get('Authorization')
            api_key = self.headers.get('X-Api-Key')
            if self.token:
                if auth and auth.startswith('Bearer '):
                    token = auth.split(' ', 1)[1].strip()
                else:
                    token = api_key
                if not token or token != self.token:
                    self._unauthorized('Invalid or missing API token')
                    return

            try:
                if parsed.path == '/ops/status':
                    status = {
                        'mode': getattr(self, 'mode', 'unknown'),
                        'execution_engine': bool(self.execution_engine),
                        'position_manager': bool(self.position_manager),
                        'database': bool(self.database),
                    }
                    # Attempt to add connector health and counts where available
                    try:
                        connector = getattr(self.execution_engine, 'connector', None)
                        status['mt5_up'] = getattr(connector, 'is_connected', False) if connector is not None else None
                    except Exception:
                        status['mt5_up'] = None
                    try:
                        status['open_positions'] = len(self.position_manager.get_positions()) if self.position_manager else None
                    except Exception:
                        status['open_positions'] = None

                    self._send_json(200, {'status': status})
                    return

                if parsed.path == '/ops/runbook':
                    # Optional query param: name to filter; if not present return whole runbook text
                    q = dict([p.split('=') for p in parsed.query.split('&') if p]) if parsed.query else {}
                    name = q.get('name')
                    try:
                        import os
                        runbook_path = os.path.join(os.path.dirname(__file__), '..', 'observability', 'RUNBOOK.md')
                        if os.path.exists(runbook_path):
                            with open(runbook_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            if name:
                                # Simple section extraction: return lines around the heading
                                sections = content.split('\n## ')
                                matched = [s for s in sections if s.strip().startswith(name)]
                                excerpt = matched[0] if matched else content[:400]
                            else:
                                excerpt = content[:4000]
                            self._send_json(200, {'runbook_excerpt': excerpt})
                            return
                        else:
                            self._send_json(404, {'error': 'Runbook not found'})
                            return
                    except Exception:
                        logger.exception('Failed to read runbook')
                        self._send_json(500, {'error': 'Failed to fetch runbook'})
                        return

                if parsed.path == '/ops/audit':
                    # Return recent audit/log entries; prefer security manager audit if present
                    try:
                        limit = int(dict([p.split('=') for p in parsed.query.split('&') if p]).get('limit', 50)) if parsed.query else 50
                    except Exception:
                        limit = 50

                    results = []
                    if self.security_manager:
                        # The AuditLogger writes JSON lines to file; attempt to load last N lines
                        try:
                            log_path = self.security_manager.config.audit_log_path
                            if log_path and os.path.exists(log_path):
                                with open(log_path, 'r', encoding='utf-8') as f:
                                    lines = f.readlines()[-limit:]
                                results = [json.loads(l.strip().split('] ', 1)[-1]) for l in lines if l.strip()]
                        except Exception:
                            logger.exception('Failed to read audit log')
                            results = []
                    elif self.database:
                        try:
                            results = self.database.get_recent_provenance(limit=limit)
                        except Exception:
                            results = []

                    self._send_json(200, {'limit': limit, 'results': results})
                    return

            except Exception:
                logger.exception('Failed serving ops endpoint')
                self._send_json(500, {'error': 'Internal server error'})
                return

        # Default: /provenance endpoint (existing behavior)
        if parsed.path != '/provenance':
            self.send_response(404)
            self.end_headers()
            return

        # Authenticate with same token as POST
        auth = self.headers.get('Authorization')
        api_key = self.headers.get('X-Api-Key')
        if self.token:
            if auth and auth.startswith('Bearer '):
                token = auth.split(' ', 1)[1].strip()
            else:
                token = api_key
            if not token or token != self.token:
                self._unauthorized('Invalid or missing API token')
                return

        # Parse query params for limit
        try:
            q = dict([p.split('=') for p in parsed.query.split('&') if p])
            limit = int(q.get('limit', 50))
        except Exception:
            limit = 50

        try:
            results = []
            if self.database:
                results = self.database.get_recent_provenance(limit=limit)
            body = json.dumps({'limit': limit, 'results': results}, default=str).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            logger.exception('Failed to serve provenance')
            self._send_json(500, {'error': 'Internal server error'})

    def log_message(self, format, *args):
        # Redirect logging through our logger rather than default stderr
        logger.info("%s - - [%s] %s" % (self.client_address[0], self.log_date_time_string(), format % args))


def run_rpc_server(
    host: str,
    port: int,
    token: Optional[str],
    execution_engine,
    risk_manager,
    position_manager,
    database,
    daemon: bool = True,
    security_config: Optional[Dict[str, Any]] = None,
    ops_controller: Optional[object] = None
):
    """
    Start RPC server in background thread with security hardening.
    
    Args:
        host: Bind address (default 127.0.0.1 for local-only)
        port: Listen port
        token: Bearer token for authentication (None = no auth)
        execution_engine: ExecutionEngine instance for trade execution
        risk_manager: RiskManager instance for trade approval
        position_manager: PositionManager instance for position tracking
        database: Database instance for trade recording
        daemon: Run as daemon thread
        security_config: Optional security configuration dict with keys:
            - rate_limit: Dict with rate limit settings
            - ip_whitelist: List of allowed IPs
            - ip_blacklist: List of blocked IPs
            - tls_enabled: Enable TLS
            - tls_cert_path: Path to TLS certificate
            - tls_key_path: Path to TLS private key
            - audit_enabled: Enable audit logging
    
    Returns:
        Tuple of (Thread, HTTPServer) instances
    """
    RPCRequestHandler.token = token
    RPCRequestHandler.execution_engine = execution_engine
    RPCRequestHandler.risk_manager = risk_manager
    RPCRequestHandler.position_manager = position_manager
    RPCRequestHandler.database = database
    RPCRequestHandler.ops_controller = ops_controller
    
    # Initialize security manager if available
    if SECURITY_AVAILABLE:
        try:
            # Build security config from dict
            sec_config = SecurityConfig()
            
            if security_config:
                # Apply rate limit config
                if 'rate_limit' in security_config:
                    rl = security_config['rate_limit']
                    sec_config.rate_limit = RateLimitConfig(
                        requests_per_minute=rl.get('requests_per_minute', 60),
                        requests_per_hour=rl.get('requests_per_hour', 1000),
                        burst_limit=rl.get('burst_limit', 10),
                        trades_per_minute=rl.get('trades_per_minute', 10),
                        trades_per_hour=rl.get('trades_per_hour', 100),
                        max_volume_per_minute=rl.get('max_volume_per_minute', 10.0),
                        adaptive_enabled=rl.get('adaptive_enabled', True),
                    )
                
                # Apply IP access controls
                if 'ip_whitelist' in security_config:
                    sec_config.ip_whitelist = security_config['ip_whitelist']
                if 'ip_blacklist' in security_config:
                    sec_config.ip_blacklist = security_config['ip_blacklist']
                
                # Apply TLS config
                if security_config.get('tls_enabled'):
                    sec_config.tls_enabled = True
                    sec_config.tls_cert_path = security_config.get('tls_cert_path')
                    sec_config.tls_key_path = security_config.get('tls_key_path')
                
                # Apply audit config
                if 'audit_enabled' in security_config:
                    sec_config.audit_enabled = security_config['audit_enabled']
                if 'audit_log_path' in security_config:
                    sec_config.audit_log_path = security_config['audit_log_path']
            
            # If the server is started with no token, do not require auth
            sec_config.require_auth = bool(token)
            RPCRequestHandler.security_manager = RPCSecurityManager(sec_config)
            RPCRequestHandler.security_config = security_config
            
            logger.info("RPC Security Manager initialized with hardened settings")
            logger.info(f"  Rate limits: {sec_config.rate_limit.requests_per_minute}/min, "
                       f"{sec_config.rate_limit.trades_per_minute} trades/min")
            logger.info(f"  IP whitelist: {len(sec_config.ip_whitelist)} entries")
            logger.info(f"  Audit logging: {'enabled' if sec_config.audit_enabled else 'disabled'}")
            
        except Exception as e:
            logger.error(f"Failed to initialize security manager: {e}")
            RPCRequestHandler.security_manager = None
    else:
        logger.warning("RPC running WITHOUT security hardening - security module not available")

    server = ThreadingHTTPServer((host, port), RPCRequestHandler)
    logger.info('Using ThreadingHTTPServer for RPC to allow concurrent request handling')
    
    # Apply TLS if configured
    if SECURITY_AVAILABLE and RPCRequestHandler.security_manager:
        tls_context = RPCRequestHandler.security_manager.tls_context
        if tls_context:
            server.socket = tls_context.wrap_socket(server.socket, server_side=True)
            logger.info("TLS enabled for RPC server")

    t = Thread(target=server.serve_forever, daemon=daemon, name='rpc-server')
    t.start()
    
    protocol = "https" if (SECURITY_AVAILABLE and RPCRequestHandler.security_manager 
                          and RPCRequestHandler.security_manager.tls_context) else "http"
    logger.info(f"RPC server listening on {protocol}://{host}:{port} (local only).")
    
    return t, server


def get_rpc_security_stats() -> Dict[str, Any]:
    """Get current RPC security statistics."""
    if RPCRequestHandler.security_manager:
        return RPCRequestHandler.security_manager.get_security_stats()
    return {"security_enabled": False}


def scan_rpc_dependencies() -> list:
    """Scan for known vulnerable dependencies."""
    if SECURITY_AVAILABLE:
        from cthulu.rpc.security import DependencyScanner
        return DependencyScanner.scan_installed()
    return []


