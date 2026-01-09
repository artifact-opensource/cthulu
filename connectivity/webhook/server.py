"""
Webhook Server - HTTP Webhook Receiver Implementation
Receives and processes HTTP webhook callbacks.
"""
import json
import logging
from typing import Dict, Any, Callable, Optional, List
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import traceback
from urllib.parse import urlparse, parse_qs
import hmac
import hashlib

logger = logging.getLogger(__name__)


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for webhooks."""
    
    def log_message(self, format, *args):
        """Override to use custom logger."""
        logger.debug(f"{self.address_string()} - {format % args}")
    
    def do_POST(self):
        """Handle POST requests."""
        try:
            # Get content length
            content_length = int(self.headers.get('Content-Length', 0))
            
            # Read body
            body = self.rfile.read(content_length)
            
            # Parse JSON payload
            try:
                payload = json.loads(body.decode('utf-8'))
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON payload")
                return
            
            # Get path
            path = self.path
            
            # Verify signature if enabled
            if hasattr(self.server, 'secret_key') and self.server.secret_key:
                signature = self.headers.get('X-Webhook-Signature')
                if not self._verify_signature(body, signature):
                    self.send_error(401, "Invalid signature")
                    return
            
            # Process webhook
            result = self.server.process_webhook(path, payload, dict(self.headers))
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'success',
                'message': 'Webhook received',
                'result': result
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
        
        except Exception as e:
            logger.error(f"Error processing webhook: {e}")
            logger.error(traceback.format_exc())
            
            self.send_error(500, "Internal server error")
    
    def do_GET(self):
        """Handle GET requests (health check)."""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            response = {
                'status': 'healthy',
                'service': 'webhook-server'
            }
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_error(404, "Not found")
    
    def _verify_signature(self, body: bytes, signature: Optional[str]) -> bool:
        """
        Verify webhook signature.
        Supports both plain hexdigest and prefixed formats (e.g., 'sha256=...').
        
        Args:
            body: Request body
            signature: Signature from header
            
        Returns:
            True if signature is valid
        """
        if not signature:
            return False
        
        try:
            # Generate expected signature
            expected_signature = hmac.new(
                self.server.secret_key.encode('utf-8'),
                body,
                hashlib.sha256
            ).hexdigest()
            
            # Support prefixed signatures (e.g., 'sha256=abc123...')
            if '=' in signature:
                prefix, sig_value = signature.split('=', 1)
                signature = sig_value
            
            return hmac.compare_digest(signature, expected_signature)
        
        except Exception as e:
            logger.error(f"Error verifying signature: {e}")
            return False


class WebhookServer:
    """
    HTTP webhook server implementation.
    
    Features:
    - HTTP server for receiving webhooks
    - Path-based routing
    - Handler registration
    - Signature verification
    - Request logging
    
    Usage:
        server = WebhookServer(host='0.0.0.0', port=8080)
        server.register_handler('/trading/signal', signal_handler)
        server.start()
    """
    
    def __init__(
        self,
        host: str = '0.0.0.0',
        port: int = 8080,
        secret_key: Optional[str] = None
    ):
        """
        Initialize webhook server.
        
        Args:
            host: Server host address
            port: Server port number
            secret_key: Optional secret key for signature verification
        """
        self.host = host
        self.port = port
        self.secret_key = secret_key
        
        self.handlers: Dict[str, Callable] = {}
        self.server: Optional[HTTPServer] = None
        self.running = False
        self.server_thread: Optional[threading.Thread] = None
        
        logger.info(f"WebhookServer initialized on {host}:{port}")
    
    def register_handler(self, path: str, handler: Callable):
        """
        Register a webhook handler for a specific path.
        
        Args:
            path: URL path (e.g., '/trading/signal')
            handler: Callable that processes the webhook
        """
        self.handlers[path] = handler
        logger.info(f"Registered webhook handler: {path}")
    
    def start(self):
        """Start the webhook server in a background thread."""
        if self.running:
            logger.warning("Webhook server already running")
            return
        
        self.running = True
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        logger.info("Webhook server started")
    
    def stop(self):
        """Stop the webhook server."""
        if not self.running:
            return
        
        self.running = False
        
        if self.server:
            self.server.shutdown()
        
        if self.server_thread:
            self.server_thread.join(timeout=5.0)
        
        logger.info("Webhook server stopped")
    
    def _run_server(self):
        """Main server loop running in background thread."""
        try:
            self.server = HTTPServer((self.host, self.port), WebhookHandler)
            self.server.secret_key = self.secret_key
            self.server.process_webhook = self._process_webhook
            
            logger.info(f"Webhook server listening on {self.host}:{self.port}")
            
            self.server.serve_forever()
        
        except Exception as e:
            logger.error(f"Webhook server error: {e}")
            logger.error(traceback.format_exc())
        
        finally:
            if self.server:
                self.server.server_close()
    
    def _process_webhook(
        self,
        path: str,
        payload: Dict[str, Any],
        headers: Dict[str, str]
    ) -> Any:
        """
        Process incoming webhook.
        
        Args:
            path: Request path
            payload: Webhook payload
            headers: Request headers
            
        Returns:
            Handler result
        """
        logger.info(f"Webhook received: {path}")
        logger.debug(f"Payload: {payload}")
        
        # Find matching handler
        handler = self.handlers.get(path)
        
        if not handler:
            # Try matching with wildcards
            for registered_path, registered_handler in self.handlers.items():
                if self._path_matches(path, registered_path):
                    handler = registered_handler
                    break
        
        if not handler:
            logger.warning(f"No handler for path: {path}")
            return None
        
        # Execute handler
        try:
            result = handler(payload, headers)
            logger.info(f"Webhook processed successfully: {path}")
            return result
        
        except Exception as e:
            logger.error(f"Error executing webhook handler: {e}")
            logger.error(traceback.format_exc())
            raise
    
    def _path_matches(self, request_path: str, pattern: str) -> bool:
        """
        Check if request path matches pattern (supports wildcards).
        
        Args:
            request_path: Incoming request path
            pattern: Handler pattern
            
        Returns:
            True if paths match
        """
        # Simple wildcard matching
        if '*' in pattern:
            pattern_parts = pattern.split('*')
            if len(pattern_parts) == 2:
                prefix, suffix = pattern_parts
                return request_path.startswith(prefix) and request_path.endswith(suffix)
        
        return request_path == pattern
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get server statistics.
        
        Returns:
            Dictionary with server stats
        """
        return {
            'running': self.running,
            'host': self.host,
            'port': self.port,
            'registered_handlers': list(self.handlers.keys()),
            'signature_verification': bool(self.secret_key)
        }
