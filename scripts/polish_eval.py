"""清書（聞き取りの後で Claude が文脈から正しい文に整える段）を、候補のモデルごとに3回ずつ本物の Claude で測る。
  python scripts/polish_eval.py [回数]
候補のモデルは config/model.json の polish_candidates。結果の表を docs/清書のモデル比べ.md に書く（コミット・モデル・条件つき）。
測るもの: 正しく直った数、直し残し、余計な直しの数、かかった秒数。数字が変わった・長くなったで清書が捨てられた回数も数える。
文は架空（院長の台本の聞き取りの結果と、院長が見つけた聞き違いの文）。患者様の名前は伏字にして送る。"""
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ai.settings import ClaudeUnavailable, load_key, MODEL_JSON  # noqa: E402

RESULT_MD = ROOT / "docs" / "清書のモデル比べ.md"
NL = chr(10)

# 院長の台本1（花子様）の聞き取りの結果
TALK1 = ("右下6番の根管充填を行いました。前回あった肺のが止まっています。X線では根尖病変は小さくなってきています。"
         "次回は次第畜造をして肩を取ります。左上の5番は陰霊を外したところ、カリエスが深かったので副髄をして、仮の詰め物をしています。"
         "全身既往は高血圧があり、服薬は高圧剤を1種類飲まれています。")
KAGAKU = ("この方は、上顎は顎骨鉄の疑似が入っていて、4番から7番までは上顎道まで交通した血損があります。"
          "インプラントを上顎道に近いところに打っており、そこに引っ掛ける形で顎骨鉄、疑似を入れております。"
          "お鉄を入れて、疑似を入れて、しゃべる場合は大丈夫なんですが、そうじゃないときには空気が抜ける感じでしゃべることがなかなかできません。"
          "疑似を入れても、そこで噛むことながらが難しいので、反対側で噛んでもらうようになっております。"
          "今のところ、封鎖も良好で、飲み込みも問題ありません。今後も経過観察をしていきます。")
CASES = [
    {"name": "台本1（根の治療・花子様）", "talk": TALK1, "patient": True,
     "pairs": [("肺の", "排膿"), ("次第畜造", "支台築造"), ("肩を取", "型を取"), ("高圧剤", "降圧剤"), ("副髄", "覆髄"), ("陰霊", "インレー")]},
    {"name": "生活死（左下3番）", "talk": "左下3番にレントゲンで根尖病変を認めます。なので、こちらは生活死ではなく既に失活しているということです。",
     "patient": False, "pairs": [("生活死", "生活歯")]},
    {"name": "顎補綴の話", "talk": KAGAKU, "patient": False,
     "pairs": [("顎骨鉄", "顎補綴"), ("疑似", "義歯"), ("上顎道", "上顎洞"), ("血損", "欠損"), ("お鉄を入れ", "補綴を入れ")]},
    {"name": "録音1（根幹重点・肺脳・次第蓄造）", "talk": "今日は右下6番の根幹重点をしました。肺脳があったので洗浄しました。次回は2週間後に次第蓄造をします。",
     "patient": False, "pairs": [("根幹重点", "根管充填"), ("肺脳", "排膿"), ("次第蓄造", "支台築造")]},
    {"name": "正しい文（何も変えない）", "talk": "右下6番の根管充填をしました。次回は2週間後に支台築造をします。降圧剤を飲まれています。生活歯です。",
     "patient": False, "pairs": []},
]


def commit_id() -> str:
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    return r.stdout.strip() or "不明"


class PinnedMouth:
    """モデルを指定して送る口。鍵は使うときに読む。ほかは本番の AnthropicMouth と同じ。"""

    wants_purpose = True

    def __init__(self, model: str):
        self.model = model

    def complete(self, system, user, max_tokens, purpose=""):
        import anthropic

        client = anthropic.Anthropic(api_key=load_key())
        res = client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                     messages=[{"role": "user", "content": user}])
        return "".join(b.text for b in res.content if getattr(b, "type", "") == "text")


def main(argv) -> int:
    runs = int(argv[1]) if len(argv) > 1 else 3
    tmp = tempfile.mkdtemp(prefix="cv_polish_")
    os.environ["CV_DATA_DIR"] = tmp
    subprocess.run([sys.executable, str(ROOT / "scripts" / "seed.py")], check=True, capture_output=True,
                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    from app.ai import fixtalk
    from app.ai.gateway import Gateway, sensitive_from_db
    from app.ai.polish_context import context_for
    from app.db import connect

    cfg = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    models = cfg.get("polish_candidates") or []
    if not models:
        print("config/model.json に polish_candidates がありません")
        return 2
    con = connect()
    sens = sensitive_from_db(con)
    v = con.execute("SELECT v.id, v.patient_id FROM visits v JOIN patients p ON p.id = v.patient_id WHERE p.chart_no = '0123' "
                    "ORDER BY v.visit_date DESC, v.id DESC LIMIT 1").fetchone()
    ctx1 = context_for(con, v["patient_id"], v["id"]) if v else ""
    rows = []
    for model in models:
        gw = Gateway(mouth=PinnedMouth(model), log_dir=Path(tmp) / "sent_log")
        right = total = extra = left = dropped = failed = doubts = 0
        secs = []
        for case in CASES:
            for _ in range(runs):
                t0 = time.time()
                try:
                    res = fixtalk.polish(case["talk"], sens, gw, ctx1 if case["patient"] else "", timeout=120)
                except ClaudeUnavailable as e:
                    print(e)
                    return 2
                secs.append(time.time() - t0)
                text = res["text"]
                if not res["polished"]:
                    if "数字" in res["note"] or "長く" in res["note"]:
                        dropped += 1
                    else:
                        failed += 1
                for bad, good in case["pairs"]:
                    total += 1
                    if good in text and (bad not in text or bad in good):
                        right += 1
                    else:
                        left += 1
                bads = [b for b, _ in case["pairs"]]
                extra += len([f for f in res["fixes"] if f["by"] == "claude" and not any(b in f["from"] or f["from"] in b for b in bads)])
                doubts += len(res["doubts"])
        rows.append((model, right, total, left, extra, doubts, dropped, failed, sum(secs) / len(secs), max(secs)))
        print(model, right, total, "余計", extra, "平均秒", round(sum(secs) / len(secs), 1))
    table = (f"| モデル | 正しく直った | 直し残し | 余計な直し | 迷う印 | 捨てられた清書 | 失敗 | 平均の秒 | いちばん長い秒 |{NL}"
             f"|---|---|---|---|---|---|---|---|---|{NL}")
    for m, r, t, left, e, d, dr, fa, av, mx in rows:
        table += f"| {m} | {r}/{t} | {left} | {e} | {d} | {dr} | {fa} | {av:.1f} | {mx:.1f} |{NL}"
    with RESULT_MD.open("a", encoding="utf-8") as f:
        f.write(f"{NL}## {datetime.now():%Y-%m-%d %H:%M} 清書のモデル比べ（各{runs}回）{NL}"
                f"- コミット: {commit_id()}{NL}- 文: {', '.join(c['name'] for c in CASES)}（直す所は計 "
                f"{sum(len(c['pairs']) for c in CASES)} か所×{runs}回）{NL}"
                f"- 数え方: 正しく直った＝直したい言葉が本文に出て、聞き違いが本文に残っていない。余計な直し＝Claude が出した直しのうち、直したい聞き違い（の一部を含む）でないもの。迷う印＝「迷う」と印を付けた言葉の数（正しい文では1つも要らない）。{NL}{NL}"
                f"{table}")
    print("docs/清書のモデル比べ.md に書きました")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
