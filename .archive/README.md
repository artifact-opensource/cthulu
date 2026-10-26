This directory contains archived development, diagnostic, and one-off scripts that are not part of the production runtime.

Purpose:
- Keep ad-hoc helpers for reproducibility and future debugging without cluttering the main `Cthulu/` tree.
- Files moved here were used during recent live testing and debugging.

Contents:
- scripts/: helper scripts for MT5 connectivity and ad-hoc tests (mt5_check.py, place_external_test_trade.py, etc.)
- tests/: diagnostic test utilities (diag_parser_debug.py, run_parser_prints.py)
- config.json.bak: last config backup moved for reference

Guidelines:
- Do not import from files in this directory in production code.
- If a file becomes useful for long-term maintenance, move it back into `Cthulu/scripts/` or refactor into a well-tested module.
- This folder is intentionally included in repository commits to preserve history but is not used during normal operation.




