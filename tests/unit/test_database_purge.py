import pytest
from datetime import datetime, timedelta

from cthulu.persistence.database import Database


def test_purge_provenance_older_than(tmp_path):
    db_path = tmp_path / "test_cthulu.db"
    db = Database(str(db_path))

    # Insert two provenance rows: one old, one recent
    old_ts = (datetime.utcnow() - timedelta(days=10)).isoformat() + 'Z'
    recent_ts = datetime.utcnow().isoformat() + 'Z'

    old_id = db.record_provenance({'timestamp': old_ts, 'signal_id': 'old', 'client_tag': 'c', 'symbol': 'EURUSD', 'side': 'BUY', 'volume': 0.01})
    new_id = db.record_provenance({'timestamp': recent_ts, 'signal_id': 'new', 'client_tag': 'c2', 'symbol': 'EURUSD', 'side': 'SELL', 'volume': 0.01})

    assert old_id > 0 and new_id > 0

    deleted = db.purge_provenance_older_than(7)

    assert deleted >= 1

    remaining = db.get_recent_provenance(limit=10)
    ids = [r['id'] for r in remaining]
    assert new_id in ids
    assert old_id not in ids




