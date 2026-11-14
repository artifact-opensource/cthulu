import json

from legacy_bridge import canonical_agent_symbol, latest_legacy_context, publish_legacy_context


def test_legacy_analysis_is_shared_between_processes(tmp_path, monkeypatch):
    database = tmp_path / "bridge.sqlite"
    monkeypatch.setenv("CTHULU_AGENT_BRIDGE_DB", str(database))
    publish_legacy_context(
        "GOLDm#",
        "M5",
        bar={"close": 2400.5},
        indicators={"rsi": 62.5, "atr": 8.0},
        signal={"direction": "buy", "confidence": 0.8},
        regime="trending",
        strategy="momentum_breakout",
        score=0.76,
    )

    rows = latest_legacy_context()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "GOLDm#"
    assert rows[0]["signal"]["direction"] == "buy"
    assert rows[0]["indicators"] == {"rsi": 62.5, "atr": 8.0}
    assert json.loads(json.dumps(rows[0]))["score"] == 0.76


def test_missing_legacy_database_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setenv("CTHULU_AGENT_BRIDGE_DB", str(tmp_path / "missing.sqlite"))
    assert latest_legacy_context() == []


def test_legacy_broker_symbols_map_to_agent_watchlist_symbols():
    assert canonical_agent_symbol("GOLDm#") == "XAUUSD"
    assert canonical_agent_symbol("BTCUSD#") == "BTCUSD"
    assert canonical_agent_symbol("OILCASH") == "WTI"
