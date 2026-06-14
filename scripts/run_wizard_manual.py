#!/usr/bin/env python3
"""Run the interactive setup wizard (manual selection) and then start Cthulu.

Usage: python scripts/run_wizard_manual.py
This script intentionally runs the interactive wizard, allowing the operator to
answer prompts. When the wizard completes it will start Cthulu with
`--skip-setup` so the runtime does not re-run the wizard.
"""
import traceback
import subprocess
import sys
import pathlib
import os

# Ensure the repository root is on sys.path so top-level imports like `config` succeed
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(script_dir, '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Prepare environment for subprocesses so they inherit PYTHONPATH
_sub_env = os.environ.copy()
_sub_env['PYTHONPATH'] = project_root + (os.pathsep + _sub_env.get('PYTHONPATH', '')) if project_root else _sub_env.get('PYTHONPATH', '')

try:
    # Import the interactive wizard and run it (do NOT override get_input)
    from config.wizard import run_setup_wizard

    cfg = run_setup_wizard('config.json')

    print('\n--- WIZARD COMPLETE ---')
    if cfg is None:
        print('Wizard returned None or was cancelled by user. Exiting.')
        sys.exit(1)

    # Report summary
    print('Config keys:', list(cfg.keys()))
    p = pathlib.Path('config.json')
    print('config.json exists?', p.exists())
    if p.exists():
        print('Size', p.stat().st_size)
        print('\nPreview:\n' + p.read_text()[:400])

    # Start Cthulu (skip setup so it doesn't prompt again)
    print('\nStarting Cthulu (skip setup, live mode)...')
    cmd = [sys.executable, '-m', 'cthulu', '--config', 'config.json', '--skip-setup']
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f'Cthulu exited with code {rc}')
        sys.exit(rc)

except KeyboardInterrupt:
    print('\nWizard cancelled by user (KeyboardInterrupt).')
    sys.exit(1)
except Exception:
    traceback.print_exc()
    sys.exit(1)
