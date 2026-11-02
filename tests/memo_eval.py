"""tests/memo_cases.json の期待を、整理の結果に当てはめて判定する（試験と scripts/real_api_check.py が使う）。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "tests" / "memo_cases.json").read_text(encoding="utf-8"))
CASES = SPEC["cases"]


def texts(items: dict, sections) -> str:
    return "\n".join(r["text"] for k in sections for r in items.get(k, []))


def judge(items: dict, rules) -> list:
    """合わない点の一覧。空なら期待どおり。抜き出し (quote) は話した言葉のままなので、禁止語は text だけで見る。"""
    bad = []
    for rule in rules:
        if "any" in rule:
            t = texts(items, rule["sections"])
            if not any(w in t for w in rule["any"]):
                bad.append(f"{'/'.join(rule['sections'])} に {rule['any']} のどれも無い")
        if "words" in rule:
            t = texts(items, rule["forbid_sections"])
            for w in rule["words"]:
                if w in t:
                    bad.append(f"{'/'.join(rule['forbid_sections'])} に出てはいけない「{w}」がある")
    return bad
