"""
RPC Server - JSON-RPC 2.0 Implementation
Handles remote procedure calls over TCP/IP with JSON serialization.
"""
import json
import socket
import threading
import logging
from typing import Dict, Any, Callable, Optional
from dataclasses import dataclass
import traceback

logger = logging.getLogger(__name__)


@dataclass
class RPCRequest:
    """RPC request structure following JSON-RPC 2.0 spec."""
    jsonrpc: str = "2.0"
    method: str = ""
    params: Dict[str, Any] = None
    id: Optional[int] = None
    
    def __post_init__(self):
        if self.params is None:
            self.params = {}


@dataclass
class RPCResponse:
    """RPC response structure following JSON-RPC 2.0 spec."""
    jsonrpc: str = "2.0"
    result: Any = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[int] = None


class RPCServer:
    """
    JSON-RPC 2.0 server implementation.
    
    Features:
    - TCP socket server
    - Multi-threaded request handling
    - Method registration
    - Error handling
    - Request/response logging
    
    Usage:
        server = RPCServer(host='0.0.0.0', port=9001)
        server.register_method('get_status', get_status_handler)
        server.start()
    """
    
    def __init__(
        self,
        host: str = '0.0.0.0',
        port: int = 9001,
        max_connections: int = 10,
        buffer_size: int = 4096
    ):
        """
        Initialize RPC server.
        
        Args:
            host: Server host address
            port: Server port number
            max_connections: Maximum concurrent connections
            buffer_size: Socket buffer size in bytes
        """
        self.host = host
        self.port = port
        self.max_connections = max_connections
        self.buffer_size = buffer_size
        
        self.methods: Dict[str, Callable] = {}
        self.socket: Optional[socket.socket] = None
        self.running = False
        self.server_thread: Optional[threading.Thread] = None
        
        logger.info(f"RPCServer initialized on {host}:{port}")
    
    def register_method(self, method_name: str, handler: Callable):
        """
        Register a method handler.
        
        Args:
            method_name: Name of the RPC method
            handler: Callable that processes the request
        """
        self.methods[method_name] = handler
        logger.info(f"Registered RPC method: {method_name}")
    
    def start(self):
        """Start the RPC server in a background thread."""
        if self.running:
            logger.warning("RPC server already running")
            return
        
        self.running = True
        self.server_thread = threading.Thread(target=self._run_server, daemon=True)
        self.server_thread.start()
        logger.info("RPC server started")
    
    def stop(self):
        """Stop the RPC server."""
        if not self.running:
            return
        
        self.running = False
        
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.error(f"Error closing server socket: {e}")
        
        if self.server_thread:
            self.server_thread.join(timeout=5.0)
        
        logger.info("RPC server stopped")
    
    def _run_server(self):
        """Main server loop running in background thread."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(self.max_connections)
            self.socket.settimeout(1.0)  # Allow periodic checks of self.running
            
            logger.info(f"RPC server listening on {self.host}:{self.port}")
            
            while self.running:
                try:
                    client_socket, address = self.socket.accept()
                    logger.debug(f"Accepted connection from {address}")
                    
                    # Handle each client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Error accepting connection: {e}")
        
        except Exception as e:
            logger.error(f"RPC server error: {e}")
            logger.error(traceback.format_exc())
        
        finally:
            if self.socket:
                self.socket.close()
    
    def _handle_client(self, client_socket: socket.socket, address: tuple):
        """
        Handle individual client connection.
        
        Args:
            client_socket: Client socket connection
            address: Client address tuple
        """
        try:
            # Receive data
            data = b''
            while True:
                chunk = client_socket.recv(self.buffer_size)
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
                logger.warning(f"Empty request from {address}")
                return
            
            # Parse request
            try:
                request_data = json.loads(data.decode('utf-8'))
                request = RPCRequest(
                    jsonrpc=request_data.get('jsonrpc', '2.0'),
                    method=request_data.get('method', ''),
                    params=request_data.get('params', {}),
                    id=request_data.get('id')
                )
            except Exception as e:
                logger.error(f"Invalid request format from {address}: {e}")
                response = RPCResponse(
                    error={'code': -32700, 'message': 'Parse error'},
                    id=None
                )
                self._send_response(client_socket, response)
                return
            
            logger.info(f"RPC request: {request.method} from {address}")
            
            # Process request
            response = self._process_request(request)
            
            # Send response
            self._send_response(client_socket, response)
            
        except Exception as e:
            logger.error(f"Error handling client {address}: {e}")
            logger.error(traceback.format_exc())
        
        finally:
            client_socket.close()
    
    def _process_request(self, request: RPCRequest) -> RPCResponse:
        """
        Process an RPC request.
        
        Args:
            request: Parsed RPC request
            
        Returns:
            RPC response
        """
        # Validate JSON-RPC version
        if request.jsonrpc != "2.0":
            return RPCResponse(
                error={'code': -32600, 'message': 'Invalid Request'},
                id=request.id
            )
        
        # Check if method exists
        if request.method not in self.methods:
            return RPCResponse(
                error={'code': -32601, 'message': 'Method not found'},
                id=request.id
            )
        
        # Execute method
        try:
            handler = self.methods[request.method]
            result = handler(request.params)
            
            return RPCResponse(
                result=result,
                id=request.id
            )
        
        except Exception as e:
            logger.error(f"Error executing method {request.method}: {e}")
            logger.error(traceback.format_exc())
            
            return RPCResponse(
                error={
                    'code': -32603,
                    'message': 'Internal error',
                    'data': str(e)
                },
                id=request.id
            )
    
    def _send_response(self, client_socket: socket.socket, response: RPCResponse):
        """
        Send response to client.
        
        Args:
            client_socket: Client socket
            response: RPC response
        """
        try:
            response_dict = {
                'jsonrpc': response.jsonrpc,
                'id': response.id
            }
            
            if response.error:
                response_dict['error'] = response.error
            else:
                response_dict['result'] = response.result
            
            response_json = json.dumps(response_dict)
            client_socket.sendall(response_json.encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error sending response: {e}")
    
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
            'registered_methods': list(self.methods.keys()),
            'max_connections': self.max_connections
        }
