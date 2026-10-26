"""
Simple DB health check script used by CI / deployment to validate DB writability.
Usage: python scripts/db_health_check.py --db cthulu.db
Exit code 0 on success, 1 on failure.
"""
import argparse
import sqlite3
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--db', default='cthulu.db')
args = parser.parse_args()

def main():
    try:
        conn = sqlite3.connect(args.db, timeout=5)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS __health_check(id INTEGER PRIMARY KEY)")
        cur.execute("INSERT INTO __health_check DEFAULT VALUES")
        conn.commit()
        cur.execute("DELETE FROM __health_check")
        conn.commit()
        conn.close()
        print('DB write check: OK')
        return 0
    except Exception as e:
        print('DB write check FAILED:', e)
        return 1

if __name__ == '__main__':
    sys.exit(main())
