"""データベースを作る、または足りない分だけ足す。scripts/seed.py と scripts/update_db.py が使う。"""
from app.db import connect, initial, schema


def update(path=None) -> dict:
    """無ければ初期の状態で作る。あれば足りない表・列・初期データの行だけ足し、あるデータは消さない。"""
    con = connect(path)
    try:
        added = schema.migrate(con)
        data = initial.build()
        inserted = {}
        for table in schema.TABLES:  # 親の表から順に入れる
            rows = data.get(table, [])
            n = 0
            for row in rows:
                cols = list(row)
                cur = con.execute(
                    f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                    [row[c] for c in cols],
                )
                n += cur.rowcount
            inserted[table] = n
            # 今回足した列には、初期データの行にも値を入れる (足した列だけ。ほかは触らない)
            for t, col in added:
                if t == table:
                    for row in rows:
                        if col in row:
                            con.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?", (row[col], row["id"]))
        # G21d: 見本データの担当者の名前を架空の名前に替える（すでに入っているデータベースにも効かせる）
        for t in schema.TABLES:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            if "staff_name" in cols:
                for old, new in (("大川内", "山本"), ("田中", "佐藤")):
                    con.execute(f"UPDATE {t} SET staff_name = ? WHERE staff_name = ?", (new, old))
        con.commit()
        return {"added_columns": added, "inserted": inserted}
    finally:
        con.close()
