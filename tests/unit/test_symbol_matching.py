"""
Tests for MT5 symbol matching behavior.

Note: Per REFACTORING_SUMMARY.md (2026-01-16), complex symbol matching was
intentionally simplified. The system now requires exact broker symbol names.

Old behavior (removed):
- 4-stage matching with prefix, suffix swapping, substring matching
- Auto-variant handling (GOLD → GOLDm#)

New behavior (current):
- 2-stage matching: exact normalized match + exact case-sensitive fallback
- Users must specify exact broker symbol name from MT5 Market Watch
"""

from types import SimpleNamespace
import cthulu.connector.mt5_connector as m5


class _FakeSymbol:
    def __init__(self, name):
        self.name = name


def test_find_matching_symbol_exact_match(monkeypatch):
    """Test that exact symbol names are matched correctly."""
    symbols = [_FakeSymbol('GOLDm#'), _FakeSymbol('Goldman Sachs'), _FakeSymbol('EURUSD')]

    monkeypatch.setattr(m5.mt5, 'symbols_get', lambda: symbols)

    conn = m5.MT5Connector.__new__(m5.MT5Connector)
    
    # Exact match should work
    matches = conn._find_matching_symbol('GOLDm#')
    assert 'GOLDm#' in matches
    
    # Exact match for another symbol
    matches = conn._find_matching_symbol('EURUSD')
    assert 'EURUSD' in matches


def test_find_matching_symbol_case_insensitive(monkeypatch):
    """Test that matching is case-insensitive for normalized comparison."""
    symbols = [_FakeSymbol('GOLDm#'), _FakeSymbol('EURUSD')]

    monkeypatch.setattr(m5.mt5, 'symbols_get', lambda: symbols)

    conn = m5.MT5Connector.__new__(m5.MT5Connector)
    
    # Lowercase should still match via normalized comparison
    matches = conn._find_matching_symbol('goldm#')
    assert 'GOLDm#' in matches


def test_ensure_symbol_selected_exact_match(monkeypatch):
    """Test that ensure_symbol_selected requires exact symbol name."""
    symbols = [_FakeSymbol('Goldman Sachs'), _FakeSymbol('GOLDm#')]
    monkeypatch.setattr(m5.mt5, 'symbols_get', lambda: symbols)

    # Stub symbol_select to return True for valid symbol
    def symbol_select_stub(s, v):
        return s in ('GOLDm#', 'EURUSD')
    monkeypatch.setattr(m5.mt5, 'symbol_select', symbol_select_stub)

    # Create connector with logger
    conn = m5.MT5Connector.__new__(m5.MT5Connector)
    import logging
    conn.logger = logging.getLogger('test_mt5')
    
    def fake_get_symbol_info(s):
        if s == 'GOLDm#':
            return {'point': 0.01, 'volume_min': 0.1}
        return None
    monkeypatch.setattr(conn, 'get_symbol_info', fake_get_symbol_info)

    # Exact symbol name should work
    selected = conn.ensure_symbol_selected('GOLDm#')
    assert selected == 'GOLDm#'
    
    # Partial name 'GOLD' should NOT auto-resolve (per new simplified behavior)
    # This is the intentional change from the refactoring
    selected = conn.ensure_symbol_selected('GOLD')
    # Returns None because 'GOLD' doesn't match any symbol exactly
    assert selected is None


def test_find_matching_symbol_no_fuzzy_match():
    """
    Test that fuzzy/prefix matching is NOT done (per refactoring).
    
    Old behavior: 'GOLD' would match 'GOLDm#', 'GOLDX', etc.
    New behavior: 'GOLD' only matches 'GOLD' exactly.
    """
    symbols = [_FakeSymbol('GOLDm#'), _FakeSymbol('GOLDX'), _FakeSymbol('GOLDMANSACHS')]

    m5.mt5.symbols_get = lambda: symbols
    conn = m5.MT5Connector.__new__(m5.MT5Connector)

    # 'GOLD' should NOT match 'GOLDm#' or others (no prefix matching)
    matches = conn._find_matching_symbol('GOLD')
    # Empty because 'GOLD' doesn't exist exactly in the list
    assert len(matches) == 0 or 'GOLD' in matches  # Only exact match if present
