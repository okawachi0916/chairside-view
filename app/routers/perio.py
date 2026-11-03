"""歯周基本検査の入力の保存。今日の日付の新しい検査として入れる。過去の検査は変えない。"""
import re

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db import TODAY, connect
from app.db.initial import ALL_TEETH

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}


class SaveBody(BaseModel):
    appt: int
    teeth: dict = {}


def _json(data, status=200):
    return JSONResponse(data, status_code=status, headers=NO_STORE)


def inspect_teeth(con, pid):
    """検査する歯は初期データで決める: 一番新しい検査の歯。検査がまだ無い人は、欠損でない歯。"""
    row = con.execute("SELECT id FROM perio_exams WHERE patient_id = ? ORDER BY exam_date DESC, id DESC LIMIT 1", (pid,)).fetchone()
    if row:
        return {r[0] for r in con.execute("SELECT tooth FROM perio_teeth WHERE exam_id = ?", (row[0],))}
    gone = {r[0] for r in con.execute("SELECT tooth FROM tooth_status WHERE patient_id = ? AND status = '欠損'", (pid,))}
    return {t for t in ALL_TEETH if t not in gone}


def _int(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


@router.post("/api/perio/save")
def save(body: SaveBody):
    con = connect()
    try:
        a = con.execute("SELECT patient_id FROM appointments WHERE id = ?", (body.appt,)).fetchone()
        if not a:
            return _json({"error": "その予約が見つかりません"}, 404)
        pid = a[0]
        want = inspect_teeth(con, pid)
        got = {}
        for k, v in body.teeth.items():
            if not str(k).isdigit() or int(k) not in want:
                return _json({"error": "検査しない歯が含まれています"}, 400)
            got[int(k)] = v if isinstance(v, dict) else {}
        missing = sorted(t for t in want if _int(got.get(t, {}).get("pocket")) is None)
        if missing:
            return _json({"error": f"入力していない歯があります（{len(missing)}本）", "missing": missing}, 400)
        rows = []
        for t in sorted(want):
            v = got[t]
            pocket, bop, mob = _int(v.get("pocket")), v.get("bop", 0), v.get("mobility", 0)
            plaque = v.get("plaque", "0000")
            if not (1 <= pocket <= 12) or bop not in (0, 1) or _int(mob) is None or not (0 <= mob <= 3) \
                    or not isinstance(plaque, str) or not re.fullmatch(r"[01]{4}", plaque):
                return _json({"error": f"{t}番の入力が正しくありません", "missing": [t]}, 400)
            rows.append((t, pocket, int(bop), plaque, mob))
        cur = con.execute("INSERT INTO perio_exams (patient_id, exam_date) VALUES (?, ?)", (pid, TODAY))
        eid = cur.lastrowid
        con.executemany("INSERT INTO perio_teeth (exam_id, tooth, pocket, bop, plaque, mobility) VALUES (?, ?, ?, ?, ?, ?)",
                        [(eid, *r) for r in rows])
        con.commit()
        return _json({"ok": True, "exam_id": eid})
    finally:
        con.close()
