from cthulu.backtesting.scripts.auto_tune_runner import call_llm_for_enhanced_summary


def test_local_fallback_returns_summary():
    prompt = "Test prompt for fallback"
    res = call_llm_for_enhanced_summary(prompt)
    assert isinstance(res, str)
    assert res.startswith("[Local fallback summary]")
