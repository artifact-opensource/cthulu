"""
MT5 Connector Module

Handles MetaTrader 5 terminal connection, session management, and health monitoring.
Implements retry logic, rate limiting, and reconnection policies.
"""

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:
    # Minimal stub of MetaTrader5 for testing and import-time resilience
    class _Mt5Stub:
        ORDER_TYPE_BUY = 0
        ORDER_TYPE_SELL = 1
        TRADE_ACTION_DEAL = 0
        ORDER_TIME_GTC = 0
        ORDER_FILLING_FOK = 3
        TRADE_RETCODE_DONE = 10009

        def initialize(self, *args, **kwargs):
            return False

        def shutdown(self):
            return False

        def last_error(self):
            return {'code': 1, 'message': 'MT5 not available'}

    mt5 = _Mt5Stub()
import os
import time
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from pathlib import Path
try:
    # Prefer a relative import when running inside the package (pytest collection)
    from ..market.tick_manager import TickManager
except Exception:
    # Fallback to absolute import for scripts run outside the package context
    from cthulu.market.tick_manager import TickManager


@dataclass
class ConnectionConfig:
    """MT5 connection configuration"""
    login: int
    password: str
    server: str
    timeout: int = 60000
    portable: bool = False
    path: Optional[str] = None
    max_retries: int = 3
    retry_delay: int = 5
    # When True, attempt to start the MT5 terminal if it's not running (safe default: False)
    start_on_missing: bool = False
    # Seconds to wait after starting terminal for it to become responsive
    start_wait: int = 5


class MT5Connector:
    """
    MetaTrader 5 connection manager with health checks and reconnection logic.
    
    Provides reliable connection management.
    - Automatic reconnection on connection loss
    - Health checks and session monitoring
    - Rate limiting and timeout handling
    - Exception consolidation
    """
    
    def __init__(self, config: ConnectionConfig):
        """
        Initialize MT5 connector.
        
        Args:
            config: Connection configuration
        """
        self.config = config
        self.connected = False
        self.logger = logging.getLogger("cthulu.connector")
        self._lock = Lock()
        self._last_request_time = 0.0
        self._min_request_interval = 0.1  # 100ms between requests
        # Tick manager for lightweight tick caching and subscriptions
        try:
            self._tick_manager = TickManager(self)
        except Exception:
            self._tick_manager = None
        
    def _is_mt5_process_running(self) -> bool:
        """Return True if a MetaTrader terminal process is running on the host."""
        try:
            # Look for likely binary names via tasklist (Windows) or ps (Unix)
            import subprocess
            exe = None
            if self.config.path:
                exe = os.path.basename(self.config.path).lower()
            if os.name == 'nt':
                out = subprocess.check_output(['tasklist', '/NH', '/FO', 'CSV'], universal_newlines=True, stderr=subprocess.DEVNULL)
                lines = out.splitlines()
                for l in lines:
                    if exe and exe in l.lower():
                        return True
                    # quick heuristic for terminal if path not provided
                    if 'terminal64.exe' in l.lower() or 'terminal.exe' in l.lower() or 'metatrader' in l.lower():
                        return True
            else:
                out = subprocess.check_output(['ps', 'ax'], universal_newlines=True, stderr=subprocess.DEVNULL)
                if exe and exe in out.lower():
                    return True
                if 'terminal64' in out.lower() or 'terminal' in out.lower() or 'metatrader' in out.lower():
                    return True
        except Exception as e:
            self.logger.debug("Failed to check MT5 process presence: %s", e, exc_info=True)
        return False

    def connect(self) -> bool:
        """
        Establish connection to MT5 terminal.
        
        Returns:
            True if connection successful
        """
        with self._lock:
            # Extra diagnostics to help operators debug environment issues
            try:
                mv = getattr(mt5, '__version__', None) or getattr(mt5, 'version', None)
                self.logger.debug(f"MT5 python package version: {mv}")
            except Exception as e:
                self.logger.debug("Failed to determine MT5 package version: %s", e, exc_info=True)
            try:
                tinfo = mt5.terminal_info()
                self.logger.debug(f"MT5 terminal_info: {tinfo}")
            except Exception:
                self.logger.debug("MT5 terminal_info: unavailable")

            # Environment variable overrides (runtime routing): allow operators to
            # provide credentials via environment to avoid accidental config edits.
            try:
                env_login = os.getenv('MT5_LOGIN')
                env_pass = os.getenv('MT5_PASSWORD')
                env_server = os.getenv('MT5_SERVER')
                if env_login:
                    try:
                        self.config.login = int(env_login)
                    except Exception:
                        # keep as string if not integer
                        self.config.login = env_login
                    self.logger.info('Using MT5 login from environment')
                if env_pass:
                    self.config.password = env_pass
                    self.logger.info('Using MT5 password from environment')
                if env_server:
                    self.config.server = env_server
                    self.logger.info('Using MT5 server from environment')
            except Exception:
                # non-fatal: continue with existing config
                pass

            # If no explicit credentials set (login==0), attempt to 'attach' to a running terminal first
            credential_mode = bool(getattr(self.config, 'login', None) and self.config.login != 0)

            for attempt in range(1, self.config.max_retries + 1):
                try:
                    self.logger.info(f"Connecting to MT5 (attempt {attempt}/{self.config.max_retries})...")

                    if credential_mode:
                        # Initialize MT5 with credentials directly (preferred when provided)
                        self.logger.info("Initializing MT5 with credentials...")
                        init_result = mt5.initialize(
                            login=self.config.login,
                            password=self.config.password,
                            server=self.config.server,
                            timeout=self.config.timeout
                        )
                    else:
                        # No credentials: attempt to attach to an already running terminal
                        self.logger.info('No account credentials provided (login==0); attempting to attach to running MT5 terminal...')
                        try:
                            init_result = mt5.initialize()
                        except TypeError:
                            # Some MT5 builds expect 'path' kw; fall back to init without args
                            init_result = mt5.initialize()

                    if not init_result:
                        # Provide richer diagnostic info
                        err = mt5.last_error()
                        self.logger.error(f"MT5 initialize returned False. last_error={err}")

                        # Check configured path presence
                        if self.config.path:
                            try:
                                if not Path(self.config.path).exists():
                                    self.logger.error(f"Configured MT5 path does not exist: {self.config.path}")
                                else:
                                    self.logger.info(f"Configured MT5 path exists: {self.config.path}")
                            except Exception:
                                pass

                        # Check whether terminal process appears to be running
                        if self._is_mt5_process_running():
                            self.logger.info('Detected a running MT5/terminal process on the host (interactive session required).')
                        else:
                            self.logger.info('No MT5 process detected on the host. Ensure MetaTrader 5 is running in an interactive desktop session.')

                        # If configured to auto-start, attempt to start the terminal process
                        if (not self._is_mt5_process_running()) and self.config.path and getattr(self.config, 'start_on_missing', False):
                            try:
                                import subprocess
                                self.logger.info(f"Starting MT5 terminal from path: {self.config.path}")
                                subprocess.Popen([self.config.path], cwd=Path(self.config.path).parent)
                                self.logger.info(f"Waiting up to {self.config.start_wait}s for MT5 to start")
                                time.sleep(self.config.start_wait)
                                if self._is_mt5_process_running():
                                    self.logger.info('MT5 process detected after start request')
                                else:
                                    self.logger.warning('MT5 process not detected after start request')
                            except Exception as e:
                                self.logger.exception(f"Failed to start MT5 terminal: {e}")

                        # If credential init failed or attach failed, try explicit fallback via configured path
                        if self.config.path:
                            try:
                                self.logger.info(f"Attempting fallback initialize using MT5 path: {self.config.path}")
                                init_path = mt5.initialize(path=self.config.path)
                                self.logger.debug(f"Fallback initialize(path) returned: {init_path}")
                                if init_path:
                                    self.logger.info('Fallback initialize succeeded using configured path')
                                else:
                                    self.logger.error(f"Fallback initialize failed: {mt5.last_error()}")
                            except Exception as e:
                                self.logger.exception(f"Exception during fallback initialize(path): {e}")

                        raise ConnectionError(f"MT5 initialize failed: {err}")

                    # Verify connection by reading account_info
                    account_info = mt5.account_info()
                    if not account_info:
                        raise ConnectionError("Connected but cannot retrieve account info")

                    if credential_mode and account_info.login != self.config.login:
                        raise ConnectionError(f"Connected to wrong account: {account_info.login}")                    
                    self.connected = True
                    # Mask account login in logs to avoid leaking full account numbers
                    acct_display = str(self.config.login)
                    acct_masked = acct_display if len(acct_display) <= 4 else f"****{acct_display[-4:]}"
                    self.logger.info(f"Connected to {self.config.server} (account: {acct_masked})")
                    self.logger.info(f"Balance: ${account_info.balance:.2f}, Trade allowed: {account_info.trade_allowed}")
                    return True
                    
                except Exception as e:
                    self.logger.error(f"Connection attempt {attempt} failed: {e}")
                    if attempt < self.config.max_retries:
                        time.sleep(self.config.retry_delay)
                        
            # Dump a small diagnostic file to aid troubleshooting
            try:
                diag_path = Path(__file__).parent.parent / 'logs' / 'mt5_diag.log'
                diag_path.parent.mkdir(parents=True, exist_ok=True)
                with open(diag_path, 'w', encoding='utf-8') as fh:
                    try:
                        fh.write(f"mt5_package_version: {getattr(mt5, '__version__', getattr(mt5, 'version', 'unknown'))}\n")
                    except Exception:
                        pass
                    try:
                        fh.write(f"last_error: {mt5.last_error()}\n")
                    except Exception:
                        pass
                    try:
                        fh.write(f"terminal_info: {mt5.terminal_info()}\n")
                    except Exception:
                        pass
                    try:
                        fh.write(f"configured_path_exists: {Path(self.config.path).exists() if self.config.path else 'no_path_configured'}\n")
                    except Exception:
                        pass
                    try:
                        fh.write(f"mt5_process_running: {self._is_mt5_process_running()}\n")
                    except Exception:
                        pass
            except Exception:
                self.logger.exception('Failed to write MT5 diagnostic file')

            self.logger.error("All connection attempts failed")
            return False
            
    def disconnect(self):
        """Disconnect from MT5 terminal."""
        with self._lock:
            if self.connected:
                mt5.shutdown()
                self.connected = False
                self.logger.info("Disconnected from MT5")
                
    def is_connected(self) -> bool:
        """
        Check if connected and terminal is responsive.
        
        Returns:
            True if connected and healthy
        """
        if not self.connected:
            return False
            
        try:
            # Test connection with terminal info request
            info = mt5.terminal_info()
            return info is not None and info.connected
        except Exception as e:
            self.logger.error(f"Connection check failed: {e}")
            self.connected = False
            return False
            
    def reconnect(self) -> bool:
        """
        Reconnect to MT5 terminal.
        
        Returns:
            True if reconnection successful
        """
        self.logger.info("Attempting reconnection...")
        self.disconnect()
        time.sleep(2)
        return self.connect()
        
    def _rate_limit(self):
        """Apply rate limiting between requests."""
        current_time = time.time()
        elapsed = current_time - self._last_request_time
        
        if elapsed < self._min_request_interval:
            time.sleep(self._min_request_interval - elapsed)
            
        self._last_request_time = time.time()
        
    def _normalize_symbol(self, s: str) -> str:
        """Return normalized symbol string for comparison (alphanumeric upper-case)."""
        if not s:
            return ""
        return ''.join(ch for ch in s.upper() if ch.isalnum())

    def _mt5_symbol_info_tick(self, symbol: str):
        """Low-level wrapper around mt5.symbol_info_tick to be used by TickManager.

        Returns the native mt5 tick object or None.
        """
        try:
            # Ensure symbol selected for terminal
            sel = self.ensure_symbol_selected(symbol)
            if not sel:
                return None
            self._rate_limit()
            return mt5.symbol_info_tick(sel)
        except Exception:
            return None

    def get_recent_ticks(self, symbol: str, seconds: float = 60.0, max_points: int = 200):
        """Return recent ticks for `symbol` from the in-memory ring buffer."""
        if self._tick_manager is None:
            return []
        return self._tick_manager.get_recent(symbol, seconds=seconds, max_points=max_points)

    def subscribe_ticks(self, symbol: str, callback, priority: str = 'high'):
        """Subscribe to tick updates for `symbol` with given priority (high/medium/low)."""
        if self._tick_manager is None:
            raise RuntimeError("Tick manager not initialized")
        self._tick_manager.subscribe(symbol, callback, priority=priority)

    def unsubscribe_ticks(self, symbol: str, callback):
        if self._tick_manager is None:
            return
        self._tick_manager.unsubscribe(symbol, callback)

    def _find_matching_symbol(self, desired: str) -> List[str]:
        """Return a list of available MT5 symbol names that best match `desired`.

        Simplified matching strategy:
        1. Exact normalized match (case-insensitive, alphanumeric only)
        2. Exact case-sensitive match as fallback
        
        This uses broker defaults and avoids complex variant matching.
        If symbol isn't found, user should use exact broker symbol name.
        """
        matches: List[str] = []
        try:
            all_symbols = mt5.symbols_get()
        except Exception:
            return matches
        if not all_symbols:
            return matches

        desired_norm = self._normalize_symbol(desired)

        # Stage 1: exact normalized match (case-insensitive)
        for s in all_symbols:
            try:
                name_norm = self._normalize_symbol(s.name)
                if name_norm == desired_norm:
                    matches.append(s.name)
            except Exception:
                continue
        if matches:
            return matches

        # Stage 2: exact case-sensitive match as fallback
        for s in all_symbols:
            try:
                if s.name == desired:
                    matches.append(s.name)
            except Exception:
                continue
        
        return matches

    def ensure_symbol_selected(self, symbol: str) -> Optional[str]:
        """Ensure symbol is selected in MT5 using broker defaults.

        Returns the actual selected symbol name on success, or None on failure.
        
        Simplified approach: Uses exact symbol name from broker.
        Users should specify the exact symbol name as shown in MT5.
        """
        # Try direct selection with exact symbol name
        try:
            if mt5.symbol_select(symbol, True):
                return symbol
        except Exception:
            pass

        # Try normalized matching (case-insensitive) as fallback
        matches = self._find_matching_symbol(symbol)
        if matches:
            self.logger.debug(f"Found candidate symbols for {symbol}: {matches}")
            for m in matches:
                try:
                    # Only select symbols that appear tradable (have point and volume_min)
                    info = self.get_symbol_info(m)
                    if not info or info.get('point') is None or info.get('volume_min') is None:
                        self.logger.debug(f"Skipping non-tradable candidate symbol: {m}")
                        continue
                    if mt5.symbol_select(m, True):
                        self.logger.info(f"Selected symbol: {m} (matched from {symbol})")
                        return m
                except Exception:
                    continue
            self.logger.warning(f"Found symbols but failed to select any tradable one: {matches}")
        
        # Log available symbols to help user find correct name
        self.logger.warning(
            f"Symbol '{symbol}' not found. Please use the exact symbol name from MT5 Market Watch. "
            f"Open MetaTrader 5 → Market Watch (Ctrl+M) → Find your instrument → Use exact name."
        )
        try:
            sample = mt5.symbols_get()[:20]
            sample_names = [s.name for s in sample]
            self.logger.info(f"Available symbols (sample): {sample_names}")
        except Exception:
            pass

        return None

    def get_rates(
        self,
        symbol: str,
        timeframe: int,
        count: int,
        start_pos: int = 0
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch historical rates for a symbol.
        
        Args:
            symbol: Trading symbol
            timeframe: MT5 timeframe constant
            count: Number of bars to fetch
            start_pos: Starting position (0 = most recent)
            
        Returns:
            List of rate dictionaries or None on error
        """
        if not self.is_connected():
            # Try to connect first
            if not self.connect():
                self.logger.error("Not connected to MT5")
                return None
            
        self._rate_limit()
        
        try:
            # Ensure symbol is selected (flexible)
            selected = self.ensure_symbol_selected(symbol)
            if not selected:
                self.logger.error(f"Failed to select symbol {symbol}")
                return None
                
            # Fetch rates
            rates = mt5.copy_rates_from_pos(selected, timeframe, start_pos, count)
            
            if rates is None or len(rates) == 0:
                error = mt5.last_error()
                self.logger.error(f"Failed to fetch rates: {error}")
                return None
                
            # Convert numpy array to list of dicts
            return [
                {
                    'time': datetime.fromtimestamp(rate[0]),
                    'open': float(rate[1]),
                    'high': float(rate[2]),
                    'low': float(rate[3]),
                    'close': float(rate[4]),
                    'tick_volume': int(rate[5]),
                    'spread': int(rate[6]),
                    'real_volume': int(rate[7])
                }
                for rate in rates
            ]
            
        except Exception as e:
            self.logger.error(f"Error fetching rates: {e}", exc_info=True)
            return None
            
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        Get current account information.
        
        Returns:
            Dictionary with account details or None
        """
        if not self.is_connected():
            return None
            
        self._rate_limit()
        
        try:
            account = mt5.account_info()
            if account is None:
                return None
                
            return {
                'login': account.login,
                'server': account.server,
                'balance': account.balance,
                'equity': account.equity,
                'margin': account.margin,
                'margin_free': account.margin_free,
                'margin_level': account.margin_level,
                'profit': account.profit,
                'currency': account.currency,
                'leverage': account.leverage,
                'trade_allowed': account.trade_allowed,
            }
        except Exception as e:
            self.logger.error(f"Error fetching account info: {e}")
            return None
            
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get symbol information and trading specifications.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Dictionary with symbol details or None
        """
        if not self.is_connected():
            return None
            
        self._rate_limit()
        
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                return None
                
            return {
                'name': info.name,
                'bid': info.bid,
                'ask': info.ask,
                'spread': info.spread,
                'digits': info.digits,
                'point': getattr(info, 'point', None),
                'trade_mode': getattr(info, 'trade_mode', None),
                'trade_stops_level': getattr(info, 'trade_stops_level', None),
                'trade_freeze_level': getattr(info, 'trade_freeze_level', None),
                'volume_min': getattr(info, 'volume_min', None),
                'volume_max': getattr(info, 'volume_max', None),
                'volume_step': getattr(info, 'volume_step', None),
                'contract_size': getattr(info, 'trade_contract_size', None) or getattr(info, 'contract_size', None),
                'currency_base': getattr(info, 'currency_base', None),
                'currency_profit': getattr(info, 'currency_profit', None),
                'currency_margin': getattr(info, 'currency_margin', None),
            }
        except Exception as e:
            self.logger.error(f"Error fetching symbol info: {e}")
            return None

    def get_point_value(self, symbol: str) -> Optional[float]:
        """Return point value in account currency for one point movement for symbol."""
        try:
            info = self.get_symbol_info(symbol)
            if not info:
                return None
            point = info.get('point')
            contract = info.get('contract_size') or info.get('trade_contract_size') or info.get('contract')
            if point is None:
                return None
            if contract is None:
                # fallback to 1.0
                contract = 1.0
            return float(point) * float(contract)
        except Exception:
            return None

    def get_point(self, symbol: str) -> float:
        """Return point size for symbol (minimum price increment)."""
        try:
            info = self.get_symbol_info(symbol)
            if not info:
                return 0.00001  # default for forex
            point = info.get('point')
            if point is not None:
                return float(point)
            return 0.00001
        except Exception:
            return 0.00001

    def get_min_lot(self, symbol: str) -> float:
        """Return minimum tradable lot size for symbol."""
        try:
            info = self.get_symbol_info(symbol)
            if not info:
                return 0.01
            return float(info.get('volume_min', 0.01))
        except Exception:
            return 0.01

    def get_spread(self, symbol: str) -> Optional[float]:
        """Return current spread for symbol in points or price units."""
        try:
            info = self.get_symbol_info(symbol)
            if not info:
                return None
            # prefer explicit spread if available
            spread = info.get('spread')
            if spread is not None:
                return float(spread)
            # fallback to ask-bid
            bid = info.get('bid')
            ask = info.get('ask')
            if bid is not None and ask is not None:
                return abs(float(ask) - float(bid))
            return None
        except Exception:
            return None

    def get_position_by_ticket(self, ticket: int) -> Optional[Dict[str, Any]]:
        """Return position information for a given MT5 position ticket.

        Returns a dict with keys: 'ticket', 'symbol', 'price_open', 'price_current',
        'profit', 'volume', 'type' or None if not found.
        """
        try:
            # Ensure connected
            if not self.is_connected():
                return None
            self._rate_limit()

            try:
                positions = mt5.positions_get(ticket=ticket)
            except Exception:
                # Some MT5 builds do not accept ticket kw; fall back to all positions
                positions = mt5.positions_get()

            if not positions:
                return None

            # If positions_get returned a single object, normalize to list
            if not isinstance(positions, list) and not hasattr(positions, '__iter__'):
                positions = [positions]

            for p in positions:
                try:
                    if getattr(p, 'ticket', None) == ticket or getattr(p, 'position', None) == ticket:
                        return {
                            'ticket': getattr(p, 'ticket', getattr(p, 'position', None)),
                            'symbol': getattr(p, 'symbol', None),
                            'price_open': getattr(p, 'price_open', getattr(p, 'price', None)),
                            'price_current': getattr(p, 'price_current', getattr(p, 'price', None)),
                            'profit': getattr(p, 'profit', None),
                            'volume': getattr(p, 'volume', None),
                            'type': getattr(p, 'type', None),
                        }
                except Exception:
                    continue

            return None
        except Exception as e:
            self.logger.error(f"Error fetching position by ticket {ticket}: {e}")
            return None

    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions from MT5.
        
        Returns:
            List of position dictionaries
        """
        try:
            positions = mt5.positions_get()
            if not positions:
                return []
            
            # If positions_get returned a single object, normalize to list
            if not isinstance(positions, list) and not hasattr(positions, '__iter__'):
                positions = [positions]
            
            result = []
            for p in positions:
                try:
                    result.append({
                        'ticket': getattr(p, 'ticket', getattr(p, 'position', None)),
                        'symbol': getattr(p, 'symbol', None),
                        'price_open': getattr(p, 'price_open', getattr(p, 'price', None)),
                        'price_current': getattr(p, 'price_current', getattr(p, 'price', None)),
                        'profit': getattr(p, 'profit', None),
                        'volume': getattr(p, 'volume', None),
                        'type': getattr(p, 'type', None),
                        'magic': getattr(p, 'magic', None),
                        'time': getattr(p, 'time', None),
                        'sl': getattr(p, 'sl', None),
                        'tp': getattr(p, 'tp', None),
                    })
                except Exception:
                    continue
            
            return result
        except Exception as e:
            self.logger.error(f"Error fetching open positions: {e}")
            return []
            
    def health_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check.
        
        Returns:
            Dictionary with health status metrics
        """
        health = {
            'connected': False,
            'terminal_connected': False,
            'trade_allowed': False,
            'account_valid': False,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            if not self.is_connected():
                return health
                
            health['connected'] = True
            
            # Check terminal
            terminal = mt5.terminal_info()
            if terminal:
                health['terminal_connected'] = terminal.connected
                health['trade_allowed'] = terminal.trade_allowed
                
            # Check account
            account = mt5.account_info()
            if account:
                health['account_valid'] = account.trade_allowed
                health['balance'] = account.balance
                health['equity'] = account.equity
                health['margin_level'] = account.margin_level
                
        except Exception as e:
            self.logger.error(f"Health check error: {e}")
            health['error'] = str(e)
            
        return health
        
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()




