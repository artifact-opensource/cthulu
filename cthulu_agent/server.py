"""Dashboard server: JSON API, live event stream (SSE) and the static frontend. Standard library only."""
from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import envfile
from .app import App
from .broker import BrokerError
from .capabilities import LEGACY_ALIASES, LEGACY_MINDSETS, LEGACY_STRATEGIES, STRATEGY_PROFILES
from .llm import LLMError, PROVIDERS
from .settings import validate_tunables
from execution_mode import ExecutionModeError, KILLSWITCH_FILE, VALID_MODES, execution_mode_path, get_execution_mode
from network_access import ACCESS_MODES, NetworkAccessError, get_access_mode

WEB = Path(__file__).resolve().parent / "web"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOOPBACK = {"localhost", "127.0.0.1", "[::1]", "::1"}
CSP = ("default-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
       "script-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")


def _run_system_script(script_name: str) -> None:
    if sys.platform != "win32":
        raise OSError("Dashboard process controls are supported only on Windows.")
    script = PROJECT_ROOT / script_name
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"dashboard_{script.stem}_{time.strftime('%Y%m%d_%H%M%S')}.log"
    with log_path.open("ab") as log_file:
        subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            cwd=str(PROJECT_ROOT),
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )


def _schedule_system_script(script_name: str) -> None:
    def launch() -> None:
        try:
            _run_system_script(script_name)
        except OSError:
            import logging
            logging.getLogger(__name__).exception("Could not launch dashboard system action %s", script_name)

    timer = threading.Timer(1.5, launch)
    timer.daemon = True
    timer.start()


class ApiError(Exception):
    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


class DashboardHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request: Any, client_address: Any) -> None:
        _, error, _ = sys.exc_info()
        if isinstance(error, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def make_handler(app: App, token: str, allowed_hosts: set):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = "CthuluAgent/1.0"

        def log_message(self, *a: Any) -> None:  # quiet
            return

        # ------------------------------------------------ plumbing
        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0].lower()
            if host not in allowed_hosts:
                return False
            origin = self.headers.get("Origin")
            if origin:
                oh = urllib.parse.urlparse(origin).netloc.split(":")[0].lower()
                if oh != host:
                    return False
            return True

        def _authed(self, qs: Dict[str, Any]) -> bool:
            if not token:
                return True
            got = (self.headers.get("Authorization", "")[7:] if self.headers.get("Authorization", "").startswith("Bearer ") else
                   self.headers.get("X-Token") or (qs.get("token") or [""])[0])
            return got == token

        def _send(self, status: int, body: bytes, ctype: str, extra: Optional[Dict[str, str]] = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj: Any, status: int = 200) -> None:
            self._send(status, json.dumps(obj, default=str).encode(), "application/json; charset=utf-8", {"Cache-Control": "no-store"})

        def _body(self, limit: int = 1_000_000) -> Any:
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                raise ApiError("Content-Type must be application/json", 415)
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ApiError("payload too large", 413)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                return json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                raise ApiError("invalid JSON")

        def _dispatch(self, method: str) -> None:
            u = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(u.query)
            if not self._host_ok():
                return self._json({"error": "forbidden host"}, 403)
            path = u.path
            try:
                if path.startswith("/api/"):
                    if not self._authed(qs):
                        return self._json({"error": "unauthorized", "auth": True}, 401)
                    if path == "/api/stream" and method == "GET":
                        return self._stream()
                    out = self.route(method, path, qs)
                    return self._json(out)
                if method != "GET":
                    return self._json({"error": "not found"}, 404)
                return self._static(path)
            except ApiError as e:
                self._json({"error": str(e)}, e.status)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as e:  # noqa
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        def do_GET(self) -> None: self._dispatch("GET")
        def do_POST(self) -> None: self._dispatch("POST")
        def do_PATCH(self) -> None: self._dispatch("PATCH")
        def do_DELETE(self) -> None: self._dispatch("DELETE")

        def _static(self, path: str) -> None:
            rel = "index.html" if path in ("/", "") else path.lstrip("/")
            f = (WEB / rel).resolve()
            if WEB.resolve() not in f.parents and f != WEB.resolve() or not f.is_file():
                f = WEB / "index.html"  # SPA fallback
            ctype = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self._send(200, f.read_bytes(), ctype, {"Content-Security-Policy": CSP, "Cache-Control": "no-cache"})

        def _stream(self) -> None:
            q = app.bus.subscribe(replay=30)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                last = time.time()
                while True:
                    try:
                        e = q.get(timeout=15)
                        self.wfile.write(f"id: {e['id']}\ndata: {json.dumps(e, default=str)}\n\n".encode())
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                app.bus.unsubscribe(q)

        # ------------------------------------------------ routes
        def route(self, method: str, path: str, qs: Dict[str, Any]) -> Any:
            rt, j, s = app.runtime, app.journal, app.settings
            g = lambda k, d="": (qs.get(k) or [d])[0]  # noqa

            def need_rt():
                if not rt:
                    raise ApiError(app.broker_error or "agent runtime is not running. Check Settings, then reconnect.", 503)
                return rt

            if method == "GET":
                if path == "/api/state":
                    st = need_rt().state() if rt else {"status": {"running": False, "phase": "offline", "error": app.broker_error}}
                    st["llm"] = app.llm.public_config()
                    st["server_time"] = time.time()
                    return st
                if path == "/api/journal":
                    return {"entries": j.entries(kind=g("kind"), q=g("q"), limit=int(g("limit", "60")), before=int(g("before", "0")), symbol=g("symbol"))}
                if path == "/api/todos": return {"todos": j.todos(limit=200)}
                if path == "/api/playbook": return {"skills": j.playbook()}
                m = re.fullmatch(r"/api/playbook/([a-z0-9_]+)/versions", path)
                if m: return {"versions": j.skill_versions(m.group(1))}
                if path == "/api/trades": return {"trades": j.trades(status=g("status") or None, limit=int(g("limit", "100")))}
                if path == "/api/stats": return j.stats()
                if path == "/api/equity": return {"series": j.equity_series(int(g("limit", "600")))}
                if path == "/api/chat": return {"messages": j.chat_history(80)}
                if path == "/api/world": return {"brief": app.world.brief, "config": app.world.public_config()}
                if path == "/api/config": return self.config()
                raise ApiError("not found", 404)

            b = self._body(4_000_000 if path == "/api/world/ingest" else 1_000_000) if method in ("POST", "PATCH") else {}
            if not isinstance(b, dict) and path != "/api/world/ingest":
                raise ApiError("JSON object expected")

            if method == "POST":
                if path == "/api/system/kill":
                    try:
                        KILLSWITCH_FILE.write_text(
                            f"Trading disabled from dashboard at {time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n",
                            encoding="ascii",
                        )
                    except OSError as exc:
                        raise ApiError(f"Could not activate the kill switch: {exc}", 500)
                    _schedule_system_script("cthulu_killswitch.ps1")
                    return {"ok": True, "kill_switch_active": True}
                if path == "/api/system/restart":
                    _schedule_system_script("cthulu_restart.ps1")
                    return {"ok": True, "restart_queued": True}
                if path == "/api/chat":
                    return need_rt().chat(str(b.get("text", "")))
                if path == "/api/control":
                    a = str(b.get("action", ""))
                    if a == "reconnect":
                        ok = app.start_runtime()
                        return {"ok": ok, "error": app.broker_error}
                    r = need_rt()
                    if a == "pause": r.pause()
                    elif a == "resume": r.resume()
                    elif a == "flatten": return {"ok": True, **r.flatten("dashboard")}
                    elif a == "think_now": r.think_now(replan=bool(b.get("replan")))
                    elif a == "review": r.run_review_now()
                    else: raise ApiError("unknown action")
                    return {"ok": True}
                m = re.fullmatch(r"/api/(positions|orders)/(\d+)/(close|cancel)", path)
                if m:
                    r = need_rt()
                    return r.operator_order(int(m.group(2)), m.group(3))
                m = re.fullmatch(r"/api/proposals/(\d+)", path)
                if m: return need_rt().decide(int(m.group(1)), bool(b.get("approve")))
                if path == "/api/journal":
                    title = str(b.get("title", "")).strip()
                    if not title: raise ApiError("title required")
                    e = j.add("user", title, str(b.get("body", "")), tags=["note"])
                    app.bus.emit("journal", entry=e)
                    return {"entry": e}
                if path == "/api/todos":
                    title = str(b.get("title", "")).strip()
                    if not title: raise ApiError("title required")
                    t = j.todo_add(title, str(b.get("detail", "")), int(b.get("priority") or 2), str(b.get("symbol", "")), source="user")
                    app.bus.emit("todo", todo=t)
                    return {"todo": t}
                if path == "/api/playbook":
                    if not b.get("name") or not b.get("body"): raise ApiError("name and body required")
                    sk = j.skill_upsert(str(b["name"]), str(b["body"]), kind=str(b.get("kind", "skill")), origin="operator", reason="edited in dashboard")
                    app.bus.emit("playbook")
                    return {"skill": sk}
                m = re.fullmatch(r"/api/playbook/([a-z0-9_]+)/status", path)
                if m:
                    if b.get("status") not in ("active", "probation", "retired"): raise ApiError("bad status")
                    j.skill_upsert(m.group(1), "", status=b["status"], reason="status set in dashboard")
                    app.bus.emit("playbook")
                    return {"skill": j.skill(m.group(1))}
                if path == "/api/models/discover":
                    pid = str(b.get("provider", ""))
                    if pid not in PROVIDERS: raise ApiError("unknown provider")
                    try:
                        models = app.llm.discover(
                            pid, str(b.get("api_key", "")), str(b.get("base_url", "")),
                            str(b.get("account_id", "")), str(b.get("gateway_id", "")),
                        )
                    except LLMError as e:
                        raise ApiError(str(e), 502)
                    return {"models": models}
                if path == "/api/llm/test":
                    pid = str(b.get("provider") or app.llm.active_provider())
                    if pid not in PROVIDERS: raise ApiError("unknown provider")
                    return app.llm.ping(pid)
                if path == "/api/config/llm":
                    pid = str(b.get("provider", ""))
                    try:
                        app.llm.apply(pid, base_url=b.get("base_url"), api_key=b.get("api_key"), model=b.get("model"),
                                      activate=bool(b.get("activate")), clear_key=bool(b.get("clear_key")),
                                      account_id=b.get("account_id"), gateway_id=b.get("gateway_id"))
                    except (ValueError, LLMError) as e:
                        raise ApiError(str(e))
                    app.bus.emit("config")
                    if rt: rt.note("system", f"LLM settings updated: {pid}" + (" (now active)" if b.get("activate") else ""))
                    return self.config()
                if path == "/api/config/agent":
                    try:
                        upd = validate_tunables({k: v for k, v in b.items()})
                    except ValueError as e:
                        raise ApiError(str(e))
                    envfile.set_env(upd)
                    app.bus.emit("config")
                    if rt: rt.note("system", "Settings changed: " + ", ".join(f"{k}={v}" for k, v in upd.items()))
                    return self.config()
                if path == "/api/config/execution":
                    mode = b.get("mode")
                    if mode not in VALID_MODES:
                        raise ApiError(f"mode must be one of: {', '.join(VALID_MODES)}")
                    try:
                        current_mode = get_execution_mode()
                    except ExecutionModeError as exc:
                        raise ApiError(str(exc), 503)
                    if mode != current_mode:
                        if not rt:
                            raise ApiError("Connect the broker before changing execution mode.", 503)
                        if mode == "legacy":
                            try:
                                positions, orders = rt.broker.positions(), rt.broker.pending()
                            except BrokerError as exc:
                                raise ApiError(f"Could not verify the account is flat: {exc}", 503)
                            if positions or orders:
                                raise ApiError("Flatten all positions and cancel pending orders before disabling Agentic trade actions.", 409)
                        envfile.set_env({"CTHULU_EXECUTION_MODE": mode}, execution_mode_path())
                        rt.note("system", f"Execution mode changed to {mode}; Legacy remains active.")
                        app.bus.emit("config")
                    return {**self.config(), "restart_required": False}
                if path == "/api/config/network":
                    mode = b.get("mode")
                    if mode not in ACCESS_MODES:
                        raise ApiError(f"mode must be one of: {', '.join(ACCESS_MODES)}")
                    try:
                        current_mode = get_access_mode()
                    except NetworkAccessError:
                        current_mode = ""
                    updates = {"DASHBOARD_ACCESS_MODE": mode}
                    token_once = ""
                    existing_token = os.environ.get("DASHBOARD_TOKEN") or envfile.read_env().get("DASHBOARD_TOKEN")
                    if mode != "loopback" and not existing_token:
                        token_once = secrets.token_urlsafe(32)
                        updates["DASHBOARD_TOKEN"] = token_once
                    try:
                        envfile.set_env(updates)
                    except (OSError, ValueError) as exc:
                        raise ApiError(f"Could not save dashboard network settings: {exc}", 500)
                    if rt:
                        rt.note("system", f"Dashboard access mode set to {mode}; restart required to apply.")
                    app.bus.emit("config")
                    result = {**self.config(), "restart_required": mode != current_mode}
                    if token_once:
                        result["token_once"] = token_once
                    return result
                if path == "/api/config/world":
                    upd: Dict[str, Optional[str]] = {}
                    for k, env in (("url", "WORLD_API_URL"), ("header", "WORLD_API_HEADER"), ("scheme", "WORLD_API_SCHEME"),
                                   ("paths", "WORLD_API_PATHS"), ("refresh_min", "WORLD_REFRESH_MIN")):
                        if k in b: upd[env] = str(b[k]).strip() or None
                    if "native_enabled" in b:
                        if not isinstance(b["native_enabled"], bool):
                            raise ApiError("native_enabled must be true or false")
                        upd["WORLD_NATIVE_ENABLED"] = "true" if b["native_enabled"] else "false"
                    if b.get("api_key"): upd["WORLD_API_KEY"] = str(b["api_key"]).strip()
                    if b.get("clear_key"): upd["WORLD_API_KEY"] = None
                    if upd.get("WORLD_API_URL") and not re.match(r"^https?://", upd["WORLD_API_URL"]): raise ApiError("URL must start with http:// or https://")
                    try:
                        envfile.set_env(upd)
                    except ValueError as e:
                        raise ApiError(str(e))
                    return self.config()
                if path == "/api/config/broker":
                    upd = {}
                    if b.get("broker") in ("paper", "mt5"): upd["BROKER"] = b["broker"]
                    for k, env in (("mt5_login", "MT5_LOGIN"), ("mt5_server", "MT5_SERVER"), ("mt5_path", "MT5_PATH")):
                        if k in b: upd[env] = str(b[k]).strip() or None
                    if b.get("mt5_password"): upd["MT5_PASSWORD"] = str(b["mt5_password"])
                    if "live_confirm" in b: upd["LIVE_RUN_CONFIRM"] = "1" if b["live_confirm"] else None
                    try:
                        envfile.set_env(upd)
                    except ValueError as e:
                        raise ApiError(str(e))
                    return {**self.config(), "restart_required": True}
                if path == "/api/world/ingest":
                    app.world.ingest(b)
                    if rt: rt.wake()
                    return {"ok": True}
                if path == "/api/world/refresh":
                    ok = app.world.fetch()
                    app.world.digested_ts = 0
                    if rt: rt.wake()
                    return {"ok": ok, "error": app.world.last_error}
                raise ApiError("not found", 404)

            if method == "PATCH":
                m = re.fullmatch(r"/api/todos/(\d+)", path)
                if m:
                    t = j.todo_update(int(m.group(1)), **{k: b.get(k) for k in ("title", "detail", "status", "priority", "result")})
                    if not t: raise ApiError("todo not found", 404)
                    app.bus.emit("todo", todo=t)
                    return {"todo": t}
            if method == "DELETE":
                m = re.fullmatch(r"/api/todos/(\d+)", path)
                if m:
                    t = j.todo_update(int(m.group(1)), status="dropped")
                    app.bus.emit("todo", todo=t)
                    return {"todo": t}
            raise ApiError("not found", 404)

        def config(self) -> Dict[str, Any]:
            import os
            e = os.environ
            project_settings = envfile.read_env(PROJECT_ROOT / ".env")
            try:
                execution_owner = get_execution_mode()
                execution_mode_error = ""
            except ExecutionModeError as exc:
                execution_owner = "disabled"
                execution_mode_error = str(exc)
            try:
                access_mode = get_access_mode()
                access_mode_error = ""
            except NetworkAccessError as exc:
                access_mode = "disabled"
                access_mode_error = str(exc)
            try:
                port = int(e.get("DASHBOARD_PORT", "8765"))
            except ValueError:
                port = 8765
            return {"llm": app.llm.public_config(), "agent": app.settings.tunables(), "world": app.world.public_config(),
                    "strategy_catalog": {"agent_profiles": STRATEGY_PROFILES, "legacy_strategies": LEGACY_STRATEGIES,
                                         "legacy_mindsets": LEGACY_MINDSETS, "legacy_aliases": LEGACY_ALIASES},
                    "execution_mode": {"mode": execution_owner, "options": list(VALID_MODES), "error": execution_mode_error},
                    "system": {
                        "kill_switch_active": KILLSWITCH_FILE.exists(),
                        "trading_mode": project_settings.get("CTHULU_TRADING_MODE", "single"),
                        "config_name": project_settings.get("CTHULU_CONFIG_NAME", "config.json"),
                    },
                    "network": {"mode": access_mode, "options": list(ACCESS_MODES), "error": access_mode_error,
                                "port": port, "token_configured": bool(e.get("DASHBOARD_TOKEN"))},
                    "broker": {"broker": app.settings.broker, "mt5_login": e.get("MT5_LOGIN", ""), "mt5_server": e.get("MT5_SERVER", ""),
                               "mt5_path": e.get("MT5_PATH", ""), "has_password": bool(e.get("MT5_PASSWORD")), "live_confirm": e.get("LIVE_RUN_CONFIRM") == "1",
                               "error": app.broker_error, "connected": bool(app.runtime)},
                    "env_file": str(envfile.default_env_path())}
    return H


def serve(app: App, host: str = "127.0.0.1", port: int = 8765, token: str = "", extra_hosts: Optional[set] = None) -> Tuple[ThreadingHTTPServer, threading.Thread]:
    hosts = set(LOOPBACK) | {h.strip().lower() for h in (extra_hosts or set()) if h.strip()}
    if host not in ("0.0.0.0", "::"):
        hosts.add(host.lower())
    if host not in ("127.0.0.1", "localhost", "::1") and not token:
        raise SystemExit("Refusing to bind a non-loopback address without DASHBOARD_TOKEN. The dashboard can place trades and write API keys.")
    srv = DashboardHTTPServer((host, port), make_handler(app, token, hosts))
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, name="cthulu-http", daemon=True)
    t.start()
    return srv, t
