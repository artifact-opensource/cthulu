import sqlite3,sys
try:
    conn=sqlite3.connect('cthulu.db',timeout=5)
    cur=conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS __repo_write_test(id INTEGER PRIMARY KEY)")
    cur.execute("INSERT INTO __repo_write_test DEFAULT VALUES")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM __repo_write_test")
    print('Insert OK, count=', cur.fetchone()[0])
    cur.execute("DELETE FROM __repo_write_test")
    conn.commit()
    conn.close()
except Exception as e:
    print('ERROR:', e)
    sys.exit(1)
