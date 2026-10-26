# Mindset Profiles

This directory stores per-mindset configuration profiles organized by timeframe.

Structure:

- `configs/mindsets/<mindset>/config_<mindset>_<suffix>.json`

Suffix mapping:
- `m1`, `m5`, `m15`, `m30`, `h1`, `h4`, `d1`, `w1`, `mn1`

Guidelines:
- Keep sensitive MT5 credentials in `.env` and use `FROM_ENV` placeholders in these files.
- Use `--mindset <name>` and `--config <path>` or the `scripts/run_Cthulu_multi_tf.ps1` helper to run multiple timeframes.




