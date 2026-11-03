"""本物の Claude を呼んで確かめる（普段の試験では動かさない）。

使い方:
  python scripts/real_api_check.py            モデル一覧→最新の Sonnet を config/model.json に書く→短文を1回送る
  python scripts/real_api_check.py --no-write モデル名を書き換えず、今の設定で送るだけ
  python scripts/real_api_check.py --questions G16 の質問9問を本物の Claude に1回ずつ通し、正解と照らす
      --claude-only  よく聞く質問の表を使わず、全部 Claude に聞く（モデルの比較用）
      --model 名前    質問だけ別のモデルで試す（config は書き換えない）
  python scripts/real_api_check.py --memo      G17 の話6通りを本物の Claude で5つに分け、期待と照らす
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


def run_questions(claude_only: bool = False, model: str = "") -> int:
    """tests/questions.json の質問を本物の Claude に通す。実データでなく、作り直した架空データを使う。

    claude_only: よく聞く質問の表を使わず、全部 Claude に聞く（モデルの比較用）。
    model: 質問だけこのモデルで試す（config は書き換えない。一時の設定ファイルを使う）。
    """
    import os
    import tempfile
    import time

    tmp = tempfile.mkdtemp(prefix="cv_g16_")
    os.environ["CV_DATA_DIR"] = tmp
    if model:
        from app.ai import settings

        trial = Path(tmp) / "model_trial.json"
        trial.write_text(json.dumps({"model": load_model(), "purposes": {"question": model}}), encoding="utf-8")
        settings.MODEL_JSON = trial
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
        t0 = time.perf_counter()
        try:
            res = ask_mod.answer(c["text"], con, pid, gw, quick=not claude_only)
        except ClaudeUnavailable as e:
            print(e)
            return 2
        sec = time.perf_counter() - t0
        want_sends = c.get("claude_sends", c["sends"]) if claude_only else c["sends"]
        good = res["result"] == exp["result"] and res["sends"] == want_sends
        if good and exp["result"] == "found":
            good = res["ref"] == exp["ref"]
        ok_all &= good
        got = res.get("ref") or res["result"]
        rows.append((c["id"], c["text"], exp.get("ref") or exp["result"], got, res["sends"], good, sec))
        print(c["id"], "合格" if good else "不合格", "送信", res["sends"], f"{sec:.2f}秒", "期待", exp.get("ref") or exp["result"], "結果", got)
    sent = "".join(p.read_text(encoding="utf-8") for p in (Path(tmp) / "sent_log").glob("*.jsonl"))
    sample = json.loads(sent.splitlines()[0])["user"] if sent else ""
    RESULT_MD.parent.mkdir(exist_ok=True)
    NL = chr(10)
    table = "".join(f"  - {r[0]}, {r[1]}, {r[2]}, {r[3]}, {r[4]}, {r[6]:.2f}秒, {'合格' if r[5] else '不合格'}{NL}"
                    for r in rows)
    from app.ai.settings import load_model as model_of

    way = "表を使わず全部 Claude に聞く" if claude_only else "よく聞く質問は表で直接、ほかは Claude"
    with RESULT_MD.open("a", encoding="utf-8") as f:
        f.write(
            f"{NL}## {datetime.now():%Y-%m-%d %H:%M} G16 質問9問＋聞き取り失敗1例（{way}）{NL}"
            f"- コミット: {commit_id()}{NL}- モデル（質問）: {model_of('question')}{NL}"
            f"- 入力（伏字後の1問目の送信文）: {sample[:600]}{NL}"
            f"- 判定の表（番号, 問い, 期待, 結果, 送信回数, 時間, 合否）:{NL}{table}"
            f"- 判定: {'全部合格' if ok_all else '不合格あり'}{NL}"
        )
    return 0 if ok_all else 1


def run_memo() -> int:
    """tests/memo_cases.json の6通りを本物の Claude で整理する。名前を付けて送り、送った文に名前が残らないことも見る。"""
    import os
    import tempfile

    tmp = tempfile.mkdtemp(prefix="cv_g17_")
    os.environ["CV_DATA_DIR"] = tmp
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], check=True, capture_output=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    from app.ai import memo
    from app.ai.gateway import Gateway, sensitive_from_db
    from app.db import connect
    from tests.memo_eval import CASES, judge

    con = connect()
    sens = sensitive_from_db(con)
    gw = Gateway(log_dir=Path(tmp) / "sent_log")
    ok_all, rows, NL = True, [], chr(10)
    for c in CASES:
        talk = "見本 花子さんの診療です。" + c["transcript"]  # 名前を入れて送り、伏字を確かめる
        try:
            items = memo.organize(talk, sens, gw)
        except ClaudeUnavailable as e:
            print(e)
            return 2
        except Exception as e:  # noqa: BLE001
            items, bad = {}, [f"失敗 {type(e).__name__}: {redact_key(str(e))[:80]}"]
        else:
            bad = judge(items, c["expect"])
        ok_all &= not bad
        rows.append((c["id"], c["title"], bad, items))
        print(c["id"], "合格" if not bad else "不合格", bad)
    sent = "".join(p.read_text(encoding="utf-8") for p in (Path(tmp) / "sent_log").glob("*.jsonl"))
    names_left = [w for w in ("見本", "花子", "ハナコ") if w in sent]
    if names_left:
        ok_all = False
        print("送った文に名前が残っています:", names_left)
    sample = json.loads(sent.splitlines()[0])["user"][:200] if sent else ""
    table = "".join(f"  - {r[0]} {r[1]}: {'合格' if not r[2] else '不合格 ' + '; '.join(r[2])}{NL}" for r in rows)
    with RESULT_MD.open("a", encoding="utf-8") as f:
        f.write(
            f"{NL}## {datetime.now():%Y-%m-%d %H:%M} G17 話した内容の整理 6通り{NL}"
            f"- コミット: {commit_id()}{NL}- モデル: {load_model()}{NL}"
            f"- 入力（伏字後の1通り目の送信文の先頭）: {sample}{NL}"
            f"- 送った文に名前が残っていない: {'はい' if not names_left else 'いいえ'}{NL}{table}"
            f"- 判定: {'全部合格' if ok_all else '不合格あり'}{NL}"
        )
    return 0 if ok_all else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--questions", action="store_true")
    ap.add_argument("--memo", action="store_true")
    ap.add_argument("--claude-only", action="store_true", help="--questions で、表を使わず全部 Claude に聞く")
    ap.add_argument("--model", default="", help="--questions で、質問だけこのモデルで試す")
    args = ap.parse_args()
    if args.memo:
        return run_memo()
    if args.questions:
        return run_questions(args.claude_only, args.model)
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
