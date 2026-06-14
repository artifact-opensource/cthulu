import sqlite3
import time
import os
import json
import sys
import threading
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
import logging

# Configure logging to stderr
logging.basicConfig(level=logging.DEBUG, stream=sys.stderr, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Configuration
DB_PATH = r"C:\workspace\cthulu\cthulu.db"
LOG_FILE = r"C:\workspace\cthulu\logs\cthulu.log"
logger.info(f"DB_PATH: {DB_PATH}")

# Track last known price for live updates
last_price = {'value': 0, 'time': 0}

def get_db_connection():
    try:
        print(f"Attempting to connect to: {DB_PATH}")
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        print("DB connection successful")
        return conn
    except Exception as e:
        import traceback
        print(f"Error connecting to DB: {e}")
        traceback.print_exc()
        return None

def parse_timestamp(ts_str):
    """Parse timestamp string with or without microseconds."""
    if not ts_str:
        return 0
    try:
        # Try with microseconds first
        if '.' in ts_str:
            dt = time.strptime(ts_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        else:
            dt = time.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
        return int(time.mktime(dt) * 1000)
    except Exception:
        return 0

def normalize_trade(row):
    return {
        "id": str(row['order_id']) if row['order_id'] else str(row['id']),
        "type": row['side'].upper() if row['side'] else 'UNKNOWN',
        "price": row['entry_price'],
        "size": row['volume'],
        "timestamp": parse_timestamp(row['entry_time']),
        "status": row['status'],
        "pnl": row['profit'],
        "origin": "AUTO",
        "reason": row['exit_reason'] or row['metadata'] or ""
    }

@app.route('/api/trades', methods=['GET'])
def get_trades():
    logger.info("GET /api/trades called")
    conn = get_db_connection()
    if not conn:
        logger.error("DB connection failed")
        return jsonify([]), 500
    
    try:
        trades = conn.execute("SELECT * FROM trades ORDER BY entry_time DESC LIMIT 50").fetchall()
        logger.info(f"Fetched {len(trades)} trades")
        result = [normalize_trade(t) for t in trades]
        logger.info(f"Normalized {len(result)} trades")
        return jsonify(result)
    except Exception as e:
        import traceback
        logger.error(f"Error querying trades: {e}")
        traceback.print_exc()
        return jsonify([]), 500
    finally:
        conn.close()

@app.route('/api/logs', methods=['GET'])
def get_logs():
    if not os.path.exists(LOG_FILE):
        return jsonify([])
    
    try:
        lines = []
        # Read last 100 lines
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            # Simple tail implementation
            f.seek(0, os.SEEK_END)
            position = f.tell()
            line_count = 0
            block_size = 1024
            
            while position > 0 and line_count < 100:
                read_len = min(block_size, position)
                position -= read_len
                f.seek(position, os.SEEK_SET)
                block = f.read(read_len)
                
                # Count newlines
                line_count += block.count('\n')
                
            f.seek(position, os.SEEK_SET)
            # Find the start of the first full line
            if position > 0:
                f.readline()
                
            lines = f.readlines()[-100:]
            
        parsed_logs = []
        for line in lines:
            # Parse log format: 2026-01-10T17:28:04 [INFO] Message
            try:
                line = line.strip()
                if not line:
                    continue
                # Format: 2026-01-10T17:28:04 [LEVEL] Message
                parts = line.split(' ', 2)  # timestamp [level] message
                if len(parts) >= 3:
                    ts_str = parts[0]
                    level = parts[1].strip('[]')
                    msg = parts[2]
                    
                    parsed_logs.append({
                        "timestamp": int(time.time() * 1000),
                        "real_time_str": ts_str,
                        "level": level if level in ['INFO', 'WARN', 'ERROR', 'WARNING', 'DEBUG'] else 'INFO',
                        "message": msg,
                        "source": "SYSTEM"
                    })
                elif len(parts) >= 1:
                    parsed_logs.append({
                        "timestamp": int(time.time() * 1000), 
                        "level": 'INFO',
                        "message": line,
                        "source": "SYSTEM"
                    })
            except:
                pass
                
        return jsonify(parsed_logs[::-1]) # Newest first
    except Exception as e:
        print(f"Error reading logs: {e}")
        return jsonify([])



@app.route('/api/signals', methods=['GET'])
def get_signals():
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500
    try:
        # Get recent signals
        signals = conn.execute("SELECT * FROM signals ORDER BY timestamp DESC LIMIT 20").fetchall()
        return jsonify([dict(s) for s in signals])
    except Exception as e:
        print(f"Error querying signals: {e}")
        return jsonify([]), 500
    finally:
        conn.close()

@app.route('/api/metrics', methods=['GET'])
def get_metrics():
    conn = get_db_connection()
    if not conn:
        return jsonify([]), 500
    try:
        # Get recent metrics
        metrics = conn.execute("SELECT * FROM metrics ORDER BY timestamp DESC LIMIT 50").fetchall()
        return jsonify([dict(m) for m in metrics])
    except Exception as e:
        print(f"Error querying metrics: {e}")
        return jsonify([]), 500
    finally:
        conn.close()

@app.route('/api/dashboard', methods=['GET'])
def get_dashboard():
    """Get dashboard summary with real data from multiple sources."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"error": "Database unavailable"}), 500
    
    try:
        # Get trade stats
        total_trades = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        open_trades = conn.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'").fetchone()[0]
        closed_trades = conn.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED'").fetchone()[0]
        
        # Get PnL
        pnl_result = conn.execute("SELECT SUM(profit) FROM trades WHERE profit IS NOT NULL").fetchone()[0]
        total_pnl = pnl_result if pnl_result else 0.0
        
        # Get win/loss
        wins = conn.execute("SELECT COUNT(*) FROM trades WHERE profit > 0").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM trades WHERE profit < 0").fetchone()[0]
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        
        # Recent signals
        recent_signals = conn.execute("SELECT COUNT(*) FROM signals WHERE timestamp > datetime('now', '-1 hour')").fetchone()[0]
        
        return jsonify({
            "total_trades": total_trades,
            "open_trades": open_trades,
            "closed_trades": closed_trades,
            "total_pnl": round(total_pnl, 2),
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "recent_signals": recent_signals,
            "status": "running"
        })
    except Exception as e:
        print(f"Error getting dashboard: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/status', methods=['GET'])
def get_status():
    lock_file = r"C:\workspace\cthulu\cthulu.lock"
    is_running = os.path.exists(lock_file)
    return jsonify({
        "status": "online" if is_running else "offline",
        "db": os.path.exists(DB_PATH),
        "trading": is_running
    })

import requests

# yfinance disabled due to Python 3.12 ssl compatibility issues
YFINANCE_AVAILABLE = False

# Configuration
RPC_URL = "http://127.0.0.1:8278/trade"

@app.route('/api/ticker', methods=['GET'])
def get_ticker():
    """Get current price from database (last trade entry_price)."""
    conn = get_db_connection()
    if conn:
        try:
            row = conn.execute("SELECT entry_price, symbol, entry_time FROM trades ORDER BY id DESC LIMIT 1").fetchone()
            if row:
                return jsonify({
                    "symbol": row['symbol'],
                    "price": row['entry_price'],
                    "timestamp": int(time.time() * 1000),
                    "source": "database"
                })
        except Exception as e:
            print(f"Error fetching price: {e}")
        finally:
            conn.close()
    return jsonify({"symbol": "BTCUSD#", "price": 0, "timestamp": int(time.time() * 1000)}), 200

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get price history from trades table."""
    conn = get_db_connection()
    if conn:
        try:
            rows = conn.execute("""
                SELECT entry_price as close, entry_time 
                FROM trades 
                ORDER BY id DESC 
                LIMIT 500
            """).fetchall()
            candles = []
            for row in reversed(rows):
                ts = parse_timestamp(row['entry_time'])
                candles.append({
                    "time": ts,
                    "open": row['close'],
                    "high": row['close'],
                    "low": row['close'],
                    "close": row['close'],
                    "volume": 0
                })
            return jsonify(candles)
        except Exception as e:
            print(f"Error fetching history: {e}")
        finally:
            conn.close()
    return jsonify([]), 200

@app.route('/api/trade', methods=['POST'])
def proxy_trade():
    try:
        payload = request.json
        # Forward to RPC server
        # RPC expects: {"symbol": str, "side": str, "volume": float, ...}
        resp = requests.post(RPC_URL, json=payload, timeout=5)
        return (resp.content, resp.status_code, resp.headers.items())
    except Exception as e:
        print(f"Error proxying trade to RPC: {e}")
        return jsonify({"error": "RPC Server Unreachable"}), 503

# WebSocket Events
@socketio.on('connect')
def handle_connect():
    logger.info("Client connected to WebSocket")
    # Send current price immediately
    emit('price', last_price)

@socketio.on('disconnect')
def handle_disconnect():
    logger.info("Client disconnected from WebSocket")

def price_streamer():
    """Background thread that polls DB and broadcasts price updates."""
    global last_price
    while True:
        try:
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT entry_price, entry_time, symbol 
                FROM trades 
                ORDER BY id DESC LIMIT 1
            """).fetchone()
            conn.close()
            
            if row and row['entry_price'] != last_price['value']:
                last_price = {
                    'value': row['entry_price'],
                    'time': int(time.time() * 1000),
                    'symbol': row['symbol']
                }
                socketio.emit('price', last_price)
                logger.debug(f"Broadcasting price: {last_price['value']}")
        except Exception as e:
            logger.error(f"Price streamer error: {e}")
        
        time.sleep(0.5)  # 500ms polling for near real-time

if __name__ == '__main__':
    print("Starting Flask server with WebSocket...", file=sys.stderr, flush=True)
    
    # Start price streaming thread
    streamer_thread = threading.Thread(target=price_streamer, daemon=True)
    streamer_thread.start()
    
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, use_reloader=False)
