import MetaTrader5 as mt5

from cthulu.__main__ import normalize_timeframe


def test_normalize_timeframe_accepts_bare_name():
    assert normalize_timeframe("H1") == mt5.TIMEFRAME_H1


def test_normalize_timeframe_accepts_prefixed_name():
    assert normalize_timeframe("TIMEFRAME_M15") == mt5.TIMEFRAME_M15


def test_normalize_timeframe_preserves_non_string_values():
    assert normalize_timeframe(mt5.TIMEFRAME_H1) == mt5.TIMEFRAME_H1
