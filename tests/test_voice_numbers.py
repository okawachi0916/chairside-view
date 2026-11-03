"""G14c: 言葉の揺れに強くする（戻す・助詞が抜けた形）と、丸の番号で部品を呼ぶ。Claude は使わない。"""
import pytest

from app.views import data as D
from app.voice.interpret import FAILED, OP, QUESTION, UNRELATED, interpret
from tests.screen_helper import browser, open_page, server  # noqa: F401

H_DOC = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
DOC = f"/unit?appt={H_DOC}&role=doctor&typed=1&hide=1"
HYG = f"/unit?appt={H_DOC}&role=hygienist&typed=1&hide=1"

PARTS = {"重要事項": "important", "口腔内写真": "intraoral-photos", "話した内容": "spoken-summary"}
NOT_YET = ["全身既往", "今日の処置", "治療歴"]
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


@pytest.mark.parametrize("part", NOT_YET)
def test_particle_less_words_for_unimplemented(part):
    for tail in ["全画面表示", "全画面", "の全画面表示", "全画面にして", "を全画面にして"]:
        res = interpret(part + tail)
        assert res["kind"] == OP and res["action"] is None and res["message"] == "まだ開けません", part + tail


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
    assert pg.evaluate("window.cvNumbers(true)") == 6
    assert sorted(badges(pg)) == [
        [1, "important"], [2, "medical-history"], [3, "today-treatment"],
        [4, "treatment-history"], [5, "intraoral-photos"], [6, "spoken-summary"],
    ]
    assert pg.locator("#num-dim").count() == 1
    dim = pg.locator("#num-dim").evaluate("e => getComputedStyle(e).backgroundColor")
    assert dim.startswith("rgba(0, 0, 0, 0.")  # 少し暗く
    for n, key in badges(pg):
        b = pg.locator(f'.num-badge[data-n="{n}"]').bounding_box()
        btn = pg.locator(f'[data-part="{key}"] [data-action="fullscreen"]').bounding_box()
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
    assert got["intraoral-photos"] == 5 and got["spoken-summary"] == 6 and got["perio-exam"] == 7
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


def test_not_yet_parts_get_number_and_say_not_yet(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    for word in ["2番", "さんばん", "よんばん", "4番を全画面にして"]:
        pg.evaluate("window.cvNumbers(true)")
        say(pg, word)
        pg.wait_for_function("document.getElementById('heard').textContent.includes('まだ開けません')")
        assert pg.locator("[data-fs-panel]").count() == 0
        pg.evaluate("document.getElementById('heard').textContent = ''")


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


def test_hygienist_perio_by_number_says_not_yet(server, browser):  # noqa: F811
    pg = open_unit(browser, server, HYG)
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "ななばん")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('まだ開けません')")


def test_overlay_numbers_beat_photo_numbers_on_normal_screen(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    assert pg.locator('[data-part="photo-list"] .ph .no').first.is_visible()
    pg.evaluate("window.cvNumbers(true)")
    assert not pg.locator('[data-part="photo-list"] .ph .no').first.is_visible()  # 写真の番号は出さない
    for word in ["3番", "3番を開いて", "3番を拡大して"]:
        pg.evaluate("window.cvNumbers(true)")
        say(pg, word)  # 部品の3（今日の処置）。まだ開けません
        pg.wait_for_function("document.getElementById('heard').textContent.includes('まだ開けません')")
        assert pg.locator("[data-fs-panel]").count() == 0
        pg.evaluate("document.getElementById('heard').textContent = ''")
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
    pg.wait_for_function("document.body.dataset.answer === 'retry'")
    assert pg.locator("[data-fs-panel]").count() == 0 and badges(pg) == []


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
    pg.click("#say-list-btn")
    pg.wait_for_selector("#say-list li")
    assert "(" not in pg.inner_text("#say-list")


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
    assert pg.locator(".num-badge").count() == 6 and pg.locator("#num-dim").count() == 1
    pg.evaluate("CVActions.run('button2')")  # 1回で止まる（止め方は今のまま）
    pg.wait_for_selector('[data-fs-panel="important"]')
    assert pg.locator(".num-badge").count() == 0 and pg.locator("#num-dim").count() == 0
    pg.wait_for_function("document.body.dataset.timing")
    t = json.loads(pg.evaluate("document.body.dataset.timing"))
    assert set(t) == {"transcribe_ms", "interpret_ms", "apply_ms", "total_ms", "kind"} and t["kind"] == "操作"
    assert t["total_ms"] >= t["transcribe_ms"] + t["interpret_ms"] - 3
    for _ in range(30):
        if log.exists() and log.read_text(encoding="utf-8").count(chr(10)) == before + 1:
            break
        time.sleep(0.2)
    assert log.read_text(encoding="utf-8").count(chr(10)) == before + 1  # 1回の声で1行
    last = log.read_text(encoding="utf-8").strip().splitlines()[-1]
    assert "文字起こし" in last and "判定" in last and "画面の反映" in last and "合計" in last
    assert "1番" not in last  # 言葉の中身は残さない
    pg.close()
