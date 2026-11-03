"""よく聞く質問（前回・アレルギー・薬・次回）は Claude を通さず、記録から直接選ぶ。

言葉の表は config/quick_answers.json。表の言葉と「つなぎの言葉」だけでできた短い質問にだけ当たる。
ほかの言葉が混ざる質問、2つ以上の項目に当たる質問、記録が見つからない質問は、当てずに Claude へ回す。
"""
import json
import re
import unicodedata
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "config" / "quick_answers.json"


def load_table() -> dict:
    """読めない・壊れているときは空の表。その場合は全部 Claude へ回る。"""
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        if isinstance(data.get("entries"), list) and isinstance(data.get("fillers", []), list):
            return data
    except (OSError, ValueError, AttributeError):
        pass
    return {"fillers": [], "entries": []}


def _norm(text: str) -> str:
    s = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[\s、。，．,.!?！？「」『』]+", "", s)


def _leftover(s: str, words) -> str:
    for w in sorted({_norm(x) for x in words if x}, key=len, reverse=True):
        s = s.replace(w, "")
    return s


def pick_entry(text: str, table: dict | None = None):
    """当たる項目を1つ返す。当たらない・2つ以上に当たる・ほかの言葉が混ざるときは None。"""
    table = table or load_table()
    s = _norm(text)
    if not s:
        return None
    hits = []
    for e in table["entries"]:
        trig = [t for t in e.get("triggers", []) if t and _norm(t) in s]
        if trig:
            hits.append(e)
    if len(hits) != 1:
        return None
    entry = hits[0]
    rest = _leftover(s, list(entry["triggers"]) + list(table.get("fillers", [])))
    return entry if rest == "" else None


def pick_record(entry: dict, records):
    """項目の指定に合う記録のうち先頭を返す。無ければ None（Claude へ回す）。"""
    target = entry.get("target", {})
    for r in records:
        if r.part != target.get("part"):
            continue
        words = target.get("contains") or []
        if words and not any(w in "".join(r.lines) for w in words):
            continue
        return r
    return None


def quick_record(text: str, records, table: dict | None = None):
    entry = pick_entry(text, table)
    return pick_record(entry, records) if entry else None
