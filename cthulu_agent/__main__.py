"""python -m cthulu_agent  (or: python run_agent.py)"""
from __future__ import annotations

import argparse
import logging
import os
import secrets
import sys
import time
import urllib.parse
import webbrowser
from pathlib import Path

from execution_mode import ExecutionModeError, require_trading_enabled


def _ensure_dashboard_token(env_path: Path) -> str:
    from . import envfile

    token = envfile.read_env(env_path).get("DASHBOARD_TOKEN", "").strip()
    if not token:
        token = secrets.token_urlsafe(32)
        envfile.set_env({"DASHBOARD_TOKEN": token}, env_path)
    os.environ["DASHBOARD_TOKEN"] = token
    return token


def main() -> None:
    try:
        require_trading_enabled()
    except ExecutionModeError as exc:
        raise SystemExit(f"Trading disabled: {exc}") from exc

    ap = argparse.ArgumentParser(prog="cthulu-agent", description="Cthulu autonomous agent + dashboard")
    ap.add_argument("--host", default=None, help="bind address (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=None, help="port (default 8765)")
    ap.add_argument("--access-mode", choices=("loopback", "lan", "tailscale"), default=None,
                     help="dashboard network access mode (default: DASHBOARD_ACCESS_MODE)")
    ap.add_argument("--no-agent", action="store_true", help="serve the dashboard only; do not start the trading loop")
    ap.add_argument("--open", action="store_true", help="open the dashboard in a browser")
    ap.add_argument("--env", default=None, help="path to .env (default: repo root)")
    ap.add_argument("--config", default=None, help="Cthulu config file for shared position protection")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if args.env:
        os.environ["CTHULU_ENV_FILE"] = str(Path(args.env).resolve())
    if args.config:
        os.environ["CTHULU_CONFIG_PATH"] = str(Path(args.config).resolve())

    from .app import App
    from .server import serve
    from . import envfile
    from network_access import NetworkAccessError, get_access_mode, resolve_bind_target

    app = App(env_path=args.env)
    env_path = Path(args.env).resolve() if args.env else envfile.default_env_path()
    port = args.port or int(os.environ.get("DASHBOARD_PORT", "8765"))
    try:
        mode = args.access_mode or get_access_mode()
        configured_host = os.environ.get("DASHBOARD_HOST") if mode == "loopback" else None
        target = resolve_bind_target(mode, port) if not args.host and not configured_host else None
    except NetworkAccessError as exc:
        raise SystemExit(f"Dashboard network setup failed: {exc}") from exc
    host = args.host or (target.host if target else configured_host or "127.0.0.1")
    token = _ensure_dashboard_token(env_path)
    extra = set(os.environ.get("DASHBOARD_ALLOWED_HOSTS", "").split(","))
    if target:
        extra.update(target.allowed_hosts)
    ok = app.start_runtime(autostart=not args.no_agent)
    srv, _t = serve(app, host, port, token, extra)
    urls = target.urls if target else [f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}/"]
    if mode == "lan" and target:
        print("\n  Cthulu agent dashboard (LAN):")
    elif mode == "tailscale" and target:
        print("\n  Cthulu agent dashboard (Tailscale):")
    else:
        print("\n  Cthulu agent dashboard:")
    for url in urls:
        print(f"    {url}")
    if mode != "loopback":
        print("  Remote API and chat require the dashboard token.")
    print(f"  broker: {app.settings.broker}{'' if ok else '  (NOT connected: ' + app.broker_error + ')'}   llm: {app.llm.active_provider()}")
    if not app.llm.configured:
        print("  LLM provider is not configured. Open dashboard > Settings and configure Cloudflare AI Gateway or another provider.")
    if args.open:
        webbrowser.open(f"{urls[0]}#token={urllib.parse.quote(token, safe='')}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\nShutting down...")
        if app.runtime:
            app.runtime.stop()
            app.runtime.broker.shutdown()
        srv.shutdown()


if __name__ == "__main__":
    main()
