"""G19m: 記録（確定）で変えた所を、1行ずつ残す。「記録を取り消す」は、これを逆にたどって記録する前へ戻す。

- 足した行（insert）は、戻すときに消す。書き替えた行（update）は、書き替える前の値（before）へ戻す。
- 記録は1つの取引の中で行う。取り消しも1つの取引（どこか1つでも戻せなければ、全部やめる）。
- 見本データを入れ直す形にはしない（ほかの患者様・ほかの日の記録に触らない）。
"""
import json

from app.db import schema
from app.ai.recpipe import RecError
from app.today import today as app_today


def _check(table: str, cols=()):
    if table not in schema.TABLES:
        raise RecError(f"記録の変更の表が正しくありません: {table}", 500)
    have = {c[0] for c in schema.TABLES[table]["cols"]}
    bad = [c for c in cols if c not in have]
    if bad:
        raise RecError(f"記録の変更の欄が正しくありません: {table}.{bad}", 500)


class Journal:
    def __init__(self, con, draft_id: int, patient_id: int):
        self.con, self.draft_id, self.patient_id = con, draft_id, patient_id
        self.seq = 0
        self.on = app_today()

    def _log(self, tbl, row_id, op, before=None):
        self.seq += 1
        self.con.execute(
            "INSERT INTO record_changes (draft_id, patient_id, seq, tbl, row_id, op, before, recorded_on) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.draft_id, self.patient_id, self.seq, tbl, row_id, op, json.dumps(before or {}, ensure_ascii=False), self.on))

    def insert(self, tbl: str, **cols) -> int:
        _check(tbl, cols)
        cur = self.con.execute(f"INSERT INTO {tbl} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", list(cols.values()))
        self._log(tbl, cur.lastrowid, "insert")
        return cur.lastrowid

    def update(self, tbl: str, row_id: int, **cols):
        _check(tbl, cols)
        row = self.con.execute(f"SELECT * FROM {tbl} WHERE id = ?", (row_id,)).fetchone()
        if not row:
            raise RecError(f"書き替える行が見つかりません: {tbl} {row_id}", 409)
        before = {c: row[c] for c in cols}
        self.con.execute(f"UPDATE {tbl} SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?", [*cols.values(), row_id])
        self._log(tbl, row_id, "update", before)


def has_changes(con, draft_id: int) -> bool:
    return con.execute("SELECT 1 FROM record_changes WHERE draft_id = ?", (draft_id,)).fetchone() is not None


def undo(con, draft_id: int) -> int:
    """draft_id の記録で変えた所を、変えた順の逆に戻し、変更の記録を消す。戻した行の数を返す（取引は呼ぶ側）。"""
    rows = con.execute("SELECT * FROM record_changes WHERE draft_id = ? ORDER BY seq DESC", (draft_id,)).fetchall()
    for r in rows:
        _check(r["tbl"])
        if r["op"] == "insert":
            cur = con.execute(f"DELETE FROM {r['tbl']} WHERE id = ?", (r["row_id"],))
        elif r["op"] == "update":
            before = json.loads(r["before"])
            _check(r["tbl"], before)
            cur = con.execute(f"UPDATE {r['tbl']} SET {', '.join(c + ' = ?' for c in before)} WHERE id = ?",
                              [*before.values(), r["row_id"]])
        else:
            raise RecError(f"記録の変更の種類が正しくありません: {r['op']}", 500)
        if cur.rowcount != 1:  # 戻す行が無い（あとで別の所から消された）。黙って進めず、取り消しごと止める
            raise RecError(f"記録で変えた所を戻せませんでした（{r['tbl']} の行 {r['row_id']} がありません）", 409)
    con.execute("DELETE FROM record_changes WHERE draft_id = ?", (draft_id,))
    return len(rows)
