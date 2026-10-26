#!/usr/bin/env python3
"""Simple webhook receiver that stores incoming webhook events in a local
SQLite queue and exposes a /next_job endpoint for MT5 EAs to poll.

Usage:
    python3 scripts/webhook_db_server.py --host 0.0.0.0 --port 9002

Endpoints:
  POST /webhook        -> store job (JSON body). Returns {"id": <int>}.
  GET  /next_job       -> return next pending job as plain text: "<id>|<CMD>|..."
  POST /ack?id=<id>    -> mark job as done

This server uses only the standard library so it can run without extra
packages. It stores the jobs in data/webhooks.db in the repo.
"""

import argparse
import http.server
import json
import logging
import os
import sqlite3
import threading
import urllib.parse
import hmac
import hashlib
from http import HTTPStatus
from datetime import datetime

logger = logging.getLogger('webhook_db_server')

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data', 'webhooks.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DB_SCHEMA = '''
CREATE TABLE IF NOT EXISTS webhooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL, -- 'tick' or 'bar'
    symbol TEXT NOT NULL,
    timeframe TEXT, -- e.g., M1, H1 (for bars)
    ts TEXT NOT NULL,
    bid REAL,
    ask REAL,
    "open" REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    raw TEXT
);
'''

lock = threading.Lock()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(DB_SCHEMA)
        conn.commit()


class WebhookHandler(http.server.BaseHTTPRequestHandler):
    server_version = 'WebhookDB/0.1'

    def _send_json(self, code, payload):
        data = json.dumps(payload).encode('utf-8')
        try:
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected while we were writing the response; ignore silently
                logger.debug('client disconnected during write (BrokenPipe/ConnectionReset)')
        except Exception as e:
            # Best-effort: log and bail
            logger.exception('Failed to send JSON response: %s', e)

    def _verify_request(self, body_bytes: bytes) -> bool:
        """Verify incoming request using HMAC-SHA256 or API key.
        If WEBHOOK_SECRET env var is not set, verification is disabled (for dev).
        Accepts either 'X-Hub-Signature-256: sha256=<hex>' OR 'X-API-KEY: <secret>'.
        """
        secret = os.environ.get('WEBHOOK_SECRET')
        if not secret:
            # No secret configured; allow all (but log warning)
            logger.warning("WEBHOOK_SECRET not set - skipping request verification")
            return True

        # Check HMAC header
        sig256 = self.headers.get('X-Hub-Signature-256') or self.headers.get('X-Hub-Signature')
        if sig256:
            try:
                if sig256.startswith('sha256='):
                    sig = sig256.split('=')[1]
                else:
                    sig = sig256
                mac = hmac.new(secret.encode('utf-8'), body_bytes, hashlib.sha256).hexdigest()
                valid = hmac.compare_digest(mac, sig)
                if not valid:
                    logger.warning("HMAC signature mismatch")
                return valid
            except Exception as e:
                logger.error(f"HMAC verification error: {e}")
                return False

        # Fallback to simple API key header
        api_key = self.headers.get('X-API-KEY')
        if api_key and api_key == secret:
            return True

        logger.warning("Missing authentication headers")
        return False

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(length) if length else b''
        body = body_bytes.decode('utf-8') if body_bytes else ''

        # Protect critical POST endpoints with HMAC or API key
        protected = ['/webhook', '/publish_tick', '/publish_bar', '/ack']
        if parsed.path in protected:
            if not self._verify_request(body_bytes):
                self._send_json(HTTPStatus.UNAUTHORIZED, {'error': 'invalid signature or missing API key'})
                return

        if parsed.path == '/webhook':
            try:
                # Store payload as received JSON/text
                payload = body
                created_at = datetime.utcnow().isoformat() + 'Z'
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute('INSERT INTO webhooks (payload, created_at) VALUES (?, ?)', (payload, created_at))
                    job_id = cur.lastrowid
                    conn.commit()
                self._send_json(HTTPStatus.CREATED, {'id': job_id})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/publish_tick':
            try:
                data = json.loads(body) if body else {}
                symbol = data.get('symbol')
                bid = float(data.get('bid', 0))
                ask = float(data.get('ask', 0))
                volume = float(data.get('volume', 0))
                ts = data.get('time', datetime.utcnow().isoformat() + 'Z')
                raw = body
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute('INSERT INTO market_data (type, symbol, timeframe, ts, bid, ask, volume, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', ('tick', symbol, None, ts, bid, ask, volume, raw))
                    rec_id = cur.lastrowid
                    conn.commit()
                self._send_json(HTTPStatus.CREATED, {'id': rec_id})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/publish_bar':
            try:
                data = json.loads(body) if body else {}
                symbol = data.get('symbol')
                tf = data.get('timeframe')
                ts = data.get('time', datetime.utcnow().isoformat() + 'Z')
                o = float(data.get('open', 0))
                h = float(data.get('high', 0))
                l = float(data.get('low', 0))
                c = float(data.get('close', 0))
                volume = float(data.get('volume', 0))
                raw = body
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute('INSERT INTO market_data (type, symbol, timeframe, ts, "open", high, low, close, volume, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', ('bar', symbol, tf, ts, o, h, l, c, volume, raw))
                    rec_id = cur.lastrowid
                    conn.commit()
                self._send_json(HTTPStatus.CREATED, {'id': rec_id})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/publish_bars':
            try:
                data = json.loads(body) if body else {}
                symbol = data.get('symbol', '')
                tf = data.get('timeframe', 'M5')
                bars = data.get('bars', [])
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    for b in bars:
                        cur.execute(
                            'INSERT INTO market_data (type, symbol, timeframe, ts, "open", high, low, close, volume, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                            ('bar', symbol, tf, b.get('time', ''), b.get('open', 0), b.get('high', 0), b.get('low', 0), b.get('close', 0), b.get('tick_volume', 0), json.dumps(b))
                        )
                    conn.commit()
                self._send_json(HTTPStatus.OK, {'stored': len(bars)})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/publish_positions':
            try:
                data = json.loads(body) if body else {}
                positions = data.get('positions', [])
                # Store positions in a simple JSON file for quick access
                pos_path = os.path.join(BASE_DIR, 'data', 'positions.json')
                with open(pos_path, 'w') as f:
                    json.dump({'positions': positions, 'updated': datetime.utcnow().isoformat() + 'Z'}, f)
                self._send_json(HTTPStatus.OK, {'positions': len(positions)})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/publish_account':
            try:
                data = json.loads(body) if body else {}
                acc_path = os.path.join(BASE_DIR, 'data', 'account.json')
                data['updated'] = datetime.utcnow().isoformat() + 'Z'
                with open(acc_path, 'w') as f:
                    json.dump(data, f)
                self._send_json(HTTPStatus.OK, {'status': 'ok'})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/submit_job':
            try:
                payload = body
                created_at = datetime.utcnow().isoformat() + 'Z'
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute('INSERT INTO webhooks (payload, created_at) VALUES (?, ?)', (payload, created_at))
                    job_id = cur.lastrowid
                    conn.commit()
                self._send_json(HTTPStatus.CREATED, {'id': job_id})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/job_result':
            try:
                data = json.loads(body) if body else {}
                job_id = data.get('id')
                result = data.get('result', {})
                if job_id:
                    with lock, sqlite3.connect(DB_PATH) as conn:
                        cur = conn.cursor()
                        cur.execute("UPDATE webhooks SET status='done', payload=? WHERE id=?", (json.dumps(result), int(job_id)))
                        conn.commit()
                # Store latest result for quick polling
                res_path = os.path.join(BASE_DIR, 'data', 'last_result.json')
                with open(res_path, 'w') as f:
                    json.dump(data, f)
                self._send_json(HTTPStatus.OK, {'status': 'ok'})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/ack':
            qs = urllib.parse.parse_qs(parsed.query)
            id_list = qs.get('id', [])
            if not id_list:
                self._send_json(HTTPStatus.BAD_REQUEST, {'error': 'missing id'})
                return
            try:
                job_id = int(id_list[0])
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute("UPDATE webhooks SET status='done' WHERE id=?", (job_id,))
                    conn.commit()
                self._send_json(HTTPStatus.OK, {'id': job_id, 'status': 'done'})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {'error': 'unknown endpoint'})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/health':
            self._send_json(HTTPStatus.OK, {'status': 'alive', 'time': datetime.utcnow().isoformat() + 'Z'})
        elif parsed.path == '/positions':
            pos_path = os.path.join(BASE_DIR, 'data', 'positions.json')
            try:
                if os.path.exists(pos_path):
                    with open(pos_path, 'r') as f:
                        data = json.load(f)
                    self._send_json(HTTPStatus.OK, data)
                else:
                    self._send_json(HTTPStatus.OK, {'positions': [], 'updated': None})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/account':
            acc_path = os.path.join(BASE_DIR, 'data', 'account.json')
            try:
                if os.path.exists(acc_path):
                    with open(acc_path, 'r') as f:
                        data = json.load(f)
                    self._send_json(HTTPStatus.OK, data)
                else:
                    self._send_json(HTTPStatus.OK, {})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/next_job':
            try:
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id, payload FROM webhooks WHERE status='pending' ORDER BY id LIMIT 1")
                    row = cur.fetchone()
                    if not row:
                        self.send_response(HTTPStatus.NO_CONTENT)
                        self.end_headers()
                        return
                    job_id, payload = row
                    # mark claimed to avoid races
                    cur.execute("UPDATE webhooks SET status='claimed' WHERE id=?", (job_id,))
                    conn.commit()
                # We expect payload to be JSON; transform to a simple command string
                try:
                    data = json.loads(payload)
                    # Accept either 'command' or 'action' (different components use different keys)
                    cmd = data.get('command') or data.get('action') or data.get('side')
                    symbol = data.get('symbol', '')
                    # Some submitters use 'volume' or 'lot_size' keys
                    volume = str(data.get('volume', data.get('lot_size', 0)))
                    # Price may be under 'price' or 'limit'
                    price = str(data.get('price', data.get('limit', 0)))
                    sl = str(data.get('sl', data.get('stop_loss', 0)))
                    tp = str(data.get('tp', data.get('take_profit', 0)))
                    order_type = data.get('order_type', data.get('type', 'market'))
                    if cmd is None:
                        # Fallback: try parsing raw payload for simple formats
                        cmd = data.get('side') or 'NONE'
                    out = f"{job_id}|{cmd}|{symbol}|{volume}|{price}|{sl}|{tp}|{order_type}"
                except Exception:
                    # Not JSON - return raw payload
                    out = f"{job_id}|RAW|{payload}"
                out_bytes = out.encode('utf-8')
                self.send_response(HTTPStatus.OK)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', str(len(out_bytes)))
                self.end_headers()
                self.wfile.write(out_bytes)
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/pending_jobs':
            # Return all pending jobs as JSON (for bridge polling)
            try:
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT id, payload FROM webhooks WHERE status='pending' ORDER BY id")
                    rows = cur.fetchall()
                    jobs = []
                    for r in rows:
                        try:
                            data = json.loads(r[1])
                            data['id'] = r[0]
                        except Exception:
                            data = {'id': r[0], 'raw': r[1]}
                        jobs.append(data)
                    # Mark them as claimed
                    if rows:
                        ids = [str(r[0]) for r in rows]
                        cur.execute(f"UPDATE webhooks SET status='claimed' WHERE id IN ({','.join(ids)})")
                        conn.commit()
                self._send_json(HTTPStatus.OK, {'jobs': jobs})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/latest_bars':
            # Query params: symbol, tf, count
            qs = urllib.parse.parse_qs(parsed.query)
            symbol = qs.get('symbol', [''])[0]
            tf = qs.get('tf', [''])[0]
            count = int(qs.get('count', ['10'])[0])
            try:
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    if symbol and tf:
                        cur.execute("SELECT ts, \"open\", high, low, close, volume FROM market_data WHERE type='bar' AND symbol=? AND timeframe=? ORDER BY id DESC LIMIT ?", (symbol, tf, count))
                    elif symbol:
                        cur.execute("SELECT ts, \"open\", high, low, close, volume FROM market_data WHERE type='bar' AND symbol=? ORDER BY id DESC LIMIT ?", (symbol, count))
                    else:
                        cur.execute("SELECT ts, \"open\", high, low, close, volume FROM market_data WHERE type='bar' ORDER BY id DESC LIMIT ?", (count,))
                    rows = cur.fetchall()
                bars = []
                for r in rows:
                    bars.append({'time': r[0], 'open': r[1], 'high': r[2], 'low': r[3], 'close': r[4], 'volume': r[5]})
                self._send_json(HTTPStatus.OK, {'bars': bars})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/latest_tick':
            qs = urllib.parse.parse_qs(parsed.query)
            symbol = qs.get('symbol', [''])[0]
            try:
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    if symbol:
                        cur.execute("SELECT ts,bid,ask,volume,raw FROM market_data WHERE type='tick' AND symbol=? ORDER BY id DESC LIMIT 1", (symbol,))
                    else:
                        cur.execute("SELECT ts,bid,ask,volume,raw FROM market_data WHERE type='tick' ORDER BY id DESC LIMIT 1")
                    row = cur.fetchone()
                    if not row:
                        self.send_response(HTTPStatus.NO_CONTENT)
                        self.end_headers()
                        return
                    ts, bid, ask, volume, raw = row
                self._send_json(HTTPStatus.OK, {'time': ts, 'bid': bid, 'ask': ask, 'volume': volume})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/job_status':
            qs = urllib.parse.parse_qs(parsed.query)
            job_id = qs.get('job_id', [''])[0]
            try:
                if not job_id:
                    self._send_json(HTTPStatus.BAD_REQUEST, {'error': 'missing job_id'})
                    return
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute('SELECT status, payload FROM webhooks WHERE id=?', (int(job_id),))
                    row = cur.fetchone()
                if not row:
                    self._send_json(HTTPStatus.NOT_FOUND, {'error': 'job not found'})
                    return
                status, payload = row
                try:
                    parsed_payload = json.loads(payload)
                except Exception:
                    parsed_payload = payload
                self._send_json(HTTPStatus.OK, {'job_id': int(job_id), 'status': status, 'payload': parsed_payload})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        elif parsed.path == '/job_result':
            qs = urllib.parse.parse_qs(parsed.query)
            job_id = qs.get('job_id', [''])[0]
            try:
                if not job_id:
                    self._send_json(HTTPStatus.BAD_REQUEST, {'error': 'missing job_id'})
                    return
                with lock, sqlite3.connect(DB_PATH) as conn:
                    cur = conn.cursor()
                    cur.execute('SELECT status, payload FROM webhooks WHERE id=?', (int(job_id),))
                    row = cur.fetchone()
                if not row:
                    self._send_json(HTTPStatus.NOT_FOUND, {'error': 'job not found'})
                    return
                status, payload = row
                try:
                    parsed_payload = json.loads(payload)
                except Exception:
                    parsed_payload = payload
                if status == 'done':
                    self._send_json(HTTPStatus.OK, {'job_id': int(job_id), 'status': status, 'result': parsed_payload})
                else:
                    self._send_json(HTTPStatus.OK, {'job_id': int(job_id), 'status': status})
            except Exception as e:
                self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {'error': str(e)})
        else:
            self._send_json(HTTPStatus.NOT_FOUND, {'error': 'unknown endpoint'})


def run(host='127.0.0.1', port=9002):
    init_db()
    server = http.server.ThreadingHTTPServer((host, port), WebhookHandler)
    print(f"Webhook DB server listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('shutting down')
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Webhook DB server')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9002)
    args = parser.parse_args()
    run(args.host, args.port)
