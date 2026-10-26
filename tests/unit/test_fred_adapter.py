import pytest
from cthulu.news.fred_adapter import FREDAdapter
from cthulu.news.base import NewsEvent


class DummyResp:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code != 200:
            raise Exception('bad status')

    def json(self):
        return self._json


def test_no_key_returns_empty():
    a = FREDAdapter(api_key=None)
    assert a.fetch_recent() == []


def test_parses_latest_observation(monkeypatch):
    sample = {
        'observations': [
            {'date': '2025-12-01', 'value': '123.45'}
        ]
    }

    def fake_get(url, params=None, timeout=None):
        return DummyResp(sample)

    monkeypatch.setattr('herald.news.fred_adapter.requests.get', fake_get)
    a = FREDAdapter(api_key='KEY', series=['GDP'])
    evs = a.fetch_recent()
    assert isinstance(evs, list) and evs
    ev = evs[0]
    assert ev.provider == 'FRED'
    assert 'GDP' in ev.symbol
    assert '123.45' in ev.headline




