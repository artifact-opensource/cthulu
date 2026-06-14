"""Local LLM wrapper with optional llama-cpp integration.

This module provides a small, well-contained interface for running a local
llama.cpp-backed model (via the `llama_cpp` Python package) when available.
If not available, or if no model file is found, it exposes a safe deterministic
fallback summary generator used for tests and CI.

Design goals:
- Non-invasive: importing this module when dependencies are missing should not
  raise exceptions.
- Lazy-loading: only attempt to load heavy model when `summarize()` is called
  and availability is requested.
- Configurable via env var `LLM_LOCAL_MODEL_PATH` if you want a custom model
  path; otherwise, check the canonical locations provided by the repo.
"""
from __future__ import annotations

import os
import glob
import logging
from typing import Optional

log = logging.getLogger("cthulu.llm.local")

# Candidate model directories (prioritised). Default preference is llama-cpp (gguf/ggml), but
# can be overridden by setting LLM_PREFERRED to 'cthulu' to prefer the training output dir.
_LLM_PREFERRED = os.environ.get('LLM_PREFERRED', '').lower()
if _LLM_PREFERRED == 'cthulu':
    _CANDIDATE_DIRS = [r"C:\workspace\models\cthulu", r"C:\workspace\models\llama-cpp"]
else:
    _CANDIDATE_DIRS = [r"C:\workspace\models\llama-cpp", r"C:\workspace\models\cthulu"]

# Model file patterns - include .gguf for gguf models
_MODEL_EXTS = ("*.gguf", "*.ggml*", "*.bin", "*.pth", "*.pt")

# Lazy imports
_llama_available = False
_Llama = None


def _discover_model_path() -> Optional[str]:
    """Discover a model file path from env var or candidate dirs.

    Returns first discovered model file path or None.
    """
    env_path = os.environ.get("LLM_LOCAL_MODEL_PATH")
    if env_path:
        # If env var points to a directory, search inside, else accept path if exists
        if os.path.isdir(env_path):
            for ext in _MODEL_EXTS:
                matches = glob.glob(os.path.join(env_path, ext))
                if matches:
                    return matches[0]
            return None
        elif os.path.isfile(env_path):
            return env_path
        else:
            log.debug("LLM_LOCAL_MODEL_PATH set but path does not exist: %s", env_path)
            return None

    for d in _CANDIDATE_DIRS:
        if not os.path.isdir(d):
            continue
        for ext in _MODEL_EXTS:
            matches = glob.glob(os.path.join(d, ext))
            if matches:
                return matches[0]
    return None


class LocalLLM:
    """Lightweight wrapper to interact with local llama.cpp models.

    Example usage:
        llm = LocalLLM()
        if llm.is_available():
            text = llm.summarize(prompt)
        else:
            fallback = deterministic_fallback(prompt)
    """

    def __init__(self):
        self._model_path: Optional[str] = _discover_model_path()
        self._loaded = False
        self._client = None

    def is_available(self) -> bool:
        """Return True if we have both a model file and a usable backend."""
        if not self._model_path:
            return False
        # Try import only when asked to avoid hard dependency
        global _llama_available, _Llama
        if _llama_available:
            return True
        try:
            from llama_cpp import Llama  # type: ignore
            _Llama = Llama
            _llama_available = True
            return True
        except Exception as e:  # ImportError or runtime errors
            log.debug("llama_cpp backend not available: %s", e)
            _llama_available = False
            return False

    def _ensure_loaded(self) -> bool:
        if self._loaded:
            return True
        if not self.is_available():
            return False
        try:
            # Llama client takes model parameter as path to model file
            self._client = _Llama(model=str(self._model_path))
            self._loaded = True
            log.info("Loaded local LLM model: %s", self._model_path)
            return True
        except Exception as e:
            log.error("Failed to load local LLM model %s: %s", self._model_path, e)
            self._loaded = False
            return False

    def summarize(self, prompt: str, max_tokens: int = 256, **kwargs) -> str:
        """Return model-generated text summary for given prompt.

        On failure, raises RuntimeError to let callers fallback gracefully.
        """
        if not self._ensure_loaded():
            raise RuntimeError("Local LLM not available or failed to load")

        try:
            # llama_cpp's Llama uses .create() to generate text
            resp = self._client.create(prompt=prompt, max_tokens=max_tokens, **kwargs)
            # Response format may vary; attempt to extract text robustly
            if isinstance(resp, dict):
                text = resp.get("text") or resp.get("response")
            else:
                text = getattr(resp, "text", None)
            return text or str(resp)
        except Exception as e:
            log.error("Local LLM generation failed: %s", e)
            raise


def deterministic_fallback(prompt: str) -> str:
    """Deterministic local summary used as fallback in tests/CI."""
    snippet = prompt[:200] + ("..." if len(prompt) > 200 else "")
    return "[Local fallback summary] " + snippet


# Module-level convenience functions
_default_llm = LocalLLM()


def available() -> bool:
    return _default_llm.is_available()


def summarize(prompt: str, max_tokens: int = 256) -> str:
    """Try to summarize with local LLM, else return deterministic fallback."""
    try:
        if _default_llm.is_available():
            return _default_llm.summarize(prompt, max_tokens=max_tokens)
    except Exception as e:
        log.warning("Local LLM call failed: %s", e)
    return deterministic_fallback(prompt)
