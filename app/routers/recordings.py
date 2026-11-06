"""録音の受け口と、録音の一覧 /recordings、下書きの画面 /drafts/{番号}、録音の窓を持つ親の画面 /app。"""
import html
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.ai import fixtalk, memo, recpipe
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
    role: str = ""


class TransferBody(BaseModel):
    appt: int | None = None


class PasteBody(BaseModel):
    text: str = ""
    appt: int | None = None


@router.post("/rec/start")
def rec_start(body: StartBody):
    return _run(lambda con: recpipe.start(con, body.appt, body.role))


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
        "<header class='rec-head'><span>録音の一覧</span><a href='/clinic'>予約一覧へ</a></header><main class='rec-main'>"
        "<table class='rtab' data-part='recording-list'><thead><tr><th>時間</th><th>長さ</th><th>カルテ番号</th><th>状態</th><th>操作</th></tr></thead>"
        "<tbody id='rows'></tbody></table>"
        "<div id='paste'><b>文字を貼り付けて下書きにする</b>（録音が使えないとき・試験用）<br>"
        "<textarea id='paste-text' placeholder='話した内容の文字'></textarea><br>"
        "<select id='paste-target'><option value=''>患者様なし（あとで選ぶ）</option></select> "
        "<button type='button' id='paste-go'>下書きにする</button> <span id='paste-msg' class='err'></span></div>"
        "</main><script src='/static/js/mic_error.js'></script><script src='/static/js/voice_keys.js'></script><script src='/static/js/rec_keys.js'></script><script src='/static/js/recordings.js'></script></body></html>", headers=NO_STORE)


def safe_back(back: str) -> str:
    """戻り先は、このサーバーの中の道（/ から始まる）だけ。外へは戻さない。無ければ予約一覧。"""
    b = (back or "").strip()
    if b.startswith("/") and not b.startswith("//") and not any(c in b for c in ("\\", "\r", "\n", "\t", " ")):
        return b
    return "/clinic"


def _fix_list(d):
    try:
        return json.loads(d["fixes"] or "[]")
    except ValueError:
        return []


def _doubt_list(d):
    try:
        return json.loads(d["doubts"] or "[]")
    except ValueError:
        return []


def _fixes_html(d):
    try:
        fixes = json.loads(d["fixes"] or "[]")
    except ValueError:
        fixes = []
    if not fixes:
        return "<p class='nofix'>聞き違いの直しはありません</p>"
    rows = "".join(f"<li><span class='fx-from'>{h(f['from'])}</span> → <span class='fx-to'>{h(f['to'])}</span></li>"
                   for f in fixes)
    return f"<ul class='fixes'>{rows}</ul>"


def _draft_html(d, p, v, rec, fix, back="/clinic"):
    items = json.loads(d["items"] or "{}")
    done = d["status"] == "confirmed"
    dis = " disabled" if done else ""
    cols = ""
    for key, _title in memo.SECTIONS:
        rows = items.get(key, [])
        body = "".join(
            f"<li class='row' data-quote='{h(r['quote'], quote=True)}'>"
            f"<input class='tx' type='text' value='{h(r['text'], quote=True)}'{dis}>"
            f"<button type='button' class='del'{dis}>消す</button>"
            f"<span class='qt'>もとの話: {h(r['quote'])}</span></li>" for r in rows)
        cols += (f"<section class='draft-sec' data-section='{key}'><h3>{h(memo.title_of(key, v['visit_date']))}</h3><ul>{body}</ul>"
                 f"<button type='button' class='add'{dis}>＋ 行を足す</button></section>")
    mark = "確定済み（診療メモに入りました）" if done else "下書き まだ記録に入っていません"
    rec_id = rec["id"] if rec else ""
    state = rec["state"] if rec else ""
    audio = ""
    if fix and rec and rec["audio_file"] and not done:
        audio = f"<audio controls src='/rec/{rec['id']}/audio' data-part='fix-audio'></audio>"
    if d["combined"]:
        fix = False  # まとめた要約は、区切りごとの文字から作る。ここでは文字を直して整理し直さない
    if fix and not done:
        left = (f"{audio}<textarea id='fix-text' class='fix-text'>{h(d['transcript'])}</textarea>"
                "<button type='button' id='fix-reorg'>この文字で整理し直す</button>")
    else:
        shown = d["fixed_transcript"] or d["transcript"]
        raw = (f"<details class='draft-raw' data-part='draft-raw'><summary>聞き取りのまま</summary><p>{h(d['transcript'])}</p></details>"
               if d["fixed_transcript"] else "")
        note = f"<p class='polish-note' data-part='polish-note'>{h(d['polish_note'])}</p>" if d["polish_note"] else ""
        left = (f"<p class='polished' data-part='draft-polished'>"
                f"{fixtalk.marked_html(shown, _fix_list(d), _doubt_list(d))}</p>{note}{raw}")
    bar = ("" if done else
           "<span class='draft-actions'><button type='button' id='btn-confirm' data-action='confirm'>カルテに記録する</button> "
           "<button type='button' id='btn-later'>あとで直す</button></span>")
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>下書き</title>" + CSS +
        f"</head><body class='rec-page' data-page='draft' data-draft-id='{d['id']}' data-rec-id='{rec_id}' "
        f"data-status='{d['status']}' data-rec-state='{h(state)}' data-fix='{1 if fix else 0}' data-back='{h(back, quote=True)}'>"
        f"<header class='rec-head'><a id='btn-back' class='back' href='{h(back, quote=True)}'>戻る</a>"
        f"<span>{h(p['name'])} 様 No. {h(p['chart_no'])}　診療日 {h(v['visit_date'])}</span>"
        + ("" if done else "<button type='button' id='btn-say' class='say-btn'>言える言葉</button>") + "</header>"
        f"<div class='draft-bar'><span class='draft-mark' data-part='draft-mark'>{mark}</span>{bar}"
        "<span id='msg' class='err' role='status'></span></div>"
        f"<div class='draft-cols'><div class='draft-left' data-part='draft-transcript'><h3>{"話したままの文字（直して整理し直す）" if (fix and not done and not d["combined"]) else "話した文字（清書）"}</h3>{left}"
        f"<h3 class='fx-title'>直した聞き違い（元 → 直し）</h3><div data-part='draft-fixes'>{_fixes_html(d)}</div></div>"
        f"<div class='draft-right' data-part='draft-items'>{cols}</div></div>"
        "<div class='plan-row'><section class='plan-block' id='plan-compare' data-part='plan-compare'><h2>治療計画の変更</h2>"
        "<p class='plan-hint'>話に出ていない計画は、そのまま残します。変えたいものだけ印を付けてください。</p>"
        "<table class='rtab plan-table'><thead><tr><th>今の計画</th><th>新しい計画</th><th>操作</th></tr></thead>"
        "<tbody id='plan-rows'></tbody></table></section>"
        + ("" if done else
           "<section class='plan-block' id='tooth-compare' hidden><h2>他の画面にも入れる（歯の絵・治療歴・次回の予定・治療方針）</h2>"
           "<p class='plan-hint' id='tooth-hint'>初めから印が付いています。入れたくないものは印を外してください（声なら「3番 外す」）。歯の処置は、歯が1本に決まり、処置の言葉が決まっている行だけ出ます。</p>"
           "<table class='rtab plan-table'><thead><tr><th>内容</th><th>今 → 記録後</th><th>操作</th></tr></thead>"
           "<tbody id='tooth-rows'></tbody></table></section>") + "</div>"
        "<script src='/static/js/mic_error.js'></script><script src='/static/js/voice_keys.js'></script><script src='/static/js/rec_keys.js'></script>"
        "<script src='/static/js/numrule.js'></script><script src='/static/js/numtags.js'></script><script src='/static/js/draft.js'></script><script src='/static/js/actions/look.js'></script></body></html>"
    )


@router.get("/drafts/{draft_id}", response_class=HTMLResponse)
def draft_page(draft_id: int, chart: str = "", fix: int = 0, back: str = ""):
    con = connect()
    try:
        d = con.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not d:
            raise HTTPException(404)
        p = con.execute("SELECT * FROM patients WHERE id = ?", (d["patient_id"],)).fetchone()
        v = con.execute("SELECT * FROM visits WHERE id = ? AND patient_id = ?", (d["visit_id"], d["patient_id"])).fetchone()
        if chart and chart != p["chart_no"]:
            raise HTTPException(404)  # 別の患者様の画面では開かない
        rec = con.execute("SELECT id, state, audio_file FROM recordings WHERE draft_id = ? OR id = ?",
                          (draft_id, d["recording_id"] or -1)).fetchone()
        return HTMLResponse(_draft_html(d, p, v, rec, bool(fix), safe_back(back)), headers=NO_STORE)
    finally:
        con.close()


@router.get("/app", response_class=HTMLResponse)
def parent_app(go: str = ""):
    """録音と右下の窓を持つ親の画面。中の画面だけを替えるので、画面が替わっても録音は切れない。
    go=/recordings のように同じ場所の画面を渡すと、その画面を中に開く（親の無い画面から録音を使うとき）。"""
    if not (go.startswith("/") and not go.startswith("//") and "\\" not in go and "\n" not in go and not go.startswith("/app")):
        go = "/"
    return HTMLResponse(
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>チェアサイドビュー</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'><link rel='stylesheet' href='/static/css/rec.css'></head><body class='rec-parent'>"
        "<iframe id='inner' title='画面' src='" + html.escape(go, quote=True) + "'></iframe>"
        "<div id='band' data-part='key-band' hidden><span data-band-text></span><span data-band-left></span></div>"
        "<div id='rec-win' data-part='rec-window' hidden><span class='dot'></span><span class='msg'></span></div>"
        "<script src='/static/js/mic_error.js'></script><script src='/static/js/voice_keys.js'></script><script src='/static/js/rec.js'></script></body></html>",
        headers=NO_STORE)
