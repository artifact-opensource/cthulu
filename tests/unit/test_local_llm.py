import os
from cthulu.llm import local_llm


def test_deterministic_fallback():
    prompt = "This is a test prompt"
    out = local_llm.deterministic_fallback(prompt)
    assert out.startswith("[Local fallback summary]")


def test_available_false_when_no_model(monkeypatch):
    # Force environment to empty and ensure no model dir exists
    monkeypatch.delenv('LLM_LOCAL_MODEL_PATH', raising=False)
    # Temporarily set candidate dirs to non-existent
    monkeypatch.setattr(local_llm, '_CANDIDATE_DIRS', [r"C:\nonexistent\12345"])
    assert not local_llm.available()


def test_summarize_uses_fallback_when_unavailable(monkeypatch):
    monkeypatch.setattr(local_llm, '_CANDIDATE_DIRS', [r"C:\nonexistent\12345"])
    res = local_llm.summarize("hello world")
    assert res.startswith("[Local fallback summary]")
