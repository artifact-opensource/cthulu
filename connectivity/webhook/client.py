"""
Webhook Client - HTTP Webhook Sender Implementation
Sends HTTP webhooks to external services.
"""
import json
import logging
from typing import Dict, Any, Optional, List
import urllib.request
import urllib.error
import time
import hmac
import hashlib

logger = logging.getLogger(__name__)


class WebhookClient:
    """
    HTTP webhook client implementation.
    
    Features:
    - HTTP POST requests
    - Automatic retry logic
    - Signature generation
    - Timeout handling
    - Batch sending
    
    Usage:
        client = WebhookClient(url='https://example.com/webhook')
        client.send({'event': 'trade_executed', 'symbol': 'EURUSD'})
    """
    
    def __init__(
        self,
        url: str,
        secret_key: Optional[str] = None,
        timeout: float = 10.0,
        retry_count: int = 3,
        retry_delay: float = 1.0,
        headers: Optional[Dict[str, str]] = None
    ):
        """
        Initialize webhook client.
        
        Args:
            url: Webhook endpoint URL
            secret_key: Optional secret key for signature
            timeout: Request timeout in seconds
            retry_count: Number of retry attempts
            retry_delay: Delay between retries in seconds
            headers: Optional custom headers
        """
        self.url = url
        self.secret_key = secret_key
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.custom_headers = headers or {}
        
        logger.info(f"WebhookClient initialized for {url}")
    
    def send(
        self,
        payload: Dict[str, Any],
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Send webhook with payload.
        
        Args:
            payload: Webhook payload
            timeout: Optional timeout override
            
        Returns:
            Response data
            
        Raises:
            WebhookError: If sending fails
        """
        timeout = timeout or self.timeout
        
        # Retry logic
        last_error = None
        for attempt in range(self.retry_count):
            try:
                result = self._send_request(payload, timeout)
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Webhook send failed (attempt {attempt + 1}/{self.retry_count}): {e}"
                )
                
                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
        
        # All retries failed
        logger.error(f"Webhook send failed after {self.retry_count} attempts")
        raise WebhookError(f"Webhook send failed: {last_error}")
    
    def _send_request(
        self,
        payload: Dict[str, Any],
        timeout: float
    ) -> Dict[str, Any]:
        """
        Send HTTP request.
        
        Args:
            payload: Request payload
            timeout: Request timeout
            
        Returns:
            Response data
            
        Raises:
            WebhookError: If request fails
        """
        try:
            # Prepare payload
            payload_json = json.dumps(payload)
            payload_bytes = payload_json.encode('utf-8')
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Cthulhu-Webhook-Client/1.0'
            }
            headers.update(self.custom_headers)
            
            # Add signature if secret key is set
            if self.secret_key:
                signature = self._generate_signature(payload_bytes)
                headers['X-Webhook-Signature'] = signature
            
            # Create request
            request = urllib.request.Request(
                self.url,
                data=payload_bytes,
                headers=headers,
                method='POST'
            )
            
            # Send request
            with urllib.request.urlopen(request, timeout=timeout) as response:
                response_data = response.read()
                
                # Parse response
                try:
                    result = json.loads(response_data.decode('utf-8'))
                except json.JSONDecodeError:
                    result = {'raw': response_data.decode('utf-8')}
                
                logger.info(f"Webhook sent successfully to {self.url}")
                return result
        
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP error {e.code}: {e.reason}"
            logger.error(error_msg)
            raise WebhookError(error_msg)
        
        except urllib.error.URLError as e:
            error_msg = f"URL error: {e.reason}"
            logger.error(error_msg)
            raise WebhookError(error_msg)
        
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(error_msg)
            raise WebhookError(error_msg)
    
    def _generate_signature(self, payload: bytes) -> str:
        """
        Generate HMAC signature for payload.
        
        Args:
            payload: Request payload bytes
            
        Returns:
            Hexadecimal signature
        """
        return hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha256
        ).hexdigest()
    
    def send_async(self, payload: Dict[str, Any]):
        """
        Send webhook asynchronously (fire-and-forget).
        
        Args:
            payload: Webhook payload
        """
        import threading
        
        thread = threading.Thread(
            target=self._send_async_worker,
            args=(payload,),
            daemon=True
        )
        thread.start()
    
    def _send_async_worker(self, payload: Dict[str, Any]):
        """Worker for async sending."""
        try:
            self.send(payload)
        except Exception as e:
            logger.error(f"Async webhook send failed: {e}")
    
    def send_batch(
        self,
        payloads: List[Dict[str, Any]],
        parallel: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Send multiple webhooks.
        
        Args:
            payloads: List of webhook payloads
            parallel: If True, send in parallel
            
        Returns:
            List of response data
        """
        if not parallel:
            results = []
            for payload in payloads:
                try:
                    result = self.send(payload)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Batch send error: {e}")
                    results.append({'error': str(e)})
            return results
        
        else:
            # Parallel sending using threads
            import threading
            import queue
            
            result_queue = queue.Queue()
            
            def worker(idx, payload):
                try:
                    result = self.send(payload)
                    result_queue.put((idx, result))
                except Exception as e:
                    logger.error(f"Batch send error: {e}")
                    result_queue.put((idx, {'error': str(e)}))
            
            threads = []
            for idx, payload in enumerate(payloads):
                thread = threading.Thread(
                    target=worker,
                    args=(idx, payload),
                    daemon=True
                )
                thread.start()
                threads.append(thread)
            
            # Wait for all threads
            for thread in threads:
                thread.join()
            
            # Collect results in order
            results_dict = {}
            while not result_queue.empty():
                idx, result = result_queue.get()
                results_dict[idx] = result
            
            return [results_dict[i] for i in range(len(payloads))]
    
    def test_connection(self) -> bool:
        """
        Test if webhook endpoint is reachable.
        
        Returns:
            True if endpoint is reachable
        """
        try:
            # Send minimal test payload
            test_payload = {'test': True, 'message': 'Connection test'}
            self.send(test_payload)
            return True
        except Exception as e:
            logger.warning(f"Connection test failed: {e}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get client configuration.
        
        Returns:
            Dictionary with client config
        """
        return {
            'url': self.url,
            'timeout': self.timeout,
            'retry_count': self.retry_count,
            'retry_delay': self.retry_delay,
            'signature_enabled': bool(self.secret_key),
            'custom_headers': list(self.custom_headers.keys())
        }


class WebhookError(Exception):
    """Webhook-specific error."""
    pass
