"""データベースを作る、または足りない分だけ足す。scripts/seed.py と scripts/update_db.py が使う。"""
from datetime import date

from app.db import connect, dates, db_path, initial, schema
from app.today import BASE


def update(path=None) -> dict:
    """無ければ初期の状態で作る。あれば足りない表・列・初期データの行だけ足し、あるデータは消さない。"""
    con = connect(path, align=False)
    try:
        added = schema.migrate(con)
        # 見本の行は BASE の日付で書いてある。いまのデータベースがすでにずれている分（印、無ければ見本の1行から決める）だけ
        # ずらして足す。足したあと、データベース全体を今日へ合わせる（日付の決まりは app/db/dates.py の1か所）
        mark = dates.get_marker(con) or dates.detect(con)
        data = dates.shift_rows(initial.build(), (date.fromisoformat(mark) - date.fromisoformat(BASE)).days)
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
                if t == table and table != "tooth_status":
                    for row in rows:
                        if col in row:
                            con.execute(f"UPDATE {table} SET {col} = ? WHERE id = ?", (row[col], row["id"]))
        # G07f: 歯の状態は歯冠と根の2つで持つ。まだ入っていない歯には、患者様と歯番で合わせて見本の値を入れる
        for row in data.get("tooth_status", []):
            if row.get("crown"):
                con.execute("UPDATE tooth_status SET crown = ?, root = ?, status = ? "
                            "WHERE patient_id = ? AND tooth = ? AND crown IS NULL",
                            (row["crown"], row["root"], row["status"], row["patient_id"], row["tooth"]))
        # G21d/G21e: 見本データの担当者の名前を替える（歯科医師は院長の「大川内」、衛生士は架空の「佐藤」）（すでに入っているデータベースにも効かせる）
        for t in schema.TABLES:
            cols = [r[1] for r in con.execute(f"PRAGMA table_info({t})")]
            if "staff_name" in cols:
                for old, new in (("山本", "大川内"), ("田中", "佐藤")):
                    con.execute(f"UPDATE {t} SET staff_name = ? WHERE staff_name = ?", (new, old))
        # G21j: 美咲様のラテックスアレルギーの「詳しく」は空にする（かゆみ程度の話は重要事項に載せない）
        con.execute("UPDATE important_notes SET detail = '' WHERE body = 'ラテックスアレルギー' AND detail LIKE '%かゆ%'")
        if dates.get_marker(con) is None:
            dates.set_marker(con, mark)
        con.commit()
        dates.align(con)  # 今日へ合わせる（起動・restore のどちらもここを通る）
        dates.mark_checked(path or db_path())
        return {"added_columns": added, "inserted": inserted}
    finally:
        con.close()
