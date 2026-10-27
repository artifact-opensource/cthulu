from types import SimpleNamespace

from config.mindsets import apply_mindset
from core.trading_loop import TradingLoop


def test_ultra_aggressive_profile_uses_m15_and_accepts_enterable_marginal_entries():
    config = apply_mindset({"trading": {}, "entry_confluence": {}}, "ultra_aggressive")
    result = SimpleNamespace(should_enter=True)

    assert config["trading"]["timeframe"] == "TIMEFRAME_M15"
    assert config["entry_confluence"]["allow_marginal_entries"] is True
    assert TradingLoop._should_accept_marginal_entry(config, result)


def test_marginal_entry_override_does_not_accept_rejected_signals():
    config = {"entry_confluence": {"allow_marginal_entries": True}}

    assert not TradingLoop._should_accept_marginal_entry(
        config, SimpleNamespace(should_enter=False)
    )
    assert not TradingLoop._should_accept_marginal_entry(
        {}, SimpleNamespace(should_enter=True)
    )
