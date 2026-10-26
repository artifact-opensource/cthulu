import argparse

from cthulu.__main__ import init_ml_collector


class FakeLogger:
    def info(self, *a, **k):
        pass
    def exception(self, *a, **k):
        pass


def test_ml_enabled_by_config():
    args = argparse.Namespace(enable_ml=None)
    config = {'ml': {'enabled': True, 'prefix': 't'}}
    ml = init_ml_collector(config, args, FakeLogger())
    assert ml is not None


def test_ml_disabled_by_config_but_enabled_by_cli():
    args = argparse.Namespace(enable_ml=True)
    config = {'ml': {'enabled': False, 'prefix': 't'}}
    ml = init_ml_collector(config, args, FakeLogger())
    assert ml is not None


def test_ml_disabled_by_cli():
    args = argparse.Namespace(enable_ml=False)
    config = {'ml': {'enabled': True, 'prefix': 't'}}
    ml = init_ml_collector(config, args, FakeLogger())
    assert ml is None




