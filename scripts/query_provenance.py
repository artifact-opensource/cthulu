#!/usr/bin/env python3
"""CLI to query recent order provenance rows."""
import argparse
import json
from cthulu.persistence.database import Database


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='cthulu.db', help='Path to DB file')
    p.add_argument('--limit', type=int, default=50)
    args = p.parse_args()

    db = Database(args.db)
    rows = db.get_recent_provenance(limit=args.limit)
    for r in rows:
        print(json.dumps(r, indent=2, default=str))

if __name__ == '__main__':
    main()




