import json
from pathlib import Path

import pytest

from cthulu.config.wizard import run_setup_wizard


def test_run_setup_wizard_skips_setup_and_returns_existing_config(tmp_path, monkeypatch, capsys):
    cfg_path = tmp_path / "config.json"
    cfg_data = {"trading": {"symbol": "EURUSD"}}
    cfg_path.write_text(json.dumps(cfg_data))

    # Simulate user choosing not to run interactive setup
    monkeypatch.setattr('cthulu.config.wizard.get_input', lambda prompt, default="": "n")

    res = run_setup_wizard(str(cfg_path))
    assert res == cfg_data

    captured = capsys.readouterr()
    assert "Starting Cthulu with the existing configuration" in captured.out
    # Ensure the y/n legend message is shown
    assert "Answer 'y' to start a new setup" in captured.out


def test_choose_mindset_accepts_four_choices(monkeypatch, capsys):
    from cthulu.config.wizard import choose_mindset

    # Simulate selecting option 3 (Aggressive)
    monkeypatch.setattr('cthulu.config.wizard.get_input', lambda prompt, default="": "3")
    res = choose_mindset()
    assert res == 'aggressive'




