"""下書きの確定。確定するまで診療メモにも治療計画にも入れない。

- 確定すると、下書きが過去の診療メモ (clinical_notes) に入る。
- 治療計画は、人が選んだ「追加・変更・削除」だけ反映する。選ばれなかった計画（話に出ていない歯の計画など）はそのまま残す。
  変更・削除された古い計画は superseded_on に日付を付けて残す。
- 確定したら音声を消す。
"""
import json
import re
from pathlib import Path

from app.ai import memo, recpipe
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
                kept.append({"text": text[:500], "quote": (r.get("quote") or "")[:500]})
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
                (json.dumps(items, ensure_ascii=False), memo.body_lines(items), draft_id))
    con.commit()
    return {"saved": True}


def confirm(con, draft_id: int, items, plan=None) -> dict:
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
        rec = con.execute("SELECT * FROM recordings WHERE draft_id = ? OR id = ?",
                          (draft_id, d["recording_id"] or -1)).fetchone()
        if rec and rec["state"] in recpipe.WORKING:
            raise RecError("整理の途中です。終わってから確定してください", 409)
        v = con.execute("SELECT * FROM visits WHERE id = ? AND patient_id = ?", (d["visit_id"], d["patient_id"])).fetchone()
        if not v:
            raise RecError("診療回が見つかりません", 409)
        pid, day = d["patient_id"], v["visit_date"]

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
            con.execute("UPDATE treatment_plans SET superseded_on = ? WHERE id = ?", (day, int(c["old_id"])))
            seq += 1
            con.execute("INSERT INTO treatment_plans (patient_id, seq, kind, body) VALUES (?, ?, 'plan', ?)", (pid, seq, text))
        for i in deletes:
            con.execute("UPDATE treatment_plans SET superseded_on = ? WHERE id = ?", (day, i))
        for t in adds:
            seq += 1
            con.execute("INSERT INTO treatment_plans (patient_id, seq, kind, body) VALUES (?, ?, 'plan', ?)", (pid, seq, t))

        body = memo.body_lines(items)
        con.execute("INSERT INTO clinical_notes (patient_id, visit_id, note_date, author_role, body) VALUES (?, ?, ?, ?, ?)",
                    (pid, d["visit_id"], day, v["role"] or "doctor", body))
        con.execute("UPDATE drafts SET status = 'confirmed', confirmed_at = ?, items = ?, body = ? WHERE id = ?",
                    (now(), json.dumps(items, ensure_ascii=False), body, draft_id))
        audio = None
        if rec:
            audio = rec["audio_file"]
            con.execute("UPDATE recordings SET state = ?, audio_file = '', updated_at = ? WHERE id = ?",
                        (recpipe.CONFIRMED, now(), rec["id"]))
        con.commit()
    except Exception:
        con.rollback()
        raise
    if audio:  # 確定したら音声を消す
        try:
            (audio_dir() / Path(audio).name).unlink()
        except OSError:
            pass
    return {"confirmed": True, "draft_id": draft_id}


# ---- 追記が必要な患者様 ----

def pending_rows(con, patient_id=None):
    """確定していない診療メモ（下書き・失敗・後で直す）。録音から作ったものだけ。"""
    sql = ("SELECT r.id AS rec_id, r.state, r.patient_id, r.visit_id, r.draft_id, p.chart_no, v.appointment_id "
           "FROM recordings r JOIN patients p ON p.id = r.patient_id LEFT JOIN visits v ON v.id = r.visit_id "
           "WHERE r.state IN (?, ?, ?)")
    args = [recpipe.DRAFT, recpipe.FAILED, recpipe.LATER]
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
