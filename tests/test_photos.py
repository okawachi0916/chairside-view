"""G14: 口腔内写真を番号で呼ぶ。文字の口（cvTyped）から言葉を全部試す。"""
import json
import urllib.error
import urllib.request

from app.views import data as D
from app.views import photos as P
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

ROWS = [r for r in D.today_list() if r["patient_id"] == 1]
H_DOC = ROWS[0]["id"]
UNIT = f"/unit?appt={H_DOC}&role=doctor&typed=1&hide=1"


def open_unit(browser, server, path=UNIT):  # noqa: F811
    pg = open_page(browser, server, path)
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("window.cvTyped")
    return pg


def say(pg, word):
    # 写真の番号は全画面の中でだけ効く。いつもの画面からは「口腔内写真の」を付けて言う
    if word.endswith(("拡大して", "大きく", "拡大する")) and pg.locator("[data-fs-panel]").count() == 0:
        word = "口腔内写真の" + word
    pg.evaluate("w => window.cvTyped(w)", word)


def figs(pg):
    return pg.locator(".fs-fig").evaluate_all("els => els.map(e => Number(e.dataset.n))")


def heard(pg):
    return pg.inner_text("#heard")


def test_photos_listed_and_served(server):  # noqa: F811
    listing = json.loads((ROOT / "data" / "photos" / "photos.json").read_text(encoding="utf-8"))["photos"]
    assert len(listing) == 17
    for x in listing:
        assert (ROOT / "data" / "photos" / x["file"]).is_file()
        with urllib.request.urlopen(f"http://127.0.0.1:{server}/photo-files/{x['file']}") as r:
            assert r.status == 200 and r.headers["Content-Type"].startswith("image/")
    assert P.url_for(1) == "/photo-files/" + listing[0]["file"]
    assert P.url_for(18) == P.url_for(1)
    for bad in ("nothing.jpg", "..%2Fphotos.json"):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{server}/photo-files/{bad}")
            raise AssertionError("開けてはいけない")
        except urllib.error.HTTPError as e:
            assert e.code == 404


def test_normal_screen_grouped_by_day_newest_first(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    groups = pg.locator('[data-part="intraoral-photos"] .pg')
    assert groups.count() == 3
    dates = groups.locator(".pg-date").all_inner_texts()
    assert dates == ["2026年8月7日", "2026年2月6日", "2025年11月25日"]
    first = pg.locator('[data-part="intraoral-photos"] .pg').first.locator(".ph .no").all_inner_texts()
    assert first == [str(i) for i in range(9, 18)]  # 13番からは最後の日に足した（G18）
    lst = pg.locator('[data-part="photo-list"]')
    assert lst.evaluate("e => e.scrollHeight > e.clientHeight + 1")  # 古い日はスクロールで遡る
    lst.evaluate("e => { e.scrollTop = e.scrollHeight }")
    assert pg.locator('[data-part="photo-list"] .ph[data-n="1"]').is_visible()
    assert pg.locator('[data-part="photo-list"] .ph img').first.evaluate("i => i.complete && i.naturalWidth > 0")


def test_fullscreen_sizes_left_is_2_5_times(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    thumb = pg.locator('[data-part="photo-list"] .ph').first.bounding_box()
    say(pg, "3番を拡大して")
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-fig')
    big = pg.locator(".fs-fig img").first.bounding_box()
    small = pg.locator(".fs-item .ph").first.bounding_box()
    assert abs(small["width"] - thumb["width"]) < 1 and abs(small["height"] - thumb["height"]) < 1
    assert 2.3 <= big["width"] / small["width"] <= 2.7 and 2.3 <= big["height"] / small["height"] <= 2.7
    assert big["x"] < small["x"]  # 左に大きい写真、右に一覧


def test_enlarge_words(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "3番を拡大して")
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    assert figs(pg) == [3]
    assert "写真 3 2025年11月25日" in pg.inner_text(".fs-big")
    assert pg.locator(".fs-item.sel").count() == 1
    say(pg, "1番と5番を大きく")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 2")
    assert figs(pg) == [1, 5] and pg.locator(".fs-item.sel").count() == 2
    boxes = pg.locator(".fs-fig img").evaluate_all("els => els.map(e => [e.width, e.height])")
    assert boxes[0] == boxes[1]
    say(pg, "1番と5番と10番を大きく")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 3")
    assert figs(pg) == [1, 5, 10]
    boxes = pg.locator(".fs-fig img").evaluate_all("els => els.map(e => [e.width, e.height])")
    assert boxes[0] == boxes[1] == boxes[2]
    say(pg, "7番を拡大する")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 1")
    assert figs(pg) == [7]


def test_back_to_list_and_pages(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.set_viewport_size({"width": 1200, "height": 470})  # 一覧が1画面に入らない大きさ
    say(pg, "17番を拡大して")  # 一覧の先頭（新しい順）。開いたとき一覧は一番上にある
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    lst = pg.locator(".fs-list")
    assert lst.evaluate("e => e.scrollHeight > e.clientHeight + 1")
    say(pg, "次のページ")
    pg.wait_for_function("document.querySelector('.fs-list').scrollTop > 0")
    say(pg, "前のページ")
    pg.wait_for_function("document.querySelector('.fs-list').scrollTop === 0")
    say(pg, "一覧に戻す")
    pg.wait_for_function("document.querySelectorAll('[data-fs-panel]').length === 0")
    assert pg.locator('[data-part="photo-list"]').is_visible()


def test_missing_number_says_so_and_changes_nothing(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "99番を拡大して")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('その番号はありません')")
    assert pg.locator("[data-fs-panel]").count() == 0
    say(pg, "3番を拡大して")
    pg.wait_for_selector(".fs-fig")
    say(pg, "1番と99番を大きく")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('その番号はありません')")
    assert figs(pg) == [3]  # 状態は変わらない


def test_enlarged_state_survives_hide_and_restore(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "1番と5番を大きく")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 2")
    pg.evaluate("CVActions.run('hide-toggle')")
    assert pg.locator(".fs-fig").count() == 0 and pg.locator("img").count() == 0
    pg.evaluate("CVActions.run('hide-toggle')")
    assert figs(pg) == [1, 5]
    assert pg.locator(".fs-item.sel").count() == 2


def test_click_on_list_picks_one(server, browser):  # noqa: F811
    pg = open_unit(browser, server, f"/unit?appt={H_DOC}&role=doctor&typed=1&hide=1")
    say(pg, "1番と5番を大きく")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 2")
    pg.locator('.fs-item[data-n="8"]').click()
    assert figs(pg) == [8]


def test_fewer_photos_patient(server, browser):  # noqa: F811
    ichiro = [r for r in D.today_list() if r["patient_id"] == 2][0]["id"]
    pg = open_unit(browser, server, f"/unit?appt={ichiro}&typed=1&hide=1")
    say(pg, "10番を拡大して")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('その番号はありません')")
    say(pg, "5番を拡大して")
    pg.wait_for_selector(".fs-fig")
    assert figs(pg) == [5]
