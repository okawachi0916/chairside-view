"""下書きの確定。確定するまで診療メモにも治療計画にも入れない。

- 確定すると、下書きが過去の診療メモ (clinical_notes) に入る。
- 治療計画は、人が選んだ「追加・変更・削除」だけ反映する。選ばれなかった計画（話に出ていない歯の計画など）はそのまま残す。
  変更・削除された古い計画は superseded_on に日付を付けて残す。
- 「他の画面にも入れる」（歯ごとの処置・次回の予定・治療方針。app/ai/reflect.py）も、人が選んだものだけ、診療メモと同じ取引の中で書く。
  変えた所は app/ai/journal.py が1行ずつ残し、その日のうちは cancel_record で全部戻せる。書けなかったら確定ごと止める。
- 確定したら音声を消す。
"""
import json
import re
from pathlib import Path

from app.ai import memo, recpipe, reflect
from app.ai.journal import Journal, undo
from app.ai.recpipe import RecError, audio_dir, now

TOOTH = re.compile(r"(?:右上|右下|左上|左下)\s*[1-8]\s*番")


def check_items(items) -> dict:
    """人が直した5つの項目を調べる。形が違えば RecError。"""
    if not isinstance(items, dict) or set(items) != set(memo.KEYS):
        raise RecError("項目の形が違います")
    out = {}
    for k in memo.KEYS:
        rows = items[k]
        if not isinstance(rows, list) or len(rows) > 50:
            raise RecError("項目の形が違います")
        kept = []
        for r in rows:
            if not isinstance(r, dict) or not isinstance(r.get("text"), str) or not isinstance(r.get("quote", ""), str):
                raise RecError("項目の形が違います")
            text = r["text"].strip()
            if text:  # 空にした行は消えたものとして扱う
                kept.append({"text": text, "quote": r.get("quote") or ""})  # 長さで黙って切らない
        out[k] = kept
    return out


def plans_active(con, patient_id: int) -> list:
    return [dict(r) for r in con.execute(
        "SELECT id, seq, body FROM treatment_plans WHERE patient_id = ? AND kind = 'plan' AND superseded_on IS NULL "
        "ORDER BY seq, id", (patient_id,))]


def draft_of(con, draft_id: int):
    d = con.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
    if not d:
        raise RecError("その下書きが見つかりません", 404)
    return d


def save_items(con, draft_id: int, items) -> dict:
    d = draft_of(con, draft_id)
    if d["status"] != "draft":
        raise RecError("確定済みの下書きは直せません", 409)
    items = check_items(items)
    con.execute("UPDATE drafts SET items = ?, body = ? WHERE id = ? AND status = 'draft'",
                (json.dumps(items, ensure_ascii=False),
                 memo.body_lines(items, recpipe.visit_day(con, d["visit_id"])), draft_id))
    con.commit()
    return {"saved": True}


def confirm(con, draft_id: int, items, plan=None, picks=None) -> dict:
    """記録する。診療メモ・治療計画・「他の画面にも入れる」で選んだもの（歯の状態・治療歴・次回の予定・治療方針）・予約の「済み」を、
    全部同じ1つの取引で書く。変えた所は Journal が1行ずつ残し、その日のうちの取り消し（cancel_record）に使う。
    どこか1つでも書けなければ、記録ごと止める（RecError）。"""
    plan = plan or {}
    items = check_items(items)
    if not any(items[k] for k in memo.KEYS):
        raise RecError("確定する内容がありません")
    con.execute("BEGIN IMMEDIATE")
    try:
        d = con.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not d:
            raise RecError("その下書きが見つかりません", 404)
        if d["status"] != "draft":
            raise RecError("この下書きはもう確定しています", 409)
        recs = con.execute("SELECT * FROM recordings WHERE draft_id = ? OR id = ?",
                           (draft_id, d["recording_id"] or -1)).fetchall()  # まとめの要約は、区切りが何件も同じ下書きにつながる
        if any(r["state"] in recpipe.WORKING for r in recs):
            raise RecError("整理の途中です。終わってから確定してください", 409)
        v = con.execute("SELECT * FROM visits WHERE id = ? AND patient_id = ?", (d["visit_id"], d["patient_id"])).fetchone()
        if not v:
            raise RecError("診療回が見つかりません", 409)
        pid, day = d["patient_id"], v["visit_date"]
        j = Journal(con, draft_id, pid)

        # 治療計画: 人が選んだものだけ
        active = {p["id"]: p for p in plans_active(con, pid)}
        changes = plan.get("changes") or []
        deletes = [int(x) for x in (plan.get("deletes") or [])]
        adds = [str(t).strip() for t in (plan.get("adds") or []) if str(t).strip()]
        touched = [int(c["old_id"]) for c in changes] + deletes
        if len(set(touched)) != len(touched) or any(i not in active for i in touched):
            raise RecError("計画の選び方が正しくありません")
        seq = max([p["seq"] for p in active.values()] + [0])
        for c in changes:
            text = str(c.get("text") or "").strip()
            if not text:
                raise RecError("新しい計画の文字が空です")
            old = active[int(c["old_id"])]
            j.update("treatment_plans", old["id"], superseded_on=day)
            j.insert("treatment_plans", patient_id=pid, seq=old["seq"], kind="plan", body=text)  # 変えた計画は、古い計画の順番を引き継ぐ
        for i in deletes:
            j.update("treatment_plans", i, superseded_on=day)
        for t in adds:
            seq += 1
            j.insert("treatment_plans", patient_id=pid, seq=seq, kind="plan", body=t)

        # 他の画面にも入れる（歯の状態・治療歴・次回の予定・治療方針）: 人が選んだものだけ
        reflect.apply(j, day, items, picks)

        body = memo.body_lines(items, day)
        j.insert("clinical_notes", patient_id=pid, visit_id=d["visit_id"], note_date=day, author_role=v["role"] or "doctor", body=body)
        j.update("drafts", draft_id, status="confirmed", confirmed_at=now(), items=json.dumps(items, ensure_ascii=False), body=body)
        if v["appointment_id"]:  # その診療回の予約を「済み」にする（取り消せば「予約中」へ戻る）
            j.update("appointments", v["appointment_id"], status="done")
        audios = []
        for rec in recs:
            if rec["state"] == recpipe.DELETED:
                continue
            audios.append(rec["audio_file"])
            j.update("recordings", rec["id"], state=recpipe.CONFIRMED, updated_at=now())
            con.execute("UPDATE recordings SET audio_file = '' WHERE id = ?", (rec["id"],))  # 音声は消す。取り消しても戻せない（戻さない）
        con.commit()
    except Exception:
        con.rollback()
        raise
    for audio in audios:  # 確定したら音声を消す
        if not audio:
            continue
        recpipe.remove_audio(audio, "確定した録音")
    return {"confirmed": True, "draft_id": draft_id}


NOT_TODAY = "その日のうちだけ取り消せます"


def cancel_record(con, draft_id: int) -> dict:
    """記録を取り消す。その記録で変わった所を全部、記録する前に戻し、下書きに戻す。
    取り消せるのは、記録した日（パソコンの今日）のうち。あとの記録が同じ患者様にあるときは、先にそちらから取り消す。"""
    from app.today import today as app_today

    con.execute("BEGIN IMMEDIATE")
    try:
        d = con.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        if not d:
            raise RecError("その下書きが見つかりません", 404)
        if d["status"] != "confirmed":
            raise RecError("取り消せる記録がありません", 409)
        rows = con.execute("SELECT recorded_on FROM record_changes WHERE draft_id = ? LIMIT 1", (draft_id,)).fetchone()
        if not rows:
            raise RecError("この記録には、取り消すための記録がありません（取り消せません）", 409)
        if rows["recorded_on"] != app_today():
            raise RecError(NOT_TODAY, 409)
        later = con.execute("SELECT 1 FROM record_changes WHERE patient_id = ? AND draft_id <> ? AND id > "
                            "(SELECT MAX(id) FROM record_changes WHERE draft_id = ?) LIMIT 1", (d["patient_id"], draft_id, draft_id)).fetchone()
        if later:
            raise RecError("あとの記録があります。先にそちらを取り消してください", 409)
        n = undo(con, draft_id)
        con.commit()
    except Exception:
        con.rollback()
        raise
    return {"cancelled": True, "draft_id": draft_id, "changes": n}


def last_cancellable(con, appt_id: int) -> int:
    """この予約の診療回で、いちばん新しく記録した下書き。無ければ RecError。"""
    row = con.execute(
        "SELECT d.id FROM drafts d JOIN visits v ON v.id = d.visit_id WHERE v.appointment_id = ? AND d.status = 'confirmed' "
        "ORDER BY d.id DESC LIMIT 1", (appt_id,)).fetchone()
    if not row:
        raise RecError("取り消せる記録がありません", 409)
    return row["id"]


# ---- 追記が必要な患者様 ----

def pending_rows(con, patient_id=None):
    """確定していない診療メモ（下書き・失敗・後で直す・要約していない区切り）。録音から作ったものだけ。"""
    sql = ("SELECT r.id AS rec_id, r.state, r.patient_id, r.visit_id, r.draft_id, p.chart_no, v.appointment_id "
           "FROM recordings r JOIN patients p ON p.id = r.patient_id LEFT JOIN visits v ON v.id = r.visit_id "
           "WHERE r.state IN (?, ?, ?, ?)")
    args = [recpipe.DRAFT, recpipe.FAILED, recpipe.LATER, recpipe.SEGMENT]
    if patient_id:
        sql += " AND r.patient_id = ?"
        args.append(patient_id)
    out = []
    for r in con.execute(sql + " ORDER BY r.id", args):
        if r["state"] == recpipe.DRAFT:
            d = con.execute("SELECT status FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
            if not d or d["status"] != "draft":
                continue
        out.append(dict(r))
    return out
