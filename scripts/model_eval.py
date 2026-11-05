"""声の質問で記録を選ぶ処理に合うモデルを、実測で決める（普段の試験では動かさない）。

使い方:
  python scripts/model_eval.py            モデル一覧から Haiku・Sonnet・Opus の最新を1つずつ選び、30問を測って docs/モデルの選び方.md に書く
  python scripts/model_eval.py --apply    上に加えて、採用するモデルが今の設定と違えば config/model.json の purposes.question を書き換える
  python scripts/model_eval.py --check    問いの形だけ確かめる（本物の Claude は呼ばない）

測るのは Claude へ送る質問だけ（よく聞く質問は言葉の表で先に答える）。架空データだけを使い、今の送信口（app/ai/gateway.py）と伏字を通して、
本番と同じ文で送る。モデル名はコードに書かず、一覧から取る。値段は config/model_prices.json。全体の費用が上限を超えそうなら止まる。
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_MD = ROOT / "docs" / "モデルの選び方.md"
PRICES = ROOT / "config" / "model_prices.json"
FAMILIES = ("haiku", "sonnet", "opus")
BUDGET_USD = 2.0       # 全体の費用の上限（手順書の決め）
STOP_AT_USD = 1.7      # これを超えそうなら次の問いの前に止める
TOLERANCE = 2          # 正解の数が一番多いモデルから、この数以内を候補にする

# 声の質問30問。chart はカルテ番号、ref は app/ai/records.py の印（None は「答えが無い」が正解）。
Q = [
    ("0123", "右下6番の根管治療を始めたのはいつ？", "note:2026-10-09"),
    ("0123", "左下7番のレジン充填はいつした？", "note:2026-07-15"),
    ("0123", "左下7番がC2と診断されたのはいつ？", "note:2026-06-20"),
    ("0123", "右下6番のC3の診断はいつ？", "note:2026-09-18"),
    ("0123", "右上5番の知覚過敏の処置はいつ？", "note:2026-04-14"),
    ("0123", "右上6番のクラウンを入れたのはいつ？", "history:2025-11-14"),
    ("0123", "最後の歯周検査はいつ？", "perio:2026-08-07"),
    ("0123", "一番古い歯周検査はいつ？", "perio:2026-05-08"),
    ("0123", "ビスホスホネート製剤はいつから服用中？", "important:2"),
    ("0123", "ペニシリンでどんな症状が出た？", "important:1"),
    ("0123", "高血圧の内服は何？", "medical"),
    ("0123", "口を長く開けているのはつらいですか", "handover"),
    ("0123", "今後、左下7番はどうする方針？", "plan:2"),
    ("0123", "右上5番の充填の計画は？", "plan:3"),
    ("0123", "クラウンを入れる前の土台の計画は？", "plan:1"),
    ("0123", "8月7日の診療メモは？", "note:2026-08-07"),
    ("0123", "デンタル撮影をしたのはいつ？", "note:2026-09-18"),
    ("0123", "10月23日にしたことは？", "note:2026-10-23"),
    ("0123", "仮封をしたのはいつ？", "note:2026-10-23"),
    ("0123", "コンポジットレジン充填をしたのは何番の歯？", "note:2026-07-15"),
    ("0456", "金属アレルギーの記録は？", "important:1"),
    ("0789", "ワルファリンを飲み始めた理由は？", "important:1"),
    ("0789", "下顎ブリッジの咬合調整はいつ？", "note:2026-10-16"),
    ("1024", "義歯の疼痛部位を調整したのはいつ？", "note:2026-10-30"),
    ("2048", "ラテックスで困ったことは？", "important:1"),
    ("0123", "インプラントの記録は？", None),
    ("0123", "親知らずを抜いたのはいつ？", None),
    ("0123", "去年のCTの結果は？", None),
    ("0456", "矯正治療の記録は？", None),
    ("1024", "根管治療の記録は？", None),
]


def prices() -> dict:
    return json.loads(PRICES.read_text(encoding="utf-8"))["usd_per_million_tokens"]


def family_of(model: str) -> str:
    return next((f for f in FAMILIES if f in model.lower()), "")


def pick_models(client) -> dict:
    """一覧は新しい順。系統ごとに先頭の1つを取る。"""
    found = {}
    for m in client.models.list(limit=100):
        fam = family_of(m.id)
        if fam and fam not in found:
            found[fam] = m.id
    missing = [f for f in FAMILIES if f not in found]
    if missing:
        raise SystemExit(f"一覧に見つからない系統: {', '.join(missing)}")
    return found


def cost_usd(model: str, tin: int, tout: int) -> float:
    p = prices()[family_of(model)]
    return (tin * p["input"] + tout * p["output"]) / 1_000_000


def make_mouth(model: str):
    from app.ai.gateway import AnthropicMouth
    from app.ai.settings import load_key

    class MeasuringMouth(AnthropicMouth):
        """本番と同じ送り方で、使った量を覚える。モデルだけ指定する。"""

        def __init__(self):
            self.in_tokens = self.out_tokens = 0

        def complete(self, system, user, max_tokens, purpose=""):
            import anthropic

            client = anthropic.Anthropic(api_key=load_key())
            kwargs = {"system": system} if system else {}
            res = client.messages.create(model=model, max_tokens=max_tokens,
                                         messages=[{"role": "user", "content": user}], **kwargs)
            self.in_tokens += res.usage.input_tokens
            self.out_tokens += res.usage.output_tokens
            return "".join(b.text for b in res.content if getattr(b, "type", "") == "text")

    return MeasuringMouth()


def fake_db():
    tmp = tempfile.mkdtemp(prefix="cv_g26c_")
    os.environ["CV_DATA_DIR"] = tmp
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], check=True, capture_output=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    from app.db import connect

    return connect(), Path(tmp)


def check_questions(con) -> list:
    """問いの形を確かめる。本物は呼ばない。"""
    from app.ai.quick import pick_entry
    from app.ai.records import build_records
    from app.voice.interpret import QUESTION, interpret

    bad = []
    if len(Q) != 30 or sum(1 for q in Q if q[2] is None) != 5:
        bad.append("問いは30問、答えが無い問いは5問")
    for chart, text, ref in Q:
        row = con.execute("SELECT id FROM patients WHERE chart_no = ?", (chart,)).fetchone()
        if not row:
            bad.append(f"{chart}: 患者様が見つからない")
            continue
        if interpret(text, "unit")["kind"] != QUESTION:
            bad.append(f"{text}: 質問に分けられない")
        if pick_entry(text) is not None:
            bad.append(f"{text}: 言葉の表に当たる（Claude へ送る質問だけを測る）")
        refs = {r.ref for r in build_records(con, row["id"])}
        if ref is not None and ref not in refs:
            bad.append(f"{text}: 正しい記録 {ref} が無い")
    return bad


def run_model(model: str, con, tmp: Path, spent: float):
    """30問を動かす。戻り値: (行の一覧, 使った費用)。上限を超えそうなら途中で止めて None の行を返す。"""
    from app.ai import ask as ask_mod
    from app.ai.gateway import Gateway
    from app.ai.settings import ClaudeUnavailable

    mouth = make_mouth(model)
    gw = Gateway(mouth=mouth, log_dir=tmp / "sent_log")
    rows, used = [], 0.0
    for i, (chart, text, ref) in enumerate(Q, 1):
        if spent + used > STOP_AT_USD:
            return rows, used, True
        pid = con.execute("SELECT id FROM patients WHERE chart_no = ?", (chart,)).fetchone()["id"]
        before = (mouth.in_tokens, mouth.out_tokens)
        t0 = time.perf_counter()
        try:
            res = ask_mod.answer(text, con, pid, gw, quick=False)
        except ClaudeUnavailable as e:
            raise SystemExit(str(e))
        sec = time.perf_counter() - t0
        used += cost_usd(model, mouth.in_tokens - before[0], mouth.out_tokens - before[1])
        if ref is None:
            ok = res["result"] == "none"
        else:
            ok = res["result"] == "found" and res.get("ref") == ref
        got = res.get("ref") or res["result"]
        rows.append({"n": i, "text": text, "expect": ref or "none", "got": got, "ok": ok, "sec": sec})
        print(f"{model} {i:2d} {'合格' if ok else '不合格'} {sec:.2f}秒 期待 {ref or 'none'} 結果 {got}", flush=True)
    return rows, used, False


def summarize(model: str, rows: list, used: float) -> dict:
    secs = [r["sec"] for r in rows]
    none_rows = [r for r in rows if r["expect"] == "none"]
    return {"model": model, "family": family_of(model), "n": len(rows),
            "correct": sum(r["ok"] for r in rows), "none_correct": sum(r["ok"] for r in none_rows),
            "none_total": len(none_rows), "median": statistics.median(secs), "max": max(secs),
            "cost_per_q": used / max(len(rows), 1), "cost": used}


def decide(results: list) -> dict:
    best = max(r["correct"] for r in results)
    cands = [r for r in results if r["correct"] >= best - TOLERANCE]
    return min(cands, key=lambda r: r["median"])


def write_md(results, chosen, all_rows, current, stopped, commit):
    NL = chr(10)
    best = max(r["correct"] for r in results)
    lines = [
        "# モデルの選び方", "",
        f"声の質問で記録を選ぶ処理（Claude へ送る質問だけ）に合うモデルを、実測で決めた記録。{datetime.now():%Y-%m-%d %H:%M} / コミット {commit}",
        "", "## やり方",
        "- 架空データだけで、声の質問を30問作った（答えのある25問、答えが無い5問）。各問の正しい答え（選ぶべき記録）は scripts/model_eval.py に固定してある。",
        "- 「前回」「アレルギー」「薬」「次回」のよく聞く質問は言葉の表で先に答え、Claude を通らないので、測っていない。",
        "- モデルは API の一覧から、Haiku・Sonnet・Opus の系統ごとに最新を1つ選んだ（モデル名はコードに書かない）。",
        "- 今の送信口と伏字を通し、本番と同じ文で送った。1問ずつ、1回だけ。", "",
        "## 実測",
        "| 系統 | モデル | 正解（30問） | 答え無しの正解（5問） | 時間の中央値 | 一番長い時間 | 1問あたりの費用 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        mark = "（採用）" if r is chosen else ""
        lines.append(f"| {r['family']} | {r['model']}{mark} | {r['correct']} / {r['n']} | {r['none_correct']} / {r['none_total']} | "
                     f"{r['median']:.2f}秒 | {r['max']:.2f}秒 | ${r['cost_per_q']:.5f} |")
    lines += ["", f"費用は合計で約 ${sum(r['cost'] for r in results):.3f}（上限 ${BUDGET_USD:.0f}）。値段は config/model_prices.json。", ""]
    if stopped:
        lines += ["**費用の上限が近づいたため、途中で止めた。** 判断待ち。", ""]
    cands = [r for r in results if r["correct"] >= best - TOLERANCE]
    lines += ["## 決め方と結果",
              f"- 正解の数が一番多いモデルは {best} 問。そこから{TOLERANCE}問以内のモデルのうち、中央値が一番短いモデルを採用する。",
              f"- 候補: {', '.join(r['model'] for r in cands)}",
              f"- 採用: **{chosen['model']}**（{chosen['correct']} / {chosen['n']}、中央値 {chosen['median']:.2f}秒）",
              "- 理由: 診療中に患者様と話しながら記録を見るので、答えが出るまで待たせないことを優先する。正解の差が小さいなら速いほうがよい。"
              "間違えたときは、画面に出る本文がデータベースの文字そのままなので、人が見て気づける（誤った記録を選んでも、作り話は出ない）。", ""]
    lines += ["## 今の設定との比べ",
              f"- 今の質問のモデル: {current}",
              f"- 採用するモデル: {chosen['model']}",
              f"- {'同じなので、設定は変えない。' if current == chosen['model'] else '違うので、config/model.json の purposes.question を書き換える。'}", ""]
    lines += ["## 不正解になった問い"]
    any_bad = False
    for model, rows in all_rows.items():
        for r in rows:
            if not r["ok"]:
                any_bad = True
                lines.append(f"- {model}: {r['n']}. {r['text']}（期待 {r['expect']}、結果 {r['got']}）")
    if not any_bad:
        lines.append("- なし")
    lines.append("")
    OUT_MD.write_text(NL.join(lines), encoding="utf-8")


def commit_id() -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() or "不明"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    con, tmp = fake_db()
    bad = check_questions(con)
    if bad:
        print("問いに問題があります:", *bad, sep="\n- ")
        return 1
    if args.check:
        print("問いの形: 合格（30問、答え無し5問、よく聞く質問の表に当たるものは無し）")
        return 0

    import anthropic

    from app.ai.settings import ClaudeUnavailable, MODEL_JSON, load_key, load_model

    try:
        client = anthropic.Anthropic(api_key=load_key())
    except ClaudeUnavailable as e:
        print(e)
        return 2
    models = pick_models(client)
    print("選んだモデル:", models)
    results, all_rows, spent, stopped = [], {}, 0.0, False
    for fam in FAMILIES:
        rows, used, stop = run_model(models[fam], con, tmp, spent)
        spent += used
        all_rows[models[fam]] = rows
        if stop:
            stopped = True
            print(f"費用が ${spent:.2f} になったので止めました（上限 ${BUDGET_USD:.0f}）。判断待ちです。")
            break
        results.append(summarize(models[fam], rows, used))
    if stopped or len(results) < len(FAMILIES):
        return 3
    chosen = decide(results)
    current = load_model("question")
    write_md(results, chosen, all_rows, current, stopped, commit_id())
    print("採用:", chosen["model"], "今の設定:", current, "費用:", f"${spent:.3f}")
    if args.apply and chosen["model"] != current:
        cfg = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
        cfg.setdefault("purposes", {})["question"] = chosen["model"]
        MODEL_JSON.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("config/model.json を書き換えました。scripts/real_api_check.py --questions を動かし直してください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
