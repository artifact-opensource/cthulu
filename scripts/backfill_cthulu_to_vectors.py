#!/usr/bin/env python3
"""Wrapper that uses Cthulu's Database to perform a backfill into pyvdb (dry-run by default)."""

from cthulu.persistence.database import Database
import argparse
import json

p = argparse.ArgumentParser()
p.add_argument('--cthulu-db', default='herald.db')
p.add_argument('--apply', action='store_true')
args = p.parse_args()

db = Database(args.cthulu_db)

# Example: pull recent provenance rows and print samples
rows = db.get_recent_provenance(limit=10)
print('Sample provenance rows:')
for r in rows:
    print(r['id'], r['timestamp'], r['signal_id'])

if not args.apply:
    print('Dry-run only. Use --apply to push to vectors via pyvdb or scripts/backfill_vectors.py')
