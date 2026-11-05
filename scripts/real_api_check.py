"""本物の Claude を呼んで確かめる（普段の試験では動かさない）。

使い方:
  python scripts/real_api_check.py            モデル一覧→最新の Sonnet を config/model.json に書く→短文を1回送る
  python scripts/real_api_check.py --no-write モデル名を書き換えず、今の設定で送るだけ
  python scripts/real_api_check.py --questions G16 の質問9問を本物の Claude に1回ずつ通し、正解と照らす
      --claude-only  よく聞く質問の表を使わず、全部 Claude に聞く（モデルの比較用）
      --model 名前    質問だけ別のモデルで試す（config は書き換えない）
  python scripts/real_api_check.py --memo      G17 の話6通りを本物の Claude で（聞き違いを直してから）5つに分け、期待と照らす
  python scripts/real_api_check.py --fix       聞き取りの後の清書を、録音1・2・台本1・生活死・顎補綴の文と、正しい文（何も変えない）で確かめる
  python scripts/polish_eval.py                清書のモデル比べ（Sonnet と Opus を3回ずつ。docs/清書のモデル比べ.md）
  python scripts/real_api_check.py --combine   G19b 診療回の区切り3つ（同じ話・言い直しを含む架空の話）を、まとめて1つの要約にする
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


def polished_items(talk, sens, gw, context=""):
    """本番と同じ流れ: 聞き取りの文を清書し、清書から5つに分ける。戻り値: (項目, 清書の結果)。"""
    from app.ai import fixtalk, memo

    pol = fixtalk.polish(talk, sens, gw, context)
    return memo.organize(pol["text"], sens, gw), pol


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
            items, pol = polished_items(talk, sens, gw)  # 清書してから5つに分ける（本番と同じ）
            _fixes = pol["fixes"]
        except ClaudeUnavailable as e:
            print(e)
            return 2
        except Exception as e:  # noqa: BLE001
            items, bad, _fixes = {}, [f"失敗 {type(e).__name__}: {redact_key(str(e))[:80]}"], []
        else:
            bad = judge(items, c["expect"])
        ok_all &= not bad
        rows.append((c["id"], c["title"], bad, items))
        print(c["id"], "合格" if not bad else "不合格", bad, "直し", [(f["from"], f["to"]) for f in _fixes])
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


def run_fix() -> int:
    """聞き違いを直す段を、本物の Claude で確かめる。録音1・2の文字は、院長の聞き違いの例から作り直した架空の文。"""
    import os
    import tempfile

    tmp = tempfile.mkdtemp(prefix="cv_fix_")
    os.environ["CV_DATA_DIR"] = tmp
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], check=True, capture_output=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    from app.ai import memo
    from app.ai.gateway import Gateway, sensitive_from_db
    from app.db import connect
    from tests.test_fixtalk import KAGAKU, REC1, REC2
    from tests.test_g19i import TALK as TALK1

    con = connect()
    sens = sensitive_from_db(con)
    gw = Gateway(log_dir=Path(tmp) / "sent_log")
    digits = lambda t: [c for c in t if c in "0123456789"]  # noqa: E731
    cases = [("録音1", REC1, ["根管充填", "排膿", "支台築造"]), ("録音2", REC2, ["支台築造", "TeC"]),
             ("副髄", "右下の5番は除去と副髄をします。", ["覆髄"]),   # G19d: 覆髄が抜髄にならない
             ("抜髄", "右下の5番は抜髄をします。", ["抜髄"]),        # 抜髄と話したら抜髄のまま
             ("顎補綴", KAGAKU, ["顎補綴", "補綴を入れ", "義歯", "上顎洞", "欠損"]),   # G19h: 院長の動画用の話（上顎の顎補綴）
             ("台本1", TALK1, ["排膿", "支台築造", "型を取", "降圧剤", "覆髄", "インレー"]),   # G19i: 院長の台本1の聞き取りの結果
             ("生活死", "左下3番にレントゲンで根尖病変を認めます。なので、こちらは生活死ではなく既に失活しているということです。", ["生活歯"]),
             ("正しい文", "右下6番の根管充填をしました。降圧剤を飲まれています。生活歯です。", ["根管充填", "降圧剤", "生活歯"])]   # 何も変わらない
    NL, ok_all, rows = chr(10), True, []
    for name, talk, want in cases:
        try:
            items, pol = polished_items("見本 花子さんの診療です。" + talk, sens, gw)
            fixed, fixes = pol["text"], pol["fixes"]
        except ClaudeUnavailable as e:
            print(e)
            return 2
        body = memo.body_lines(items)
        bad = [w for w in want if w not in fixed]
        if not pol["polished"]:
            bad.append("清書が使われていない: " + pol["note"])
        if name not in ("顎補綴", "台本1", "生活死"):   # この話は、清書の文に出ればよい（項目には状態と指示の話などだけ入る）
            bad += [f"項目に無い: {w}" for w in want if w not in body]
        bad += [w for w in ("根幹重点", "肺脳", "次第蓄造", "次第地駆動", "TEK") if w in fixed or w in body]
        if name == "顎補綴":
            bad += [w for w in ("顎骨鉄", "お鉄", "疑似", "上顎道", "血損") if w in fixed or w in body]
            bad += [f"{k}が空" for k in ("done", "explained") if not items[k]]   # 状態の確認と患者様への指示が入る
        if name == "台本1":
            bad += [w for w in ("肺の", "次第畜造", "肩を取", "高圧剤", "副髄", "陰霊") if w in fixed]
        if name == "生活死" and "生活死" in fixed:
            bad.append("生活死が残った")
        if name == "正しい文" and fixed != "見本 花子さんの診療です。" + talk:
            bad.append("正しい文が変わった")
        if name == "副髄":
            bad += [w for w in ("抜髄", "副髄") if w in fixed or w in body]
        if digits(fixed) != digits("見本 花子さんの診療です。" + talk):
            bad.append("数字が変わった")
        ok_all &= not bad
        rows.append((name, fixes, bad, fixed, body))
        print(name, "合格" if not bad else "不合格", bad, [(f["from"], f["to"]) for f in fixes])
    sent = "".join(p.read_text(encoding="utf-8") for p in (Path(tmp) / "sent_log").glob("*.jsonl"))
    left = [w for w in ("見本", "花子", "ハナコ") if w in sent]
    if left:
        ok_all = False
        print("送った文に名前が残っています:", left)
    sample = json.loads(sent.splitlines()[0])["user"][:200] if sent else ""
    table = "".join(f"  - {r[0]}: {'合格' if not r[2] else '不合格 ' + '; '.join(r[2])}。直し: "
                    f"{', '.join(f['from'] + '→' + f['to'] for f in r[1]) or 'なし'}{NL}" for r in rows)
    with RESULT_MD.open("a", encoding="utf-8") as f:
        f.write(
            f"{NL}## {datetime.now():%Y-%m-%d %H:%M} 聞き違いを直す段（録音1・2の文字）{NL}"
            f"- コミット: {commit_id()}{NL}- モデル: {load_model()}{NL}"
            f"- 入力（伏字後の送信文の先頭）: {sample}{NL}"
            f"- 送った文に名前が残っていない: {'はい' if not left else 'いいえ'}{NL}{table}"
            f"- 判定: {'全部合格' if ok_all else '不合格あり'}{NL}"
        )
    return 0 if ok_all else 1


SEGMENTS = [
    "見本 花子さんの診療です。今日は右下6番の根幹重点をしました。",
    "右下6番の根幹重点を行いました。肺脳があったので洗浄しました。次回は二週間後に形成をします。",
    "さっきの次回の予定は言い直します。次回は三週間後に次第蓄造をします。仮歯はTEKを入れる予定です。",
]


def run_combine() -> int:
    """区切り3つをつないで1つの要約にする。同じ話は1つ・言い直しは後の言い方・聞き違いは直る・名前は送らない、を確かめる。"""
    import os
    import tempfile

    tmp = tempfile.mkdtemp(prefix="cv_combine_")
    os.environ["CV_DATA_DIR"] = tmp
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], check=True, capture_output=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    from app.ai import memo
    from app.ai.gateway import Gateway, sensitive_from_db
    from app.db import connect

    con = connect()
    gw = Gateway(log_dir=Path(tmp) / "sent_log")
    NL = chr(10)
    try:
        from app.ai import fixtalk

        sens = sensitive_from_db(con)
        pols = [fixtalk.polish(t, sens, gw) for t in SEGMENTS]   # 区切りごとに、聞き取りのすぐ後で清書する
        fixed = NL.join(p["text"] for p in pols)
        fixes = [f for p in pols for f in p["fixes"]]
        items = memo.organize(fixed, sens, gw, combined=True)
    except ClaudeUnavailable as e:
        print(e)
        return 2
    body = memo.body_lines(items)
    bad = [w for w in ("根幹重点", "肺脳", "次第蓄造", "次第地駆動", "TEK") if w in fixed or w in body]
    bad += [f"項目に無い: {w}" for w in ("根管充填", "排膿", "支台築造", "TeC") if w not in body]
    if sum("根管充填" in r["text"] for r in items["done"]) != 1:
        bad.append("同じ話（根管充填）が1つにまとまっていない")
    plans = " ".join(r["text"] for r in items["next_plan"] + items["future_plan"])
    if not any(w in plans for w in ("三週間", "3週間")) or any(w in plans for w in ("二週間", "2週間")):
        bad.append("言い直しの後の言い方（三週間後）になっていない")
    sent = "".join(p.read_text(encoding="utf-8") for p in (Path(tmp) / "sent_log").glob("*.jsonl"))
    left = [w for w in ("見本", "花子", "ハナコ") if w in sent]
    if left:
        bad.append("送った文に名前が残っています: " + "、".join(left))
    print("合格" if not bad else "不合格", bad)
    print(body)
    sample = json.loads(sent.splitlines()[0])["user"][:200] if sent else ""
    with RESULT_MD.open("a", encoding="utf-8") as f:
        f.write(
            f"{NL}## {datetime.now():%Y-%m-%d %H:%M} G19b 今日の分をまとめて要約（区切り3つ）{NL}"
            f"- コミット: {commit_id()}{NL}- モデル: {load_model()}{NL}"
            f"- 入力（伏字後の送信文の先頭）: {sample}{NL}"
            f"- 送った文に名前が残っていない: {'はい' if not left else 'いいえ'}{NL}"
            f"- 直し: {', '.join(f['from'] + '→' + f['to'] for f in fixes) or 'なし'}{NL}"
            f"- 要約: {body.replace(NL, ' / ')}{NL}"
            f"- 判定: {'全部合格' if not bad else '不合格 ' + '; '.join(bad)}{NL}"
        )
    return 0 if not bad else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--questions", action="store_true")
    ap.add_argument("--memo", action="store_true")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--combine", action="store_true")
    ap.add_argument("--claude-only", action="store_true", help="--questions で、表を使わず全部 Claude に聞く")
    ap.add_argument("--model", default="", help="--questions で、質問だけこのモデルで試す")
    args = ap.parse_args()
    if args.combine:
        return run_combine()
    if args.fix:
        return run_fix()
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
