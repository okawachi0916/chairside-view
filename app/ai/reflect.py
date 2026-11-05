"""G19m: 記録のとき「他の画面にも入れる候補」。歯ごとの処置（G19l の toothtx.py）に、次回の予定・治療方針を足して広げた1つの仕組み。

- 候補は、下書きの項目から作る（歯の処置は toothtx.candidates、次回の予定は「次回の予定」の各行、治療方針は「今後の治療方針」の各行）。
- 画面ではどれも、はじめから印が付いていて、人が外したものだけが入らない。サーバーは、印の付いた候補の印（key）だけを受け取る。
- 次回の予定: 今の次回の予定（kind=next）をその日付で古くし（superseded_on）、印のある行を新しい次回の予定にする。受付の「次回」とAIの「次回は？」が読む。
- 治療方針: 今の治療方針（kind=policy）をその日付で古くして残し、印のある行を新しい治療方針にする。古い方針は全画面で見られる。
- 書き込みは Journal（app/ai/journal.py）を通す。戻せるように、変えた所を1行ずつ残す。診断も状態の決め打ちもしない（言葉は話した行のまま）。
"""
import re

from app.ai import toothtx
from app.ai.recpipe import RecError

PREFIX = {"next": "next_plan", "policy": "future_policy"}
TITLE = {"next": "次回の予定", "policy": "治療方針"}


def _text(s: str) -> str:
    return re.sub(r"[。.]+$", "", (s or "").strip())


def _current(con, patient_id: int, kind: str) -> list:
    return [r["body"] for r in con.execute(
        "SELECT body FROM treatment_plans WHERE patient_id = ? AND kind = ? AND superseded_on IS NULL ORDER BY seq, id", (patient_id, kind))]


def candidates(con, patient_id: int, items: dict) -> list:
    out = []
    for c in toothtx.candidates(con, patient_id, items):
        out.append({**c, "kind": "tooth", "title": f"{c['site']} {c['word']}"})
    for kind, section in PREFIX.items():
        now = "、".join(_current(con, patient_id, kind)) or "（なし）"
        for i, r in enumerate((items or {}).get(section, [])):
            t = _text(r.get("text"))
            if t:
                out.append({"key": f"{kind}:{i}:{t}", "kind": kind, "title": TITLE[kind], "row": t, "before": now, "after": t})
    return out


def split(picked) -> tuple:
    """選んだ印を、歯ごとの処置と、そのほかに分ける。形が違えば RecError。"""
    if picked is None:
        return [], []
    if not isinstance(picked, list) or any(not isinstance(k, str) for k in picked) or len(set(picked)) != len(picked):
        raise RecError("他の画面へ入れる選び方が正しくありません")
    other = [k for k in picked if k.split(":")[0] in PREFIX]
    return [k for k in picked if k not in other], other


def apply(j, day: str, items: dict, picked) -> None:
    teeth, other = split(picked)
    toothtx.apply(j, day, items, teeth)
    if not other:
        return
    con, pid = j.con, j.patient_id
    cands = {c["key"]: c for c in candidates(con, pid, items) if c["kind"] in PREFIX}
    unknown = [k for k in other if k not in cands]
    if unknown:
        raise RecError("候補に無いものが選ばれています: " + "、".join(unknown))
    for kind in PREFIX:
        chosen = [cands[k]["after"] for k in other if cands[k]["kind"] == kind]
        if not chosen:
            continue
        for r in con.execute("SELECT id FROM treatment_plans WHERE patient_id = ? AND kind = ? AND superseded_on IS NULL ORDER BY id",
                             (pid, kind)).fetchall():
            j.update("treatment_plans", r["id"], superseded_on=day)  # 古い方は消さず、日付を付けて残す
        for n, t in enumerate(chosen, 1):
            j.insert("treatment_plans", patient_id=pid, seq=0 if kind == "next" else n, kind=kind, body=t)
