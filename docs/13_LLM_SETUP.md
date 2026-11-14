---
title: LLM SETUP
description: Configuration of the separate legacy auto_tune LLM endpoint
tags: [llm, ai, auto_tune, integration]
sidebar_position: 13
---

# LLM integration for `auto_tune`

> **Scope:** This page documents the separate Legacy `auto_tune` integration and its `LLM_ENDPOINT` / `LLM_API_KEY` settings. It does not configure the Agent's trading model. Configure the Agent through the first-run wizard or Agent Settings using Cloudflare AI Gateway; see the [Quick Start](02_QUICKSTART.md) and [Agent guide](../cthulu_agent/README.md).

## Environment variables

- `LLM_ENDPOINT`: HTTP endpoint that accepts a JSON payload such as `{ "prompt": "..." }` and returns JSON with a `text` or `response` field.
- `LLM_API_KEY`: Optional API key sent in the `Authorization: Bearer <key>` header.

## Supported endpoint patterns

1. **Remote provider:** Set `LLM_ENDPOINT` to an endpoint or proxy that implements the JSON request/response shape above.
2. **Local HTTP wrapper:** Run a local server that exposes the same interface.

If `LLM_ENDPOINT` is not configured, the auto-tune summarizer uses a deterministic local fallback to produce an `ai_summary`. This is not equivalent to a real LLM.

Treat `LLM_API_KEY` as a secret. Do not commit it to Git, and monitor provider costs and rate limits.
