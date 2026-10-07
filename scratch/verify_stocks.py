import sqlite3

conn = sqlite3.connect("C:/Intel/Database/Shioaji.db")
c = conn.cursor()

c.execute("SELECT code, count(*) FROM stock5k WHERE ts >= '2025-07-01' AND ts <= '2026-09-30' GROUP BY code HAVING count(*) > 5000")
c5 = dict(c.fetchall())

c.execute("SELECT code, count(*) FROM stock60k WHERE ts >= '2025-07-01' AND ts <= '2026-09-30' GROUP BY code HAVING count(*) > 300")
c60 = dict(c.fetchall())

common = set(c5.keys()) & set(c60.keys())
print(f"Total stocks with both deep 5k and 60k: {len(common)}")
sorted_stocks = sorted(list(common), key=lambda x: c5[x], reverse=True)
for s in sorted_stocks[:35]:
    print(f"  {s}: 5k={c5[s]}, 60k={c60[s]}")
conn.close()
