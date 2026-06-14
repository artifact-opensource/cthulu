"""
RPC Client - JSON-RPC 2.0 Client Implementation
Sends remote procedure calls to RPC server.
"""
import json
import socket
import logging
from typing import Dict, Any, Optional
import time

logger = logging.getLogger(__name__)


class RPCClient:
    """
    JSON-RPC 2.0 client implementation.
    
    Features:
    - TCP socket client
    - Synchronous request/response
    - Automatic retry logic
    - Connection pooling support
    - Timeout handling
    
    Usage:
        client = RPCClient(host='localhost', port=9001)
        result = client.call('get_status', {'symbol': 'EURUSD'})
    """
    
    def __init__(
        self,
        host: str = 'localhost',
        port: int = 9001,
        timeout: float = 10.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        buffer_size: int = 4096
    ):
        """
        Initialize RPC client.
        
        Args:
            host: Server host address
            port: Server port number
            timeout: Socket timeout in seconds
            retry_count: Number of retry attempts
            retry_delay: Delay between retries in seconds
            buffer_size: Socket buffer size in bytes
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.buffer_size = buffer_size
        
        self.request_id = 0
        
        logger.info(f"RPCClient initialized for {host}:{port}")
    
    def call(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Any:
        """
        Call a remote method.
        
        Args:
            method: Method name to call
            params: Method parameters
            timeout: Optional timeout override
            
        Returns:
            Method result
            
        Raises:
            RPCError: If the call fails
            ConnectionError: If connection fails
        """
        if params is None:
            params = {}
        
        self.request_id += 1
        request = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params,
            'id': self.request_id
        }
        
        timeout = timeout or self.timeout
        
        # Retry logic
        last_error = None
        for attempt in range(self.retry_count):
            try:
                result = self._send_request(request, timeout)
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(
                    f"RPC call failed (attempt {attempt + 1}/{self.retry_count}): {e}"
                )
                
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
        
        # All retries failed
        logger.error(f"RPC call to {method} failed after {self.retry_count} attempts")
        raise RPCError(f"RPC call failed: {last_error}")
    
    def _send_request(self, request: Dict[str, Any], timeout: float) -> Any:
        """
        Send request and receive response.
        
        Args:
            request: Request dictionary
            timeout: Socket timeout
            
        Returns:
            Response result
            
        Raises:
            RPCError: If the server returns an error
            ConnectionError: If connection fails
        """
        sock = None
        try:
            # Create socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            # Connect to server
            sock.connect((self.host, self.port))
            
            # Send request
            request_json = json.dumps(request)
            sock.sendall(request_json.encode('utf-8'))
            
            # Receive response
            data = b''
            while True:
                chunk = sock.recv(self.buffer_size)
                if not chunk:
                    break
                data += chunk
                # Check if we have a complete JSON object
                try:
                    json.loads(data.decode('utf-8'))
                    break
                except json.JSONDecodeError:
                    continue
            
            if not data:
                raise RPCError("Empty response from server")
            
            # Parse response
            response = json.loads(data.decode('utf-8'))
            
            # Validate response
            if response.get('jsonrpc') != '2.0':
                raise RPCError("Invalid JSON-RPC version in response")
            
            if response.get('id') != request['id']:
                raise RPCError("Response ID mismatch")
            
            # Check for error
            if 'error' in response:
                error = response['error']
                raise RPCError(
                    f"RPC error {error.get('code')}: {error.get('message')}"
                )
            
            # Return result
            return response.get('result')
        
        except socket.timeout:
            raise RPCError(f"Request timeout after {timeout}s")
        
        except socket.error as e:
            raise ConnectionError(f"Socket error: {e}")
        
        finally:
            if sock:
                sock.close()
    
    def call_async(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None
    ):
        """
        Call a remote method without waiting for response (fire-and-forget).
        
        Args:
            method: Method name to call
            params: Method parameters
        """
        if params is None:
            params = {}
        
        # Notification request (no id field)
        request = {
            'jsonrpc': '2.0',
            'method': method,
            'params': params
        }
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            
            request_json = json.dumps(request)
            sock.sendall(request_json.encode('utf-8'))
            
            sock.close()
            
            logger.debug(f"Async call sent: {method}")
        
        except Exception as e:
            logger.error(f"Async call failed: {e}")
    
    def ping(self) -> bool:
        """
        Check if server is reachable.
        
        Returns:
            True if server is reachable, False otherwise
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((self.host, self.port))
            sock.close()
            return True
        except Exception:
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get client configuration.
        
        Returns:
            Dictionary with client config
        """
        return {
            'host': self.host,
            'port': self.port,
            'timeout': self.timeout,
            'retry_count': self.retry_count,
            'retry_delay': self.retry_delay
        }


class RPCError(Exception):
    """RPC-specific error."""
    pass
