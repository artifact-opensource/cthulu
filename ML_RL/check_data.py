"""Check all available training data sources."""
import sqlite3
import os
import glob
import gzip
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("CTHULU DATA INVENTORY")
print("=" * 60)

# Check databases
print("\n[DATABASES]")
dbs = ['cthulu.db', 'cthulu_balanced.db', 'cthulu_aggressive.db', 
       'cthulu_conservative.db', 'Cthulu_ultra_aggressive.db', 'data/herald.db']
for db in dbs:
    db_path = os.path.join(BASE_DIR, db)
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            size_mb = os.path.getsize(db_path) / (1024*1024)
            print(f"\n{db} ({size_mb:.2f} MB):")
            for table in tables:
                cursor.execute(f'SELECT COUNT(*) FROM "{table[0]}"')
                count = cursor.fetchone()[0]
                print(f"  {table[0]}: {count} rows")
            conn.close()
        except Exception as e:
            print(f"  Error: {e}")

# Check JSONL event files
print("\n\n[JSONL EVENT FILES]")
raw_dir = os.path.join(BASE_DIR, 'ML_RL', 'data', 'raw')
if os.path.exists(raw_dir):
    files = glob.glob(os.path.join(raw_dir, '*.jsonl.gz'))
    total_events = 0
    event_types = {}
    for f in files[:10]:  # Sample first 10
        try:
            with gzip.open(f, 'rt') as fp:
                for line in fp:
                    event = json.loads(line.strip())
                    et = event.get('event_type', 'unknown')
                    event_types[et] = event_types.get(et, 0) + 1
                    total_events += 1
        except:
            pass
    print(f"Total files: {len(files)}")
    print(f"Sample events (first 10 files): {total_events}")
    print("Event types:")
    for et, count in sorted(event_types.items()):
        print(f"  {et}: {count}")

# Check CSV files
print("\n\n[CSV FILES]")
csv_files = glob.glob(os.path.join(BASE_DIR, '**', '*.csv'), recursive=True)
for f in csv_files:
    size_kb = os.path.getsize(f) / 1024
    rel_path = os.path.relpath(f, BASE_DIR)
    print(f"  {rel_path}: {size_kb:.1f} KB")

# Check backtesting reports
print("\n\n[BACKTESTING REPORTS]")
bt_reports = glob.glob(os.path.join(BASE_DIR, 'backtesting', 'reports', '*.json'))
for f in bt_reports:
    rel_path = os.path.relpath(f, BASE_DIR)
    print(f"  {rel_path}")

print("\n" + "=" * 60)
