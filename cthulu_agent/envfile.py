"""Safe .env reading/writing. Preserves comments and ordering, writes atomically."""
from __future__ import annotations

import os
import re
import tempfile
import threading
from pathlib import Path
from typing import Dict, Optional

_LOCK = threading.Lock()
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def default_env_path() -> Path:
    override = os.environ.get("CTHULU_ENV_FILE")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / ".env"


def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        inner = v[1:-1]
        if v[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    # strip trailing inline comment for unquoted values
    m = re.search(r"\s+#", v)
    return v[: m.start()].rstrip() if m else v


def _quote(v: str) -> str:
    if v == "" or re.search(r"[\s#\"'\\]", v):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return v


def read_env(path: Optional[Path] = None) -> Dict[str, str]:
    p = Path(path) if path else default_env_path()
    out: Dict[str, str] = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        if s.startswith("export "):
            s = s[7:]
        k, v = s.split("=", 1)
        k = k.strip()
        if _KEY_RE.match(k):
            out[k] = _unquote(v)
    return out


def load_env(path: Optional[Path] = None, override: bool = False) -> int:
    n = 0
    for k, v in read_env(path).items():
        if override or k not in os.environ:
            os.environ[k] = v
            n += 1
    return n


def set_env(updates: Dict[str, Optional[str]], path: Optional[Path] = None) -> None:
    """Write updates into .env (None removes the key) and mirror into os.environ."""
    for k, v in updates.items():
        if not _KEY_RE.match(k):
            raise ValueError(f"invalid env key: {k!r}")
        if v is not None and ("\n" in str(v) or "\r" in str(v) or "\x00" in str(v)):
            raise ValueError(f"invalid characters in value for {k}")
    p = Path(path) if path else default_env_path()
    with _LOCK:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines() if p.exists() else []
        pending = dict(updates)
        out = []
        for line in lines:
            s = line.strip()
            body = s[7:] if s.startswith("export ") else s
            key = body.split("=", 1)[0].strip() if ("=" in body and not s.startswith("#")) else None
            if key in pending:
                val = pending.pop(key)
                if val is not None:
                    out.append(f"{key}={_quote(str(val))}")
                continue
            out.append(line)
        for k, v in pending.items():
            if v is not None:
                out.append(f"{k}={_quote(str(v))}")
        text = "\n".join(out).rstrip("\n") + "\n"
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".env.", dir=str(p.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        for k, v in updates.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = str(v)
