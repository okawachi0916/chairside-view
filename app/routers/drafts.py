"""下書きの確定、後で直す、追記が必要な患者様の印、今日の診療一覧 /today。"""
import html
import json
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.ai import confirm, memo, recpipe
from app.ai.recpipe import RecError
from app.db import connect
from app.db.initial import TODAY
from app.routers.recordings import safe_back

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}
h = html.escape
DOCTOR_MARK = "山本先生 追記必要"  # 後で直す人・確定していない下書きがある人の印


def _json(data, status=200):
    return JSONResponse(data, status_code=status, headers=NO_STORE)


def _run(fn):
    con = connect()
    try:
        return _json(fn(con))
    except RecError as e:
        return _json({"error": str(e)}, e.status)
    finally:
        con.close()


class ItemsBody(BaseModel):
    items: dict


class ConfirmBody(BaseModel):
    items: dict
    plan: dict | None = None


class TextBody(BaseModel):
    transcript: str = ""


class ApptBody(BaseModel):
    appt: int


@router.get("/api/drafts/{draft_id}")
def api_draft(draft_id: int):
    def go(con):
        d = confirm.draft_of(con, draft_id)
        rec = con.execute("SELECT id, state, error, audio_file FROM recordings WHERE draft_id = ? OR id = ?",
                          (draft_id, d["recording_id"] or -1)).fetchone()
        p = con.execute("SELECT chart_no FROM patients WHERE id = ?", (d["patient_id"],)).fetchone()
        return {"id": d["id"], "status": d["status"], "transcript": d["transcript"], "chart_no": p["chart_no"],
                "items": json.loads(d["items"] or "{}"),
                "fixed_transcript": d["fixed_transcript"], "fixes": json.loads(d["fixes"] or "[]"),
                "plans": confirm.plans_active(con, d["patient_id"]),
                "rec": dict(rec) if rec else None}
    return _run(go)


@router.put("/api/drafts/{draft_id}/items")
def api_save_items(draft_id: int, body: ItemsBody):
    return _run(lambda con: confirm.save_items(con, draft_id, body.items))


@router.post("/api/drafts/{draft_id}/confirm")
def api_confirm(draft_id: int, body: ConfirmBody):
    return _run(lambda con: confirm.confirm(con, draft_id, body.items, body.plan))


@router.post("/rec/{rec_id}/reorganize")
def rec_reorganize(rec_id: int, body: TextBody):
    return _run(lambda con: recpipe.reorganize(con, rec_id, body.transcript))


@router.get("/rec/{rec_id}/audio")
def rec_audio_file(rec_id: int):
    con = connect()
    try:
        r = recpipe.get(con, rec_id)
    finally:
        con.close()
    if not r or not r["audio_file"]:
        raise HTTPException(404)
    path = recpipe.audio_dir() / Path(r["audio_file"]).name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, media_type="audio/webm", headers=NO_STORE)


@router.get("/api/pending-memo")
def api_pending_memo(appt: int):
    """この予約の患者様に、確定していない診療メモがあるか。次の患者様を開く前に調べる。"""
    def go(con):
        a = con.execute("SELECT patient_id FROM appointments WHERE id = ?", (appt,)).fetchone()
        if not a:
            raise RecError("その予約が見つかりません", 404)
        return {"memos": confirm.pending_rows(con, a["patient_id"])}
    return _run(go)


@router.post("/api/pending-memo/later")
def api_pending_later(body: ApptBody):
    """「後で直す」: 下書きのまま、音声を残して置く。失敗は音声と診療回を残す。"""
    def go(con):
        a = con.execute("SELECT patient_id FROM appointments WHERE id = ?", (body.appt,)).fetchone()
        if not a:
            raise RecError("その予約が見つかりません", 404)
        n = 0
        for m in confirm.pending_rows(con, a["patient_id"]):
            if m["state"] in (recpipe.DRAFT, recpipe.FAILED):
                recpipe.later(con, m["rec_id"])
                n += 1
        return {"later": n}
    return _run(go)


@router.get("/fix/{rec_id}", response_class=HTMLResponse)
def fix_page(rec_id: int, back: str = ""):
    """後で直す画面。下書きがあればその画面（音声つき）、まだ無ければ文字を直して整理する画面。"""
    con = connect()
    try:
        r = recpipe.get(con, rec_id)
    finally:
        con.close()
    if not r:
        raise HTTPException(404)
    if r["draft_id"]:
        return HTMLResponse(status_code=302, headers={"Location": f"/drafts/{r['draft_id']}?fix=1&back={quote(safe_back(back), safe='')}"})
    audio = f"<audio controls src='/rec/{rec_id}/audio' data-part='fix-audio'></audio>" if r["audio_file"] else "<p>音声は残っていません</p>"
    return HTMLResponse(
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>後で直す</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'><link rel='stylesheet' href='/static/css/rec.css'></head>"
        f"<body class='rec-page' data-page='fix' data-rec-id='{rec_id}' data-back='{h(safe_back(back), quote=True)}'>"
        f"<header class='rec-head'><a class='back' href='{h(safe_back(back), quote=True)}'>戻る</a>"
        f"<span>あとで直す　カルテ番号 {h(r['chart_no'] or '患者様なし')}　{h(r['state'])}</span></header><main class='rec-main'>"
        f"{audio}<p class='err'>{h(r['error'] or '')}</p>"
        "<p>話したままの文字（直せます）</p>"
        f"<textarea id='fix-text' style='width:100%;height:220px'>{h(r['transcript'])}</textarea><p>"
        "<button type='button' id='fix-reorg'>この文字で整理し直す</button> "
        "<button type='button' id='fix-retry'>文字起こしからやり直す</button> <span id='fix-msg' class='err'></span></p>"
        "</main><script src='/static/js/fix.js'></script></body></html>", headers=NO_STORE)


# ---- 今日の診療一覧 ----

def _memo_href(m) -> str:
    """追記が必要な印から開く画面。下書きがあれば下書き、無ければ直す画面。記録したら今日の診療一覧へ戻る。"""
    return f"/drafts/{m['draft_id']}?back=/today" if m["draft_id"] else f"/fix/{m['rec_id']}?back=/today"


@router.get("/api/today")
def api_today():
    con = connect()
    try:
        recpipe.recover_stale(con)
        pend = {}
        for m in confirm.pending_rows(con):
            pend.setdefault(m["appointment_id"], []).append(m)  # 録音を始めた診療回の予約の行に印を付ける
        rows = []
        for a in con.execute(
                "SELECT a.id, a.start_time, a.end_time, a.treatment, a.role, a.status, p.id AS pid, p.chart_no, p.name "
                "FROM appointments a JOIN patients p ON p.id = a.patient_id "
                "WHERE a.appt_date = ? AND a.status = 'booked' ORDER BY a.start_time, p.chart_no, a.id", (TODAY,)):
            v = con.execute("SELECT id, status FROM visits WHERE appointment_id = ? AND patient_id = ?",
                            (a["id"], a["pid"])).fetchone()
            note = v and con.execute("SELECT 1 FROM clinical_notes WHERE visit_id = ?", (v["id"],)).fetchone()
            state = "記録済み" if note else ("診療中" if v else "予約")
            rows.append({"id": a["id"], "time": f"{a['start_time']}〜{a['end_time']}", "chart_no": a["chart_no"],
                         "name": a["name"], "treatment": a["treatment"], "role": a["role"], "state": state,
                         "mark": DOCTOR_MARK if a["id"] in pend else "",
                         "memo_href": _memo_href(min(pend[a["id"]], key=lambda m: not m["draft_id"])) if a["id"] in pend else ""})
        return _json({"rows": rows})
    finally:
        con.close()


@router.get("/today", response_class=HTMLResponse)
def today_page():
    return HTMLResponse(
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>今日の診療一覧</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'><link rel='stylesheet' href='/static/css/booklist.css'>"
        "<link rel='stylesheet' href='/static/css/rec.css'></head><body class='role-list' data-page='today'>"
        "<header class='topbar'><span class='role-tag'>今日の診療一覧</span><a class='today-link' href='/'>予約一覧へ</a></header>"
        "<main class='list' data-part='today-list'><table class='book'>"
        "<thead><tr><th>時間</th><th>カルテ番号</th><th>氏名</th><th>処置</th><th>状態</th></tr></thead>"
        "<tbody id='today-rows'></tbody></table></main>"
        "<script src='/static/js/voice_keys.js'></script><script src='/static/js/rec_keys.js'></script>"
        "<script src='/static/js/today.js'></script></body></html>", headers=NO_STORE)
