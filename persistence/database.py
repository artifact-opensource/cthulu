"""
Database Module

Implements SQLite-based persistence for trades, signals, and metrics.
Provides historical retention and export capabilities.
"""

import sqlite3
import logging
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import os


@dataclass
class TradeRecord:
    """Trade record structure"""
    id: Optional[int] = None
    signal_id: str = ""
    order_id: Optional[int] = None
    symbol: str = ""
    side: str = ""
    volume: float = 0.0
    entry_price: float = 0.0
    exit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    profit: Optional[float] = None
    status: str = "OPEN"
    exit_reason: str = ""
    metadata: str = ""  # JSON string


@dataclass
class SignalRecord:
    """Signal record structure"""
    id: Optional[int] = None
    signal_id: str = ""
    timestamp: Optional[datetime] = None
    symbol: str = ""
    timeframe: str = ""
    side: str = ""
    action: str = ""
    confidence: float = 0.0
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    reason: str = ""
    executed: bool = False
    metadata: str = ""  # JSON string
    execution_timestamp: Optional[datetime] = None
    strategy_name: str = ""  # Name of strategy that generated the signal


class Database:
    """
    SQLite database manager for trade and signal persistence.
    
    Responsibilities:
    - Store all trades, signals, and execution results
    - Provide query interface for analytics
    - Historical data retention
    - Export capabilities
    """
    
    def __init__(self, db_path: str = "cthulu.db"):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.logger = logging.getLogger("Cthulu.persistence")
        self.conn: Optional[sqlite3.Connection] = None
        # Read-only marker (set if filesystem prevents initialization writes)
        self._read_only = False

        # Create database directory if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._initialize_db()
        
    def _initialize_db(self):
        """Create database tables if they don't exist."""
        try:
            self.conn = sqlite3.connect(
                self.db_path,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                timeout=30.0  # 30 second timeout to reduce lock conflicts
            )
            self.conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent access, but tolerate read-only files
            try:
                self.conn.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                # If the filesystem disallows writes (e.g., readonly file), mark and continue
                if 'readonly' in msg or 'attempt to write' in msg:
                    self.logger.warning("Database file appears read-only; continuing in read-only mode")
                    self._read_only = True
                else:
                    raise

            # If DB is read-only, skip schema creation and migrations (tests expect DB object to init)
            if getattr(self, '_read_only', False):
                self.logger.info("Skipping schema initialization due to read-only DB")
                return

            # Always attempt to set busy timeout if possible
            try:
                self.conn.execute("PRAGMA busy_timeout=30000")
            except Exception:
                pass
            
            cursor = self.conn.cursor()
            
            # Trades table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT NOT NULL,
                    order_id INTEGER,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    volume REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    entry_time TIMESTAMP NOT NULL,
                    exit_time TIMESTAMP,
                    profit REAL,
                    status TEXT DEFAULT 'OPEN',
                    exit_reason TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Positions table for tracking open positions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket INTEGER UNIQUE NOT NULL,
                    symbol TEXT NOT NULL,
                    type TEXT NOT NULL,
                    volume REAL NOT NULL,
                    open_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    sl REAL,
                    tp REAL,
                    profit REAL DEFAULT 0.0,
                    open_time TIMESTAMP NOT NULL,
                    magic_number INTEGER DEFAULT 0,
                    comment TEXT,
                    strategy_name TEXT,
                    entry_reason TEXT,
                    status TEXT DEFAULT 'open',
                    pnl REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Signals table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    signal_id TEXT UNIQUE NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    side TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    price REAL,
                    stop_loss REAL,
                    take_profit REAL,
                    reason TEXT,
                    executed BOOLEAN DEFAULT FALSE,
                    execution_timestamp TIMESTAMP,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Metrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Provenance table for order telemetry / auditing
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_provenance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    signal_id TEXT,
                    client_tag TEXT,
                    symbol TEXT,
                    side TEXT,
                    volume REAL,
                    caller_module TEXT,
                    caller_function TEXT,
                    stack_snippet TEXT,
                    metadata TEXT,
                    pid INTEGER,
                    thread_id INTEGER,
                    hostname TEXT,
                    python_version TEXT,
                    env_snapshot TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_ticket ON positions(ticket)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prov_timestamp ON order_provenance(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_prov_client_tag ON order_provenance(client_tag)")
            
            self.conn.commit()
            self.logger.info(f"Database initialized: {self.db_path}")
            # Run migrations if any
            try:
                self._run_migrations()
            except Exception:
                self.logger.exception('Failed to run DB migrations')
            
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}", exc_info=True)
            raise
            
    def _run_migrations(self):
        """Run lightweight migrations and create meta/version table."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # Example migration: ensure order_provenance exists (older DBs may lack it)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_provenance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP NOT NULL,
                    signal_id TEXT,
                    client_tag TEXT,
                    symbol TEXT,
                    side TEXT,
                    volume REAL,
                    caller_module TEXT,
                    caller_function TEXT,
                    stack_snippet TEXT,
                    metadata TEXT,
                    pid INTEGER,
                    thread_id INTEGER,
                    hostname TEXT,
                    python_version TEXT,
                    env_snapshot TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Set a schema_version if not present
            cursor.execute("SELECT value FROM meta WHERE key = 'schema_version'")
            row = cursor.fetchone()
            if not row:
                cursor.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', '1')")
            self.conn.commit()
        except Exception:
            self.logger.exception('Migration step failed')

    def purge_provenance_older_than(self, days: int) -> int:
        """Delete provenance rows older than `days` and return deleted count."""
        try:
            cursor = self.conn.cursor()
            # Use a parameterized interval string for sqlite datetime comparison
            interval = f"-{int(days)} days"
            cursor.execute("DELETE FROM order_provenance WHERE timestamp < datetime('now', ?)", (interval,))
            deleted = cursor.rowcount
            self.conn.commit()
            self.logger.info(f"Purged {deleted} order_provenance rows older than {days} days")
            return deleted
        except Exception:
            self.logger.exception('Failed to purge provenance rows')
            return 0

    def _normalize_timestamp(self, ts) -> Optional[str]:
        """Normalize various timestamp inputs to SQLite-friendly TEXT format:
        - Accepts datetime objects or ISO strings like 'YYYY-MM-DDTHH:MM:SS(.micro)[Z]'
        - Returns string in 'YYYY-MM-DD HH:MM:SS(.micro)' or None
        """
        if ts is None:
            return None
        # datetime -> ISO then normalize
        try:
            if hasattr(ts, 'isoformat'):
                s = ts.isoformat()
            else:
                s = str(ts)
            # Handle trailing Z (UTC marker)
            if s.endswith('Z'):
                s = s[:-1]
            # Replace 'T' separator with space to satisfy sqlite's parser
            s = s.replace('T', ' ')
            return s
        except Exception:
            # As a last resort, return the input coerced to string
            try:
                return str(ts)
            except Exception:
                return None

    def record_provenance(self, provenance: Dict[str, Any]) -> int:
        """
        Record an order provenance entry into the DB and return its row id.
        """
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                # Ensure metadata and stack_snippet serialization is safe
                stack_json = json.dumps(provenance.get('stack_snippet', []), default=str)
                try:
                    meta_json = json.dumps(provenance.get('metadata', {}))
                except Exception:
                    # Fallback: serialize a safe stringified dict
                    try:
                        meta_json = json.dumps({k: str(v) for k, v in (provenance.get('metadata') or {}).items()})
                    except Exception:
                        meta_json = '{}'

                env_json = json.dumps(provenance.get('env_snapshot', {}))

                ts = self._normalize_timestamp(provenance.get('timestamp'))
                cursor.execute("""
                    INSERT INTO order_provenance (
                        timestamp, signal_id, client_tag, symbol, side, volume,
                        caller_module, caller_function, stack_snippet, metadata,
                        pid, thread_id, hostname, python_version, env_snapshot
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    ts,
                    provenance.get('signal_id'),
                    provenance.get('client_tag'),
                    provenance.get('symbol'),
                    provenance.get('side'),
                    provenance.get('volume'),
                    provenance.get('caller', {}).get('module'),
                    provenance.get('caller', {}).get('function'),
                    stack_json,
                    meta_json,
                    provenance.get('pid'),
                    provenance.get('thread_id'),
                    provenance.get('hostname'),
                    provenance.get('python_version'),
                    env_json
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            self.logger.exception('Failed to record provenance')
            return -1

    def get_recent_provenance(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Retrieve recent provenance entries as dicts.
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, CAST(timestamp AS TEXT) AS timestamp_text, signal_id, client_tag, symbol, side, volume,
                       caller_module, caller_function, stack_snippet, metadata,
                       pid, thread_id, hostname, python_version, env_snapshot
                FROM order_provenance
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            out = []
            for r in rows:
                out.append({
                    'id': r['id'],
                    'timestamp': r['timestamp_text'],
                    'signal_id': r['signal_id'],
                    'client_tag': r['client_tag'],
                    'symbol': r['symbol'],
                    'side': r['side'],
                    'volume': r['volume'],
                    'caller_module': r['caller_module'],
                    'caller_function': r['caller_function'],
                    'stack_snippet': json.loads(r['stack_snippet']) if r['stack_snippet'] else None,
                    'metadata': json.loads(r['metadata']) if r['metadata'] else None,
                    'pid': r['pid'],
                    'thread_id': r['thread_id'],
                    'hostname': r['hostname'],
                    'python_version': r['python_version'],
                    'env_snapshot': json.loads(r['env_snapshot']) if r['env_snapshot'] else None
                })
            return out
        except Exception:
            self.logger.exception('Failed to fetch provenance entries')
            return []
    def record_signal(self, signal_record: SignalRecord) -> int:
        """
        Record a trading signal.
        
        Args:
            signal_record: Signal record to store
            
        Returns:
            Database row ID
        """
        import time
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                # Use fresh connection per call for better concurrency
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO signals (
                            signal_id, timestamp, symbol, timeframe, side, action,
                            confidence, price, stop_loss, take_profit, reason, executed, execution_timestamp, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        signal_record.signal_id,
                        self._normalize_timestamp(signal_record.timestamp),
                        signal_record.symbol,
                        signal_record.timeframe,
                        signal_record.side,
                        signal_record.action,
                        signal_record.confidence,
                        signal_record.price,
                        signal_record.stop_loss,
                        signal_record.take_profit,
                        signal_record.reason,
                        int(signal_record.executed),
                        signal_record.execution_timestamp.isoformat() if hasattr(signal_record.execution_timestamp, 'isoformat') and signal_record.execution_timestamp is not None else signal_record.execution_timestamp,
                        json.dumps(signal_record.metadata) if not isinstance(signal_record.metadata, str) else signal_record.metadata
                    ))
                    conn.commit()
                    row_id = cursor.lastrowid
                    self.logger.debug(f"Signal recorded: {signal_record.signal_id} (ID: {row_id})")
                    return row_id
                finally:
                    conn.close()
                    
            except sqlite3.IntegrityError:
                # UNIQUE constraint - signal already exists, expected on retries
                self.logger.debug(f"Signal {signal_record.signal_id} already exists (upserted)")
                return -1
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                self.logger.warning(f"Database busy recording signal after {max_retries} attempts")
                return -1
            except Exception as e:
                self.logger.error(f"Failed to record signal: {e}")
                return -1
        return -1
            
    def record_trade(self, trade_record: TradeRecord) -> int:
        """
        Record a trade entry.
        
        Args:
            trade_record: Trade record to store
            
        Returns:
            Database row ID
        """
        import time
        max_retries = 3
        retry_delay = 0.5
        
        for attempt in range(max_retries):
            try:
                # Use a fresh connection per call with timeout and WAL mode for better concurrency
                conn = sqlite3.connect(self.db_path, timeout=30.0)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
                
                try:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO trades (
                            signal_id, order_id, symbol, side, volume, entry_price,
                            stop_loss, take_profit, entry_time, status, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        trade_record.signal_id,
                        trade_record.order_id,
                        trade_record.symbol,
                        trade_record.side,
                        trade_record.volume,
                        trade_record.entry_price,
                        trade_record.stop_loss,
                        trade_record.take_profit,
                        self._normalize_timestamp(trade_record.entry_time),
                        trade_record.status,
                        json.dumps(trade_record.metadata) if not isinstance(trade_record.metadata, str) else trade_record.metadata
                    ))
                    conn.commit()
                    row_id = cursor.lastrowid
                    return row_id
                finally:
                    conn.close()
                
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    self.logger.debug(f"Database busy, retry {attempt + 1}/{max_retries}")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    self.logger.warning(f"Database busy recording trade after {max_retries} attempts")
                    return -1
            except Exception as e:
                self.logger.error(f"Failed to record trade: {e}")
                return -1
        
        return -1

    def check_writable(self) -> bool:
        """
        Verify the database file is writable by performing a small transactional write.
        Raises PermissionError if a write cannot be performed.
        Returns True if writable.
        """
        # Quick path: if DB was previously detected as read-only during initialization, fail fast
        if getattr(self, '_read_only', False):
            raise PermissionError("Database file appears to be read-only")

        try:
            test_conn = sqlite3.connect(str(self.db_path), timeout=5)
            test_cur = test_conn.cursor()
            test_cur.execute("CREATE TABLE IF NOT EXISTS __health_check(id INTEGER PRIMARY KEY)")
            test_cur.execute("INSERT INTO __health_check DEFAULT VALUES")
            test_conn.commit()
            test_cur.execute("DELETE FROM __health_check")
            test_conn.commit()
            test_conn.close()
            return True
        except Exception as e:
            self.logger.error(f"Database write check failed: {e}")
            raise PermissionError(f"Database not writable: {e}")

    def save_position(
        self,
        ticket: int,
        symbol: str,
        type: str,
        volume: float,
        open_price: float,
        current_price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        open_time: Optional[datetime] = None,
        magic_number: int = 0,
        comment: str = "",
        strategy_name: str = ""
    ) -> bool:
        """
        Save or update position in database.
        
        Args:
            ticket: Position ticket
            symbol: Trading symbol
            type: Position type (buy/sell)
            volume: Position volume
            open_price: Opening price
            sl: Stop loss price
            tp: Take profit price
            open_time: Opening time
            magic_number: Magic number
            comment: Position comment
            strategy_name: Strategy name
            
        Returns:
            True if saved successfully
        """
        try:
            cursor = self.conn.cursor()
            
            # Default current_price to open_price if not provided
            if current_price is None:
                current_price = open_price
            
            # Use INSERT OR REPLACE to handle updates
            cursor.execute("""
                INSERT OR REPLACE INTO positions (
                    ticket, symbol, type, volume, open_price, current_price, sl, tp,
                    open_time, magic_number, comment, strategy_name, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket,
                symbol,
                type,
                volume,
                open_price,
                current_price,
                sl,
                tp,
                self._normalize_timestamp(open_time or datetime.now()),
                magic_number,
                comment,
                strategy_name,
                self._normalize_timestamp(datetime.now())
            ))
            
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save position {ticket}: {e}", exc_info=True)
            return False
    
    def update_position_price(self, ticket: int, current_price: float, profit: float) -> bool:
        """
        Update position current price and profit.
        
        Args:
            ticket: Position ticket
            current_price: Current market price
            profit: Current profit/loss
            
        Returns:
            True if updated successfully
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE positions 
                SET current_price = ?, pnl = ?, updated_at = ?
                WHERE ticket = ?
            """, (
                current_price,
                profit,
                self._normalize_timestamp(datetime.now()),
                ticket
            ))
            self.conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            self.logger.error(f"Failed to update position {ticket}: {e}", exc_info=True)
            return False
    
    def remove_position(self, ticket: int) -> bool:
        """
        Remove position from database (when closed).
        
        Args:
            ticket: Position ticket
            
        Returns:
            True if removed successfully
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM positions WHERE ticket = ?", (ticket,))
            self.conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            self.logger.error(f"Failed to remove position {ticket}: {e}", exc_info=True)
            return False
    
    def get_positions(self, status: str = "open") -> List[Dict[str, Any]]:
        """
        Get positions from database.
        
        Args:
            status: Position status filter
            
        Returns:
            List of position dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM positions WHERE status = ?", (status,))
            rows = cursor.fetchall()
            
            positions = []
            for row in rows:
                positions.append(dict(row))
            
            return positions
            
        except Exception as e:
            self.logger.error(f"Failed to get positions: {e}", exc_info=True)
            return []
    
    def update_position_status(self, ticket: int, status: str, exit_reason: str = "") -> bool:
        """
        Update position status.
        
        Args:
            ticket: Position ticket
            status: New status
            exit_reason: Exit reason if closing
            
        Returns:
            True if updated successfully
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE positions 
                SET status = ?, exit_reason = ?, updated_at = ?
                WHERE ticket = ?
            """, (
                status,
                exit_reason,
                self._normalize_timestamp(datetime.now()),
                ticket
            ))
            self.conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            self.logger.error(f"Failed to update position status {ticket}: {e}", exc_info=True)
            return False
            
    def update_trade_exit(
        self,
        order_id: int,
        exit_price: float,
        exit_time: datetime,
        profit: float,
        exit_reason: str
    ) -> bool:
        """
        Update trade with exit information.
        
        Args:
            order_id: MT5 order ticket
            exit_price: Exit price
            exit_time: Exit timestamp
            profit: Realized profit/loss
            exit_reason: Reason for exit
            
        Returns:
            True if updated successfully
        """
        try:
            cursor = self.conn.cursor()
            exit_ts = self._normalize_timestamp(exit_time)
            cursor.execute("""
                UPDATE trades
                SET exit_price = ?,
                    exit_time = ?,
                    profit = ?,
                    status = 'CLOSED',
                    exit_reason = ?
                WHERE order_id = ?
            """, (exit_price, exit_ts, profit, exit_reason, order_id))
            self.conn.commit()
            
            if cursor.rowcount > 0:
                self.logger.info(f"Trade exit recorded: Order #{order_id} | Profit: {profit:.2f}")
                return True
            else:
                self.logger.warning(f"Trade not found for update: Order #{order_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to update trade exit: {e}", exc_info=True)
            return False
            
    def get_open_trades(self) -> List[TradeRecord]:
        """
        Get all open trades.
        
        Returns:
            List of open trade records
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, signal_id, order_id, symbol, side, volume, entry_price,
                       exit_price, stop_loss, take_profit, CAST(entry_time AS TEXT) AS entry_time,
                       CAST(exit_time AS TEXT) AS exit_time, profit, status, exit_reason, metadata
                FROM trades
                WHERE status = 'OPEN'
                ORDER BY entry_time DESC
            """)
            
            trades = []
            for row in cursor.fetchall():
                trades.append(TradeRecord(
                    id=row['id'],
                    signal_id=row['signal_id'],
                    order_id=row['order_id'],
                    symbol=row['symbol'],
                    side=row['side'],
                    volume=row['volume'],
                    entry_price=row['entry_price'],
                    exit_price=row['exit_price'],
                    stop_loss=row['stop_loss'],
                    take_profit=row['take_profit'],
                    entry_time=row['entry_time'],
                    exit_time=row['exit_time'],
                    profit=row['profit'],
                    status=row['status'],
                    exit_reason=row['exit_reason'],
                    metadata=row['metadata']
                ))
            
            return trades
            
        except Exception as e:
            self.logger.error(f"Failed to get open trades: {e}", exc_info=True)
            return []
            
    def get_all_trades(self, limit: int = 100) -> List[TradeRecord]:
        """
        Get all trades (open and closed), most recent first.
        
        Args:
            limit: Maximum number of trades to return
            
        Returns:
            List of trade records
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, signal_id, order_id, symbol, side, volume, entry_price,
                       exit_price, stop_loss, take_profit, CAST(entry_time AS TEXT) AS entry_time,
                       CAST(exit_time AS TEXT) AS exit_time, profit, status, exit_reason, metadata
                FROM trades
                ORDER BY entry_time DESC
                LIMIT ?
            """, (limit,))
            
            trades = []
            for row in cursor.fetchall():
                trades.append(TradeRecord(
                    id=row['id'],
                    signal_id=row['signal_id'],
                    order_id=row['order_id'],
                    symbol=row['symbol'],
                    side=row['side'],
                    volume=row['volume'],
                    entry_price=row['entry_price'],
                    exit_price=row['exit_price'],
                    stop_loss=row['stop_loss'],
                    take_profit=row['take_profit'],
                    entry_time=row['entry_time'],
                    exit_time=row['exit_time'],
                    profit=row['profit'],
                    status=row['status'],
                    exit_reason=row['exit_reason'],
                    metadata=row['metadata']
                ))
            
            return trades
            
        except Exception as e:
            self.logger.error(f"Failed to get all trades: {e}", exc_info=True)
            return []
            
    def record_metric(self, name: str, value: float, metadata: str = "") -> bool:
        """
        Record a performance metric.
        
        Args:
            name: Metric name
            value: Metric value
            metadata: Additional metadata (JSON)
            
        Returns:
            True if recorded successfully
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO metrics (timestamp, metric_name, metric_value, metadata)
                VALUES (?, ?, ?, ?)
            """, (self._normalize_timestamp(datetime.now()), name, value, metadata))
            self.conn.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to record metric: {e}", exc_info=True)
            return False
            
    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.logger.info("Database connection closed")




