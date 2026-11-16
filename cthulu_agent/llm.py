"""Provider-agnostic LLM layer.

Providers (all configurable from the dashboard, persisted to .env, hot-swappable):
  cloudflare  Cloudflare AI Gateway (Workers AI), the default (Granite 4.0 H-Micro)
  openrouter  OpenAI-style API
  openai      any OpenAI-compatible endpoint (OpenAI, Ollama, LM Studio, Together, Groq...)
  anthropic   Anthropic Messages API (or a compatible proxy)
  gemini      Google's OpenAI-compatible Gemini endpoint
  grok        xAI's OpenAI-compatible endpoint

The agent never relies on native tool calling (many free models lack it). It asks for strict
JSON and parses it tolerantly, with one automatic repair pass.
"""
from __future__ import annotations

import ast
import json
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import envfile

PROVIDERS: Dict[str, Dict[str, str]] = {
    "cloudflare": {"label": "Cloudflare AI Gateway", "kind": "openai", "base_url": "",
                   "model": "@cf/ibm-granite/granite-4.0-h-micro", "key_env": "CLOUDFLARE_API_KEY",
                   "base_env": "CLOUDFLARE_BASE_URL", "model_env": "CLOUDFLARE_MODEL",
                   "account_env": "CLOUDFLARE_ACCOUNT_ID", "gateway_env": "CLOUDFLARE_AI_GATEWAY_ID",
                   "hint": "Workers AI via AI Gateway. Granite 4.0 H-Micro is a low-cost agentic option."},
    "openrouter": {"label": "OpenRouter", "kind": "openai", "base_url": "https://openrouter.ai/api/v1",
                   "model": "openrouter/free", "key_env": "OPENROUTER_API_KEY", "base_env": "OPENROUTER_BASE_URL",
                   "model_env": "OPENROUTER_MODEL", "hint": "One key, hundreds of models. Free tier works without credits."},
    "openai": {"label": "OpenAI compatible", "kind": "openai", "base_url": "https://api.openai.com/v1",
               "model": "gpt-4o-mini", "key_env": "OPENAI_API_KEY", "base_env": "OPENAI_BASE_URL",
               "model_env": "OPENAI_MODEL", "hint": "OpenAI, or any compatible server: Ollama, LM Studio, Together, Groq."},
    "anthropic": {"label": "Anthropic compatible", "kind": "anthropic", "base_url": "https://api.anthropic.com",
                  "model": "claude-sonnet-5-5", "key_env": "ANTHROPIC_API_KEY", "base_env": "ANTHROPIC_BASE_URL",
                  "model_env": "ANTHROPIC_MODEL", "hint": "Claude models through the Messages API."},
    "gemini": {"label": "Gemini compatible", "kind": "openai",
               "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "model": "gemini-2.5-flash", "key_env": "GEMINI_API_KEY", "base_env": "GEMINI_BASE_URL",
               "model_env": "GEMINI_MODEL", "hint": "Google Gemini through its OpenAI-compatible endpoint."},
    "grok": {"label": "Grok compatible", "kind": "openai", "base_url": "https://api.x.ai/v1",
             "model": "grok-4", "key_env": "XAI_API_KEY", "base_env": "XAI_BASE_URL",
             "model_env": "XAI_MODEL", "hint": "xAI Grok models."},
}
DEFAULT_PROVIDER = "cloudflare"


class LLMError(Exception):
    """Raised for any provider failure. Messages never contain credentials."""

    def __init__(self, msg: str, status: Optional[int] = None, retry_after: Optional[float] = None):
        super().__init__(msg)
        self.status = status
        self.retry_after = retry_after


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency: float
    tokens_in: int = 0
    tokens_out: int = 0
    finish_reason: str = ""


# ---------------------------------------------------------------- http
def _check_url(url: str) -> str:
    u = urllib.parse.urlparse(url)
    if u.scheme not in ("http", "https") or not u.netloc:
        raise LLMError("Base URL must start with http:// or https://")
    return url.rstrip("/")


def _http(method: str, url: str, headers: Dict[str, str], body: Optional[dict], timeout: float) -> Tuple[int, Any, Dict[str, str]]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdr = {"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "cthulu-agent/1.0"}
    hdr.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdr)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw, status, rh = r.read(), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw, status, rh = e.read(), e.code, dict(e.headers or {})
    except (socket.timeout, TimeoutError):
        raise LLMError("request timed out")
    except urllib.error.URLError as e:
        raise LLMError(f"could not reach server ({getattr(e, 'reason', e)})")
    try:
        js = json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        js = None
    return status, js, rh


def _err_text(status: int, js: Any) -> str:
    msg = ""
    if isinstance(js, dict):
        e = js.get("error")
        if isinstance(e, dict):
            msg = str(e.get("message") or e.get("type") or "")
        elif e:
            msg = str(e)
        if not msg and isinstance(js.get("errors"), list):
            messages = [str(error.get("message", "")) for error in js["errors"] if isinstance(error, dict)]
            msg = "; ".join(message for message in messages if message)
        msg = msg or str(js.get("message") or "")
    return f"HTTP {status}" + (f": {msg[:240]}" if msg else "")


# ---------------------------------------------------------------- JSON extraction
def extract_json(text: str) -> Any:
    """Pull the first JSON object out of model output (fences, prose, trailing commas tolerated)."""
    if not text:
        raise ValueError("empty reply")
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I)
    start = t.find("{")
    if start < 0:
        raise ValueError("no JSON object in reply")
    depth, in_str, esc = 0, False, False
    end = -1
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    chunk = t[start:end + 1] if end > 0 else t[start:]
    for candidate in (chunk, re.sub(r",\s*([}\]])", r"\1", chunk)):
        try:
            return json.loads(candidate)
        except ValueError:
            pass
    try:
        return ast.literal_eval(re.sub(r",\s*([}\]])", r"\1", chunk))
    except Exception:
        raise ValueError("could not parse JSON from reply")


# ---------------------------------------------------------------- client
class LLMClient:
    def __init__(self, pid: str, base_url: str, api_key: str, model: str, timeout: float = 90.0,
                 account_id: str = "", gateway_id: str = "default"):
        self.pid, self.kind = pid, PROVIDERS[pid]["kind"]
        self.base_url, self.api_key, self.model, self.timeout = base_url, api_key, model, timeout
        self.account_id, self.gateway_id = account_id, gateway_id

    # -- auth / urls
    def _headers(self) -> Dict[str, str]:
        if self.kind == "anthropic":
            return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}
        h = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        if self.pid == "cloudflare":
            h["cf-aig-gateway-id"] = self.gateway_id
        if self.pid == "openrouter":
            h["X-Title"] = "Cthulu Agent"
            h["HTTP-Referer"] = "https://github.com/cthulu-agent"
        return h

    def _anthropic_root(self) -> str:
        b = _check_url(self.base_url)
        return b[:-3] if b.endswith("/v1") else b

    # -- chat
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.3, max_tokens: int = 1800,
             retries: int = 2, json_mode: bool = False, allow_empty: bool = False) -> LLMResponse:
        if self.pid == "cloudflare" and not self.account_id:
            raise LLMError("Cloudflare Account ID is required. Add it in Settings.")
        if not self.api_key and self.pid in ("cloudflare", "openrouter", "anthropic", "gemini", "grok"):
            raise LLMError(f"No API key set for {PROVIDERS[self.pid]['label']}. Add one in Settings.")
        attempt = 0
        while True:
            t0 = time.time()
            try:
                response = self._chat_once(messages, temperature, max_tokens, t0, json_mode=json_mode)
                if not response.text.strip() and not allow_empty:
                    reason = response.finish_reason or "unknown"
                    raise LLMError(
                        f"model returned an empty reply (finish_reason={reason}, output_tokens={response.tokens_out})",
                        status=502,
                    )
                return response
            except LLMError as e:
                retryable = (
                    e.status in (429, 500, 502, 503, 504, None)
                    and "No API key" not in str(e)
                    and "model returned an empty reply" not in str(e)
                )
                if attempt >= retries or not retryable or (e.status is None and "timed out" not in str(e)):
                    raise
                time.sleep(min(e.retry_after or (2.0 * (attempt + 1) ** 2), 20.0))
                attempt += 1

    def _chat_once(self, messages, temperature, max_tokens, t0, json_mode: bool = False) -> LLMResponse:
        if self.kind == "anthropic":
            system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
            turns = [m for m in messages if m["role"] != "system"] or [{"role": "user", "content": "Continue."}]
            body = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature, "messages": turns}
            if system:
                body["system"] = system
            status, js, rh = _http("POST", self._anthropic_root() + "/v1/messages", self._headers(), body, self.timeout)
        else:
            body = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            if json_mode:
                body["response_format"] = {"type": "json_object"}
                if self.pid == "openrouter":
                    body["reasoning"] = {"effort": "low"}
            status, js, rh = _http("POST", _check_url(self.base_url) + "/chat/completions", self._headers(), body, self.timeout)
            if "reasoning" in body and self._unsupported_reasoning_effort(status, js):
                retry_body = dict(body)
                retry_body.pop("reasoning")
                status, js, rh = _http("POST", _check_url(self.base_url) + "/chat/completions", self._headers(), retry_body, self.timeout)
        if status != 200 or not isinstance(js, dict):
            ra = None
            try:
                ra = float(rh.get("Retry-After") or rh.get("retry-after") or "")
            except ValueError:
                pass
            raise LLMError(_err_text(status, js), status=status, retry_after=ra)
        if isinstance(js.get("error"), dict) or js.get("success") is False:
            error = js.get("error") if isinstance(js.get("error"), dict) else {}
            code = error.get("code")
            status = int(code) if str(code).isdigit() else 502
            raise LLMError(_err_text(200, js), status=status)
        text, tin, tout, finish_reason = "", 0, 0, ""
        if self.kind == "anthropic":
            text = "".join(b.get("text", "") for b in js.get("content", []) if b.get("type") == "text")
            u = js.get("usage") or {}
            tin, tout = int(u.get("input_tokens", 0)), int(u.get("output_tokens", 0))
            finish_reason = str(js.get("stop_reason") or "")
        else:
            ch = (js.get("choices") or [{}])[0]
            msg = ch.get("message") or {}
            c = msg.get("content")
            if isinstance(c, list):
                c = "".join(p.get("text", "") for p in c if isinstance(p, dict))
            text = c or ""
            u = js.get("usage") or {}
            tin, tout = int(u.get("prompt_tokens", 0)), int(u.get("completion_tokens", 0))
            finish_reason = str(ch.get("finish_reason") or "")
        return LLMResponse(text=text, provider=self.pid, model=js.get("model") or self.model,
                           latency=time.time() - t0, tokens_in=tin, tokens_out=tout,
                           finish_reason=finish_reason)

    def _unsupported_reasoning_effort(self, status: int, response: Any) -> bool:
        if self.pid != "openrouter" or status not in (200, 400, 422):
            return False
        message = _err_text(status, response).lower()
        if status == 200 and isinstance(response, dict) and isinstance(response.get("error"), dict):
            message = str(response["error"].get("message") or "").lower()
        return "reasoning" in message and any(
            phrase in message
            for phrase in ("unsupported", "not supported", "unknown parameter", "unrecognized", "not allowed")
        )

    def chat_json(self, messages: List[Dict[str, str]], temperature: float = 0.2, max_tokens: int = 1800) -> Tuple[Any, LLMResponse]:
        json_mode = self.kind == "openai"
        r = self.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode, allow_empty=True)
        for repair_attempt in range(4):
            empty = not r.text.strip()
            try:
                return extract_json(r.text), r
            except ValueError as e:
                if repair_attempt == 3:
                    detail = "empty " if empty else ""
                    if r.finish_reason in ("length", "max_tokens"):
                        detail += "truncated "
                    raise LLMError(
                        f"model did not return valid {detail}JSON ({e}); "
                        f"model={r.model}, finish_reason={r.finish_reason or 'unknown'}, "
                        f"input_tokens={r.tokens_in}, output_tokens={r.tokens_out}",
                        status=422 if not empty else 502,
                    )

                truncated = r.finish_reason in ("length", "max_tokens")
                fix = [dict(message) for message in messages]
                if empty:
                    correction = (
                        "The previous completion used its token budget for reasoning and returned no visible content. "
                        "Use minimal internal reasoning. Return the requested JSON now, with every field concise; "
                        "do not add prose or code fences."
                    )
                else:
                    correction = (
                        "Return the requested result as one complete JSON object only. "
                        "Use minimal internal reasoning and concise field values; do not add prose or code fences."
                    )
                    if truncated:
                        correction += " The previous response was truncated after hitting its generation-token limit."
                if fix and fix[-1].get("role") == "user":
                    fix[-1]["content"] += "\n\n" + correction
                else:
                    fix.append({"role": "user", "content": correction})

                repair_max_tokens = min(max(max_tokens * 2, 2800) * (2 ** repair_attempt), 16384)
                r = self.chat(
                    fix, temperature=0.0, max_tokens=repair_max_tokens, retries=1,
                    json_mode=json_mode, allow_empty=True,
                )

    # -- discovery
    def list_models(self) -> List[Dict[str, Any]]:
        models: List[Dict[str, Any]] = []
        if self.pid == "cloudflare":
            if not self.account_id:
                raise LLMError("Cloudflare Account ID is required to discover models.")
            if not self.api_key:
                raise LLMError("No API key set for Cloudflare AI Gateway. Add one in Settings.")
            seen = set()
            per_page = 100
            for page in range(1, 51):
                query = urllib.parse.urlencode({"format": "openrouter", "per_page": per_page, "page": page})
                url = (
                    "https://api.cloudflare.com/client/v4/accounts/"
                    + urllib.parse.quote(self.account_id, safe="")
                    + "/ai/models/search?"
                    + query
                )
                status, js, _h = _http("GET", url, self._headers(), None, 30)
                if status != 200 or not isinstance(js, dict) or js.get("success") is False:
                    error_status = status if status != 200 else 400
                    raise LLMError(_err_text(error_status, js), status=error_status)
                result = js.get("result") or {}
                page_models = js.get("data") if isinstance(js.get("data"), list) else (
                    result.get("data", []) if isinstance(result, dict) else result
                )
                if not isinstance(page_models, list):
                    raise LLMError("Cloudflare model search returned an unexpected response.")
                for item in page_models:
                    if not isinstance(item, dict):
                        continue
                    model_id = str(item.get("id") or item.get("name") or "")
                    if not model_id or model_id in seen:
                        continue
                    seen.add(model_id)
                    models.append({"id": model_id, "name": item.get("name") or model_id})
                if len(page_models) < per_page:
                    break
            else:
                raise LLMError("Cloudflare model search exceeded 5,000 models; narrow the catalog search.")
        elif self.kind == "anthropic":
            after = None
            for _ in range(5):
                url = self._anthropic_root() + "/v1/models?limit=100" + (f"&after_id={urllib.parse.quote(after)}" if after else "")
                status, js, _h = _http("GET", url, self._headers(), None, 30)
                if status != 200 or not isinstance(js, dict):
                    raise LLMError(_err_text(status, js), status=status)
                for m in js.get("data", []):
                    models.append({"id": m["id"], "name": m.get("display_name") or m["id"]})
                if not js.get("has_more") or not js.get("last_id"):
                    break
                after = js["last_id"]
        else:
            status, js, _h = _http("GET", _check_url(self.base_url) + "/models", self._headers(), None, 30)
            if status != 200 or not isinstance(js, dict):
                raise LLMError(_err_text(status, js), status=status)
            for m in js.get("data", js.get("models", [])) or []:
                mid = str(m.get("id") or m.get("name") or "")
                if not mid:
                    continue
                if mid.startswith("models/"):
                    mid = mid[7:]
                pr = m.get("pricing") or {}
                free = mid.endswith(":free") or (pr.get("prompt") in ("0", 0) and pr.get("completion") in ("0", 0))
                models.append({"id": mid, "name": m.get("name") or mid, "context": m.get("context_length"), "free": bool(free)})
            if self.pid == "openrouter" and not any(m["id"] == "openrouter/free" for m in models):
                models.insert(0, {"id": "openrouter/free", "name": "Free models router", "free": True})
        seen, out = set(), []
        for m in models:
            if m["id"] not in seen:
                seen.add(m["id"])
                out.append(m)
        return sorted(out, key=lambda m: (not m["id"].startswith("openrouter/"), m["id"]))


# ---------------------------------------------------------------- manager
class LLMManager:
    """Reads provider config live from the environment, so a settings change is a hot swap."""

    def __init__(self, on_event: Optional[Callable[..., Any]] = None):
        self._lock = threading.Lock()
        self._on_event = on_event
        self.stats: Dict[str, Dict[str, Any]] = {}
        self.busy = 0

    # -- config
    def active_provider(self) -> str:
        p = (os.environ.get("LLM_PROVIDER") or DEFAULT_PROVIDER).strip().lower()
        return p if p in PROVIDERS else DEFAULT_PROVIDER

    def provider_config(self, pid: str) -> Dict[str, str]:
        s = PROVIDERS[pid]
        account_id = os.environ.get(s.get("account_env", ""), "").strip()
        base_url = (os.environ.get(s["base_env"]) or s["base_url"]).strip()
        if pid == "cloudflare" and not base_url and account_id:
            base_url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
        return {"base_url": base_url, "model": (os.environ.get(s["model_env"]) or s["model"]).strip(),
                "api_key": os.environ.get(s["key_env"], "").strip(), "account_id": account_id,
                "gateway_id": os.environ.get(s.get("gateway_env", ""), "default").strip() or "default"}

    def public_config(self) -> Dict[str, Any]:
        provs = {}
        for pid, s in PROVIDERS.items():
            c = self.provider_config(pid)
            k = c["api_key"]
            provs[pid] = {"label": s["label"], "kind": s["kind"], "hint": s["hint"], "base_url": c["base_url"],
                          "model": c["model"], "has_key": bool(k), "key_hint": ("…" + k[-4:]) if len(k) >= 8 else ("set" if k else ""),
                          "default_base_url": s["base_url"], "default_model": s["model"], "key_env": s["key_env"],
                          "account_id": c["account_id"], "gateway_id": c["gateway_id"],
                          "configured": bool(k) and (bool(c["account_id"]) if pid == "cloudflare" else True),
                          "stats": self.stats.get(pid, {})}
        return {"active": self.active_provider(), "providers": provs}

    def client(self, pid: Optional[str] = None, **override: str) -> LLMClient:
        pid = pid or self.active_provider()
        if pid not in PROVIDERS:
            raise LLMError(f"unknown provider: {pid}")
        c = self.provider_config(pid)
        c.update({k: v for k, v in override.items() if v})
        return LLMClient(pid, c["base_url"], c["api_key"], c["model"],
                         account_id=c["account_id"], gateway_id=c["gateway_id"])

    def apply(self, pid: str, base_url: Optional[str] = None, api_key: Optional[str] = None,
              model: Optional[str] = None, activate: bool = False, clear_key: bool = False,
              account_id: Optional[str] = None, gateway_id: Optional[str] = None) -> None:
        if pid not in PROVIDERS:
            raise ValueError(f"unknown provider: {pid}")
        s = PROVIDERS[pid]
        upd: Dict[str, Optional[str]] = {}
        if base_url is not None:
            b = base_url.strip()
            if b:
                _check_url(b)
            upd[s["base_env"]] = b or None
        if model is not None:
            upd[s["model_env"]] = model.strip() or None
        if pid == "cloudflare":
            if account_id is not None:
                account_id = account_id.strip()
                if account_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", account_id):
                    raise ValueError("Cloudflare Account ID must contain only letters, numbers, underscores, or hyphens.")
                upd[s["account_env"]] = account_id or None
            if gateway_id is not None:
                gateway_id = gateway_id.strip()
                if gateway_id and not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", gateway_id):
                    raise ValueError("Cloudflare Gateway ID must contain only letters, numbers, underscores, or hyphens.")
                upd[s["gateway_env"]] = gateway_id or None
        if clear_key:
            upd[s["key_env"]] = None
        elif api_key:
            upd[s["key_env"]] = api_key.strip()
        if activate:
            upd["LLM_PROVIDER"] = pid
        envfile.set_env(upd)
        if pid == "cloudflare" and clear_key:
            root_env = Path(__file__).resolve().parent.parent / ".env"
            active_env = envfile.default_env_path().resolve()
            if active_env != root_env.resolve():
                envfile.set_env({"CLOUDFLARE_API_KEY": None}, root_env)

    # -- calls (tracked for the dashboard)
    def _track(self, pid: str, ok: bool, resp: Optional[LLMResponse], err: str = "", purpose: str = ""):
        with self._lock:
            st = self.stats.setdefault(pid, {"calls": 0, "errors": 0, "tokens_in": 0, "tokens_out": 0})
            st["calls"] += 1
            if ok and resp:
                st.update(tokens_in=st["tokens_in"] + resp.tokens_in, tokens_out=st["tokens_out"] + resp.tokens_out,
                          last_latency=round(resp.latency, 2), last_ok=time.time(), last_error="")
            else:
                st["errors"] += 1
                st["last_error"] = err
        if self._on_event:
            self._on_event("llm", provider=pid, ok=ok, purpose=purpose, error=err,
                           latency=round(resp.latency, 2) if resp else None, model=resp.model if resp else None, busy=self.busy)

    def _call(self, fn: Callable[[LLMClient], Tuple[Any, LLMResponse]], purpose: str) -> Tuple[Any, LLMResponse]:
        cli = self.client()
        with self._lock:
            self.busy += 1
        if self._on_event:
            self._on_event("llm", provider=cli.pid, ok=None, purpose=purpose, busy=self.busy)
        try:
            out, resp = fn(cli)
            self._track(cli.pid, True, resp, purpose=purpose)
            return out, resp
        except LLMError as e:
            self._track(cli.pid, False, None, err=str(e), purpose=purpose)
            raise
        finally:
            with self._lock:
                self.busy -= 1

    def chat(self, messages: List[Dict[str, str]], purpose: str = "chat", **kw) -> LLMResponse:
        def go(c: LLMClient):
            r = c.chat(messages, **kw)
            return r.text, r
        return self._call(go, purpose)[1]

    def chat_json(self, messages: List[Dict[str, str]], purpose: str = "reason", **kw) -> Any:
        return self._call(lambda c: c.chat_json(messages, **kw), purpose)[0]

    def discover(self, pid: str, api_key: str = "", base_url: str = "", account_id: str = "",
                 gateway_id: str = "") -> List[Dict[str, Any]]:
        return self.client(pid, api_key=api_key, base_url=base_url, account_id=account_id,
                           gateway_id=gateway_id).list_models()

    def ping(self, pid: Optional[str] = None) -> Dict[str, Any]:
        cli = self.client(pid)
        try:
            r = cli.chat([{"role": "user", "content": "Reply with exactly: OK"}], temperature=0, max_tokens=16, retries=0)
            return {"ok": True, "provider": cli.pid, "model": r.model, "latency": round(r.latency, 2)}
        except LLMError as e:
            return {"ok": False, "provider": cli.pid, "model": cli.model, "error": str(e)}

    @property
    def configured(self) -> bool:
        c = self.provider_config(self.active_provider())
        pid = self.active_provider()
        return (bool(c["api_key"]) and bool(c["account_id"])) if pid == "cloudflare" else (
            bool(c["api_key"]) or pid == "openai"
        )
