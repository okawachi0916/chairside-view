"""録音の受け口と、録音の一覧 /recordings、下書きの画面 /drafts/{番号}、録音の窓を持つ親の画面 /app。"""
import html
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.ai import memo, recpipe
from app.ai.recpipe import RecError
from app.db import connect

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}
h = html.escape


def _json(data, status=200):
    return JSONResponse(data, status_code=status, headers=NO_STORE)


def _run(fn):
    """RecError を画面に出してよい文にして返す。"""
    con = connect()
    try:
        return _json(fn(con))
    except RecError as e:
        return _json({"error": str(e)}, e.status)
    finally:
        con.close()


class StartBody(BaseModel):
    appt: int | None = None


class TransferBody(BaseModel):
    appt: int | None = None


class PasteBody(BaseModel):
    text: str = ""
    appt: int | None = None


@router.post("/rec/start")
def rec_start(body: StartBody):
    return _run(lambda con: recpipe.start(con, body.appt))


@router.post("/rec/{rec_id}/audio")
async def rec_audio(rec_id: int, request: Request, dur: float = 0):
    data = await request.body()
    return _run(lambda con: recpipe.save_audio(con, rec_id, data, dur))


@router.post("/rec/{rec_id}/transfer")
def rec_transfer(rec_id: int, body: TransferBody):
    return _run(lambda con: recpipe.transfer(con, rec_id, body.appt))


@router.post("/rec/{rec_id}/retry")
def rec_retry(rec_id: int):
    return _run(lambda con: recpipe.retry(con, rec_id))


@router.post("/rec/{rec_id}/later")
def rec_later(rec_id: int):
    return _run(lambda con: recpipe.later(con, rec_id))


@router.post("/rec/paste")
def rec_paste(body: PasteBody):
    return _run(lambda con: recpipe.paste(con, body.text, body.appt))


def _mmss(sec):
    sec = int(sec or 0)
    return f"{sec // 60:02d}:{sec % 60:02d}"


@router.get("/api/recordings")
def api_recordings():
    con = connect()
    try:
        recpipe.recover_stale(con)
        rows = con.execute(
            "SELECT r.*, p.chart_no FROM recordings r LEFT JOIN patients p ON p.id = r.patient_id "
            "ORDER BY r.id DESC").fetchall()
        out = []
        for r in rows:
            out.append({
                "id": r["id"], "rec_no": r["rec_no"], "time": r["started_at"], "duration": _mmss(r["duration_sec"]),
                "chart_no": r["chart_no"] or "患者様なし", "fixed": r["patient_id"] is not None, "state": r["state"],
                "error": r["error"], "draft_id": r["draft_id"], "has_transcript": bool(r["transcript"]),
            })
        pending = sum(1 for r in out if r["state"] == recpipe.WAITING)
        return _json({"recordings": out, "pending": pending})
    finally:
        con.close()


@router.get("/api/recordings/pending")
def api_pending():
    con = connect()
    try:
        n = con.execute("SELECT COUNT(*) FROM recordings WHERE state = ?", (recpipe.WAITING,)).fetchone()[0]
        return _json({"pending": n})
    finally:
        con.close()


@router.get("/api/recordings/{rec_id}")
def api_recording(rec_id: int):
    con = connect()
    try:
        recpipe.recover_stale(con)
        r = recpipe.get(con, rec_id)
        if not r:
            raise HTTPException(404)
        return _json({k: r[k] for k in ("id", "rec_no", "state", "error", "draft_id", "patient_id", "visit_id",
                                        "duration_sec", "chart_no")})
    finally:
        con.close()


@router.get("/api/rec/options")
def api_options():
    """転送先に選べる患者様 (カルテ番号) と予約。氏名は出さない。"""
    con = connect()
    try:
        out = []
        for p in con.execute("SELECT id, chart_no FROM patients ORDER BY chart_no"):
            appts = [{"id": a["id"], "label": f"{a['appt_date']} {a['start_time']} {a['treatment']}"}
                     for a in con.execute("SELECT id, appt_date, start_time, treatment FROM appointments "
                                          "WHERE patient_id = ? ORDER BY appt_date DESC, start_time", (p["id"],))]
            out.append({"chart_no": p["chart_no"], "appts": appts})
        return _json(out)
    finally:
        con.close()


# ---- 画面 ----

CSS = "<link rel='stylesheet' href='/static/css/mock.css'><link rel='stylesheet' href='/static/css/rec.css'>"


@router.get("/recordings", response_class=HTMLResponse)
def recordings_page():
    return HTMLResponse(
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>録音の一覧</title>"
        f"{CSS}</head><body class='rec-page' data-page='recordings'>"
        "<header class='rec-head'><span>録音の一覧</span><a href='/'>予約一覧へ</a></header><main class='rec-main'>"
        "<table class='rec' data-part='recording-list'><thead><tr><th>時間</th><th>長さ</th><th>カルテ番号</th><th>状態</th><th>操作</th></tr></thead>"
        "<tbody id='rows'></tbody></table>"
        "<div id='paste'><b>文字を貼り付けて下書きにする</b>（録音が使えないとき・試験用）<br>"
        "<textarea id='paste-text' placeholder='話した内容の文字'></textarea><br>"
        "<select id='paste-target'><option value=''>患者様なし（あとで選ぶ）</option></select> "
        "<button type='button' id='paste-go'>下書きにする</button> <span id='paste-msg' class='err'></span></div>"
        "</main><script src='/static/js/recordings.js'></script></body></html>", headers=NO_STORE)


def _draft_html(d, p, v):
    items = json.loads(d["items"] or "{}")
    cols = ""
    for key, title in memo.SECTIONS:
        rows = items.get(key, [])
        body = "".join(
            f"<li data-quote='{h(r['quote'], quote=True)}'><span class='tx'>{h(r['text'])}</span>"
            f"<span class='qt'>もとの話: {h(r['quote'])}</span></li>" for r in rows
        ) or "<li class='empty'>（なし）</li>"
        cols += f"<section class='draft-sec' data-section='{key}'><h3>{h(title)}</h3><ul>{body}</ul></section>"
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>下書き</title>" + CSS +
        f"</head><body class='rec-page' data-page='draft' data-draft-id='{d['id']}'>"
        f"<header class='rec-head'><span>{h(p['name'])} 様 No. {h(p['chart_no'])}　診療日 {h(v['visit_date'])}</span>"
        "<a href='/recordings'>録音の一覧へ</a></header>"
        "<div class='draft-bar'><span class='draft-mark' data-part='draft-mark'>下書き まだ記録に入っていません</span></div>"
        f"<div class='draft-cols'><div class='draft-left' data-part='draft-transcript'><h3>話したままの文字</h3><p>{h(d['transcript'])}</p></div>"
        f"<div class='draft-right' data-part='draft-items'>{cols}</div></div></body></html>"
    )


@router.get("/drafts/{draft_id}", response_class=HTMLResponse)
def draft_page(draft_id: int, chart: str = ""):
    con = connect()
    try:
        d = con.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not d:
            raise HTTPException(404)
        p = con.execute("SELECT * FROM patients WHERE id = ?", (d["patient_id"],)).fetchone()
        v = con.execute("SELECT * FROM visits WHERE id = ? AND patient_id = ?", (d["visit_id"], d["patient_id"])).fetchone()
        if chart and chart != p["chart_no"]:
            raise HTTPException(404)  # 別の患者様の画面では開かない
        return HTMLResponse(_draft_html(d, p, v), headers=NO_STORE)
    finally:
        con.close()


@router.get("/app", response_class=HTMLResponse)
def parent_app():
    """録音と右下の窓を持つ親の画面。中の画面だけを替えるので、画面が替わっても録音は切れない。"""
    return HTMLResponse(
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>チェアサイドビュー</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'><link rel='stylesheet' href='/static/css/rec.css'></head><body class='rec-parent'>"
        "<iframe id='inner' title='画面' src='/'></iframe>"
        "<div id='band' data-part='key-band' hidden><span data-band-text></span><span data-band-left></span></div>"
        "<div id='rec-win' data-part='rec-window' hidden><span class='dot'></span><span class='msg'></span>"
        "<button type='button' class='ok' hidden>OK</button></div>"
        "<script src='/static/js/voice_keys.js'></script><script src='/static/js/rec.js'></script></body></html>",
        headers=NO_STORE)
