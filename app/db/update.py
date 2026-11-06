"""データベースを作る、または足りない分だけ足す。scripts/seed.py と scripts/update_db.py が使う。"""
from datetime import date

from app.db import connect, dates, db_path, initial, schema
from app.today import BASE


def update(path=None) -> dict:
    """無ければ初期の状態で作る。あれば足りない表・列・初期データの行だけ足し、あるデータは消さない。"""
    con = connect(path, align=False)
    try:
        base = initial.build()  # 形を変える前に作る（ここで失敗したら形も変えず、形を変えたときの一度だけの直しを逃さない）
        added = schema.migrate(con)
        # 見本の行は BASE の日付で書いてある。いまのデータベースがすでにずれている分（印、無ければ見本の1行から決める）だけ
        # ずらして足す。足したあと、データベース全体を今日へ合わせる（日付の決まりは app/db/dates.py の1か所）
        mark = dates.get_marker(con) or dates.detect(con)
        data = dates.shift_rows(base, (date.fromisoformat(mark) - date.fromisoformat(BASE)).days)
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
        # G07f / G07g: 歯の状態の形が変わった（歯冠と根、カリエスの印、インプラント）。形を変えたときに一度だけ、
        # 見本の歯の行を患者様と歯番で合わせて見本の値にする（無い歯は足す）。歯の状態を書き替える画面は無い
        if {("tooth_status", "crown"), ("tooth_status", "caries")} & set(added):
            for row in data.get("tooth_status", []):
                vals = (row["status"], row["crown"], row["root"], row["caries"], row["patient_id"], row["tooth"])
                cur = con.execute("UPDATE tooth_status SET status = ?, crown = ?, root = ?, caries = ? "
                                  "WHERE patient_id = ? AND tooth = ?", vals)
                if not cur.rowcount:
                    con.execute("INSERT INTO tooth_status (status, crown, root, caries, patient_id, tooth) "
                                "VALUES (?, ?, ?, ?, ?, ?)", vals)
            # 花子様の有床義歯は右上4番の所（左下5番はブリッジにした）
            for row in data.get("dentures", []):
                con.execute("UPDATE dentures SET site = ? WHERE id = ? AND patient_id = ? AND kind = ?",
                            (row["site"], row["id"], row["patient_id"], row["kind"]))
        # G07g: 「根充後」は「根充済」と呼ぶ
        con.execute("UPDATE tooth_status SET root = '根充済' WHERE root = '根充後'")
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
