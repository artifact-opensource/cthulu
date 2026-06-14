from persistence.database import Database
import sqlite3
print('Using Database class...')
db = Database()
print('DB path:', db.db_path)
ok = db.save_position(999999, 'TESTSYM', 'buy', 0.01, 1.2345, current_price=1.2345, sl=1.2, tp=1.4)
print('save_position returned', ok)
# Clean up test record
conn = sqlite3.connect(str(db.db_path))
c = conn.cursor()
c.execute("DELETE FROM positions WHERE ticket=?", (999999,))
conn.commit()
conn.close()
print('cleanup done')
