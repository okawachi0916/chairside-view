"""歯周検査の入力。新しい検査は「基本検査」か「精密検査」を選んで入れる。今日の日付の新しい検査として入れ、過去の検査は変えない。

- GET  /api/perio/blank?appt=…&kind=basic|precise … 入力用の空の表（見る画面と同じ部品 perio_table）
- POST /api/perio/save … 検査1回分を保存する
基本検査は1本に1つのポケット（mm）と出血。精密検査は1本に6点（頬側の遠心・中央・近心、舌側または口蓋側の遠心・中央・近心）。
精密検査の pocket は6点のいちばん深い値、bop は6点のどれかに出血があれば1。基本検査と同じに数えられる。
"""
import re
import sqlite3
import time

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.db import connect
from app.db.initial import ALL_TEETH
from app.mockview.perio_parts import KINDS, blank_exam, perio_table
from app.today import today

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}


class SaveBody(BaseModel):
    appt: int
    kind: str = "basic"
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


def _patient_of(con, appt):
    a = con.execute("SELECT patient_id FROM appointments WHERE id = ?", (appt,)).fetchone()
    return a[0] if a else None


@router.get("/api/perio/blank")
def blank(appt: int, kind: str = "basic"):
    if kind not in KINDS:
        return _json({"error": "検査の種類が正しくありません"}, 400)
    con = connect()
    try:
        pid = _patient_of(con, appt)
        if pid is None:
            return _json({"error": "その予約が見つかりません"}, 404)
        return HTMLResponse(perio_table(blank_exam(sorted(inspect_teeth(con, pid)), kind)), headers=NO_STORE)
    finally:
        con.close()


def _point(v):
    return _int(v) is not None and 1 <= v <= 12


def _row_basic(t, v):
    pocket, bop = _int(v.get("pocket")), v.get("bop", 0)
    if pocket is None:
        return None
    if not _point(pocket) or bop not in (0, 1):
        return "bad"
    return pocket, int(bop), "", ""


def _row_precise(t, v):
    pts, bops = v.get("pts"), v.get("bops")
    if not isinstance(pts, list) or len(pts) != 6 or all(_int(x) is None for x in pts):
        return None
    if not all(_point(x) for x in pts) or not isinstance(bops, list) or len(bops) != 6 or any(b not in (0, 1) for b in bops):
        return "bad"
    return max(pts), int(any(bops)), ",".join(str(x) for x in pts), "".join(str(int(b)) for b in bops)


@router.post("/api/perio/save")
def save(body: SaveBody):
    if body.kind not in KINDS:
        return _json({"error": "検査の種類が正しくありません"}, 400)
    con = connect()
    try:
        pid = _patient_of(con, body.appt)
        if pid is None:
            return _json({"error": "その予約が見つかりません"}, 404)
        want = inspect_teeth(con, pid)
        got = {}
        for k, v in body.teeth.items():
            if not str(k).isdigit() or int(k) not in want:
                return _json({"error": "検査しない歯が含まれています"}, 400)
            got[int(k)] = v if isinstance(v, dict) else {}
        make = _row_precise if body.kind == "precise" else _row_basic
        made = {t: make(t, got.get(t, {})) for t in sorted(want)}
        missing = [t for t, r in made.items() if r is None]
        if missing:
            return _json({"error": f"入力していない歯があります（{len(missing)}本）", "missing": missing}, 400)
        rows = []
        for t, r in made.items():
            v = got[t]
            mob, plaque = v.get("mobility", 0), v.get("plaque", "0000")
            if r == "bad" or _int(mob) is None or not (0 <= mob <= 3) or not isinstance(plaque, str) \
                    or not re.fullmatch(r"[01]{4}", plaque):
                return _json({"error": f"{t}番の入力が正しくありません", "missing": [t]}, 400)
            rows.append((t, *r[:2], plaque, mob, *r[2:]))
        try:
            cur = con.execute("INSERT INTO perio_exams (patient_id, exam_date, kind, exam_time) VALUES (?, ?, ?, ?)",
                              (pid, today(), body.kind, time.strftime("%H:%M")))
        except sqlite3.IntegrityError:  # 1日に1回の検査だけ（同じ日の検査は2つ入れない）
            return _json({"error": "今日の検査はもう保存されています"}, 409)
        eid = cur.lastrowid
        con.executemany("INSERT INTO perio_teeth (exam_id, tooth, pocket, bop, plaque, mobility, pockets6, bops6) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [(eid, *r) for r in rows])
        con.commit()
        return _json({"ok": True, "exam_id": eid})
    finally:
        con.close()
