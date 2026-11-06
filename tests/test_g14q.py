"""G14q: 歯周検査の全画面でも、声を待つときに暗くして、押せるボタンに番号と、言える言葉を出す。
ほかの全画面と同じ決まり（numrule.js の番号・examples.json の表）に乗せる。歯周検査だけの特別扱いは入れない。"""
import json

from tests.screen_helper import ROOT, browser, server  # noqa: F401
from tests.test_voice_numbers import HYG, open_unit, say

EX = json.loads((ROOT / "config" / "examples.json").read_text(encoding="utf-8"))


def open_perio(browser, server):  # noqa: F811
    pg = open_unit(browser, server, HYG)
    say(pg, "歯周検査を全画面にして")
    pg.wait_for_selector('[data-fs-panel="perio-exam"]')
    return pg


def chips(pg):
    return [t.strip("「」") for t in pg.locator("#num-band .ex-chip").all_inner_texts()]


def badges(pg):
    return pg.evaluate("Array.from(document.querySelectorAll('.num-badge')).map(b => [b.textContent, b.dataset.key.split('] ').pop()])")


def scroll_top(pg):
    return pg.evaluate("document.querySelector('.fs-panel .fs-scroll').scrollTop")


def test_table_marks_perio_numbered_buttons_and_no_other_screen_changed():
    assert EX["screens"]["perio-exam"]["numbered_buttons"] is True
    assert [k for k, v in EX["screens"].items() if v.get("numbered_buttons")] == ["perio-exam"]


def test_perio_fullscreen_dims_and_shows_numbers_and_words(server, browser):  # noqa: F811
    pg = open_perio(browser, server)
    assert pg.evaluate("document.querySelectorAll('.fs-page').length") >= 2  # 組が2つ以上ある（次のページが効く）
    n = pg.evaluate("window.cvNumbers(true)")
    assert n == 2
    assert badges(pg) == [["1番", '[data-action="fs-next"]'], ["2番", '[data-action="fs-close"]']]  # 最初のページ: 前のページは押せないので出さない
    assert chips(pg) == ["次のページ", "戻して"]  # 効かない「前のページ」は出さない
    assert pg.locator("#num-dim").count() == 1  # 少し暗くする
    band = pg.locator("#num-band").bounding_box()
    assert band["y"] <= 1 and band["width"] >= 1900
    pg.evaluate("window.cvNumbers(false)")
    assert pg.locator("#num-band, #num-dim, .num-badge").count() == 0


def test_perio_number_1_next_page_then_number_for_prev_and_close(server, browser):  # noqa: F811
    pg = open_perio(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    say(pg, "1番")  # 次のページ
    pg.wait_for_function("document.querySelector('.fs-panel .fs-scroll').scrollTop > 0")
    pg.evaluate("window.cvNumbers(true)")
    got = badges(pg)
    assert got[-1] == [f"{len(got)}番", '[data-action="fs-close"]']  # 「もとに戻す」は最後
    assert any(k == '[data-action="fs-prev"]' for _, k in got)  # 2ページ目からは前のページも押せる
    prev_no = [t for t, k in got if k == '[data-action="fs-prev"]'][0]
    top = scroll_top(pg)
    say(pg, prev_no)
    pg.wait_for_function(f"document.querySelector('.fs-panel .fs-scroll').scrollTop < {top}")
    pg.evaluate("window.cvNumbers(true)")
    say(pg, badges(pg)[-1][0])  # 最後の番号 = もとに戻す
    pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")


def test_perio_last_page_has_no_next(server, browser):  # noqa: F811
    pg = open_perio(browser, server)
    pg.evaluate("for (let i = 0; i < 20; i++) CVActions.run('fs-next')")
    pg.wait_for_function("document.querySelector('.fs-panel [data-action=fs-next]').disabled")
    pg.evaluate("window.cvNumbers(true)")
    assert [k for _, k in badges(pg)] == ['[data-action="fs-prev"]', '[data-action="fs-close"]']
    assert chips(pg) == ["前のページ", "戻して"]  # 押せない「次のページ」は出さない


def test_perio_words_work_and_wobbles_are_caught(server, browser):  # noqa: F811
    pg = open_perio(browser, server)
    for heard in ["次のページ", "つぎのページ", "次のペイジ", "次ページ"]:
        pg.evaluate("document.querySelector('.fs-panel .fs-scroll').scrollTop = 0")
        pg.evaluate("window.cvNumbers(true)")
        say(pg, heard)
        pg.wait_for_function("document.querySelector('.fs-panel .fs-scroll').scrollTop > 0", timeout=5000)
    pg.close()
    for heard in ["元に戻す", "もとにもどす", "元にもどす", "戻して"]:
        pg = open_perio(browser, server)
        pg.evaluate("window.cvNumbers(true)")
        say(pg, heard)
        pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0", timeout=5000)
        pg.close()


def test_spoken_summary_numbers_unchanged_and_same_rule(server, browser):  # noqa: F811
    """話した内容の整理の番号はこれまでどおり。番号の並べ方は同じ決まり（5・8を飛ばす）。"""
    pg = open_unit(browser, server, HYG)
    say(pg, "話した内容を全画面にして")
    pg.wait_for_selector('[data-fs-panel="spoken-summary"]')
    pg.evaluate("window.cvNumbers(true)")
    nums = pg.evaluate("Array.from(document.querySelectorAll('.num-badge')).map(b => Number(b.dataset.n))")
    assert nums and 5 not in nums and 8 not in nums
