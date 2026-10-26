---
title: LLM AUTO-TUNE
description: Configuration and usage of LLM endpoints for AI-assisted summarization and PR generation in the Cthulu trading system
tags: [llm, ai, auto_tune, integration]
sidebar_position: 13
version: 6.0.0
---

![](https://img.shields.io/badge/Version-6.0.0-4B0082?style=for-the-badge&labelColor=0D1117)
![Last Update](https://img.shields.io/badge/Last_Update-2026--01--06-4B0082?style=for-the-badge&labelColor=0D1117&logo=calendar)
![](https://img.shields.io/github/last-commit/amuzetnoM/cthulu?style=for-the-badge&labelColor=0D1117&logo=github&logoColor=white)

# LLM integration for auto_tune

This document explains how to configure an LLM endpoint for AI-assisted summarization and PR generation.

Environment variables (recommended):

- LLM_ENDPOINT: URL of an HTTP endpoint that accepts JSON payload `{ "prompt": "..." }` and returns JSON with `text` or `response` field.
- LLM_API_KEY: API key (optional) to pass in `Authorization: Bearer <key>` header.

Supported modes:

1. Remote provider (OpenAI-compatible): set `LLM_ENDPOINT` to your proxy or provider URL. Example: `https://api.example.com/v1/generate`
2. Local HTTP wrapper: run a local server that exposes a simple JSON API compatible with the above payload. Projects like `gpt4all-web` or a simple FastAPI wrapper around `llama.cpp`-style models can be used.

Fallback:

- If no `LLM_ENDPOINT` is configured, the auto-tune summarizer uses a deterministic local fallback summary so the pipeline still produces an `ai_summary` field. This is *not* equivalent to a real LLM but avoids blocking automation.

Security and costs:

- Treat `LLM_API_KEY` as a secret. Do not commit it to Git.
- Monitor and rate-limit calls when enabling expensive (paid) providers.

Next steps to fully enable cloud/local LLMs:

- Provide a tested endpoint that adheres to the simple JSON shape.
- Update CI to avoid leaking keys and to gate production auto-apply flows when an LLM is in use (optional).
