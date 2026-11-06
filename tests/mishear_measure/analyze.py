"""実測の結果（results.json）を声の操作に通し、言った言葉と同じ操作になるかを数える。"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.voice.interpret import interpret  # noqa: E402


def key(r):
    n = str(r["numbers"][0]) if r.get("numbers") else (str(r["arg"]) if r.get("arg") is not None else None)  # 「いち番」(arg) と「1番」(numbers) は同じ番号
    return (r["kind"], r.get("action"), n)


def main():
    if "--off" in sys.argv:  # 表を使わないときの数（比べるため）
        import app.voice.interpret as I
        I.mishear_variants = lambda s: []
    rows = json.loads(Path(__file__).with_name("results.json").read_text(encoding="utf-8"))["結果"]
    bad = collections.Counter()
    n_bad = n_garbage = 0
    for x in rows:
        want = interpret(x["言った"])
        if want["kind"] != "操作":
            continue
        got = interpret(x["聞こえた"])
        if key(got) != key(want):
            n_bad += 1
            bad[(x["言った"], x["聞こえた"].strip())] += 1
    print("通らなかった:", n_bad, "/", len(rows))
    for (a, h), c in sorted(bad.items()):
        print(f"{a} <= {h}  x{c}")


main()
