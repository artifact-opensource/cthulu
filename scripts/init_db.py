"""
Database Initialization Script

Creates SQLite database schema for Cthulu trading system.
Schemas: trades, orders, positions, signals, metrics
"""

import sqlite3
import logging
from pathlib import Path
from datetime import datetime


def init_database(db_path: str = "data/cthulu.db"):
    """
    Initialize Cthulu database with required tables.
    
    Args:
        db_path: Path to SQLite database file
    """
    # Ensure directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    logging.info(f"Initializing database: {db_path}")
    
    # Signals table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            side TEXT NOT NULL,
            action TEXT NOT NULL,
            price REAL,
            stop_loss REAL,
            take_profit REAL,
            confidence REAL,
            reason TEXT,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY,
            signal_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            volume REAL NOT NULL,
            order_type TEXT NOT NULL,
            price REAL,
            sl REAL,
            tp REAL,
            status TEXT NOT NULL,
            executed_price REAL,
            executed_volume REAL,
            error TEXT,
            metadata TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            executed_at TEXT,
            FOREIGN KEY (signal_id) REFERENCES signals(id)
        )
    """)
    
    # Trades table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER,
            ticket INTEGER UNIQUE,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            volume REAL NOT NULL,
            open_price REAL NOT NULL,
            close_price REAL,
            sl REAL,
            tp REAL,
            profit REAL,
            commission REAL,
            swap REAL,
            status TEXT NOT NULL,
            open_time TEXT NOT NULL,
            close_time TEXT,
            metadata TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        )
    """)
    
    # Positions table (current open positions)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            ticket INTEGER PRIMARY KEY,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            volume REAL NOT NULL,
            open_price REAL NOT NULL,
            current_price REAL NOT NULL,
            sl REAL,
            tp REAL,
            profit REAL NOT NULL,
            open_time TEXT NOT NULL,
            last_update TEXT NOT NULL,
            metadata TEXT
        )
    """)
    
    # Metrics table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            metric_type TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            metadata TEXT
        )
    """)
    
    # Risk events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS risk_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            description TEXT NOT NULL,
            action_taken TEXT,
            metadata TEXT
        )
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_type ON metrics(metric_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
    
    # Commit changes
    conn.commit()
    
    logging.info("Database schema created successfully")
    
    # Insert initial metric
    cursor.execute("""
        INSERT INTO metrics (timestamp, metric_type, metric_name, metric_value)
        VALUES (?, 'system', 'database_initialized', 1)
    """, (datetime.now().isoformat(),))
    
    conn.commit()
    conn.close()
    
    print(f"✓ Database initialized: {db_path}")
    print(f"  - Created tables: signals, orders, trades, positions, metrics, risk_events")
    print(f"  - Created indexes for performance")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_database()




