"""G19h: 顎補綴の話の聞き違い（顎骨鉄→顎補綴、お鉄を入れ→補綴を入れ）と、状態の話が「やったこと」「説明したこと」に入る指示。偽物の口。"""
import json
from pathlib import Path

from app.ai import fixtalk, memo
from app.ai.fake import ScriptedMouth
from app.ai.gateway import Gateway
from app.ai.redact import Sensitive
from tests.test_fixtalk import KAGAKU, fx

ROOT = Path(__file__).resolve().parents[1]
SENS = Sensitive(patients=[], staff=[], clinics=[])
# 院長の画面で Claude が直していた3つ（読みは同じ）
CLAUDE_FIX = [fx("疑似", "義歯", "ぎし", "ぎし"), fx("上顎道", "上顎洞", "じょうがくどう", "じょうがくどう"), fx("血損", "欠損", "けっそん", "けっそん")]
FIXED = ("この方は、上顎は顎補綴の義歯が入っていて、4番から7番までは上顎洞まで交通した欠損があります。"
         "インプラントを上顎洞に近いところに打っており、そこに引っ掛ける形で顎補綴、義歯を入れております。"
         "補綴を入れて、義歯を入れて、しゃべる場合は大丈夫なんですが、そうじゃないときには空気が抜ける感じでしゃべることがなかなかできません。"
         "義歯を入れても、そこで噛むことながらが難しいので、反対側で噛んでもらうようになっております。"
         "今のところ、封鎖も良好で、飲み込みも問題ありません。今後も経過観察をしていきます。")


def test_terms_and_rules_added():
    cfg = json.loads((ROOT / "config" / "dental_terms.json").read_text(encoding="utf-8"))
    for w in ("顎補綴", "顎義歯", "補綴", "上顎洞", "欠損", "交通", "封鎖"):
        assert w in cfg["terms"]
    assert len(cfg["terms"]) <= 80
    assert "顎骨鉄" in cfg["readings"]["顎補綴"] and "お鉄を入れ" in cfg["readings"]["補綴を入れ"]
    for w in ("顎補綴", "上顎洞", "封鎖"):  # 文字起こしへ渡すヒントにも入る
        assert w in fixtalk.initial_prompt()


def test_doctors_screen_sentence_is_fixed(tmp_path):
    mouth = ScriptedMouth("{}", fix_reply=json.dumps(CLAUDE_FIX, ensure_ascii=False))
    gw = Gateway(mouth=mouth, log_dir=tmp_path / "log")
    text, done = fixtalk.fix_transcript(KAGAKU, SENS, gw)
    assert text == FIXED
    for w in ("顎補綴", "補綴", "義歯", "上顎洞", "欠損"):
        assert w in text
    for w in ("顎骨鉄", "お鉄", "疑似", "上顎道", "血損"):
        assert w not in text
    pairs = {(d["from"], d["to"]) for d in done}
    # 「直した聞き違い（元 → 直し）」の欄に、足した分も出る
    assert ("顎骨鉄", "顎補綴") in pairs and ("お鉄を入れ", "補綴を入れ") in pairs
    assert {("疑似", "義歯"), ("上顎道", "上顎洞"), ("血損", "欠損")} <= pairs


def test_rules_work_without_claude(tmp_path):
    """Claude が何も直さなくても、足した2つの決まりは効く。「お鉄」は「お鉄を入れ」の形のときだけ。"""
    mouth = ScriptedMouth("{}", fix_reply="[]")
    gw = Gateway(mouth=mouth, log_dir=tmp_path / "log")
    text, _ = fixtalk.fix_transcript("顎骨鉄を入れて、お鉄を入れました。お鉄のことは別です。", SENS, gw)
    assert text == "顎補綴を入れて、補綴を入れました。お鉄のことは別です。"


def test_correct_words_are_left_alone(tmp_path):
    mouth = ScriptedMouth("{}", fix_reply="[]")
    gw = Gateway(mouth=mouth, log_dir=tmp_path / "log")
    ok = "顎補綴の義歯を入れて、補綴を入れました。上顎洞まで交通した欠損です。"
    assert fixtalk.fix_transcript(ok, SENS, gw)[0] == ok


def test_prompt_puts_status_talk_in_done_and_instructions_in_explained():
    assert "封鎖は良好" in memo.SYSTEM and "反対側で噛んでもらう" in memo.SYSTEM
    assert "話していない言葉は足しません" in memo.SYSTEM


def test_status_items_are_kept_when_quotes_are_in_the_talk():
    """Claude が返した「やったこと」「説明したこと」は、抜き出しが話の中にあれば残る（作った話は残らない）。"""
    reply = json.dumps({
        "done": [{"text": "封鎖は良好、飲み込みは問題ない。", "quote": "封鎖も良好で、飲み込みも問題ありません"}],
        "explained": [{"text": "反対側で噛んでもらうようにしている。", "quote": "反対側で噛んでもらうようになっております"},
                      {"text": "作った話。", "quote": "話に無い抜き出し"}],
        "next_plan": [], "future_plan": [],
        "future_policy": [{"text": "経過観察をしていく。", "quote": "今後も経過観察をしていきます"}]}, ensure_ascii=False)
    items = memo.parse_items(reply, FIXED)
    assert len(items["done"]) == 1 and len(items["explained"]) == 1 and not items["next_plan"]
    body = memo.body_lines(items, "2026-11-06")
    assert "2026年11月6日にやったこと: 封鎖は良好" in body
