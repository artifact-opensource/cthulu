import os

from cthulu_agent import envfile
from cthulu_agent.__main__ import _ensure_dashboard_token


def test_missing_dashboard_token_is_generated_and_persisted(tmp_path, monkeypatch):
    token_file = tmp_path / ".env.agent"
    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)

    token = _ensure_dashboard_token(token_file)

    assert len(token) >= 40
    assert envfile.read_env(token_file)["DASHBOARD_TOKEN"] == token
    assert _ensure_dashboard_token(token_file) == token


def test_existing_dashboard_token_is_preserved_in_selected_env(tmp_path, monkeypatch):
    token_file = tmp_path / ".env.agent"
    envfile.set_env({"DASHBOARD_TOKEN": "configured-token"}, token_file)
    monkeypatch.setenv("DASHBOARD_TOKEN", "inherited-token")

    assert _ensure_dashboard_token(token_file) == "configured-token"
    assert envfile.read_env(token_file)["DASHBOARD_TOKEN"] == "configured-token"
    assert os.environ["DASHBOARD_TOKEN"] == "configured-token"
