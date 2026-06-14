#!/usr/bin/env python3
import sqlite3
conn = sqlite3.connect('cthulu.db')
c = conn.cursor()
c.execute('SELECT id, signal_id, order_id, symbol, side, volume, entry_price, entry_time, status FROM trades WHERE order_id = ?', (495264958,))
rows = c.fetchall()
print('rows:', rows)
conn.close()



