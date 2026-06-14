import sqlite3,sys
try:
    conn=sqlite3.connect('Cthulu.db',timeout=5)
    c=conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS __perm_test(id integer primary key autoincrement, t text)")
    c.execute("INSERT INTO __perm_test(t) VALUES('x')")
    conn.commit()
    c.execute("SELECT COUNT(*) FROM __perm_test")
    print('Insert succeeded, count=',c.fetchone()[0])
    conn.close()
except Exception as e:
    print('PYTHON ERROR:',e)
    sys.exit(1)
