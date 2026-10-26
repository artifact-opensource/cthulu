import pandas as pd
import pytest

from data.layer import DataLayer


def test_normalize_rates_sets_time_index_and_caches_copy():
    layer = DataLayer()
    rates = [
        {
            "time": "2026-01-01T00:00:00",
            "open": 1.0,
            "high": 1.2,
            "low": 0.9,
            "close": 1.1,
            "tick_volume": 42,
        }
    ]

    normalized = layer.normalize_rates(rates, symbol="EURUSD")

    assert isinstance(normalized.index, pd.DatetimeIndex)
    assert normalized.index[0] == pd.Timestamp("2026-01-01T00:00:00")
    assert normalized["volume"].tolist() == [42]
    cached = layer.get_cached_data("EURUSD")
    assert cached is not None
    assert cached.equals(normalized)
    cached.iloc[0, 0] = -1
    assert layer.get_cached_data("EURUSD").iloc[0, 0] != -1


def test_normalize_rates_accepts_datetime_index():
    frame = pd.DataFrame(
        {"close": [1.1]},
        index=pd.DatetimeIndex(["2026-01-01T00:00:00"]),
    )

    normalized = DataLayer(cache_enabled=False).normalize_rates(frame)

    assert isinstance(normalized.index, pd.DatetimeIndex)
    assert normalized["close"].tolist() == [1.1]


def test_normalize_rates_requires_time_information():
    with pytest.raises(ValueError, match="time"):
        DataLayer().normalize_rates([{"close": 1.1}])


def test_disabled_cache_returns_no_data():
    layer = DataLayer(cache_enabled=False)
    layer.normalize_rates([{"time": "2026-01-01T00:00:00", "close": 1.1}], "EURUSD")

    assert layer.get_cached_data("EURUSD") is None
