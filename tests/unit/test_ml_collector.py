import os
import time
import glob
from cthulu.ML_RL.instrumentation import MLDataCollector


def test_ml_collector_non_blocking(tmp_path):
    # Use a unique prefix per test to avoid collisions
    prefix = f"test_{int(time.time())}_{os.getpid()}"
    collector = MLDataCollector(prefix=prefix, rotate_size_bytes=1000)

    # Record many events quickly
    for i in range(200):
        collector.record_event('test', {'i': i})

    # Close to ensure flush
    collector.close(timeout=2.0)

    base = os.path.join(os.path.dirname(__import__('cthulu.ML_RL.instrumentation', fromlist=['']).__file__), 'data', 'raw')
    pattern = os.path.join(base, f"{prefix}*.jsonl*")
    files = glob.glob(pattern)

    assert files, "No output files created by MLDataCollector"

    # Read a sample line from files
    found = False
    for p in files:
        try:
            if p.endswith('.gz'):
                import gzip, json
                with gzip.open(p, 'rt', encoding='utf-8') as fh:
                    for line in fh:
                        if line.strip():
                            obj = json.loads(line)
                            assert obj['event_type'] == 'test'
                            found = True
                            break
            else:
                import json
                with open(p, 'r', encoding='utf-8') as fh:
                    for line in fh:
                        if line.strip():
                            obj = json.loads(line)
                            assert obj['event_type'] == 'test'
                            found = True
                            break
        except Exception:
            continue
    assert found, "No valid JSON events found in ML output files"

    # Cleanup
    for p in files:
        try:
            os.remove(p)
        except Exception:
            pass





