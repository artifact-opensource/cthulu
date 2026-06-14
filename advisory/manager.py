from __future__ import annotations
import time
import logging
from typing import Dict, Any, Optional
from cthulu.execution.engine import OrderRequest, ExecutionResult, ExecutionEngine, OrderType

logger = logging.getLogger('cthulu.advisory')


class AdvisoryManager:
    """Manage advisory and ghost modes for orders.

    Modes:
      - disabled/production: orders proceed as normal
      - advisory: do not execute orders; record advisory events and suggestions
      - ghost: place tiny "ghost" trades (configurable) to validate live plumbing

    Safety: ghost mode enforces strict caps (max_trades, max_duration) and requires explicit enable flag.
    """
    def __init__(self, config: Dict[str, Any], execution_engine: ExecutionEngine, ml_collector=None):
        self.config = config or {}
        self.execution_engine = execution_engine
        self.ml = ml_collector
        self.enabled = bool(self.config.get('enabled', False))
        self.mode = self.config.get('mode', 'advisory')  # 'advisory' | 'ghost' | 'production'
        self.ghost_lot_size = float(self.config.get('ghost_lot_size', 0.01))
        self.ghost_max_trades = int(self.config.get('ghost_max_trades', 5))
        self.ghost_max_duration = int(self.config.get('ghost_max_duration', 3600))
        self.ghost_trades_count = 0
        self.ghost_start_ts: Optional[float] = None
        self.log_only = bool(self.config.get('log_only', False))

        # Background queue/worker for ghost orders to ensure non-blocking behavior
        from queue import Queue
        import threading
        self._ghost_queue: "Queue[OrderRequest]" = Queue()
        self._ghost_stop = threading.Event()
        self._ghost_thread = threading.Thread(target=self._ghost_worker, name='advisory-ghost-worker', daemon=True)
        self._ghost_thread.start()
    def _record_ml(self, event_type: str, payload: Dict[str, Any]):
        try:
            if self.ml:
                self.ml.record_event(event_type, payload)
        except Exception:
            logger.exception('Failed to record advisory ML event')

    def _ghost_worker(self):
        """Background worker that processes queued ghost orders asynchronously."""
        while not self._ghost_stop.is_set():
            try:
                req = self._ghost_queue.get(timeout=0.5)
            except Exception:
                continue
            try:
                # Attempt to place the ghost order unless log_only
                res = None
                if not self.log_only:
                    res = self.execution_engine.place_order(req)
                # Emit ML result event for ghost attempt
                payload = {
                    'ts': time.time(),
                    'symbol': req.symbol,
                    'side': req.side,
                    'volume': req.volume,
                    'client_tag': req.client_tag,
                    'result_order_id': getattr(res, 'order_id', None) if res else None,
                    'result_status': getattr(res, 'status', None).name if getattr(res, 'status', None) else None,
                }
                self._record_ml('advisory.ghost_result', payload)
            except Exception as e:
                logger.exception('Ghost worker failed')
                self._record_ml('advisory.ghost_result', {'ts': time.time(), 'error': str(e)})
            finally:
                try:
                    self._ghost_queue.task_done()
                except Exception:
                    pass

    def close(self):
        """Stop background ghost worker and flush remaining items."""
        try:
            self._ghost_stop.set()
            if self._ghost_thread.is_alive():
                self._ghost_thread.join(timeout=2.0)
        except Exception:
            logger.exception('Failed to stop ghost worker')

    def decide(self, order_req: OrderRequest, signal: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Decide what to do with an order request.

        Returns dict: {action: 'execute'|'advisory'|'ghost'|'reject', 'result': ExecutionResult|None}
        """
        if not self.enabled:
            return {'action': 'execute', 'result': None}

        payload = {
            'ts': time.time(),
            'mode': self.mode,
            'signal_id': getattr(signal, 'id', None) if signal is not None else order_req.signal_id,
            'symbol': order_req.symbol,
            'volume': order_req.volume,
            'order_type': order_req.order_type.value if hasattr(order_req.order_type, 'value') else str(order_req.order_type),
            'side': order_req.side
        }

        # Advisory mode: log and record, do not execute
        if self.mode == 'advisory' or self.log_only:
            payload['decision'] = 'advisory'
            self._record_ml('advisory.signal', payload)
            logger.info('Advisory mode: recording advisory signal for %s', order_req.symbol)
            return {'action': 'advisory', 'result': None}

        # Ghost mode: limited live test trades
        if self.mode == 'ghost':
            now = time.time()
            if self.ghost_start_ts is None:
                self.ghost_start_ts = now

            if (now - (self.ghost_start_ts or now)) > self.ghost_max_duration:
                payload['decision'] = 'reject'
                payload['reason'] = 'ghost duration exceeded'
                self._record_ml('advisory.signal', payload)
                logger.warning('Ghost window expired - rejecting ghost order')
                return {'action': 'reject', 'result': None}

            if self.ghost_trades_count >= self.ghost_max_trades:
                payload['decision'] = 'reject'
                payload['reason'] = 'ghost max trades reached'
                self._record_ml('advisory.signal', payload)
                logger.warning('Ghost trade cap reached - rejecting ghost order')
                return {'action': 'reject', 'result': None}

            # Enqueue a tiny test order for background processing (non-blocking)
            try:
                ghost_req = OrderRequest(
                    signal_id=order_req.signal_id,
                    symbol=order_req.symbol,
                    side=order_req.side,
                    volume=self.ghost_lot_size,
                    order_type=order_req.order_type,
                    price=order_req.price,
                    sl=order_req.sl,
                    tp=order_req.tp,
                    client_tag=(order_req.client_tag or '') + ':ghost',
                    metadata={**order_req.metadata, 'advisory_mode': 'ghost'}
                )
                logger.info('Ghost mode: queueing background test order %s %s %s', ghost_req.side, ghost_req.volume, ghost_req.symbol)

                # Start ghost window if needed
                now = time.time()
                if self.ghost_start_ts is None:
                    self.ghost_start_ts = now

                # Enforce duration and max trades caps (counted at queue time)
                if (now - (self.ghost_start_ts or now)) > self.ghost_max_duration:
                    payload['decision'] = 'reject'
                    payload['reason'] = 'ghost duration exceeded'
                    self._record_ml('advisory.signal', payload)
                    logger.warning('Ghost window expired - rejecting ghost order')
                    return {'action': 'reject', 'result': None}

                if self.ghost_trades_count >= self.ghost_max_trades:
                    payload['decision'] = 'reject'
                    payload['reason'] = 'ghost max trades reached'
                    self._record_ml('advisory.signal', payload)
                    logger.warning('Ghost trade cap reached - rejecting ghost order')
                    return {'action': 'reject', 'result': None}

                # Enqueue the ghost order for background worker; increment the queued count
                self._ghost_queue.put(ghost_req)
                self.ghost_trades_count += 1
                payload['decision'] = 'ghost_queued'
                payload['queued_at'] = now
                payload['expected_volume'] = ghost_req.volume
                self._record_ml('advisory.signal', payload)
                return {'action': 'ghost', 'result': None}
            except Exception as e:
                payload['decision'] = 'reject'
                payload['reason'] = str(e)
                self._record_ml('advisory.signal', payload)
                logger.exception('Ghost order failed to queue')
                return {'action': 'reject', 'result': None}

        # Default: execute
        payload['decision'] = 'execute'
        self._record_ml('advisory.signal', payload)
        return {'action': 'execute', 'result': None}




