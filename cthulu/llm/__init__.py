"""Local LLM package interface.

Expose convenience functions for determining availability and summarization.
"""
from .local_llm import available, summarize, deterministic_fallback, LocalLLM

__all__ = ["available", "summarize", "deterministic_fallback", "LocalLLM"]
