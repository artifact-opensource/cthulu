"""Simple local server to serve the report UI and reports directory.

Run: python serve.py
Opens http://localhost:8000/backtesting/report_ui/static/index.html
"""
import http.server
import socketserver
import webbrowser
import os
from pathlib import Path

PORT = 8000
ROOT = Path(__file__).parents[2].resolve()  # repository root
os.chdir(ROOT)

Handler = http.server.SimpleHTTPRequestHandler

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    url = f'http://localhost:{PORT}/backtesting/report_ui/static/index.html'
    print(f"Serving HTTP on port {PORT} (root: {ROOT})")
    print(f"Open in browser: {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")
        httpd.server_close()