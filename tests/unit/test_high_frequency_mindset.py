import json
from types import SimpleNamespace

from config.mindsets import apply_mindset
from config_schema import Config
from core.bootstrap import CthuluBootstrap
from core.strategy_factory import StrategyFactory
from core.trading_loop import TradingLoop


def test_high_frequency_profile_scales_risk_and_caps_active_positions():
    config = apply_mindset(
        {
            "risk": {
                "max_lot_size": 1.0,
                "max_positions_per_symbol": 10,
                "max_total_positions": 10,
                "max_daily_trades": 50,
            },
            "trading": {
                "symbol": "GOLD",
                "timeframe": "TIMEFRAME_H1",
                "poll_interval": 60,
                "min_trade_interval": 120,
            },
        },
        "high_frequency",
    )

    assert config["risk"]["max_lot_size"] == 100.0
    assert config["risk"]["default_position_size"] == 0.01
    assert config["risk"]["max_position_size_pct"] == 0.01
    assert config["risk"]["max_aggregate_open_risk_pct"] == 5.0
    assert config["risk"]["max_positions_per_symbol"] == 2
    assert config["risk"]["max_total_positions"] == 10
    assert config["risk"]["max_daily_loss_pct"] == 4.0
    assert config["risk"]["drawdown_halt_percent"] == 15.0
    assert config["risk"]["max_daily_trades"] == 1000
    assert config["strategy"]["type"] == "scalping"
    assert config["strategy"]["params"]["fast_ema"] == 5
    assert config["strategy"]["params"]["slow_ema"] == 10
    assert config["trading"]["symbol"] == "GOLD"
    assert config["trading"]["timeframe"] == "TIMEFRAME_M1"
    assert config["trading"]["poll_interval"] == 5
    assert config["trading"]["min_trade_interval"] == 0


def test_high_frequency_profile_emits_scalping_signal_on_ema_cross():
    config = apply_mindset(
        {"strategy": {"type": "dynamic", "params": {}, "strategies": []}},
        "high_frequency",
    )
    strategy = StrategyFactory().create(config["strategy"])

    import pandas as pd

    strategy.on_bar(
        pd.Series(
            {
                "ema_5": 100.0,
                "ema_10": 100.0,
                "rsi": 50.0,
                "rsi_7": 50.0,
                "atr": 1.0,
                "close": 100.0,
            }
        )
    )
    signal = strategy.on_bar(
        pd.Series(
            {
                "ema_5": 101.0,
                "ema_10": 100.0,
                "rsi": 50.0,
                "rsi_7": 50.0,
                "atr": 1.0,
                "close": 101.0,
            }
        )
    )

    assert signal is not None
    assert signal.side.name == "LONG"


def test_high_frequency_limits_survive_schema_and_reach_risk_manager():
    config = Config.model_validate(
        {
            "mt5": {"login": 1, "password": "test", "server": "test"},
            "strategy": {"type": "sma_crossover", "params": {}},
            "risk": {
                "max_lot_size": 0.02,
                "max_daily_trades": 1000,
                "max_positions_per_symbol": 50,
                "max_total_positions": 100,
            },
            "trading": {
                "symbol": "GOLD",
                "timeframe": "TIMEFRAME_M1",
                "poll_interval": 5,
                "min_trade_interval": 0,
            },
        }
    )
    config_dict = config.model_dump()
    limits = CthuluBootstrap().initialize_risk_manager(config_dict)

    assert limits.max_lot_size == 0.02
    assert limits.max_positions_per_symbol == 50
    assert limits.max_total_positions == 100
    assert limits.max_daily_trades == 1000
    assert config_dict["trading"]["min_trade_interval"] == 0


def test_installer_risk_limits_override_mindset_presets(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "mt5": {"login": 1, "password": "test", "server": "test"},
                "risk": {},
                "trading": {"symbol": "EURUSD", "timeframe": "TIMEFRAME_H1"},
                "strategy": {"type": "sma_crossover", "params": {}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CTHULU_LEGACY_MAX_POSITION_SIZE_PCT", "0.005")
    monkeypatch.setenv("CTHULU_LEGACY_MAX_DAILY_LOSS_PCT", "0.02")
    monkeypatch.setenv("CTHULU_LEGACY_DRAWDOWN_HALT_PERCENT", "10")
    monkeypatch.setenv("CTHULU_LEGACY_MAX_POSITIONS_PER_SYMBOL", "3")
    monkeypatch.setenv("CTHULU_LEGACY_MAX_TOTAL_POSITIONS", "3")

    config = CthuluBootstrap().load_configuration(str(config_path), mindset="high_frequency")

    assert config["risk"]["max_position_size_pct"] == 0.005
    assert config["risk"]["max_daily_loss_pct"] == 0.02
    assert config["risk"]["drawdown_halt_percent"] == 10
    assert config["risk"]["max_positions_per_symbol"] == 3
    assert config["risk"]["max_total_positions"] == 3


def test_trading_loop_uses_nested_high_frequency_cooldown():
    loop = TradingLoop(
        SimpleNamespace(
            config={"trading": {"min_trade_interval": 0}, "watchlist": []},
            logger=SimpleNamespace(info=lambda *args: None),
        )
    )

    assert loop._min_trade_interval_seconds == 0
