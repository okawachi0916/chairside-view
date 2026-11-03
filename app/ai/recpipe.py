"""録音の流れ: 録音中 → 転送待ち → 文字起こし中 → 文字起こし済み（区切り）→ 整理中 → 下書き（失敗・後で直す）。

- 録音は1回止めるごとに診療回の「区切り」になる。止めたら文字起こしまで（config/model.json の auto_summary が true のときだけ要約まで）。
- 要約は、区切りごと（summarize_segment）か、診療回の区切りを全部つないで1つ（combine）。
- 区切りは消せる（delete_segment）。数秒は元に戻せ、そのあと音声と文字を消す。

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

from app.ai import fake, fixtalk, memo
from app.ai.gateway import sensitive_from_db
from app.ai.settings import ClaudeUnavailable, redact_key
from app.db import connect, data_dir

RECORDING, WAITING, TRANSCRIBING, ORGANIZING, FAILED, DRAFT, CONFIRMED, LATER = (
    "録音中", "転送待ち", "文字起こし中", "整理中", "失敗", "下書き", "確定", "後で直す")
SEGMENT, DELETED = "文字起こし済み", "消した"  # 区切り（文字起こしまで済み・要約はまだ） / 消した（元に戻せる間だけ）
STATES = [RECORDING, WAITING, TRANSCRIBING, ORGANIZING, FAILED, DRAFT, CONFIRMED, LATER, SEGMENT, DELETED]
WORKING = (TRANSCRIBING, ORGANIZING)
UNDO_SEC = 5  # 「この区切りを消す」を元に戻せる秒数（画面に出す）。サーバーは少し長く待つ
UNDO_GRACE = 2
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


def _auto_summary() -> bool:
    from app.ai.settings import auto_summary
    return auto_summary()


def _next_state(r, summarize=False) -> str:
    if not r["transcript"] and r["audio_file"]:
        return TRANSCRIBING
    if r["patient_id"]:
        return ORGANIZING if (summarize or _auto_summary()) else SEGMENT
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


def transfer(con, rec_id: int, appt_id=None, summarize=False) -> dict:
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
    nxt = _next_state(r, summarize)
    if nxt == WAITING:
        raise RecError("転送できません")
    if nxt == SEGMENT:  # 文字はもう有る。要約は自動では作らず、区切りとして残す
        con.execute("UPDATE recordings SET state = ?, error = '', updated_at = ? WHERE id = ? AND state = ?",
                    (SEGMENT, now(), rec_id, WAITING))
        con.commit()
    else:
        _claim_and_run(con, rec_id, [WAITING], nxt)
    return get(con, rec_id)


def retry(con, rec_id: int) -> dict:
    r = get(con, rec_id)
    if not r:
        raise RecError("その録音が見つかりません", 404)
    if r["state"] not in (FAILED, LATER):
        raise RecError(f"今の状態（{r['state']}）では再試行できません", 409)
    nxt = _next_state(r)
    if nxt in (WAITING, SEGMENT):
        con.execute("UPDATE recordings SET state = ?, error = '', updated_at = ? WHERE id = ? AND state IN (?, ?)",
                    (nxt, now(), rec_id, FAILED, LATER))
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
        return transfer(con, r["id"], summarize=True)  # 貼り付けは、押した人が下書きを求めている
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

    # ボタン1の録音だけ、歯科の短い一文と主な語を渡して聞き違いを減らす（ボタン2の声には使わない）
    res = tr.transcribe(tr.to_pcm(audio_path.read_bytes()), initial_prompt=fixtalk.initial_prompt() or None)
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
            nxt = (ORGANIZING if _auto_summary() else SEGMENT) if r["patient_id"] else WAITING
            cur = con.execute(
                "UPDATE recordings SET transcript = ?, state = ?, updated_at = ?, fix_off = 0 "
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
        # 聞き違いを直してから5つに分ける。人が直した文字（fix_off=1）は直さない
        items, fixed, fixes = _with_timeout(
            lambda: memo.make_draft(r["transcript"], sens, gw, fix=not r["fix_off"]), timeout_sec("ai"))
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
            con.execute("UPDATE drafts SET body = ?, transcript = ?, items = ?, fixed_transcript = ?, fixes = ? WHERE id = ?",
                        (memo.body_lines(items), cur["transcript"], json.dumps(items, ensure_ascii=False), fixed,
                         json.dumps(fixes, ensure_ascii=False), draft_id))
        elif d:
            draft_id = d["id"]  # 確定済みは触らない
        else:
            c2 = con.execute(
                "INSERT INTO drafts (patient_id, visit_id, kind, body, transcript, status, created_at, "
                "recording_id, items, fixed_transcript, fixes) VALUES (?, ?, 'spoken_summary', ?, ?, 'draft', ?, ?, ?, ?, ?)",
                (cur["patient_id"], cur["visit_id"], memo.body_lines(items), cur["transcript"], now(),
                 rec_id, json.dumps(items, ensure_ascii=False), fixed, json.dumps(fixes, ensure_ascii=False)))
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
    if r["state"] not in (DRAFT, LATER, FAILED, SEGMENT):
        raise RecError(f"今の状態（{r['state']}）では整理し直せません", 409)
    con.execute("UPDATE recordings SET transcript = ?, fix_off = 1 WHERE id = ? AND state IN (?, ?, ?, ?)",
                (transcript, rec_id, DRAFT, LATER, FAILED, SEGMENT))  # 人が直した文字は、聞き違いの自動の直しをしない
    con.commit()
    _claim_and_run(con, rec_id, [DRAFT, LATER, FAILED, SEGMENT], ORGANIZING)
    return get(con, rec_id)


# ---- 区切り: 区切りごとの要約、今日の分をまとめて要約、消す ----

def summarize_segment(con, rec_id: int) -> dict:
    """この区切りの文字だけを要約する。"""
    r = get(con, rec_id)
    if not r:
        raise RecError("その区切りが見つかりません", 404)
    if not r["patient_id"]:
        raise RecError("先に患者様と診療回を選んでください", 409)
    if not r["transcript"]:
        raise RecError("文字がありません", 409)
    if r["state"] == DRAFT:
        raise RecError("この区切りはもう要約があります", 409)
    if r["state"] not in (SEGMENT, FAILED, LATER):
        raise RecError(f"今の状態（{r['state']}）では要約できません", 409)
    _claim_and_run(con, rec_id, [SEGMENT, FAILED, LATER], ORGANIZING)
    return get(con, rec_id)


def segments_of_visit(con, visit_id: int):
    """診療回の区切りを、録音した順に。消した区切りは含めない。"""
    return [dict(x) for x in con.execute(
        "SELECT * FROM recordings WHERE visit_id = ? AND state != ? ORDER BY rec_no, id", (visit_id, DELETED))]


def combine(con, appt_id: int) -> dict:
    """その診療回の区切りを、録音した順に全部つないで1つの要約にする。前の区切りごとの要約は置き換える。"""
    v = con.execute("SELECT v.id FROM visits v WHERE v.appointment_id = ?", (appt_id,)).fetchone()
    if not v:
        raise RecError("その診療回が見つかりません", 404)
    segs = segments_of_visit(con, v["id"])
    if any(x["state"] in WORKING or x["state"] == RECORDING for x in segs):
        raise RecError("録音か文字起こしの途中の区切りがあります。終わってからお試しください", 409)
    use = [x for x in segs if x["state"] in (SEGMENT, DRAFT, LATER, FAILED) and x["transcript"]]
    if not use:
        raise RecError("まとめる区切りがありません", 409)
    for x in use:
        cur = con.execute("UPDATE recordings SET state = ?, attempt = attempt + 1, error = '', updated_at = ? "
                          "WHERE id = ? AND state = ?", (ORGANIZING, now(), x["id"], x["state"]))
        if cur.rowcount != 1:
            con.rollback()
            raise RecError("区切りの状態が変わりました。もう一度お試しください", 409)
    con.commit()
    marks = {}
    for x in use:
        marks[x["id"]] = con.execute("SELECT attempt FROM recordings WHERE id = ?", (x["id"],)).fetchone()[0]
        with _live_lock:
            _live[(x["id"], marks[x["id"]])] = True
    threading.Thread(target=_combine_job, args=(use, marks), daemon=True).start()
    return {"count": len(use), "ids": [x["id"] for x in use]}


def _restore_after_combine_fail(con, use, marks, why):
    for x in use:
        if x["state"] == DRAFT and x["draft_id"]:
            back = DRAFT
        else:
            back = x["state"] if x["state"] in (FAILED, LATER) else SEGMENT
        con.execute("UPDATE recordings SET state = ?, error = ?, updated_at = ? WHERE id = ? AND attempt = ? AND state = ?",
                    (back, why, now(), x["id"], marks[x["id"]], ORGANIZING))
    con.commit()


def _combine_job(use, marks):
    con = connect()
    try:
        from app.routers import ai as ai_router  # 試験が make_gateway を差し替えられるように、使うときに読む

        try:
            sens = sensitive_from_db(con)
            gw = ai_router.make_gateway()
            texts = [x["transcript"] for x in use]
            offs = [bool(x["fix_off"]) for x in use]
            items, fixed, fixes = _with_timeout(lambda: memo.make_combined(texts, offs, sens, gw), timeout_sec("ai"))
        except Exception as e:  # noqa: BLE001
            if isinstance(e, TimeoutError):
                why = "時間切れ（もう一度お試しください）"
            elif isinstance(e, ClaudeUnavailable):
                why = "Claude が使えません（鍵が設定されていません）"
            else:
                why = redact_key(f"{type(e).__name__}: {str(e)[:80]}")
            _restore_after_combine_fail(con, use, marks, why)
            return
        con.execute("BEGIN IMMEDIATE")
        try:
            ids = [x["id"] for x in use]
            q = ",".join("?" * len(ids))
            live = con.execute(f"SELECT id, attempt, state FROM recordings WHERE id IN ({q})", ids).fetchall()
            if len(live) != len(ids) or any(r["state"] != ORGANIZING or r["attempt"] != marks[r["id"]] for r in live):
                con.rollback()
                return  # 遅れて届いた結果は捨てる（消された・やり直された）
            last = use[-1]
            joined = "\n".join(x["transcript"] for x in use)
            for d in {x["draft_id"] for x in use if x["draft_id"]}:  # 前の区切りごとの要約・まとめの要約は置き換える（確定済みは触らない）
                con.execute("DELETE FROM drafts WHERE id = ? AND status = 'draft'", (d,))
            c2 = con.execute(
                "INSERT INTO drafts (patient_id, visit_id, kind, body, transcript, status, created_at, "
                "recording_id, items, fixed_transcript, fixes, combined) VALUES (?, ?, 'spoken_summary', ?, ?, 'draft', ?, ?, ?, ?, ?, 1)",
                (last["patient_id"], last["visit_id"], memo.body_lines(items), joined, now(), last["id"],
                 json.dumps(items, ensure_ascii=False), fixed, json.dumps(fixes, ensure_ascii=False)))
            con.execute(f"UPDATE recordings SET state = ?, draft_id = ?, updated_at = ? WHERE id IN ({q})",
                        [DRAFT, c2.lastrowid, now(), *ids])
            con.commit()
        except Exception:
            con.rollback()
            raise
    finally:
        con.close()
        with _live_lock:
            for i, a in marks.items():
                _live.pop((i, a), None)


def delete_segment(con, rec_id: int) -> dict:
    """この区切りを消す。すぐ消えたことにして、UNDO_SEC 秒だけ元に戻せる。そのあと音声と文字を消す。"""
    r = get(con, rec_id)
    if not r:
        raise RecError("その区切りが見つかりません", 404)
    if r["state"] not in (SEGMENT, DRAFT, FAILED, LATER, WAITING):
        raise RecError(f"今の状態（{r['state']}）では消せません", 409)
    cur = con.execute("UPDATE recordings SET prev_state = state, state = ?, deleted_at = ?, updated_at = ? "
                      "WHERE id = ? AND state = ?", (DELETED, now(), now(), rec_id, r["state"]))
    con.commit()
    if cur.rowcount != 1:
        raise RecError("区切りの状態が変わりました", 409)
    t = threading.Timer(UNDO_SEC + UNDO_GRACE + 1, _purge_later)
    t.daemon = True
    t.start()
    return {"deleted": rec_id, "undo_sec": UNDO_SEC}


def undelete_segment(con, rec_id: int) -> dict:
    r = get(con, rec_id)
    if not r or r["state"] != DELETED:
        raise RecError("元に戻せる区切りがありません", 409)
    age = (datetime.now() - datetime.fromisoformat(r["deleted_at"])).total_seconds()
    if age > UNDO_SEC + UNDO_GRACE:
        purge_deleted(con)
        raise RecError("元に戻せる時間が過ぎました", 409)
    con.execute("UPDATE recordings SET state = ?, deleted_at = NULL, prev_state = '', updated_at = ? WHERE id = ? AND state = ?",
                (r["prev_state"] or SEGMENT, now(), rec_id, DELETED))
    con.commit()
    return get(con, rec_id)


def _purge_later():
    con = connect()
    try:
        purge_deleted(con)
    finally:
        con.close()


def purge_deleted(con):
    """元に戻せる時間が過ぎた区切りの、音声・文字・その区切りの話が入った下書きを消す。"""
    rows = con.execute("SELECT * FROM recordings WHERE state = ? AND deleted_at IS NOT NULL", (DELETED,)).fetchall()
    for r in rows:
        age = (datetime.now() - datetime.fromisoformat(r["deleted_at"])).total_seconds()
        if age <= UNDO_SEC + UNDO_GRACE:
            continue
        if r["audio_file"]:
            try:
                (audio_dir() / Path(r["audio_file"]).name).unlink()
            except OSError:
                pass
        d = r["draft_id"]
        if d:
            row = con.execute("SELECT status FROM drafts WHERE id = ?", (d,)).fetchone()
            if row and row["status"] == "draft":
                con.execute("DELETE FROM drafts WHERE id = ?", (d,))
                con.execute("UPDATE recordings SET state = ?, draft_id = NULL, updated_at = ? "
                            "WHERE draft_id = ? AND id != ? AND state = ?", (SEGMENT, now(), d, r["id"], DRAFT))
        con.execute("DELETE FROM recordings WHERE id = ?", (r["id"],))
    con.commit()
