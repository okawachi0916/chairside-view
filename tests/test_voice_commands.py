"""G13: 決まった言葉で画面を動かす。照合は config/commands.json の表だけで行い、Claude は使わない。"""
import json
import time

import pytest

from app.views import data as D
from app.voice.interpret import FAILED, OP, QUESTION, UNRELATED, expand, interpret, load_table
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

ROWS = [r for r in D.today_list() if r["patient_id"] == 1]
H_DOC, H_HYG = ROWS[0]["id"], ROWS[1]["id"]
UNIT = f"/unit?appt={H_DOC}&role=doctor&typed=1&hide=1"

UNRELATED_WORDS = [
    "大きく口を開けてください", "右下6番を見てください", "今日は寒いですね", "麻酔をしますね", "ゆっくり息を吸ってください",
    "うがいをしてください", "少し痛みますよ", "お疲れさまでした", "ライトを動かします", "次回は来週の予約です",
]


def test_table_shape():
    rows = load_table()
    assert len(rows) >= 50
    for r in rows:
        assert set(r) == {"言葉", "使える画面", "状態", "結果"}
        assert r["状態"] in ("使える", "未実装")


def _fill(word):
    """{n1} などの欄は、試験では 3, 5, 10 に置き換えて言う。"""
    for k, n in (("{n1}", "3"), ("{n2}", "5"), ("{n3}", "10")):
        word = word.replace(k, n)
    return word


def test_every_row_gives_its_result():
    for r in load_table():
        for word in expand(r["言葉"]):
            word = _fill(word)
            for w in {word, word[:-2] + "する" if word.endswith("して") else word}:
                res = interpret(w, r["使える画面"][0])  # 行ごとに、その行の使える画面で試す（下書きの画面の行は draft）
                assert res["kind"] == OP, w
                if r["状態"] == "使える":
                    assert res["action"] == r["結果"]["action"], w
                    assert res["arg"] == r["結果"].get("arg"), w
                    if "{n1}" in r["言葉"]:
                        assert res["numbers"] == [3, 5, 10][: r["言葉"].count("{n")], w
                else:
                    assert res["action"] is None and res["message"] == "まだ開けません", w


def test_all_fullscreens_are_ready():
    rows = load_table()
    assert all(r["状態"] == "使える" for r in rows)  # G22: 未実装の行は無い
    ready = {r["結果"]["arg"] for r in rows if r["結果"].get("action") == "fs-open"}
    assert ready == {"important", "intraoral-photos", "spoken-summary", "medical-history", "today-treatment",
                     "treatment-history", "perio-exam"}  # 受付メモは声の言葉に足さない
    for part, arg in (("全身既往", "medical-history"), ("今日の処置", "today-treatment"), ("治療歴", "treatment-history"),
                      ("歯周検査", "perio-exam")):
        res = interpret(f"{part}を全画面にして")
        assert res["action"] == "fs-open" and res["arg"] == arg
    assert interpret("受付メモを全画面にして")["action"] is None


def test_whole_sentence_only():
    assert interpret("重要事項を全画面にして")["kind"] == OP
    assert interpret("えっと重要事項を全画面にして")["action"] is None
    assert interpret("重要事項を全画面にしてください")["action"] == "fs-open"  # G14l: 敬語でも同じ動き
    assert interpret("重要事項を")["action"] is None


@pytest.mark.parametrize("word", UNRELATED_WORDS)
def test_unrelated_words_do_nothing(word):
    res = interpret(word)
    assert res["kind"] == UNRELATED and res["action"] is None and res["message"] == "もう一度お願いします"


def test_classes():
    for t in ["前回は何をした", "次の予約はいつ", "アレルギーは", "麻酔の既往はありますか", "歯科衛生士の担当を教えて", "写真を見せて", "今日の予約は？"]:
        res = interpret(t)
        assert res["kind"] == QUESTION and res["message"] == "まだ答えられません" and res["action"] is None, t
    for t in ["", "あ", "あの", "えっと", "あのえっと", "はいはい", "ああああ", "重要重要"]:
        res = interpret(t)
        assert res["kind"] == FAILED and res["message"] == "もう一度お願いします", t


def open_unit(browser, server, path=UNIT):  # noqa: F811
    pg = open_page(browser, server, path)
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("window.cvTyped || !!document.getElementById('typed-input')")
    return pg


def test_hide_flag_hides_input_and_cvtyped_works(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    assert pg.locator("#typed-input").count() == 0 or not pg.locator("#typed-input").is_visible()
    assert pg.evaluate("typeof window.cvTyped") == "function"
    pg.evaluate("window.cvTyped('重要事項を全画面にして')")
    pg.wait_for_selector('[data-fs-panel="important"]')
    assert "「重要事項を全画面にして」" in pg.inner_text("#heard")
    pg.evaluate("window.cvTyped('もとに戻す')")
    pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")


def test_typed_input_visible_without_hide(server, browser):  # noqa: F811
    pg = open_unit(browser, server, f"/unit?appt={H_DOC}&role=doctor&typed=1")
    assert pg.locator("#typed-input").is_visible()
    pg.fill("#typed-input", "口腔内写真を拡大して")
    pg.keyboard.press("Enter")
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')


def test_fullscreen_open_and_close_by_voice_words(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    for word, part in [("話した内容を詳細表示して", "spoken-summary"), ("重要事項の詳細を教えて", "important"),
                       ("口腔内写真を大きく表示する", "intraoral-photos")]:
        pg.evaluate("w => window.cvTyped(w)", word)
        pg.wait_for_selector(f'[data-fs-panel="{part}"]')
        pg.evaluate("window.cvTyped('戻して')")
        pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")


def test_treatment_history_opens_by_voice(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvTyped('治療歴を全画面にして')")
    pg.wait_for_selector('[data-fs-panel="treatment-history"]')


def test_question_and_unrelated_messages_and_no_move(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    before = pg.inner_text("main.body")
    for word in UNRELATED_WORDS:
        pg.evaluate("w => window.cvTyped(w)", word)
    pg.evaluate("window.cvTyped('ペニシリンの記録は')")
    # G16 から質問は Claude に聞く（試験では偽物の口が「分からない」を返す）。画面は動かさない。
    # 前回・アレルギー・薬・次回の質問は表で直接答えるので、ここでは表に無い質問を使う
    pg.wait_for_function("document.body.dataset.answer === 'retry'")
    pg.evaluate("window.cvTyped('えっと')")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('もう一度お願いします')")
    assert pg.locator("[data-fs-panel]").count() == 0
    assert pg.inner_text(".bands") == before.split("\n", 0)[0] or pg.locator("[data-fs-panel]").count() == 0


def test_page_words_in_fullscreen(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvTyped('重要事項を全画面にして')")
    pg.wait_for_selector('[data-fs-panel="important"]')
    pg.evaluate("window.cvTyped('次のページ')")
    pg.evaluate("window.cvTyped('前のページ')")
    assert pg.locator('[data-fs-panel="important"]').count() == 1


def test_role_switch_by_voice(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    assert pg.locator("body.role-doctor").count() == 1
    pg.evaluate("window.cvTyped('歯科衛生士の画面を出して')")
    pg.wait_for_selector("body.role-hygienist")
    pg.evaluate("window.cvTyped('歯科医師の画面を出して')")
    pg.wait_for_selector("body.role-doctor")


def test_say_list_button(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.click("#say-list-btn")  # プルダウンではなく全画面
    pg.wait_for_selector('[data-fs-panel="say-list"]')
    assert pg.locator("#say-list").count() == 0
    text = pg.inner_text('[data-fs-panel="say-list"]')
    assert "1番と3番を並べて" in text and "前回は何をした？" in text and "10番 言える言葉" in text
    pg.evaluate("window.cvTyped('戻して')")
    pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")


def test_reception_has_no_voice(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/reception?typed=1")
    pg.wait_for_selector("body[data-kind='reception']")
    time.sleep(0.5)
    assert pg.evaluate("typeof window.cvTyped") == "undefined"
    assert pg.locator("#typed-box, #heard, #say-list-btn").count() == 0


def test_draft_screen_words_come_from_the_table_only():
    """G21k-6: 下書きの画面の言葉は commands.json の draft の行だけ。unit では動かない。"""
    for w, act in [("カルテに記録する", "draft-arm"), ("確定して", "draft-arm"), ("記録", "draft-confirm"), ("確定", "draft-confirm"),
                   ("後で直して", "draft-later"), ("あとで直す", "draft-later"), ("戻って", "draft-back"), ("戻して", "draft-back")]:
        assert interpret(w, "draft")["action"] == act, w
    assert interpret("カルテに記録する", "unit")["action"] is None
    assert interpret("3番", "draft")["action"] == "part-number"
    js = (__import__("pathlib").Path(__file__).resolve().parents[1] / "app" / "static" / "js" / "draft.js").read_text(encoding="utf-8")
    assert "カルテに記録(する|して)" not in js and "(あとで|後で)直" not in js  # 自分専用の言葉の書き方を持たない


def test_voice_commands_list_has_no_duplicate_rows_and_shows_each_command_once():
    import json
    from pathlib import Path
    rows = json.loads((Path(__file__).resolve().parents[1] / "config" / "commands.json").read_text(encoding="utf-8"))
    seen = {}
    for r in rows:
        for s in r["使える画面"]:
            for w in expand(r["言葉"]):
                key = (s, w)
                assert key not in seen or seen[key] == r["結果"], f"同じ言葉が2行にある: {w}"
                seen.setdefault(key, r["結果"])
