import sqlite3
import sys

try:
    conn = sqlite3.connect('cthulu.db', timeout=5)
    c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS __perm_test(id INTEGER PRIMARY KEY)')
    c.execute('INSERT INTO __perm_test DEFAULT VALUES')
    conn.commit()
    print('Insert OK')
    # cleanup
    c.execute('DELETE FROM __perm_test')
    conn.commit()
    conn.close()
except Exception as e:
    print('ERROR', e)
    sys.exit(1)
