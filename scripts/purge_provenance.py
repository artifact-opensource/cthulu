#!/usr/bin/env python3
"""CLI to purge old provenance rows from DB."""
import argparse
from cthulu.persistence.database import Database


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--db', default='cthulu.db', help='Path to DB file')
    p.add_argument('--days', type=int, required=True, help='Delete rows older than DAYS days')
    args = p.parse_args()

    db = Database(args.db)
    deleted = db.purge_provenance_older_than(args.days)
    print(f"Purged {deleted} provenance rows older than {args.days} days")

if __name__ == '__main__':
    main()




