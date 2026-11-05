"""G19h: 顎補綴の話の聞き違いが直る。状態の話は「やったこと」、患者様への指示は「説明したこと」に振り分けられる。偽物の口。
（結果を見る試験。表に語があるか、指示文に文字があるかだけを見る試験はやめた。）"""
import json

from app.ai import fixtalk, memo
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.ai.redact import Sensitive
from tests.polish_helper import polish_reply
from tests.test_fixtalk import KAGAKU

SENS = Sensitive(patients=[], staff=[], clinics=[])
PAIRS = [("顎骨鉄", "顎補綴"), ("疑似", "義歯"), ("上顎道", "上顎洞"), ("血損", "欠損"), ("お鉄を入れ", "補綴を入れ")]
FIXED = ("この方は、上顎は顎補綴の義歯が入っていて、4番から7番までは上顎洞まで交通した欠損があります。"
         "インプラントを上顎洞に近いところに打っており、そこに引っ掛ける形で顎補綴、義歯を入れております。"
         "補綴を入れて、義歯を入れて、しゃべる場合は大丈夫なんですが、そうじゃないときには空気が抜ける感じでしゃべることがなかなかできません。"
         "義歯を入れても、そこで噛むことながらが難しいので、反対側で噛んでもらうようになっております。"
         "今のところ、封鎖も良好で、飲み込みも問題ありません。今後も経過観察をしていきます。")


def test_doctors_screen_sentence_is_fixed_and_listed(tmp_path):
    gw = Gateway(mouth=ScriptedMouth("{}", polish_reply=polish_reply(KAGAKU, PAIRS)), log_dir=tmp_path / "log")
    res = fixtalk.polish(KAGAKU, SENS, gw)
    assert res["text"] == FIXED  # 「噛むことながらが」は文のつながりの崩れ。直せなければそのまま
    for w in ("顎補綴", "補綴", "義歯", "上顎洞", "欠損"):
        assert w in res["text"]
    for w in ("顎骨鉄", "お鉄", "疑似", "上顎道", "血損"):
        assert w not in res["text"]
    # 「直した聞き違い（元 → 直し）」の欄に、直した分が出る
    assert {(d["from"], d["to"]) for d in res["fixes"]} == set(PAIRS)


def test_status_goes_to_done_and_instruction_to_explained(tmp_path):
    """整理は清書から作る。Claude が返した振り分けのとおりに、やったこと・説明したことの欄に入り、作った話は入らない。"""
    reply = json.dumps({
        "done": [{"text": "封鎖は良好、飲み込みは問題ない。", "quote": "封鎖も良好で、飲み込みも問題ありません"}],
        "explained": [{"text": "反対側で噛んでもらうようにしている。", "quote": "反対側で噛んでもらうようになっております"},
                      {"text": "作った話。", "quote": "話に無い抜き出し"}],
        "next_plan": [], "future_plan": [],
        "future_policy": [{"text": "経過観察をしていく。", "quote": "今後も経過観察をしていきます"}]}, ensure_ascii=False)
    items = memo.organize(FIXED, SENS, Gateway(mouth=ScriptedMouth(reply), log_dir=tmp_path / "log"))
    assert [r["text"] for r in items["done"]] == ["封鎖は良好、飲み込みは問題ない。"]
    assert [r["text"] for r in items["explained"]] == ["反対側で噛んでもらうようにしている。"]
    assert not items["next_plan"] and "作った話" not in memo.body_lines(items)
    body = memo.body_lines(items, "2026-11-06")
    assert "2026年11月6日にやったこと: 封鎖は良好" in body and "説明したこと: 反対側で噛んでもらう" in body


def test_organize_prompt_is_general_not_one_case():
    """整理の指示は、特定の症例の言葉ではなく、一般の言い方にしてある。"""
    for case_word in ("封鎖", "飲み込み", "反対側で噛"):
        assert case_word not in memo.SYSTEM
    assert "所見" in memo.SYSTEM and "explained" in memo.SYSTEM
