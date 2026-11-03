"""G24: 歯周基本検査の入力。数字・BOP・プラーク・動揺度を入れて保存し、再読み込みしても残る。"""
import httpx
import pytest

from app.db import connect
from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

ROWS = [r for r in D.today_list() if r["patient_id"] == 1]
H_HYG = ROWS[1]["id"]
URL = f"/unit?appt={H_HYG}&role=hygienist"


def db(sql, *a):
    c = connect()
    try:
        return c.execute(sql, a).fetchall()
    finally:
        c.close()


@pytest.fixture(autouse=True)
def clean_exams():
    top = db("SELECT COALESCE(MAX(id), 0) FROM perio_exams")[0][0]

    def wipe():
        c = connect()
        c.execute("DELETE FROM perio_teeth WHERE exam_id > ?", (top,))
        c.execute("DELETE FROM perio_exams WHERE id > ?", (top,))
        c.commit()
        c.close()

    wipe()
    yield top
    wipe()


def open_unit(browser, server):  # noqa: F811
    pg = open_page(browser, server, URL)
    pg.wait_for_selector('[data-part="perio-exam"] table.perio')
    pg.wait_for_function("window.cv && document.querySelector('[data-action=\"perio-input\"]')")
    return pg


def teeth_of(pg):
    return pg.locator('[data-part="perio-exam"] td[data-k="pocket"]').evaluate_all("els => els.map(e => Number(e.dataset.tooth))")


def stats(pg):
    return {s.locator("small").inner_text(): s.locator("span").inner_text() for s in pg.locator(".perio-stats .st").all()}


def pick(pg, tooth, value, bop=False):
    pg.locator(f'[data-part="perio-exam"] td[data-k="pocket"][data-tooth="{tooth}"]').click()
    pg.locator(f'.perio-pop button[data-pocket="{value}"][data-bop="{1 if bop else 0}"]').click()


def test_enter_and_cancel_keeps_the_table(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    before = pg.inner_html('[data-part="perio-exam"] table.perio')
    pg.click('[data-action="perio-input"]')
    assert pg.locator("td.todo").count() == 26  # 全部の歯が未入力
    assert pg.locator('[data-action="perio-input"]').is_disabled()
    pg.click('[data-action="perio-cancel"]')
    assert pg.inner_html('[data-part="perio-exam"] table.perio') == before
    assert pg.locator(".perio-bar").count() == 0
    pg.close()


def test_input_save_reload_and_numbers(server, browser, clean_exams):  # noqa: F811
    old = db("SELECT exam_id, tooth, pocket, bop, plaque, mobility FROM perio_teeth ORDER BY exam_id, tooth")
    pg = open_unit(browser, server)
    teeth = teeth_of(pg)
    assert len(teeth) == 26
    pg.click('[data-action="perio-input"]')

    # 未入力の歯があると保存を止める
    pick(pg, teeth[0], 3)
    pg.click('[data-action="perio-save"]')
    assert "入力していない歯があります（25本）" in pg.inner_text(".perio-bar .msg")
    assert pg.locator("td.flash").count() == 25
    assert db("SELECT COUNT(*) FROM perio_exams WHERE id > ?", clean_exams)[0][0] == 0

    # 4mm以上 6本、BOP 4本（赤く太い数字）、赤い面 19、動揺度
    deep, bops = set(teeth[:6]), set(teeth[3:7])
    for t in teeth:
        pick(pg, t, 4 if t in deep else 3, bop=t in bops)
    cell = pg.locator(f'td[data-k="pocket"][data-tooth="{teeth[3]}"]')
    assert "bop" in cell.get_attribute("class") and "deep" in cell.get_attribute("class")
    assert cell.evaluate("e => getComputedStyle(e).color") == "rgb(198, 40, 40)"  # BOP は赤
    assert cell.evaluate("e => Number(getComputedStyle(e).fontWeight)") >= 700  # 太く
    assert cell.evaluate("e => getComputedStyle(e).backgroundColor") != "rgba(0, 0, 0, 0)"  # 4mm以上は背景に色
    assert pg.locator(f'td[data-k="pocket"][data-tooth="{teeth[10]}"]').evaluate("e => getComputedStyle(e).backgroundColor") == "rgba(0, 0, 0, 0)"
    for t in teeth[:19]:
        pg.locator(f'td[data-k="plq"][data-tooth="{t}"] polygon[data-side="t"]').click()  # 1面ずつ赤くする
    assert pg.locator("polygon.pq-on").count() == 19
    pg.locator(f'td[data-k="plq"][data-tooth="{teeth[0]}"] polygon[data-side="t"]').click()  # もう一度押すと戻る
    assert pg.locator("polygon.pq-on").count() == 18
    pg.locator(f'td[data-k="plq"][data-tooth="{teeth[0]}"] polygon[data-side="r"]').click()
    assert pg.locator("polygon.pq-on").count() == 19
    pg.locator(f'td[data-k="mob"][data-tooth="{teeth[5]}"]').click()
    pg.locator('.perio-pop button[data-mob="2"]').click()

    pg.click('[data-action="perio-save"]')
    pg.wait_for_function("document.querySelector('.perio-stats') && !document.querySelector('.perio-bar')")
    for page in (pg, None):
        if page is None:
            pg.reload()
            pg.wait_for_selector('[data-part="perio-exam"] table.perio')
        s = stats(pg)
        assert s["4mm以上"].startswith("6本") and s["BOP"].startswith("15%") and s["PCR"].startswith("18%"), s
        assert s["動揺のある歯"].startswith("1本") and s["検査した歯"].startswith("26本")
        assert "前回 6本" in s["4mm以上"] and "前回 15%" in s["BOP"]  # 前回（8月）と並ぶ
        assert f"検査日 2026年11月6日" in pg.inner_text('[data-part="perio-exam"] .meta')
        assert pg.locator("polygon.pq-on").count() == 19
    # 過去の検査は変わらない。新しい検査は今日の日付で1つ
    assert [tuple(r) for r in db("SELECT exam_id, tooth, pocket, bop, plaque, mobility FROM perio_teeth WHERE exam_id <= ? ORDER BY exam_id, tooth", clean_exams)] == [tuple(r) for r in old]
    new = db("SELECT id, exam_date FROM perio_exams WHERE id > ?", clean_exams)
    assert len(new) == 1 and new[0]["exam_date"] == "2026-11-06"
    pg.close()


def test_api_refuses_wrong_input(server):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    latest = db("SELECT tooth FROM perio_teeth WHERE exam_id = (SELECT id FROM perio_exams WHERE patient_id=1 "
                "ORDER BY exam_date DESC, id DESC LIMIT 1)")
    good = {str(r[0]): {"pocket": 3, "bop": 0, "plaque": "0000", "mobility": 0} for r in latest}
    assert len(good) == 26
    with httpx.Client(base_url=base) as h:
        def post(teeth):
            return h.post("/api/perio/save", json={"appt": H_HYG, "teeth": teeth})

        r = post({**good, "18": {"pocket": 3}})  # 検査しない歯 (欠損)
        assert r.status_code == 400
        r = post({k: v for k, v in good.items() if k != "16"})
        assert r.status_code == 400 and r.json()["missing"] == [16]
        for bad in ({"pocket": 0}, {"pocket": 13}, {"pocket": 3, "bop": 2}, {"pocket": 3, "plaque": "12"}, {"pocket": 3, "mobility": 4}):
            r = post({**good, "16": bad})
            assert r.status_code == 400, bad
        assert db("SELECT COUNT(*) FROM perio_exams WHERE exam_date = '2026-11-06'")[0][0] == 0
        assert h.post("/api/perio/save", json={"appt": 999999, "teeth": good}).status_code == 404


def test_percent_rounds_half_up():
    assert D.percent(1, 8) == 13 and D.percent(4, 26) == 15 and D.percent(19, 104) == 18 and D.percent(0, 0) == 0
