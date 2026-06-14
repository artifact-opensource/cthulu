from cthulu.news.tradingeconomics_adapter import TradingEconomicsAdapter


def test_no_key_returns_empty():
    a = TradingEconomicsAdapter(api_key=None)
    assert a.fetch_recent() == []


def test_parses_calendar(monkeypatch):
    sample = [
        {'country': 'US', 'event': 'GDP Release', 'date': '2025-12-01', 'importance': 'High'}
    ]

    class DummyResp:
        def __init__(self, json_data):
            self._json = json_data

        def raise_for_status(self):
            return None

        def json(self):
            return self._json

    def fake_get(url, params=None, timeout=None):
        return DummyResp(sample)

    monkeypatch.setattr('herald.news.tradingeconomics_adapter.requests.get', fake_get)
    a = TradingEconomicsAdapter(api_key='KEY')
    evs = a.fetch_recent()
    assert isinstance(evs, list) and evs
    ev = evs[0]
    assert ev.provider == 'TradingEconomics'
    assert 'US' == ev.symbol
    assert ev.meta.get('importance') == 'high'




