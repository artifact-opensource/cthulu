"""A scripted local LLM server speaking OpenAI-style and Anthropic-style APIs, for tests."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _ctx(text):
    i = text.find("CONTEXT:\n")
    if i < 0:
        i = text.find("CURRENT STATE:\n")
        i = i + len("CURRENT STATE:\n") - len("CONTEXT:\n") if i >= 0 else -1
    try:
        return json.loads(text[i + 9:]) if i >= 0 else {}
    except ValueError:
        return {}


def script(messages):
    """Decide the reply from the phase marker in the last user message."""
    text = messages[-1]["content"] if messages else ""
    full = " ".join(m["content"] for m in messages)
    ctx = _ctx(text)
    if "PHASE: PLAN" in text:
        return {"focus": "Look for sweeps of equal lows on EURUSD", "bias": {"EURUSD": "bullish"},
                "watch": [{"symbol": "EURUSD", "level": 1.08, "why": "equal lows"}], "risks": ["news"],
                "todos": {"add": [{"title": "Track sweep reversals on EURUSD", "detail": "log each one", "priority": 1}]}, "notes": "test plan"}
    if "PHASE: REASON" in text:
        m = (ctx.get("markets") or {}).get("EURUSD") or {}
        if ctx.get("positions") or ctx.get("pending_orders") or not m.get("price"):
            return {"assessment": "Managing what is open.", "confidence": 0.5, "actions": [{"type": "hold", "reason": "nothing to do"}], "journal": "hold", "next_check_minutes": 1}
        p, a = m["price"], m["atr"]
        return {"assessment": "Equal lows swept and reclaimed; expect a retrace.", "confidence": 0.6, "journal": "Resting a limit below price.",
                "actions": [{"type": "place_limit", "symbol": "EURUSD", "side": "buy", "entry": round(p - 0.5 * a, 5), "sl": round(p - 1.8 * a, 5),
                             "tp": round(p + 2.2 * a, 5), "risk_pct": 0.5, "skills": ["liquidity_sweep_reversal"], "thesis": "sweep and reclaim",
                             "invalidation": "close below the sweep low", "expires_minutes": 90}], "next_check_minutes": 1}
    if "PHASE: ADJUST" in text:
        return {"actions": [], "note": "dropping the rejected idea"}
    if "PHASE: REFLECT" in text:
        return {"verdict": "as_expected", "notes": "Order resting as planned.", "next_check_minutes": 1}
    if "PHASE: TRADE REVIEW" in text:
        return {"process": "good", "outcome_vs_thesis": "played out as thesis suggested", "lessons": ["Wait for reclaim candle close"],
                "skill_changes": [{"name": "liquidity_sweep_reversal", "action": "edit", "kind": "setup",
                                   "body": "Sweep, reclaim close, displacement. Enter on retrace with stop beyond the wick. Wait for the reclaim candle to close.",
                                   "reason": "review of trade"}], "todos": []}
    if "PHASE: META REVIEW" in text:
        return {"summary": "Early days.", "skill_changes": [], "experiments": [{"title": "Test London open sweeps", "detail": "count outcomes"}],
                "scaling_notes": "Hold 1R risk until 20 trades", "process_notes": "Cite skills on every entry"}
    if "PHASE: WORLD BRIEF" in text:
        return {"summary": "Risk appetite remains steady across the currently available market feeds.", "themes": [{"theme": "Rates", "assets": ["EURUSD"], "bias": "neutral", "urgency": "low", "why": "The available feed reports calm rate conditions."}],
                "event_risk": [], "stand_down": False}
    if "operator in chat" in full:
        last = messages[-1]["content"]
        if "tighten risk" in last:
            return {"reply": "Lowering the per-trade cap to 0.5%.", "actions": [{"type": "set_setting", "key": "RISK_MAX_PER_TRADE_PCT", "value": "0.5"}]}
        if "max risk 50" in last:
            return {"reply": "Setting it.", "actions": [{"type": "set_setting", "key": "RISK_MAX_PER_TRADE_PCT", "value": "50"}]}
        return {"reply": "All good. Watching EURUSD.", "actions": []}
    return {"ok": True}


class FakeLLM:
    def __init__(self, fail_first=0):
        self.calls, self.fail = [], fail_first
        outer = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a): pass

            def _send(self, code, obj, hdr=None):
                b = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                for k, v in (hdr or {}).items(): self.send_header(k, v)
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                outer.calls.append(("GET", self.path, {k.lower(): v for k, v in self.headers.items()}))
                if self.path.startswith("/v1/models") and "x-api-key" in {k.lower() for k in self.headers}:
                    return self._send(200, {"data": [{"id": "claude-test-1", "display_name": "Claude Test"}], "has_more": False})
                if self.path.startswith("/models"):
                    return self._send(200, {"data": [{"id": "vendor/model-a:free", "name": "A", "context_length": 8000, "pricing": {"prompt": "0", "completion": "0"}},
                                                     {"id": "vendor/model-b", "name": "B", "pricing": {"prompt": "0.1", "completion": "0.2"}}]})
                self._send(404, {"error": {"message": "nope"}})

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n) or b"{}")
                outer.calls.append(("POST", self.path, {k.lower(): v for k, v in self.headers.items()}, body))
                if outer.fail > 0:
                    outer.fail -= 1
                    return self._send(429, {"error": {"message": "rate limited"}}, {"Retry-After": "0"})
                if self.path.endswith("/chat/completions"):
                    msgs = body["messages"]
                    out = script(msgs)
                    txt = out if isinstance(out, str) else "```json\n" + json.dumps(out) + "\n```"
                    return self._send(200, {"model": body["model"], "choices": [{"message": {"content": txt}}], "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
                if self.path.endswith("/v1/messages"):
                    msgs = [{"role": "system", "content": body.get("system", "")}] + body["messages"]
                    out = script(msgs)
                    return self._send(200, {"model": body["model"], "content": [{"type": "text", "text": json.dumps(out)}], "usage": {"input_tokens": 7, "output_tokens": 3}})
                self._send(404, {"error": {"message": "nope"}})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def url(self): return f"http://127.0.0.1:{self.port}"
    def close(self):
        self.srv.shutdown()
        self.srv.server_close()
