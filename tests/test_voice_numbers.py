"""G14c: 言葉の揺れに強くする（戻す・助詞が抜けた形）と、丸の番号で部品を呼ぶ。Claude は使わない。"""
import pytest

from app.views import data as D
from app.voice.interpret import FAILED, OP, QUESTION, UNRELATED, interpret
from tests.screen_helper import browser, open_page, server  # noqa: F401

H_DOC = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
DOC = f"/unit?appt={H_DOC}&role=doctor&typed=1&hide=1"
HYG = f"/unit?appt={H_DOC}&role=hygienist&typed=1&hide=1"

PARTS = {"重要事項": "important", "口腔内写真": "intraoral-photos", "話した内容": "spoken-summary",
         "全身既往": "medical-history", "今日の処置": "today-treatment", "治療歴": "treatment-history",
         "歯周基本検査": "perio-exam"}
BACK = ["もとに戻す", "元に戻す", "もとに戻して", "元に戻して", "戻す", "戻して", "閉じて"]
NUMBER_WORDS = {
    1: ["1番", "一番", "いちばん", "1番です", "一番です", "いちばんで", "1", "いち番", "1ばん", "1番で", "いちばんです"],
    2: ["2番", "二番", "にばん", "2番です", "にばんで"],
    3: ["3番", "三番", "さんばん", "3番です"],
    4: ["4番", "よんばん", "4番です", "よんばんで"],
    5: ["5番", "ごばん", "5番です"],
    6: ["6番", "ろくばん"],
    7: ["7番", "ななばん", "7番です", "ななばんで"],
}


def number_of(res):
    return res["numbers"][0] if res.get("numbers") else res["arg"]


def test_back_words_all_close():
    for w in BACK:
        res = interpret(w)
        assert res["kind"] == OP and res["action"] == "fs-close", w
        assert interpret(w + "。")["action"] == "fs-close", w


def test_back_words_with_stutter_do_not_break():
    assert interpret("元に戻して")["action"] == "fs-close"
    assert interpret("元に")["action"] is None


@pytest.mark.parametrize("part,arg", PARTS.items())
def test_particle_less_words_open(part, arg):
    for tail in ["全画面表示", "全画面", "の全画面表示", "全画面にして", "を全画面にして", "の全画面表示して", "詳細表示", "拡大して"]:
        res = interpret(part + tail)
        assert res["kind"] == OP and res["action"] == "fs-open" and res["arg"] == arg, part + tail


def test_old_words_still_work():
    assert interpret("重要事項を全画面にして")["arg"] == "important"
    assert interpret("重要事項の詳細を教えて")["arg"] == "important"
    assert interpret("口腔内写真を大きく表示して")["arg"] == "intraoral-photos"
    assert interpret("一覧に戻す")["action"] == "photo-list"


@pytest.mark.parametrize("n,words", NUMBER_WORDS.items())
def test_number_words(n, words):
    for w in words:
        res = interpret(w)
        assert res["kind"] == OP and res["action"] == "part-number", w
        assert number_of(res) == n, w


@pytest.mark.parametrize("n,words", NUMBER_WORDS.items())
def test_long_number_words(n, words):
    for base in [w for w in words if w.endswith(("番", "ばん")) and len(w) > 1][:3]:
        for tail in ["を開いて", "開いて", "を全画面にして", "全画面にして", "を全画面表示して", "を全画面表示する"]:
            res = interpret(base + tail)
            assert res["kind"] == OP and res["action"] == "part-number" and number_of(res) == n, base + tail


def test_four_and_seven_only_yon_and_nana():
    for w in ["しばん", "しちばん", "し番", "しち番", "しばんです", "しちばんを開いて"]:
        res = interpret(w)
        assert res["action"] is None, w
        assert res["kind"] in (UNRELATED, FAILED, QUESTION), w


def test_photo_numbers_unchanged_and_question_unchanged():
    res = interpret("3番を拡大して")
    assert res["action"] == "photo-show" and res["numbers"] == [3]
    assert interpret("1番と5番を大きく")["numbers"] == [1, 5]
    res = interpret("口腔内写真の3番を拡大して")
    assert res["action"] == "photo-open" and res["numbers"] == [3]
    assert interpret("写真の1番と5番と10番を大きく")["numbers"] == [1, 5, 10]
    assert interpret("前回は何をした？")["kind"] == QUESTION
    assert interpret("右下6番を見てください")["action"] is None


def open_unit(browser, server, path=DOC):  # noqa: F811
    pg = open_page(browser, server, path)
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("!!(window.cvTyped && window.cvNumbers)")
    pg.wait_for_function("document.body.dataset.numbersReady")
    pg.evaluate("document.fonts.ready")
    return pg


def say(pg, word):
    pg.evaluate("w => window.cvTyped(w)", word)


def badges(pg):
    return pg.evaluate("Array.from(document.querySelectorAll('.num-badge')).map(b => [Number(b.dataset.n), b.dataset.key])")


def heard(pg):
    return pg.inner_text("#heard")


def test_badges_doctor_over_fullscreen_buttons_and_big(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    assert badges(pg) == []
    assert pg.evaluate("window.cvNumbers(true)") == 9
    assert sorted(badges(pg)) == [
        [1, "important"], [2, "medical-history"], [3, "today-treatment"],
        [4, "treatment-history"], [5, "intraoral-photos"], [6, "spoken-summary"], [8, "say-list"],
        [9, "change-role"], [10, "phone"],
    ]
    assert pg.locator("#num-dim").count() == 1
    dim = pg.locator("#num-dim").evaluate("e => getComputedStyle(e).backgroundColor")
    assert dim.startswith("rgba(0, 0, 0, 0.")  # 少し暗く
    for n, key in badges(pg):
        b = pg.locator(f'.num-badge[data-n="{n}"]').bounding_box()
        sel = ("#say-list-btn" if key == "say-list" else '[data-action="change-role"]' if key == "change-role"
               else '[data-action="phone"]' if key == "phone" else f'[data-part="{key}"] [data-action="fullscreen"]')
        btn = pg.locator(sel).bounding_box()
        assert abs((b["x"] + b["width"] / 2) - (btn["x"] + btn["width"] / 2)) <= 2, key
        assert abs((b["y"] + b["height"] / 2) - (btn["y"] + btn["height"] / 2)) <= 2, key
        assert b["width"] >= 70 and b["height"] >= 70, key
    size = pg.locator(".num-badge").first.evaluate("e => parseFloat(getComputedStyle(e).fontSize)")
    assert size >= 48
    pg.evaluate("window.cvNumbers(false)")
    assert badges(pg) == [] and pg.locator("#num-dim").count() == 0


def test_same_part_same_number_on_hygienist(server, browser):  # noqa: F811
    pg = open_unit(browser, server, HYG)
    pg.evaluate("window.cvNumbers(true)")
    got = dict((key, n) for n, key in badges(pg))
    assert got["important"] == 1 and got["medical-history"] == 2
    assert got["intraoral-photos"] == 5 and got["spoken-summary"] == 6 and got["perio-exam"] == 7 and got["say-list"] == 8
    assert "today-treatment" not in got and "treatment-history" not in got  # 画面に無い部品は出さない
    pg.evaluate("window.cvNumbers(false)")


def test_number_opens_part_and_clears_overlay(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    for word, part in [("1番", "important"), ("ごばん", "intraoral-photos"), ("6番を開いて", "spoken-summary"),
                       ("一番", "important"), ("5", "intraoral-photos"), ("ろく番を全画面にして", "spoken-summary")]:
        pg.evaluate("window.cvNumbers(true)")
        say(pg, word)
        pg.wait_for_selector(f'[data-fs-panel="{part}"]')
        assert badges(pg) == [] and pg.locator("#num-dim").count() == 0, word  # 聞き取りが終わったら消える
        say(pg, "戻して")
        pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")


def test_remaining_parts_open_by_number(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    for word, part in [("2番", "medical-history"), ("さんばん", "today-treatment"), ("よんばん", "treatment-history"),
                       ("4番を全画面にして", "treatment-history")]:
        pg.evaluate("window.cvNumbers(true)")
        say(pg, word)
        pg.wait_for_selector(f'[data-fs-panel="{part}"]')
        say(pg, "戻して")
        pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")


def test_no_numbers_inside_fullscreen_back_by_word(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "重要事項を全画面にして")
    pg.wait_for_selector('[data-fs-panel="important"]')
    assert pg.evaluate("window.cvNumbers(true)") == 0 and pg.locator("#num-dim").count() == 0
    say(pg, "いちばん")  # 全画面の中では番号は効かない
    pg.wait_for_function("document.getElementById('heard').textContent.includes('番号は出ていません')")
    assert pg.locator('[data-fs-panel="important"]').count() == 1
    say(pg, "戻して")
    pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")


def test_number_words_do_nothing_when_numbers_are_not_shown(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    for w in ["1番", "いちばん", "5", "ごばんを開いて"]:
        say(pg, w)
        pg.wait_for_function("document.getElementById('heard').textContent.includes('番号は出ていません')")
        assert pg.locator("[data-fs-panel]").count() == 0, w
        pg.evaluate("document.getElementById('heard').textContent = ''")


def test_number_not_on_screen(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "7番")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('その番号はありません')")
    assert pg.locator("[data-fs-panel]").count() == 0
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "ななばん")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('その番号はありません')")


def test_hygienist_perio_by_number_opens(server, browser):  # noqa: F811
    pg = open_unit(browser, server, HYG)
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "ななばん")
    pg.wait_for_selector('[data-fs-panel="perio-exam"]')


def test_overlay_numbers_beat_photo_numbers_on_normal_screen(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    assert pg.locator('[data-part="photo-list"] .ph .no').first.is_visible()
    pg.evaluate("window.cvNumbers(true)")
    assert not pg.locator('[data-part="photo-list"] .ph .no').first.is_visible()  # 写真の番号は出さない
    for word in ["3番", "3番を開いて", "3番を拡大して"]:
        pg.evaluate("window.cvNumbers(true)")
        say(pg, word)  # 部品の3（今日の処置）の全画面が開く。写真の3ではない
        pg.wait_for_selector('[data-fs-panel="today-treatment"]')
        say(pg, "戻して")
        pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "5番を拡大して")  # 部品の5（口腔内写真）の全画面が開く。写真の5ではない
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    assert pg.locator(".fs-fig").count() == 1 and pg.locator(".fs-fig").first.get_attribute("data-n") != "5"


def test_photo_numbers_only_inside_photo_fullscreen(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "3番を拡大して")  # 番号が出ていないいつもの画面では効かない
    pg.wait_for_function("document.getElementById('heard').textContent.includes('番号は出ていません')")
    assert pg.locator("[data-fs-panel]").count() == 0
    say(pg, "1番と5番を大きく")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('番号は出ていません')")
    assert pg.locator("[data-fs-panel]").count() == 0
    say(pg, "口腔内写真の3番を拡大して")  # 名前つきならいつもの画面から開く
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-fig')
    js = "w => JSON.stringify(Array.from(document.querySelectorAll('.fs-fig')).map(e => Number(e.dataset.n))) === JSON.stringify(w)"
    for word, want in [("5番", [5]), ("ごばん", [5]), ("1番と5番を大きく", [1, 5]), ("3番を拡大して", [3]), ("10", [10])]:
        say(pg, word)
        pg.wait_for_function(js, arg=want)
    say(pg, "99番")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('その番号はありません')")


def test_questions_unchanged_with_overlay(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "前回は何をした")  # 質問は番号が出ていてもこれまでどおり
    pg.wait_for_function("document.body.dataset.answer && document.body.dataset.answer !== 'waiting'")
    # 番号の部品は開かない（答えの画面は開いてよい）。番号は消える
    assert pg.locator("[data-fs-panel]:not([data-fs-panel='answer'])").count() == 0 and badges(pg) == []


def test_hidden_screen_has_no_numbers(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("CVActions.run('hide-toggle')")
    assert pg.evaluate("window.cvNumbers(true)") == 0
    assert pg.locator("#num-dim").count() == 0
    pg.evaluate("CVActions.run('hide-toggle')")


def test_reception_has_no_numbers(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/reception?typed=1")
    pg.wait_for_selector("body[data-kind='reception']")
    assert pg.evaluate("typeof window.cvNumbers") == "undefined"
    assert pg.locator(".num-badge, #num-dim").count() == 0


def test_numbers_config_and_say_list(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    cfg = pg.evaluate("fetch('/voice/numbers').then(r => r.json())")
    assert "back" not in cfg and cfg["parts"]["important"] == 1 and cfg["parts"]["medical-history"] == 2
    assert cfg["parts"]["today-treatment"] == 3
    assert len(set(cfg["parts"].values())) == len(cfg["parts"])
    assert cfg["parts"]["say-list"] == 8
    pg.click("#say-list-btn")
    pg.wait_for_selector('[data-fs-panel="say-list"]')
    assert "(" not in pg.inner_text('[data-fs-panel="say-list"]')


FAKE_MIC = """
Object.defineProperty(navigator, 'mediaDevices', {value: {getUserMedia: async () => ({getTracks: () => [{stop() {}}]})}, configurable: true});
window.MediaRecorder = class {
  constructor() { this.state = 'inactive'; }
  start() { this.state = 'recording'; }
  stop() { this.state = 'inactive'; setTimeout(() => { this.ondataavailable && this.ondataavailable({data: new Blob(['x'])}); this.onstop && this.onstop(); }, 30); }
};
"""


def test_button2_numbers_during_listening_and_timing_log(server, browser):  # noqa: F811
    """録音中だけ丸の番号が出て、止めると消え、言葉は出ていた番号で受ける。時間は1行のログに残る（マイクと文字起こしは偽物）。"""
    import json
    import time
    from pathlib import Path

    log = Path(__file__).resolve().parent.parent / "data" / "runtime" / "logs" / "voice_timing.log"
    before = log.read_text(encoding="utf-8").count(chr(10)) if log.exists() else 0
    pg = browser.new_page(viewport={"width": 1920, "height": 1030})
    pg.add_init_script(FAKE_MIC)
    pg.route("**/voice/transcribe", lambda r: r.fulfill(json={"text": "1番"}))
    pg.goto(f"http://127.0.0.1:{server}{DOC}")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("document.body.dataset.numbersReady")
    pg.evaluate("CVActions.run('button2')")
    pg.wait_for_selector(".topbar .mic.rec")
    pg.wait_for_selector(".num-badge")
    assert pg.locator(".num-badge").count() == 9 and pg.locator("#num-dim").count() == 1
    pg.evaluate("CVActions.run('button2')")  # 1回で止まる（止め方は今のまま）
    pg.wait_for_selector('[data-fs-panel="important"]')
    assert pg.locator(".num-badge").count() == 0 and pg.locator("#num-dim").count() == 0
    pg.wait_for_function("document.body.dataset.timing")
    t = json.loads(pg.evaluate("document.body.dataset.timing"))
    assert set(t) == {"transcribe_ms", "interpret_ms", "apply_ms", "total_ms", "mic_ms", "kind"} and t["kind"] == "操作"
    assert t["total_ms"] >= t["transcribe_ms"] + t["interpret_ms"] - 3
    for _ in range(30):
        if log.exists() and log.read_text(encoding="utf-8").count(chr(10)) == before + 1:
            break
        time.sleep(0.2)
    assert log.read_text(encoding="utf-8").count(chr(10)) == before + 1  # 1回の声で1行
    last = log.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "文字起こし" in last and "判定" in last and "画面の反映" in last and "合計" in last and "録音の開始" in last
    assert "1番" not in last  # 言葉の中身は残さない
    pg.close()


# ---- 暗い画面の文字・質問のボタン・全画面の上の帯・言える言葉・写真の並べて・/app への移動 ----
import json  # noqa: E402

from tests.screen_helper import ROOT  # noqa: E402

EX = json.loads((ROOT / "config" / "examples.json").read_text(encoding="utf-8"))
QUESTIONS = ["前回は何をした？", "アレルギーは？", "薬は？", "次回は？"]


def chips(pg):
    return pg.evaluate("Array.from(document.querySelectorAll('#num-band .ex-chip')).map(e => e.textContent)")


def test_badge_text_has_ban(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    texts = pg.evaluate("Array.from(document.querySelectorAll('.num-badge')).map(e => e.textContent)")
    assert sorted(texts) == sorted(["1番", "2番", "3番", "4番", "5番", "6番", "8番", "9番", "10番"])
    say(pg, "1番")
    pg.wait_for_selector('[data-fs-panel="important"]')


def test_question_buttons_shown_bright_and_work_as_written(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    got = pg.evaluate("Array.from(document.querySelectorAll('#num-questions .q-btn')).map(e => e.textContent)")
    assert got == QUESTIONS
    z_dim = pg.locator("#num-dim").evaluate("e => Number(getComputedStyle(e).zIndex)")
    assert pg.locator("#num-questions").evaluate("e => Number(getComputedStyle(e).zIndex)") > z_dim  # 暗い画面より明るく手前に
    for q in QUESTIONS:
        pg.evaluate("window.cvNumbers(true)")
        pg.evaluate("document.body.dataset.answer = ''")
        say(pg, q)  # 出ている言葉のとおりに言えば動く
        pg.wait_for_function("document.body.dataset.answer && document.body.dataset.answer !== 'waiting'", timeout=20000)
        assert pg.locator("#num-questions").count() == 0  # 聞き取りが終わったら消える
        pg.evaluate("CVActions.run('fs-close')")
    pg.evaluate("window.cvNumbers(true)")
    pg.evaluate("document.body.dataset.answer = ''")
    say(pg, "アレルギーは？")
    pg.wait_for_selector('[data-fs-panel="answer"]')  # 記録から直接答える


def open_screen(pg, name):
    if name == "answer":
        say(pg, "アレルギーは？")
    elif name == "say-list":
        pg.click("#say-list-btn")
    else:
        say(pg, {"important": "重要事項を全画面にして", "intraoral-photos": "口腔内写真の3番を拡大して",
                 "spoken-summary": "話した内容を全画面にして", "medical-history": "全身既往を全画面にして",
                 "today-treatment": "今日の処置を全画面にして", "treatment-history": "治療歴を全画面にして"}[name])
    pg.wait_for_selector(f'[data-fs-panel="{name}"]')


SCREENS = ["important", "intraoral-photos", "spoken-summary", "answer", "say-list", "medical-history", "today-treatment", "treatment-history"]


@pytest.mark.parametrize("name", SCREENS)
def test_fullscreen_top_band_dark_with_examples_that_work(server, browser, name):  # noqa: F811
    pg = open_unit(browser, server)
    open_screen(pg, name)
    assert pg.evaluate("window.cvNumbers(true)") == 0  # 全画面の中に丸の番号は付けない
    band = pg.locator("#num-band")
    assert band.count() == 1 and pg.locator("#num-dim").count() == 0  # 全体は暗くしない
    top = pg.locator(".topbar").bounding_box()
    b = band.bounding_box()
    assert b["y"] <= 1 and abs(b["height"] - top["height"]) <= 6 and b["width"] >= 1900  # 上の帯だけ
    bg = band.evaluate("e => getComputedStyle(e).backgroundColor")
    assert bg.startswith("rgba(8, 10, 14")
    panel = pg.locator(f'[data-fs-panel="{name}"]').bounding_box()
    assert panel["y"] + 1 >= b["y"] + b["height"] - 1  # 本文は帯の下。暗くならない
    sc = EX["screens"][name]
    want = (EX["page_words"] if sc["pages"] and pg.evaluate("(() => { const n = document.querySelector('.fs-panel [data-action=fs-next]'); return !!n && !n.hidden })()") else []) + sc["words"]
    assert chips(pg) == ["「" + w + "」" for w in want]
    assert "戻して" in sc["words"]
    # 例文はそのまま言えば動く
    for w in want:
        pg.evaluate("window.cvNumbers(true)")
        say(pg, w)
        pg.wait_for_function("document.querySelectorAll('#num-band').length === 0")  # 聞き取りが終わったら元に戻る
        if w == "戻して":
            pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")
        elif "拡大" in w or "並べて" in w:
            assert pg.evaluate("Array.from(document.querySelectorAll('.fs-fig')).map(e => Number(e.dataset.n))") == [1, 3]
        else:
            assert pg.locator(f'[data-fs-panel="{name}"]').count() == 1
    assert pg.locator("#num-band, #num-dim").count() == 0


def test_photos_not_dimmed_in_photo_fullscreen(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    open_screen(pg, "intraoral-photos")
    pg.evaluate("window.cvNumbers(true)")
    img = pg.locator(".fs-fig img").first.bounding_box()
    band = pg.locator("#num-band").bounding_box()
    assert img["y"] >= band["y"] + band["height"]
    # 写真の上に重なる暗い物は無い
    cx, cy = img["x"] + img["width"] / 2, img["y"] + img["height"] / 2
    top_el = pg.evaluate("([x, y]) => document.elementFromPoint(x, y).tagName", [cx, cy])
    assert top_el == "IMG"
    assert pg.locator("#num-dim").count() == 0


def test_every_fullscreen_has_an_examples_row():
    # 全画面が増えたら config/examples.json の表に足す。足し忘れを見つける
    import re

    html = open(ROOT / "app" / "views" / "render.py", encoding="utf-8").read()

    parts = set(re.findall(r'data-fs="([a-z-]+)"', html))
    assert parts >= {"important", "intraoral-photos", "spoken-summary"}
    for p in parts:
        assert p in EX["screens"], p + " の例文が表に無い"
    assert "answer" in EX["screens"] and "say-list" in EX["screens"]


def test_hidden_screen_still_gets_a_dark_band(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("CVActions.run('hide-toggle')")
    pg.evaluate("window.cvNumbers(true)")
    assert pg.locator("#num-band").count() == 1
    assert "画面を隠しています" in pg.inner_text("#num-band")
    pg.evaluate("window.cvNumbers(false)")
    pg.evaluate("CVActions.run('hide-toggle')")


def test_say_list_by_number_and_word(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "8番")
    pg.wait_for_selector('[data-fs-panel="say-list"]')
    say(pg, "戻して")
    pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")
    for w in ["言える言葉を全画面にして", "言える言葉"]:
        say(pg, w)
        pg.wait_for_selector('[data-fs-panel="say-list"]')
        say(pg, "戻して")
        pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")


def test_side_by_side_photo_words():
    for w, nums in [("1番と3番を並べて拡大して", [1, 3]), ("1番と3番を並べて", [1, 3]), ("1番と3番を並べて大きく", [1, 3]),
                    ("1番と3番と5番を並べて", [1, 3, 5])]:
        res = interpret(w)
        assert res["kind"] == OP and res["action"] == "photo-show" and res["numbers"] == nums, w
    res = interpret("口腔内写真の1番と3番を並べて拡大して")
    assert res["action"] == "photo-open" and res["numbers"] == [1, 3]


def test_side_by_side_in_photo_fullscreen(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "口腔内写真の1番と3番を並べて")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 2")
    say(pg, "3番を拡大して")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 1")
    say(pg, "1番と3番を並べて拡大して")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 2")


def test_outside_app_opens_same_screen_inside_app(server, browser):  # noqa: F811
    import time

    for path, sel in [("/", "[data-part=appointment-list]"), ("/recordings", "body")]:
        pg = open_page(browser, server, path)
        pg.wait_for_selector(sel)
        time.sleep(0.4)
        key = json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))["button1"].split("+")[-1]
        for _ in range(2):
            pg.evaluate("k => window.dispatchEvent(new KeyboardEvent('keydown', {code: k, key: k, ctrlKey: true, shiftKey: true, bubbles: true}))", key)
            time.sleep(0.08)
        pg.wait_for_url("**/app?**")
        assert "go=" in pg.url and "start=1" in pg.url
        inner_src = pg.evaluate("document.getElementById('inner').getAttribute('src')")
        assert inner_src == path
        pg.close()


def test_app_go_only_takes_local_screens(server, browser):  # noqa: F811
    for go, want in [("/recordings", "/recordings"), ("//evil.example/x", "/"), ("http://evil.example", "/"), ("/app?go=/", "/"),
                     ("/unit?appt=1&role=doctor", "/unit?appt=1&amp;role=doctor")]:
        import urllib.parse
        import urllib.request

        with urllib.request.urlopen(f"http://127.0.0.1:{server}/app?go=" + urllib.parse.quote(go, safe="")) as r:
            body = r.read().decode("utf-8")
        assert f"src='{want}'" in body, (go, want)


def test_unit_button1_outside_app_goes_to_app(server, browser):  # noqa: F811
    import time

    pg = open_unit(browser, server)
    key = json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))["button1"].split("+")[-1]
    for _ in range(2):
        pg.evaluate("k => window.dispatchEvent(new KeyboardEvent('keydown', {code: k, key: k, ctrlKey: true, shiftKey: true, bubbles: true}))", key)
        time.sleep(0.08)
    pg.wait_for_url("**/app?**")
    assert pg.evaluate("document.getElementById('inner').getAttribute('src')").startswith("/unit?appt=")


# ---- G14g: 9番 = 役割を変える ----

def role_of(pg):
    return pg.evaluate("document.body.className.includes('role-hygienist') ? 'hygienist' : 'doctor'")


def test_9_is_change_role_after_the_existing_numbers():
    cfg = json.loads((ROOT / "config" / "numbers.json").read_text(encoding="utf-8"))["parts"]
    assert cfg["change-role"] == 9
    assert [cfg[k] for k in ("important", "medical-history", "today-treatment", "treatment-history",
                             "intraoral-photos", "spoken-summary", "perio-exam", "say-list")] == [1, 2, 3, 4, 5, 6, 7, 8]
    assert "change-patient" not in cfg  # 患者様を変えるには番号を付けない（スマホは G14h で10番）


def test_badge_9_sits_on_change_role_and_none_on_change_patient(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    assert [9, "change-role"] in badges(pg)
    b = pg.locator('.num-badge[data-n="9"]')
    assert b.inner_text() == "9番"
    bb, btn = b.bounding_box(), pg.locator('[data-action="change-role"]').bounding_box()
    assert abs((bb["x"] + bb["width"] / 2) - (btn["x"] + btn["width"] / 2)) <= 2
    assert abs((bb["y"] + bb["height"] / 2) - (btn["y"] + btn["height"] / 2)) <= 2
    assert not any(k == "change-patient" for _, k in badges(pg))
    pg.close()


@pytest.mark.parametrize("word", ["9番", "9番です", "きゅうばん", "9番を開いて"])
def test_saying_9_switches_role_like_the_mouse(server, browser, word):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    say(pg, word)
    pg.wait_for_function("document.body.className.includes('role-hygienist')")
    assert role_of(pg) == "hygienist"
    assert pg.locator(".num-badge").count() == 0  # 言い終わったら番号は消える
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "9番")  # もう一度で歯科医師へ
    pg.wait_for_function("document.body.className.includes('role-doctor')")
    pg.close()


def test_9_without_badges_does_nothing(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "9番")
    pg.wait_for_timeout(300)
    assert role_of(pg) == "doctor"
    pg.close()


def test_9_inside_fullscreen_does_nothing(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.click('[data-part="important"] [data-action="fullscreen"]')
    pg.wait_for_selector(".fs-panel")
    say(pg, "9番")
    pg.wait_for_timeout(300)
    assert role_of(pg) == "doctor" and pg.locator(".fs-panel").count() == 1
    pg.close()


def test_say_list_and_examples_mention_9(server, browser):  # noqa: F811
    ex = json.loads((ROOT / "config" / "examples.json").read_text(encoding="utf-8"))
    assert "9番 役割を変える" in ex["say_list"][0]["words"]


# ---- G14h: スマホで写真をやり取り（声と10番） ----

def modal_open(pg):
    return pg.locator("#phone-modal").count() == 1


@pytest.mark.parametrize("word", [
    "スマホで写真をやり取り", "スマホ", "スマホで写真", "QR", "QRを出して", "スマホで写真をやり取りして", "スマホを開いて",
    "スマートフォン", "キューアール", "QRコード",
])
def test_phone_words_open_qr_in_normal_screen(server, browser, word):  # noqa: F811
    assert interpret(word, "unit")["action"] == "phone-open"
    pg = open_unit(browser, server)
    say(pg, word)
    pg.wait_for_selector("#phone-modal")
    assert pg.locator("#phone-modal .qr svg").count() == 1 or pg.wait_for_selector("#phone-modal .qr svg")
    pg.close()


def test_phone_words_open_qr_inside_photo_fullscreen(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector(".fs-panel")
    say(pg, "スマホで写真をやり取り")
    pg.wait_for_selector("#phone-modal")
    pg.wait_for_selector("#phone-modal .qr svg")
    assert "もう一度お願いします" not in pg.evaluate("document.body.dataset.heard")
    pg.close()


def test_phone_goes_through_the_button_click(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("""() => { window.__p = 0; document.addEventListener('click', e => {
        if (e.target.closest('[data-action=phone]')) window.__p++; }, true); }""")
    say(pg, "スマホ")
    pg.wait_for_selector("#phone-modal")
    assert pg.evaluate("window.__p") == 1
    pg.close()


def test_badge_10_on_phone_button_bright_and_not_overlapping(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    assert [10, "phone"] in badges(pg)
    b = pg.locator('.num-badge[data-n="10"]')
    assert b.inner_text() == "10番"
    bb, btn = b.bounding_box(), pg.locator('[data-action="phone"]').bounding_box()
    assert abs((bb["x"] + bb["width"] / 2) - (btn["x"] + btn["width"] / 2)) <= 2
    assert abs((bb["y"] + bb["height"] / 2) - (btn["y"] + btn["height"] / 2)) <= 2
    for n in range(1, 10):  # ほかの丸と重ならない
        o = pg.locator(f'.num-badge[data-n="{n}"]')
        if not o.count():
            continue
        ob = o.bounding_box()
        assert (ob["x"] + ob["width"] <= bb["x"] or bb["x"] + bb["width"] <= ob["x"]
                or ob["y"] + ob["height"] <= bb["y"] or bb["y"] + bb["height"] <= ob["y"]), n
    # ボタンそのものも暗くならない（暗い幕より前に出る）
    z = pg.evaluate("getComputedStyle(document.querySelector('[data-action=phone]')).zIndex")
    assert z not in ("auto", "0") and int(z) > 30
    pg.close()


def test_saying_10_opens_qr_and_1_to_9_unchanged(server, browser):  # noqa: F811
    cfg = json.loads((ROOT / "config" / "numbers.json").read_text(encoding="utf-8"))["parts"]
    assert cfg["phone"] == 10 and cfg["change-role"] == 9 and cfg["say-list"] == 8 and cfg["important"] == 1
    pg = open_unit(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "10番")
    pg.wait_for_selector("#phone-modal")
    assert pg.locator(".num-badge").count() == 0
    pg.close()


def test_10_without_badges_or_in_fullscreen_does_nothing(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "10番")
    pg.wait_for_timeout(300)
    assert not modal_open(pg)
    pg.click('[data-part="important"] [data-action="fullscreen"]')
    pg.wait_for_selector(".fs-panel")
    say(pg, "10番")
    pg.wait_for_timeout(300)
    assert not modal_open(pg)
    pg.close()


def test_examples_mention_phone():
    ex = json.loads((ROOT / "config" / "examples.json").read_text(encoding="utf-8"))
    assert "スマホで写真をやり取り" in ex["screens"]["intraoral-photos"]["words"]
    assert "10番 スマホで写真をやり取り" in ex["say_list"][0]["words"]
