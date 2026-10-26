# Vector Studio Adapter — Integration Guide

This doc explains how `cthulu.integrations.VectorStudioAdapter` connects to Vector Studio (`pyvdb`) and the fallback behavior.

## Behavior
- Connects to pyvdb on `connect()`.
- If pyvdb is unavailable and `fallback_on_failure=True`, it initializes a SQLite fallback at `./data/vector_fallback.db` with tables `vector_queue` and `semantic_cache`.
- Supports `async_writes`: writes are put into a local queue and a background thread flushes to pyvdb or fallback.

## Configuration (example)
```yaml
vector_studio:
  enabled: true
  database_path: ./vectors/cthulu
  dimension: 512
  hnsw_m: 16
  hnsw_ef_construction: 200
  hnsw_ef_search: 50
  async_writes: true
  fallback_on_failure: true
```

## Operational notes
- Monitor `vector_studio` adapter metrics: `using_fallback`, `queue_size`, `pending_sync`.
- Use `scripts/async_ingest_worker.py` to process fallback queue for bulk sync and to perform retries.
- Use `scripts/backfill_vectors.py` for historical backfills (dry-run first).
