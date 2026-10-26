"""
Execution Engine

Handles order placement, modification, and reconciliation.
Supports market/limit orders with idempotent submission and external reconciliation.
"""

from cthulu.connector.mt5_connector import mt5
import logging
import traceback
import inspect
import json
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from cthulu.strategy.base import Signal, SignalType
from cthulu import constants


class OrderType(Enum):
    """Order types"""
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class OrderStatus(Enum):
    """Order execution status"""
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


@dataclass
class OrderRequest:
    """
    Order request structure.
    
    Attributes:
        signal_id: Originating signal ID
        symbol: Trading symbol
        side: BUY or SELL
        volume: Position size in lots
        order_type: MARKET, LIMIT, or STOP
        price: Limit/stop price (None for market)
        sl: Stop loss price
        tp: Take profit price
        client_tag: Client order identifier
        comment: Order comment for MT5
        metadata: Additional order data
    """
    symbol: str
    side: str
    volume: float
    order_type: OrderType
    signal_id: str = ""
    price: Optional[float] = None
    sl: Optional[float] = None
    tp: Optional[float] = None
    client_tag: str = ""
    comment: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionResult:
    """
    Execution result structure.
    
    Attributes:
        order_id: MT5 order ticket
        status: Execution status
        executed_price: Filled price
        executed_volume: Filled volume
        timestamp: Execution time
        error: Error message if failed
        metadata: Additional execution data
    """
    order_id: Optional[int]
    status: OrderStatus
    executed_price: Optional[float]
    executed_volume: Optional[float]
    timestamp: datetime
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    # position_ticket (MT5 position ticket if determinable) — order tickets and position tickets differ
    position_ticket: Optional[int] = None

    # Backwards-compatible aliases expected by other modules
    @property
    def fill_price(self) -> Optional[float]:
        return self.executed_price

    @property
    def filled_volume(self) -> Optional[float]:
        return self.executed_volume

    @property
    def commission(self) -> float:
        return float(self.metadata.get('commission', 0.0))

    @property
    def message(self) -> Optional[str]:
        return self.error


class ExecutionEngine:
    """
    Order execution and management engine.
    
    Responsibilities:
    - Place market and limit orders
    - Handle partial fills
    - Idempotent order submission
    - External reconciliation
    - Order modification and cancellation
    """
    
    # CRITICAL: Maximum stop loss distance as percentage
    # This prevents catastrophic losses from misconfigured stop losses
    # DO NOT increase beyond 0.15 (15%) without careful consideration
    MAX_STOP_LOSS_PCT = 0.10  # 10% default maximum stop loss distance
    
    # Absolute hard cap - no configuration can exceed this
    MAX_CONFIGURABLE_SL_PCT = 0.15  # 15% absolute maximum (hard cap)
    
    def __init__(self, connector, magic_number: int = None, slippage: int = 10, risk_config: Optional[Dict[str, Any]] = None, metrics=None, ml_collector=None, telemetry=None):
        """
        Initialize execution engine.
        
        Args:
            connector: MT5Connector instance
            magic_number: Unique identifier for bot orders (if None, use DEFAULT_MAGIC)
            slippage: Maximum allowed slippage in points
            risk_config: Optional risk configuration (can include 'max_sl_pct' override)
        """
        self.connector = connector
        # Use provided magic number or fall back to centralized DEFAULT_MAGIC
        self.magic_number = magic_number if magic_number is not None else constants.DEFAULT_MAGIC
        self.slippage = slippage
        # Optional risk configuration overrides (from app config)
        self.risk_config = risk_config or {}
        self.logger = logging.getLogger("cthulu.execution")
        # Optional metrics collector (MetricsCollector)
        self.metrics = metrics
        # Optional ML instrumentation collector
        self.ml_collector = ml_collector
        # Optional telemetry persistence helper
        self.telemetry = telemetry
        
        # Order tracking for idempotency
        self._submitted_orders: Dict[str, int] = {}
        # Max size to avoid unbounded growth; old entries will be pruned
        self._idempotency_max = 1000
        
        # Allow risk_config to override max SL percentage (but cap at hard limit)
        config_max_sl = self.risk_config.get('max_sl_pct', self.MAX_STOP_LOSS_PCT)
        self.max_sl_pct = min(float(config_max_sl), self.MAX_CONFIGURABLE_SL_PCT)
        
    def place_order(self, order_req: OrderRequest) -> ExecutionResult:
        """
        Place order with idempotency check.
        
        Args:
            order_req: Order request
            
        Returns:
            ExecutionResult with order outcome
        """
        # Ensure metadata present
        if order_req.metadata is None:
            order_req.metadata = {}

        # Enforce symbol min/step at engine level to catch system-generated orders as well
        try:
            sym_min = None
            sym_step = None
            try:
                sym_min = self.connector.get_min_lot(order_req.symbol)
            except Exception:
                sym_min = None
            try:
                sym_info = self.connector.get_symbol_info(order_req.symbol) or {}
                sym_step = sym_info.get('volume_step')
            except Exception:
                sym_step = None

            orig_vol = float(order_req.volume)
            adjusted_vol = orig_vol
            if sym_min is not None:
                try:
                    minf = float(sym_min)
                    if adjusted_vol < minf:
                        adjusted_vol = minf
                except Exception:
                    pass
            if sym_step:
                try:
                    stepf = float(sym_step)
                    multiplier = round(adjusted_vol / stepf)
                    adjusted_vol = round(max(stepf, multiplier * stepf), 8)
                except Exception:
                    pass

            if abs(adjusted_vol - orig_vol) > 1e-9:
                order_req.metadata['adjusted_from'] = orig_vol
                order_req.metadata['adjusted_to'] = adjusted_vol
                order_req.volume = float(adjusted_vol)
                self.logger.info('ExecutionEngine adjusted volume for %s: %s -> %s (min=%s step=%s)', order_req.symbol, orig_vol, adjusted_vol, sym_min, sym_step)
        except Exception:
            self.logger.debug('Failed to auto-adjust order volume at engine level', exc_info=True)

        # If client_tag not provided, generate a deterministic tag based on order content
        if not order_req.client_tag:
            try:
                import hashlib
                canonical = json.dumps({
                    'signal_id': order_req.signal_id,
                    'symbol': order_req.symbol,
                    'side': order_req.side,
                    'volume': order_req.volume,
                    'order_type': order_req.order_type.value if hasattr(order_req.order_type, 'value') else str(order_req.order_type),
                    'price': order_req.price,
                    'sl': order_req.sl,
                    'tp': order_req.tp,
                    # Include position-specific metadata (e.g., closing ticket) to avoid idempotency collisions
                    'closing_ticket': (order_req.metadata.get('closing_ticket') if isinstance(order_req.metadata, dict) else None)
                }, sort_keys=True, default=str)
                order_req.client_tag = hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:16]
                self.logger.debug(f"Autogenerated client_tag: {order_req.client_tag}")
            except Exception as _:
                from datetime import datetime as _dt
                order_req.client_tag = f"autogen:{int(_dt.now().timestamp())}"

        # Record provenance for tracing unexpected orders
        try:
            # Find caller frame outside this module
            caller_info = {'module': None, 'function': None, 'filename': None}
            for frame_info in inspect.stack()[1:10]:
                fname = os.path.basename(frame_info.filename or '')
                if fname != os.path.basename(__file__):
                    caller_info['module'] = frame_info.frame.f_globals.get('__name__', None)
                    caller_info['function'] = frame_info.function
                    caller_info['filename'] = frame_info.filename
                    break
            stack_snippet = traceback.format_stack(limit=6)
            # Build enriched environment snapshot with safe redaction
            try:
                import socket, platform, threading
                pid = os.getpid()
                tid = threading.get_ident()
                hostname = socket.gethostname()
                python_version = platform.platform()
                # Redact env vars that look sensitive
                env_snapshot = {}
                secret_patterns = ('KEY','TOKEN','SECRET','PASSWORD','PASS','AWS','API')
                for k, v in os.environ.items():
                    up = k.upper()
                    if any(p in up for p in secret_patterns):
                        env_snapshot[k] = 'REDACTED'
                    else:
                        # Limit long values
                        sval = str(v)
                        env_snapshot[k] = sval if len(sval) < 200 else sval[:200] + '...'
            except Exception:
                pid = None
                tid = None
                hostname = None
                python_version = None
                env_snapshot = {}

            # Sanitize metadata to avoid circular refs and non-serializable objects
            try:
                raw_meta = order_req.metadata if isinstance(order_req.metadata, dict) else {}
                meta_copy = {}
                for k, v in raw_meta.items():
                    if k == 'provenance':
                        continue
                    try:
                        json.dumps(v)
                        meta_copy[k] = v
                    except Exception:
                        try:
                            meta_copy[k] = str(v)
                        except Exception:
                            meta_copy[k] = None
            except Exception:
                meta_copy = {}

            provenance = {
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'signal_id': order_req.signal_id,
                'client_tag': order_req.client_tag,
                'symbol': order_req.symbol,
                'side': order_req.side,
                'volume': order_req.volume,
                'caller': caller_info,
                'stack_snippet': stack_snippet,
                'metadata': meta_copy,
                'pid': pid,
                'thread_id': tid,
                'hostname': hostname,
                'python_version': python_version,
                'env_snapshot': env_snapshot
            }
            # Attach provenance into order metadata for downstream tracing
            try:
                order_req.metadata['provenance'] = provenance
                order_req.metadata['provenance_logged'] = True
            except Exception as e:
                self.logger.debug("Failed to attach provenance to order metadata: %s", e, exc_info=True)

            # Persist to telemetry DB if available
            try:
                if hasattr(self, 'telemetry') and self.telemetry is not None:
                    prov_id = self.telemetry.record_provenance(provenance)
                    provenance['id'] = prov_id
                    try:
                        order_req.metadata['provenance_db_id'] = prov_id
                    except Exception as e:
                        self.logger.debug("Failed to write provenance_db_id into metadata: %s", e, exc_info=True)
            except Exception:
                self.logger.exception('Failed to record provenance into telemetry DB')

            # Log summary line
            self.logger.info(f"Order provenance: signal_id={order_req.signal_id} client_tag={order_req.client_tag} caller={caller_info.get('module')}#{caller_info.get('function')} pid={pid} tid={tid} host={hostname}")
            # Append to provenance log file
            try:
                logs_dir = os.path.join(os.path.dirname(__file__), '..', 'logs')
                logs_dir = os.path.abspath(logs_dir)
                os.makedirs(logs_dir, exist_ok=True)
                prov_path = os.path.join(logs_dir, 'order_provenance.log')
                with open(prov_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(provenance, default=str) + '\n')
            except Exception:
                self.logger.exception('Failed to write order provenance file')
        except Exception:
            self.logger.exception('Failed to record order provenance')

        # Check if already submitted (idempotency)
        if order_req.client_tag in self._submitted_orders:
            existing_ticket = self._submitted_orders[order_req.client_tag]
            self.logger.warning(f"Order {order_req.client_tag} already submitted as ticket #{existing_ticket}")
            return ExecutionResult(
                order_id=existing_ticket,
                status=OrderStatus.PENDING,
                executed_price=None,
                executed_volume=None,
                timestamp=datetime.now(),
                error="Duplicate order submission"
            )
            
        # Validate connection
        if not self.connector.is_connected():
            self.logger.error("Not connected to MT5")
            return ExecutionResult(
                order_id=None,
                status=OrderStatus.REJECTED,
                executed_price=None,
                executed_volume=None,
                timestamp=datetime.now(),
                error="MT5 not connected"
            )
            
        try:
            # Prepare MT5 order request
            request = self._build_mt5_request(order_req)
            
            # Submit order
            self.logger.info(
                f"Placing {order_req.order_type.value} order: "
                f"{order_req.side} {order_req.volume} {order_req.symbol}"
            )
            
            # DEBUG: Log exact request being sent to MT5
            self.logger.info(f"MT5 request dict: {request}")
            for k, v in request.items():
                self.logger.debug(f"  {k}: {v} (type={type(v).__name__})")

            # Submit order directly - MT5 Python API is NOT thread-safe
            # ThreadPoolExecutor causes "Unnamed arguments not allowed" error
            result = mt5.order_send(request)

            if result is None:
                error = mt5.last_error()
                self.logger.error(f"Order submission failed: {error}")
                # Instrumentation: record failed execution if collector available
                try:
                    if self.ml_collector:
                        exec_payload = {
                            'order_id': None,
                            'status': 'REJECTED',
                            'error': str(error)
                        }
                        self.ml_collector.record_execution(exec_payload)
                except Exception:
                    self.logger.exception('ML collector failed')

                return ExecutionResult(
                    order_id=None,
                    status=OrderStatus.REJECTED,
                    executed_price=None,
                    executed_volume=None,
                    timestamp=datetime.now(),
                    error=str(error)
                )
                
            # Check if trading is allowed - ensure account is permitted before processing result
            account_info = self.connector.get_account_info()
            if account_info is None or not account_info.get('trade_allowed', False):
                self.logger.error("Trading not allowed on the connected account")
                return ExecutionResult(
                    order_id=None,
                    status=OrderStatus.REJECTED,
                    executed_price=None,
                    executed_volume=None,
                    timestamp=datetime.now(),
                    error="Trade not allowed on account",
                    metadata={'trade_allowed': False}
                )

            # Check result
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                # Track for idempotency
                if order_req.client_tag:
                    # Prune oldest entries if necessary
                    if len(self._submitted_orders) >= self._idempotency_max:
                        oldest = next(iter(self._submitted_orders))
                        try:
                            del self._submitted_orders[oldest]
                        except KeyError:
                            pass  # Already removed
                    self._submitted_orders[order_req.client_tag] = result.order
                    
                self.logger.info(
                    f"Order executed: Ticket #{result.order} | "
                    f"Price: {result.price:.5f} | Volume: {result.volume}"
                )
                
                # Gather metadata including commission if present
                md = {
                    'bid': getattr(result, 'bid', None),
                    'ask': getattr(result, 'ask', None),
                    'comment': getattr(result, 'comment', None)
                }
                if hasattr(result, 'commission'):
                    md['commission'] = getattr(result, 'commission')

                # Try to resolve the resulting position ticket (MT5 differentiates orders and positions)
                position_ticket = None
                try:
                    positions = mt5.positions_get()
                    if positions:
                        # Filter by symbol
                        candidates = [p for p in positions if getattr(p, 'symbol', None) == order_req.symbol]
                        # Prefer matching magic
                        magic_matches = [p for p in candidates if getattr(p, 'magic', None) == self.magic_number]
                        candidates = magic_matches or candidates
                        # Prefer most recent positions
                        candidates = sorted(candidates, key=lambda x: getattr(x, 'time', 0), reverse=True)
                        for p in candidates:
                            try:
                                if abs(getattr(p, 'volume', 0) - result.volume) < 0.0001:
                                    position_ticket = getattr(p, 'ticket', None)
                                    break
                            except (AttributeError, TypeError):
                                continue
                except (AttributeError, RuntimeError) as e:
                    self.logger.debug(f"Position ticket resolution skipped: {e}")
                    position_ticket = None

                # Instrumentation: record order and execution events for ML and telemetry
                try:
                    if self.ml_collector:
                        order_payload = {
                            'source': 'Cthulu',
                            'signal_id': order_req.signal_id,
                            'symbol': order_req.symbol,
                            'side': order_req.side,
                            'volume': order_req.volume,
                            'order_type': order_req.order_type.value if hasattr(order_req.order_type, 'value') else str(order_req.order_type),
                            'price': order_req.price,
                            'sl': order_req.sl,
                            'tp': order_req.tp,
                            'client_tag': order_req.client_tag,
                            'metadata': order_req.metadata,
                            'provenance_id': order_req.metadata.get('provenance_db_id') if isinstance(order_req.metadata, dict) else None
                        }
                        # Best-effort include a small provenance snapshot into ML payload
                        try:
                            prov = order_req.metadata.get('provenance') if isinstance(order_req.metadata, dict) else None
                            if prov:
                                order_payload['provenance_snippet'] = {
                                    'caller': prov.get('caller'),
                                    'pid': prov.get('pid'),
                                    'thread_id': prov.get('thread_id'),
                                    'hostname': prov.get('hostname')
                                }
                        except Exception:
                            pass

                        self.ml_collector.record_order(order_payload)

                        exec_payload = {
                            'source': 'Cthulu',
                            'order_id': getattr(result, 'order', None),
                            'position_ticket': position_ticket,
                            'status': 'FILLED',
                            'price': getattr(result, 'price', None),
                            'volume': getattr(result, 'volume', None),
                            'timestamp': datetime.utcnow().isoformat() + 'Z',
                            'metadata': md,
                            'provenance_id': order_req.metadata.get('provenance_db_id') if isinstance(order_req.metadata, dict) else None
                        }
                        self.ml_collector.record_execution(exec_payload)
                except Exception:
                    # Best-effort: do not fail order flow if instrumentation errors
                    self.logger.exception('ML collector failed')

                return ExecutionResult(
                    order_id=result.order,
                    position_ticket=position_ticket,
                    status=OrderStatus.FILLED,
                    executed_price=result.price,
                    executed_volume=result.volume,
                    timestamp=datetime.now(),
                    metadata=md
                )
            else:
                self.logger.error(f"Order rejected: {result.retcode} - {result.comment}")
                # Instrumentation: record failed execution
                try:
                    if self.ml_collector:
                        exec_payload = {
                            'order_id': None,
                            'status': 'REJECTED',
                            'error': f"{result.retcode}: {getattr(result, 'comment', None)}",
                            'metadata': {'retcode': getattr(result, 'retcode', None), 'comment': getattr(result, 'comment', None)}
                        }
                        self.ml_collector.record_execution(exec_payload)
                except Exception:
                    self.logger.exception('ML collector failed')

                return ExecutionResult(
                    order_id=None,
                    status=OrderStatus.REJECTED,
                    executed_price=None,
                    executed_volume=None,
                    timestamp=datetime.now(),
                    error=f"{result.retcode}: {getattr(result, 'comment', None)}",
                    metadata={'retcode': getattr(result, 'retcode', None), 'comment': getattr(result, 'comment', None)}
                )

        except Exception as e:
            self.logger.error(f"Order execution error: {e}", exc_info=True)
            try:
                if self.ml_collector:
                    exec_payload = {
                        'order_id': None,
                        'status': 'REJECTED',
                        'error': str(e)
                    }
                    self.ml_collector.record_execution(exec_payload)
            except Exception:
                self.logger.exception('ML collector failed')

            return ExecutionResult(
                order_id=None,
                status=OrderStatus.REJECTED,
                executed_price=None,
                executed_volume=None,
                timestamp=datetime.now(),
                error=str(e)
            )

    def close_position(self, ticket: int, volume: Optional[float] = None) -> ExecutionResult:
        """
        Close an existing position.
        
        Args:
            ticket: Position ticket number
            volume: Volume to close (None = full position)
            
        Returns:
            ExecutionResult with close outcome
        """
        try:
            # Get position
            position = mt5.positions_get(ticket=ticket)
            if not position:
                return ExecutionResult(
                    order_id=None,
                    status=OrderStatus.REJECTED,
                    executed_price=None,
                    executed_volume=None,
                    timestamp=datetime.now(),
                    error=f"Position #{ticket} not found"
                )
                
            position = position[0]
            
            # Determine close parameters
            close_volume = volume if volume else position.volume
            
            if position.type == mt5.ORDER_TYPE_BUY:
                order_type = mt5.ORDER_TYPE_SELL
                price = mt5.symbol_info_tick(position.symbol).bid
            else:
                order_type = mt5.ORDER_TYPE_BUY
                price = mt5.symbol_info_tick(position.symbol).ask
                
            # Build close request
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": str(position.symbol),
                "volume": float(close_volume),
                "type": int(order_type),
                "position": int(ticket),
                "price": float(price),
                "deviation": int(self.slippage),
                "magic": int(self.magic_number),
                "comment": "Cthulu close",
                "type_time": int(mt5.ORDER_TIME_GTC),
                "type_filling": int(mt5.ORDER_FILLING_IOC),
            }
            
            # Submit close order
            result = mt5.order_send(request)
            
            if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                # Safely get profit - not all brokers/MT5 versions include it in order_send result
                close_profit = getattr(result, 'profit', 0.0) or 0.0
                self.logger.info(f"Position closed: #{ticket} | Profit: {close_profit:.2f}")
                try:
                    if self.ml_collector:
                        exec_payload = {
                            'position_ticket': ticket,
                            'order_id': getattr(result, 'order', None),
                            'status': 'CLOSED',
                            'price': getattr(result, 'price', None),
                            'volume': getattr(result, 'volume', None),
                            'profit': getattr(result, 'profit', None),
                            'timestamp': datetime.utcnow().isoformat() + 'Z',
                        }
                        self.ml_collector.record_execution(exec_payload)
                except (AttributeError, TypeError) as e:
                    self.logger.debug(f'ML collector recording skipped: {e}')
                except Exception:
                    self.logger.exception('ML collector failed')

                return ExecutionResult(
                    order_id=result.order,
                    status=OrderStatus.FILLED,
                    executed_price=result.price,
                    executed_volume=result.volume,
                    timestamp=datetime.now(),
                    metadata={'profit': close_profit, 'commission': getattr(result, 'commission', 0.0)}
                )
            else:
                error = result.comment if result else "Unknown error"
                try:
                    if self.ml_collector:
                        exec_payload = {
                            'position_ticket': ticket,
                            'order_id': None,
                            'status': 'REJECTED',
                            'error': error,
                            'timestamp': datetime.utcnow().isoformat() + 'Z'
                        }
                        self.ml_collector.record_execution(exec_payload)
                except Exception:
                    self.logger.exception('ML collector failed')

                return ExecutionResult(
                    order_id=None,
                    status=OrderStatus.REJECTED,
                    executed_price=None,
                    executed_volume=None,
                    timestamp=datetime.now(),
                    error=error
                )
                
        except Exception as e:
            self.logger.error(f"Position close error: {e}")
            try:
                if self.ml_collector:
                    exec_payload = {
                        'position_ticket': ticket,
                        'order_id': None,
                        'status': 'REJECTED',
                        'error': str(e),
                        'timestamp': datetime.utcnow().isoformat() + 'Z'
                    }
                    self.ml_collector.record_execution(exec_payload)
            except Exception:
                self.logger.exception('ML collector failed')

            return ExecutionResult(
                order_id=None,
                status=OrderStatus.REJECTED,
                executed_price=None,
                executed_volume=None,
                timestamp=datetime.now(),
                error=str(e)
            )

    def execute_order(self, symbol: str, order_type: str, volume: float, sl: Optional[float] = None, tp: Optional[float] = None, comment: str = "", magic_number: Optional[int] = None) -> Optional[int]:
        """Compatibility wrapper for legacy callers.

        Places a MARKET order using the existing `place_order` pathway and returns
        the resulting position ticket or order id if the order was filled.
        """
        try:
            sid = f"exec_{int(datetime.now().timestamp())}"
            side = 'BUY' if str(order_type).lower() in ('buy', 'long') else 'SELL'

            order_req = OrderRequest(
                signal_id=sid,
                symbol=symbol,
                side=side,
                volume=volume,
                order_type=OrderType.MARKET,
                sl=sl,
                tp=tp,
                client_tag=f"legacy:{sid}",
                metadata={'comment': comment}
            )

            orig_magic = self.magic_number
            if magic_number is not None:
                self.magic_number = magic_number

            result = self.place_order(order_req)

            if magic_number is not None:
                self.magic_number = orig_magic

            if result and result.status == OrderStatus.FILLED:
                return result.position_ticket or result.order_id
            return None
        except Exception as e:
            self.logger.error(f"Legacy execute_order failed: {e}", exc_info=True)
            return None

    def modify_position(self, ticket: int, sl: Optional[float] = None, 
                       tp: Optional[float] = None) -> bool:
        """
        Modify stop-loss and/or take-profit for an existing position.
        
        Args:
            ticket: Position ticket to modify
            sl: New stop loss (None to keep current)
            tp: New take profit (None to keep current)
            
        Returns:
            True if modified successfully, False otherwise
        """
        try:
            # Get position info
            position = mt5.positions_get(ticket=ticket)
            if not position:
                self.logger.warning(f"Position {ticket} not found for modification")
                return False
            
            position = position[0]
            
            # Get current SL/TP if not provided
            new_sl = sl if sl is not None else position.sl
            new_tp = tp if tp is not None else position.tp
            
            # Skip if values haven't changed (avoid unnecessary broker calls)
            # Use tolerance for float comparison
            sl_unchanged = (sl is None or abs(new_sl - position.sl) < 0.00001) if position.sl else (sl is None)
            tp_unchanged = (tp is None or abs(new_tp - position.tp) < 0.00001) if position.tp else (tp is None)
            
            if sl_unchanged and tp_unchanged:
                self.logger.debug(f"Position {ticket}: SL/TP unchanged, skipping modification")
                return True  # Consider this a success - nothing to do
            
            # Build modification request
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": str(position.symbol),
                "position": int(ticket),
                "sl": float(new_sl) if new_sl is not None else 0.0,
                "tp": float(new_tp) if new_tp is not None else 0.0,
                "magic": int(self.magic_number),
            }
            
            self.logger.debug(f"Modifying position {ticket}: SL={new_sl}, TP={new_tp}")
            
            # Validate stop distances against broker minimums when available
            try:
                sym_info = self.connector.get_symbol_info(position.symbol)
                point = float(sym_info.get('point')) if sym_info and sym_info.get('point') else None
                stops_level = None
                if sym_info:
                    stops_level = sym_info.get('trade_stops_level') or sym_info.get('trade_freeze_level')
                if point and stops_level:
                    min_dist = float(point) * float(stops_level)
                    # For buy: price - sl must be >= min_dist; For sell: sl - price must be >= min_dist
                    cur_price = getattr(position, 'price_current', None) or getattr(position, 'price_open', None)
                    if cur_price is not None and new_sl is not None:
                        if (new_sl >= cur_price and position.type == mt5.ORDER_TYPE_BUY) or (
                            (new_sl <= cur_price) and position.type == mt5.ORDER_TYPE_SELL
                        ):
                            self.logger.error(f"Rejected SL {new_sl} for {ticket}: wrong side relative to current price {cur_price}")
                            return False
                        if position.type == mt5.ORDER_TYPE_BUY and (cur_price - new_sl) < min_dist - 1e-12:
                            self.logger.error(f"Rejected SL {new_sl} for {ticket}: too close to price {cur_price} (min_dist={min_dist})")
                            return False
                        if position.type == mt5.ORDER_TYPE_SELL and (new_sl - cur_price) < min_dist - 1e-12:
                            self.logger.error(f"Rejected SL {new_sl} for {ticket}: too close to price {cur_price} (min_dist={min_dist})")
                            return False
            except Exception:
                # Non-fatal: proceed to broker and let it decide
                pass

            # Submit modification
            self.logger.debug("MT5 modify request for %s: %s", ticket, request)
            result = mt5.order_send(request)
            # Log result details for diagnosis
            try:
                rc = getattr(result, 'retcode', None)
                comment = getattr(result, 'comment', None)
                self.logger.debug("MT5 order_send result for modify %s: retcode=%s, comment=%s", ticket, rc, comment)
            except Exception:
                pass
            
            if result is None:
                try:
                    error = mt5.last_error()
                except Exception:
                    error = None
                self.logger.error(f"Position modification failed for {ticket}: {error}")
                return False
            
            # Consider 'DONE' or broker-specific 'No changes' retcode (10025) as success for idempotency
            if result.retcode == getattr(mt5, 'TRADE_RETCODE_DONE', None) or getattr(result, 'retcode', None) == 10025:
                if getattr(result, 'retcode', None) == 10025:
                    self.logger.info(f"Position modification returned 'No changes' for {ticket} (retcode={result.retcode}), treating as success")
                else:
                    self.logger.info(f"Position {ticket} modified: SL={new_sl}, TP={new_tp}")
                return True
            else:
                self.logger.error(f"Position modification rejected for {ticket}: {result.retcode} - {getattr(result, 'comment', '')}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error modifying position {ticket}: {e}", exc_info=True)
            return False

    def _build_mt5_request(self, order_req: OrderRequest) -> Dict[str, Any]:
        """Build MT5 order request dictionary."""
        # Determine MT5 order type
        if order_req.side.upper() == 'BUY':
            mt5_type = mt5.ORDER_TYPE_BUY
        else:
            mt5_type = mt5.ORDER_TYPE_SELL
            
        # Ensure symbol exists and select the proper variant
        selected_symbol = self.connector.ensure_symbol_selected(order_req.symbol) or order_req.symbol

        # Get current price if market order
        if order_req.order_type == OrderType.MARKET:
            symbol_info = self.connector.get_symbol_info(selected_symbol)
            price = None
            if symbol_info and symbol_info.get('ask') is not None and symbol_info.get('bid') is not None:
                price = symbol_info['ask'] if order_req.side.upper() == 'BUY' else symbol_info['bid']
            else:
                # Fallback to tick data
                tick = self.connector._mt5_symbol_info_tick(selected_symbol)
                if tick is not None:
                    price = getattr(tick, 'ask', None) if order_req.side.upper() == 'BUY' else getattr(tick, 'bid', None)

            if price is None:
                raise ValueError(f"Cannot determine market price for {selected_symbol}")
        else:
            price = order_req.price

        # Validate volume against symbol constraints when available
        final_volume = order_req.volume
        if symbol_info:
            try:
                min_v = float(symbol_info.get('volume_min', 0.01))
                max_v = float(symbol_info.get('volume_max', 100.0))
                step = float(symbol_info.get('volume_step', 0.01))
                
                # Auto-adjust to minimum volume if below
                if final_volume < min_v:
                    self.logger.warning(f"Volume {final_volume} below minimum {min_v} for {selected_symbol}, adjusting to minimum")
                    final_volume = min_v
                    
                if final_volume > max_v:
                    raise ValueError(f"Requested volume {final_volume} > maximum {max_v} for {selected_symbol}")
                    
                # Normalize to step
                final_volume = round(round(final_volume / step) * step, 2)
            except ValueError:
                raise  # Re-raise ValueError for max volume exceeded
            except Exception:
                # If validation fails for other reasons, let the order submit and let MT5 reject with clearer message
                pass

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": str(selected_symbol),
            "volume": float(final_volume),
            "type": int(mt5_type),
            "price": float(price),
            "deviation": int(self.slippage),
            "magic": int(self.magic_number),
            "comment": str(order_req.client_tag or "Cthulu")[:31],  # MT5 comment max 31 chars
            "type_time": int(mt5.ORDER_TIME_GTC),
            "type_filling": int(mt5.ORDER_FILLING_IOC),
        }
        
        # Add SL/TP if specified
        # If no SL provided, ask risk manager for a suggested default based on balance
        if not order_req.sl:
            try:
                acct = self.connector.get_account_info()
                balance = float(acct.get('balance')) if acct and acct.get('balance') is not None else None
            except Exception:
                balance = None

            if balance is not None and price is not None:
                # Compute a proposed SL distance using RiskManager helper
                try:
                    # Import SL helpers from position.risk_manager (compatibility stubs)
                    from cthulu.position.risk_manager import suggest_sl_adjustment as _sugg_fn
                    from cthulu.position.risk_manager import _threshold_from_config as _thr_fn
                    
                    # Get threshold config for this balance tier
                    threshold_info = _thr_fn(
                        balance, 
                        self.risk_config.get('sl_balance_thresholds') if isinstance(self.risk_config, dict) else None, 
                        self.risk_config.get('sl_balance_breakpoints') if isinstance(self.risk_config, dict) else None
                    )
                    threshold_pct = threshold_info.get('threshold', 0.01) if isinstance(threshold_info, dict) else 0.01
                    
                    # Compute a naive proposed SL using the threshold
                    if order_req.side.upper() == 'BUY':
                        proposed_sl = float(price) * (1.0 - threshold_pct)
                    else:
                        proposed_sl = float(price) * (1.0 + threshold_pct)

                    # Ask the risk helper to refine the proposed SL
                    suggestion = _sugg_fn(
                        order_req.symbol,
                        balance,
                        float(price),
                        float(proposed_sl),
                        side=order_req.side.upper(),
                        thresholds=self.risk_config.get('sl_balance_thresholds') if isinstance(self.risk_config, dict) else None,
                        breakpoints=self.risk_config.get('sl_balance_breakpoints') if isinstance(self.risk_config, dict) else None,
                    )
                    adj = suggestion.get('adjusted_sl')
                    if adj is not None:
                        final_sl = adj
                    else:
                        final_sl = proposed_sl

                    order_req.metadata.setdefault('risk_suggestion', suggestion)
                    order_req.sl = float(final_sl)
                    self.logger.info(f"Risk-managed SL for {order_req.symbol}: {order_req.sl} (balance={balance})")
                except Exception:
                    # Fallback: use small percent of price (1%) based on side
                    try:
                        if order_req.side.upper() == 'BUY':
                            order_req.sl = float(price) * 0.99
                        else:
                            order_req.sl = float(price) * 1.01
                        self.logger.debug(f'Using fallback SL calculation: {order_req.sl}')
                    except Exception:
                        self.logger.exception('Failed to compute risk-managed SL; proceeding without SL')

        # If we now have SL but no TP, set TP using a conservative RR (2.0) based on distance
        if order_req.sl and not order_req.tp and price is not None:
            try:
                rr = self.risk_config.get('default_rr', 2.0) if isinstance(self.risk_config, dict) else 2.0
                if order_req.side.upper() == 'BUY':
                    sl_dist = float(price) - float(order_req.sl)
                    order_req.tp = float(price) + abs(sl_dist) * float(rr)
                else:
                    sl_dist = float(order_req.sl) - float(price)
                    order_req.tp = float(price) - abs(sl_dist) * float(rr)
                self.logger.info(f"Auto TP for {order_req.symbol}: {order_req.tp} (RR={rr})")
            except Exception:
                self.logger.exception('Failed to compute auto TP')

        # Validate and cap stop loss to prevent excessive risk
        # CRITICAL: This safety check prevents misconfigured stop losses
        # that could cause massive losses (e.g., the 25% bug that was fixed)
        if order_req.sl and price is not None:
            max_sl_pct = self.max_sl_pct  # Use configurable max from instance
            sl_dist_pct = abs(float(price) - float(order_req.sl)) / float(price)
            
            if sl_dist_pct > max_sl_pct:
                self.logger.warning(
                    f"Stop loss distance {sl_dist_pct*100:.2f}% exceeds maximum {max_sl_pct*100:.0f}% - "
                    f"capping to {max_sl_pct*100:.0f}% (prevents excessive risk)"
                )
                # Cap the SL to max allowed distance
                if order_req.side.upper() == 'BUY':
                    order_req.sl = float(price) * (1.0 - max_sl_pct)
                else:
                    order_req.sl = float(price) * (1.0 + max_sl_pct)
                
                # Ensure metadata exists before setting values
                if order_req.metadata is None:
                    order_req.metadata = {}
                order_req.metadata['sl_capped'] = True
                order_req.metadata['original_sl_dist_pct'] = sl_dist_pct
        
        if order_req.sl:
            request["sl"] = float(order_req.sl)
        if order_req.tp:
            request["tp"] = float(order_req.tp)
            
        return request




