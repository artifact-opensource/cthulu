import json

from config_schema import Config


def test_load_parses_quoted_env_values(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({
        "mt5": {
            "login": "${MT5_LOGIN}",
            "password": "${MT5_PASSWORD}",
            "server": "${MT5_SERVER}",
        },
        "risk": {},
        "trading": {},
        "strategy": {},
    }))
    (tmp_path / ".env").write_text(
        'MT5_LOGIN=123456\n'
        'MT5_PASSWORD="test password"\n'
        'MT5_SERVER="Demo Server With Spaces"\n'
    )
    for name in ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER"):
        monkeypatch.delenv(name, raising=False)

    config = Config.load(str(config_path))

    assert config.mt5.login == 123456
    assert config.mt5.password == "test password"
    assert config.mt5.server == "Demo Server With Spaces"
