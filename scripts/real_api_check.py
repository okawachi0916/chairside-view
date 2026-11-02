"""本物の Claude を呼んで確かめる（普段の試験では動かさない）。

使い方:
  python scripts/real_api_check.py            モデル一覧→最新の Sonnet を config/model.json に書く→短文を1回送る
  python scripts/real_api_check.py --no-write モデル名を書き換えず、今の設定で送るだけ
  python scripts/real_api_check.py --questions G16 の質問9問を本物の Claude に1回ずつ通し、正解と照らす
結果は docs/実API結果.md に追記する。鍵は出力にも記録にも出さない。
"""
import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import anthropic  # noqa: E402

from app.ai.settings import ClaudeUnavailable, load_key, load_model, redact_key, MODEL_JSON  # noqa: E402

RESULT_MD = ROOT / "docs" / "実API結果.md"
PROMPT = "こんにちは。1文で返事をしてください。"


def newest_sonnet(client) -> str:
    # 一覧は新しい順で返る。名前に sonnet を含むものの先頭を取る。
    names = [m.id for m in client.models.list(limit=100) if "sonnet" in m.id.lower()]
    if not names:
        raise SystemExit("使える Sonnet が一覧に見つかりません")
    return names[0]


def commit_id() -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "不明"


def run_questions() -> int:
    """tests/questions.json の質問を本物の Claude に通す。実データでなく、作り直した架空データを使う。"""
    import os
    import tempfile

    tmp = tempfile.mkdtemp(prefix="cv_g16_")
    os.environ["CV_DATA_DIR"] = tmp
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], check=True, capture_output=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    from app.ai import ask as ask_mod
    from app.ai.gateway import Gateway
    from app.db import connect

    spec = json.loads((ROOT / "tests" / "questions.json").read_text(encoding="utf-8"))
    con = connect()
    pid = con.execute("SELECT id FROM patients WHERE chart_no = ?", (spec["patient"]["chart_no"],)).fetchone()["id"]
    gw = Gateway(log_dir=Path(tmp) / "sent_log")
    rows, ok_all = [], True
    for c in spec["cases"]:
        exp = c["expect"]
        try:
            res = ask_mod.answer(c["text"], con, pid, gw)
        except ClaudeUnavailable as e:
            print(e)
            return 2
        good = res["result"] == exp["result"] and res["sends"] == c["sends"]
        if good and exp["result"] == "found":
            good = res["ref"] == exp["ref"]
        ok_all &= good
        got = res.get("ref") or res["result"]
        rows.append((c["id"], c["text"], exp.get("ref") or exp["result"], got, res["sends"], good))
        print(c["id"], "合格" if good else "不合格", "送信", res["sends"], "期待", exp.get("ref") or exp["result"], "結果", got)
    sent = "".join(p.read_text(encoding="utf-8") for p in (Path(tmp) / "sent_log").glob("*.jsonl"))
    sample = json.loads(sent.splitlines()[0])["user"] if sent else ""
    RESULT_MD.parent.mkdir(exist_ok=True)
    NL = chr(10)
    table = "".join(f"  - {r[0]}, {r[1]}, {r[2]}, {r[3]}, {r[4]}, {'合格' if r[5] else '不合格'}{NL}" for r in rows)
    with RESULT_MD.open("a", encoding="utf-8") as f:
        f.write(
            f"{NL}## {datetime.now():%Y-%m-%d %H:%M} G16 質問9問＋聞き取り失敗1例{NL}"
            f"- コミット: {commit_id()}{NL}- モデル: {load_model()}{NL}"
            f"- 入力（伏字後の1問目の送信文）: {sample[:600]}{NL}"
            f"- 判定の表（番号, 問い, 期待, 結果, 送信回数, 合否）:{NL}{table}"
            f"- 判定: {'全部合格' if ok_all else '不合格あり'}{NL}"
        )
    return 0 if ok_all else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--questions", action="store_true")
    args = ap.parse_args()
    if args.questions:
        return run_questions()
    try:
        client = anthropic.Anthropic(api_key=load_key())  # 鍵は明示して渡す。ANTHROPIC_API_KEY は使わない
    except ClaudeUnavailable as e:
        print(e)
        return 2
    try:
        if not args.no_write:
            model = newest_sonnet(client)
            MODEL_JSON.parent.mkdir(exist_ok=True)
            MODEL_JSON.write_text(json.dumps({"model": model}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        model = load_model()
        res = client.messages.create(model=model, max_tokens=100, messages=[{"role": "user", "content": PROMPT}])
        text = "".join(b.text for b in res.content if getattr(b, "type", "") == "text")
        ok = bool(text.strip())
    except Exception as e:  # noqa: BLE001
        print("失敗:", redact_key(f"{type(e).__name__}: {e}")[:200])
        return 1
    print("モデル:", model)
    print("応答:", redact_key(text)[:100])
    RESULT_MD.parent.mkdir(exist_ok=True)
    if not RESULT_MD.exists():
        RESULT_MD.write_text("# 実API結果\n\n本物の Claude を呼んだ確認の記録。\n", encoding="utf-8")
    with RESULT_MD.open("a", encoding="utf-8") as f:
        f.write(
            f"\n## {datetime.now():%Y-%m-%d %H:%M} 接続の確認\n"
            f"- コミット: {commit_id()}\n- モデル: {model}\n- 入力: {PROMPT}\n"
            f"- 判定: {'合格（応答あり）' if ok else '不合格（応答が空）'}\n"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
