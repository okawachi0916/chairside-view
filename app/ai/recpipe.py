"""録音の流れ: 録音中 → 転送待ち → 文字起こし中 → 整理中 → 下書き（失敗・後で直す）。

- 音声は先に data/runtime/audio に保存する。通信や文字起こしが失敗しても、保存した音声からやり直せる。
- 状態の変更は「今の状態と試行番号が合っているときだけ」行う。遅れて届いた結果や二重の再試行は捨てる。
- 結果は、録音を始めたときに固定した患者様と診療回にだけ入れる。今開いている患者様は見ない。
- 下書きは1つの録音から1つだけ。
"""
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from datetime import datetime
from pathlib import Path

from app.ai import fake, memo
from app.ai.gateway import sensitive_from_db
from app.ai.settings import ClaudeUnavailable, redact_key
from app.db import connect, data_dir

RECORDING, WAITING, TRANSCRIBING, ORGANIZING, FAILED, DRAFT, CONFIRMED, LATER = (
    "録音中", "転送待ち", "文字起こし中", "整理中", "失敗", "下書き", "確定", "後で直す")
STATES = [RECORDING, WAITING, TRANSCRIBING, ORGANIZING, FAILED, DRAFT, CONFIRMED, LATER]
WORKING = (TRANSCRIBING, ORGANIZING)
STALE_SEC = 3  # 働いている処理が無いまま、この秒数たった作業中の録音は「失敗」にする（サーバーの再起動のあと）

_live = {}  # (録音の番号, 試行番号) -> 動いている処理。このサーバーの中だけ
_live_lock = threading.Lock()


class RecError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def audio_dir() -> Path:
    return data_dir() / "audio"


def timeout_sec(kind: str) -> float:
    if kind == "ai":
        return float(os.environ.get("CHAIRSIDE_AI_TIMEOUT", "90"))
    return float(os.environ.get("CHAIRSIDE_STT_TIMEOUT", "180"))


def row_dict(r):
    return dict(r) if r else None


def visit_for(con, appt_id: int):
    """予約から (患者様, 診療回) を決める。診療回が無ければ作る。"""
    a = con.execute("SELECT * FROM appointments WHERE id = ?", (appt_id,)).fetchone()
    if not a:
        raise RecError("その予約が見つかりません", 404)
    v = con.execute("SELECT id FROM visits WHERE appointment_id = ? AND patient_id = ?",
                    (appt_id, a["patient_id"])).fetchone()
    if v:
        return a["patient_id"], v["id"]
    cur = con.execute(
        "INSERT INTO visits (patient_id, appointment_id, visit_date, start_time, role, unit, status) "
        "VALUES (?, ?, ?, ?, ?, ?, 'open')",
        (a["patient_id"], appt_id, a["appt_date"], a["start_time"], a["role"], a["unit"]))
    return a["patient_id"], cur.lastrowid


def start(con, appt_id=None) -> dict:
    pid = vid = None
    if appt_id:
        pid, vid = visit_for(con, int(appt_id))
    n = con.execute("SELECT COALESCE(MAX(rec_no), 0) + 1 FROM recordings").fetchone()[0]
    cur = con.execute(
        "INSERT INTO recordings (rec_no, started_at, patient_id, visit_id, state, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?)", (n, now(), pid, vid, RECORDING, now()))
    con.commit()
    return get(con, cur.lastrowid)


def get(con, rec_id: int):
    r = con.execute(
        "SELECT r.*, p.chart_no FROM recordings r LEFT JOIN patients p ON p.id = r.patient_id WHERE r.id = ?",
        (rec_id,)).fetchone()
    return row_dict(r)


def _set(con, rec_id, **kw):
    cols = ", ".join(f"{k} = ?" for k in kw)
    con.execute(f"UPDATE recordings SET {cols}, updated_at = ? WHERE id = ?", [*kw.values(), now(), rec_id])


def save_audio(con, rec_id: int, data: bytes, duration: float) -> dict:
    r = get(con, rec_id)
    if not r:
        raise RecError("その録音が見つかりません", 404)
    if r["state"] != RECORDING:
        raise RecError("この録音はもう止まっています", 409)
    d = audio_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"rec_{rec_id}.webm"
    path.write_bytes(data)
    _set(con, rec_id, audio_file=path.name, duration_sec=round(float(duration), 1))
    if r["patient_id"]:
        _set(con, rec_id, state=WAITING)  # OK か「転送」を待つ。押されなくても、このまま転送待ち
        con.commit()
    else:
        con.commit()
        _claim_and_run(con, rec_id, [RECORDING], TRANSCRIBING)  # 患者様なしは文字起こしまで進めて止める
    return get(con, rec_id)


def _next_state(r) -> str:
    if not r["transcript"] and r["audio_file"]:
        return TRANSCRIBING
    if r["patient_id"]:
        return ORGANIZING
    return WAITING


def _claim_and_run(con, rec_id, from_states, to_state):
    """今の状態が合うときだけ状態を進め、裏の処理を始める。合わなければ何もしない（二重の再試行を防ぐ）。"""
    marks = ",".join("?" * len(from_states))
    cur = con.execute(
        f"UPDATE recordings SET state = ?, attempt = attempt + 1, error = '', updated_at = ? "
        f"WHERE id = ? AND state IN ({marks})", [to_state, now(), rec_id, *from_states])
    con.commit()
    if cur.rowcount != 1:
        return False
    attempt = con.execute("SELECT attempt FROM recordings WHERE id = ?", (rec_id,)).fetchone()[0]
    with _live_lock:
        _live[(rec_id, attempt)] = True
    threading.Thread(target=_job, args=(rec_id, attempt), daemon=True).start()
    return True


def transfer(con, rec_id: int, appt_id=None) -> dict:
    """転送する。患者様なしの録音は、ここで患者様と診療回を決める。"""
    r = get(con, rec_id)
    if not r:
        raise RecError("その録音が見つかりません", 404)
    if r["state"] != WAITING:
        raise RecError(f"今の状態（{r['state']}）では転送できません", 409)
    if appt_id:
        pid, vid = visit_for(con, int(appt_id))
        if r["patient_id"] and r["patient_id"] != pid:
            raise RecError("この録音は別の患者様に固定されています", 409)
        con.execute("UPDATE recordings SET patient_id = ?, visit_id = ? WHERE id = ? AND state = ?",
                    (pid, vid, rec_id, WAITING))
        con.commit()
    elif not r["patient_id"]:
        raise RecError("患者様と診療回を選んでください")
    r = get(con, rec_id)
    nxt = _next_state(r)
    if nxt == WAITING:
        raise RecError("転送できません")
    _claim_and_run(con, rec_id, [WAITING], nxt)
    return get(con, rec_id)


def retry(con, rec_id: int) -> dict:
    r = get(con, rec_id)
    if not r:
        raise RecError("その録音が見つかりません", 404)
    if r["state"] not in (FAILED, LATER):
        raise RecError(f"今の状態（{r['state']}）では再試行できません", 409)
    nxt = _next_state(r)
    if nxt == WAITING:
        con.execute("UPDATE recordings SET state = ?, error = '', updated_at = ? WHERE id = ? AND state IN (?, ?)",
                    (WAITING, now(), rec_id, FAILED, LATER))
        con.commit()
    else:
        _claim_and_run(con, rec_id, [FAILED, LATER], nxt)
    return get(con, rec_id)


def later(con, rec_id: int) -> dict:
    cur = con.execute("UPDATE recordings SET state = ?, updated_at = ? WHERE id = ? AND state IN (?, ?)",
                      (LATER, now(), rec_id, FAILED, DRAFT))
    con.commit()
    if cur.rowcount != 1:
        raise RecError("失敗した録音か下書きだけ「後で直す」にできます", 409)
    return get(con, rec_id)


def paste(con, text: str, appt_id=None) -> dict:
    """文字を貼り付けて、録音のあとと同じ処理を動かす。"""
    text = (text or "").strip()
    if not text:
        raise RecError("文字を入れてください")
    r = start(con, appt_id)
    _set(con, r["id"], transcript=text, state=WAITING)
    con.commit()
    if appt_id:
        return transfer(con, r["id"])
    return get(con, r["id"])


def recover_stale(con):
    """働いている処理が無いまま止まっている録音（サーバーの再起動のあと）を「失敗」にして、再試行できるようにする。"""
    rows = con.execute(
        "SELECT id, attempt, state, updated_at FROM recordings WHERE state IN (?, ?, ?)",
        (TRANSCRIBING, ORGANIZING, RECORDING)).fetchall()
    for r in rows:
        with _live_lock:
            alive = (r["id"], r["attempt"]) in _live
        age = (datetime.now() - datetime.fromisoformat(r["updated_at"])).total_seconds()
        if alive or age < STALE_SEC:
            continue
        if r["state"] == RECORDING and age < 3600 * 6:
            continue  # 録音中は長いことがある。サーバーが覚えている録音かは分からないので、しばらく待つ
        why = "録音が途中で切れました" if r["state"] == RECORDING else "サーバーが止まったため中断しました"
        con.execute("UPDATE recordings SET state = ?, error = ?, updated_at = ? WHERE id = ? AND state = ?",
                    (FAILED, why, now(), r["id"], r["state"]))
    con.commit()


# ---- 裏の処理 ----

def _with_timeout(fn, sec):
    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(fn)
    try:
        return fut.result(timeout=sec)
    except FutureTimeout:
        raise TimeoutError("時間切れ") from None
    finally:
        ex.shutdown(wait=False)


def _transcribe(audio_path: Path) -> str:
    fake_text = fake.fake_transcript()
    if fake_text is not None:
        return fake_text
    from app.voice import transcribe as tr

    res = tr.transcribe(tr.to_pcm(audio_path.read_bytes()))
    return (res.get("text") or "").strip()


def _fail(con, rec_id, attempt, state, e):
    if isinstance(e, TimeoutError):
        why = "時間切れ（もう一度お試しください）"
    elif isinstance(e, ClaudeUnavailable):
        why = "Claude が使えません（鍵が設定されていません）"
    else:
        why = redact_key(f"{type(e).__name__}: {str(e)[:80]}")
    cur = con.execute("UPDATE recordings SET state = ?, error = ?, updated_at = ? "
                      "WHERE id = ? AND attempt = ? AND state = ?", (FAILED, why, now(), rec_id, attempt, state))
    con.commit()
    return cur.rowcount


def _job(rec_id: int, attempt: int):
    con = connect()
    try:
        r = get(con, rec_id)
        if not r or r["attempt"] != attempt:
            return
        if r["state"] == TRANSCRIBING:
            try:
                text = _with_timeout(lambda: _transcribe(audio_dir() / r["audio_file"]), timeout_sec("stt"))
                if not text.strip():
                    raise ValueError("声が聞き取れませんでした")
            except Exception as e:  # noqa: BLE001
                _fail(con, rec_id, attempt, TRANSCRIBING, e)
                return
            nxt = ORGANIZING if r["patient_id"] else WAITING
            cur = con.execute(
                "UPDATE recordings SET transcript = ?, state = ?, updated_at = ? "
                "WHERE id = ? AND attempt = ? AND state = ?", (text, nxt, now(), rec_id, attempt, TRANSCRIBING))
            con.commit()
            if cur.rowcount != 1 or nxt != ORGANIZING:
                return
            r = get(con, rec_id)
        if r["state"] == ORGANIZING:
            _organize(con, rec_id, attempt, r)
    finally:
        con.close()
        with _live_lock:
            _live.pop((rec_id, attempt), None)


def _organize(con, rec_id, attempt, r):
    from app.routers import ai as ai_router  # 試験が make_gateway を差し替えられるように、使うときに読む

    try:
        sens = sensitive_from_db(con)
        gw = ai_router.make_gateway()
        items = _with_timeout(lambda: memo.organize(r["transcript"], sens, gw), timeout_sec("ai"))
    except Exception as e:  # noqa: BLE001
        _fail(con, rec_id, attempt, ORGANIZING, e)
        return
    con.execute("BEGIN IMMEDIATE")
    try:
        cur = get(con, rec_id)  # 結果を入れる先は、録音を始めたときに固定した患者様と診療回
        if not cur or cur["attempt"] != attempt or cur["state"] != ORGANIZING:
            con.rollback()
            return  # 遅れて届いた結果は捨てる
        d = con.execute("SELECT id, status FROM drafts WHERE recording_id = ?", (rec_id,)).fetchone()
        if d and d["status"] == "draft":
            # 整理し直した新しい下書き。人が見てから確定する（二重に作らず、同じ下書きを新しくする）
            draft_id = d["id"]
            con.execute("UPDATE drafts SET body = ?, transcript = ?, items = ? WHERE id = ?",
                        (memo.body_lines(items), cur["transcript"], json.dumps(items, ensure_ascii=False), draft_id))
        elif d:
            draft_id = d["id"]  # 確定済みは触らない
        else:
            c2 = con.execute(
                "INSERT INTO drafts (patient_id, visit_id, kind, body, transcript, status, created_at, "
                "recording_id, items) VALUES (?, ?, 'spoken_summary', ?, ?, 'draft', ?, ?, ?)",
                (cur["patient_id"], cur["visit_id"], memo.body_lines(items), cur["transcript"], now(),
                 rec_id, json.dumps(items, ensure_ascii=False)))
            draft_id = c2.lastrowid
        con.execute("UPDATE recordings SET state = ?, draft_id = ?, updated_at = ? WHERE id = ?",
                    (DRAFT, draft_id, now(), rec_id))
        con.commit()
    except Exception:
        con.rollback()
        raise


def reorganize(con, rec_id: int, transcript: str) -> dict:
    """話したままの文字を直して、整理し直す。新しい下書きは人が見てから確定する。"""
    transcript = (transcript or "").strip()
    if not transcript:
        raise RecError("話したままの文字を入れてください")
    r = get(con, rec_id)
    if not r:
        raise RecError("その録音が見つかりません", 404)
    if not r["patient_id"]:
        raise RecError("先に患者様と診療回を選んでください", 409)
    if r["state"] not in (DRAFT, LATER, FAILED):
        raise RecError(f"今の状態（{r['state']}）では整理し直せません", 409)
    con.execute("UPDATE recordings SET transcript = ? WHERE id = ? AND state IN (?, ?, ?)",
                (transcript, rec_id, DRAFT, LATER, FAILED))
    con.commit()
    _claim_and_run(con, rec_id, [DRAFT, LATER, FAILED], ORGANIZING)
    return get(con, rec_id)
