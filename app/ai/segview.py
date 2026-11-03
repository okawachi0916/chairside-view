"""画面に出す「区切り」の一覧（話した内容の整理の全画面）。録音した順。氏名は出さない。"""
import json
from datetime import datetime

from app.ai import recpipe

LABEL = {
    recpipe.SEGMENT: "まだ要約していません",
    recpipe.TRANSCRIBING: "文字にしています…",
    recpipe.ORGANIZING: "要約しています…",
    recpipe.RECORDING: "録音中",
    recpipe.WAITING: "転送待ち",
    recpipe.FAILED: "失敗",
    recpipe.DRAFT: "要約あり",
    recpipe.LATER: "あとで直す",
}


def _hm(started_at: str) -> str:
    try:
        return datetime.fromisoformat(started_at).strftime("%H:%M")
    except ValueError:
        return ""


def undo_left(deleted_at) -> float:
    """元に戻せる残り秒。過ぎていれば 0。"""
    try:
        age = (datetime.now() - datetime.fromisoformat(deleted_at)).total_seconds()
    except (TypeError, ValueError):
        return 0
    return max(0.0, recpipe.UNDO_SEC - age)


def list_for_visit(con, visit_id):
    """診療回の区切り。消した直後（元に戻せる間）の区切りも、印をつけて含める。"""
    if not visit_id:
        return []
    recpipe.purge_deleted(con)
    out = []
    for r in con.execute("SELECT * FROM recordings WHERE visit_id = ? AND patient_id IS NOT NULL ORDER BY rec_no, id",
                         (visit_id,)):
        deleted = r["state"] == recpipe.DELETED
        if deleted and undo_left(r["deleted_at"]) <= 0:
            continue
        lines = []
        if r["draft_id"] and r["state"] == recpipe.DRAFT:
            d = con.execute("SELECT body, combined, status FROM drafts WHERE id = ?", (r["draft_id"],)).fetchone()
            if d and not d["combined"]:
                lines = [x for x in d["body"].split("\n") if x]
        out.append({
            "id": r["id"], "rec_no": r["rec_no"], "time": _hm(r["started_at"]), "state": r["state"],
            "label": LABEL.get(r["state"], r["state"]), "text": r["transcript"], "lines": lines,
            "error": r["error"], "draft_id": r["draft_id"], "deleted": deleted,
            "undo_left": undo_left(r["deleted_at"]) if deleted else 0,
        })
    return out


def combined_draft(con, visit_id):
    """この診療回の、まとめた要約（確定前）。無ければ None。"""
    if not visit_id:
        return None
    r = con.execute("SELECT id FROM drafts WHERE visit_id = ? AND combined = 1 AND status = 'draft' ORDER BY id DESC",
                    (visit_id,)).fetchone()
    return r["id"] if r else None


def to_json(segments):
    return json.dumps(segments, ensure_ascii=False)
