"""G24・G24b: 歯周検査の入力（基本検査｜精密検査）と、見る画面の書式。
基本検査と精密検査は同じ表で、違うのはポケットの行だけ。見る画面に「精密」「基本」の文字は出さない。"""
import httpx
import pytest

from app.db import connect
from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

ROWS = [r for r in D.today_list() if r["patient_id"] == 1]
H_HYG = ROWS[1]["id"]
URL = f"/unit?appt={H_HYG}&role=hygienist"
RED = "rgb(198, 40, 40)"


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


LATEST_TEETH = "SELECT tooth FROM perio_teeth WHERE exam_id = (SELECT id FROM perio_exams WHERE patient_id=1 ORDER BY exam_date DESC, id DESC LIMIT 1)"


def add_precise(date="2026-11-05", time="10:15", bleed=((16, 1), (16, 4), (26, 2), (36, 5)), plaque_teeth=(16, 26), loose=(26,)):
    """花子様に精密検査を1つ足す（検査する歯は今のいちばん新しい検査と同じ26本）。ポケットは歯と点で決まる値。"""
    teeth = sorted(r[0] for r in db(LATEST_TEETH))
    c = connect()
    eid = c.execute("INSERT INTO perio_exams (patient_id, exam_date, kind, exam_time) VALUES (1, ?, 'precise', ?)", (date, time)).lastrowid
    for t in teeth:
        pts = [2 + (t + i) % 4 for i in range(6)]
        bops = "".join("1" if (t, i) in bleed else "0" for i in range(6))
        c.execute("INSERT INTO perio_teeth (exam_id, tooth, pocket, bop, plaque, mobility, pockets6, bops6) VALUES (?,?,?,?,?,?,?,?)",
                  (eid, t, max(pts), int("1" in bops), "1010" if t in plaque_teeth else "0000", 1 if t in loose else 0,
                   ",".join(map(str, pts)), bops))
    c.commit()
    c.close()
    return teeth, eid


def open_unit(browser, server, url=URL):  # noqa: F811
    pg = open_page(browser, server, url)
    pg.wait_for_selector('[data-part="perio-exam"] table.perio')
    pg.wait_for_function("window.cv && document.querySelector('[data-action=\"perio-input\"]')")
    return pg


def stats(pg):
    return {s.locator("small").inner_text(): (s.locator("b").inner_text().replace("\n", ""), s.locator("i").all_inner_texts())
            for s in pg.locator('[data-part="perio-exam"] .perio-stats .st').all()}


def row_labels(pg):
    return pg.locator('[data-part="perio-exam"] table.perio th.row').all_inner_texts()


def pick(pg, el, value, bop=False):
    el.click()
    pg.locator(f'.perio-pop button[data-pocket="{value}"][data-bop="{1 if bop else 0}"]').click()


def teeth_of(pg):
    return pg.locator('[data-part="perio-exam"] td[data-k="pocket"]').evaluate_all("els => els.map(e => Number(e.dataset.tooth))")


# ---------- 見る画面 ----------

def test_heading_is_perio_exam_everywhere(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    assert pg.inner_text('[data-part="perio-exam"] h2') == "歯周検査"
    assert "歯周基本検査" not in pg.content()
    pg.click('[data-part="perio-exam"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="perio-exam"]')
    assert pg.inner_text('[data-fs-panel="perio-exam"] h2, [data-fs-panel="perio-exam"] .fs-title').strip().startswith("歯周検査")
    assert "歯周基本検査" not in pg.content()
    pg.close()


def test_basic_view_layout(server, browser):  # noqa: F811
    """いちばん新しい検査が基本検査: PD の1行・1本に1マス。表の形は G24b の書式どおり。"""
    pg = open_unit(browser, server)
    card = pg.locator('[data-part="perio-exam"]')
    assert card.locator("table.perio").get_attribute("data-kind") == "basic"
    assert row_labels(pg) == ["動揺度", "PD", "プラーク", "", "プラーク", "PD", "動揺度"]
    assert card.locator('td[data-k="pocket"]').count() == 26  # 1本に1マス
    assert card.locator("td.p3").count() == 0
    text = card.inner_text()
    for word in ("精密", "基本"):
        assert word not in text
    s = stats(pg)
    assert list(s) == ["PCR", "BOP率", "動揺のある歯（本数）", "検査した歯（本数）"]
    assert s["PCR"][1] == ["前回 24%"] and s["BOP率"][1] == ["前回 19%"]  # 前回の割合を小さく添える
    assert s["動揺のある歯（本数）"][1] == [] and s["検査した歯（本数）"][0] == "26"
    assert card.locator(".pdate b").inner_text() == "2026/8/7" and card.locator(".pdate .wd").inner_text() == "(金)"
    assert card.locator(".pdate .wd").evaluate("e => getComputedStyle(e).color") == RED  # 曜日は赤の丸かっこ
    assert [x.strip() for x in card.locator(".perio-lr span").all_inner_texts()] == ["右", "左"]
    legend = card.locator(".perio-legend").inner_text()
    assert "赤の太字 = 出血(BOP)" in legend and "プラーク" in legend and "斜線 = 欠損・対象外" in legend
    assert "3マス" not in legend  # 基本検査には3マスの説明は付けない
    pg.close()


def test_precise_view_layout(server, browser):  # noqa: F811
    teeth, _ = add_precise()
    pg = open_unit(browser, server)
    card = pg.locator('[data-part="perio-exam"]')
    assert card.locator("table.perio").get_attribute("data-kind") == "precise"
    # 上は頬側→口蓋側（口蓋側が番号の帯に近い）、下は舌側→頬側（舌側が帯に近い）
    assert row_labels(pg) == ["動揺度", "頬側", "口蓋側", "プラーク", "", "プラーク", "舌側", "頬側", "動揺度"]
    assert card.locator("td.p3").count() == 26 * 2  # 歯ごとに2行（上は頬側・口蓋側、下は舌側・頬側）
    assert card.locator('td.p3 span[data-k="pt"]').count() == 26 * 6  # 1本に3マス × 2行
    text = card.inner_text()
    for word in ("精密", "基本"):
        assert word not in text
    # 見たままの並び: 右側の歯（16）は 遠心・中央・近心 = 0,1,2。左側の歯（26）は 近心・中央・遠心 = 2,1,0
    right = card.locator('td.p3[data-tooth="16"]').first.locator("span").evaluate_all("e => e.map(x => Number(x.dataset.i))")
    left = card.locator('td.p3[data-tooth="26"]').first.locator("span").evaluate_all("e => e.map(x => Number(x.dataset.i))")
    assert right == [0, 1, 2] and left == [2, 1, 0]
    lower = card.locator('td.p3[data-tooth="46"]').first.locator("span").evaluate_all("e => e.map(x => Number(x.dataset.i))")
    assert lower == [3, 4, 5]  # 下の歯の最初の行は舌側（3〜5）
    # 値が見たままに入る（16 の頬側）
    vals = card.locator('td.p3[data-tooth="16"]').first.locator("span").all_inner_texts()
    assert vals == [str(2 + (16 + i) % 4) for i in (0, 1, 2)]
    # 出血の点は赤の太字で大きめ
    bop = card.locator('td.p3[data-tooth="16"] span.bop')
    assert bop.count() == 2  # 16 は 点1（頬側・中央）と 点4（舌側・遠心）
    assert bop.first.evaluate("e => getComputedStyle(e).color") == RED
    assert bop.first.evaluate("e => Number(getComputedStyle(e).fontWeight)") >= 700
    plain = card.locator('td.p3[data-tooth="16"] span:not(.bop)').first
    assert bop.first.evaluate("e => parseFloat(getComputedStyle(e).fontSize)") > plain.evaluate("e => parseFloat(getComputedStyle(e).fontSize)")
    # 割合は6点で数える: BOP率 = 出血の点 4 ÷ (26本×6点) = 3%。PCR = 赤い面 4 ÷ (26×4) = 4%
    s = stats(pg)
    assert s["BOP率"][0] == "3%" and s["BOP率"][1] == ["前回 15%"]  # 前回は 8月の基本検査
    assert s["PCR"][0] == "4%" and s["PCR"][1] == ["前回 18%"]
    assert s["動揺のある歯（本数）"][0] == "1" and s["検査した歯（本数）"][0] == "26"
    assert card.locator(".pdate b").inner_text() == "2026/11/5" and card.locator(".pdate .tm").inner_text() == "10:15"
    assert "3マスは見たままの並び" in card.locator(".perio-legend").inner_text()
    pg.close()


@pytest.mark.parametrize("precise", [False, True])
def test_table_form(server, browser, precise):  # noqa: F811
    """真ん中の太線・番号の帯・プラークの三角・斜線・歯の並び（どちらの検査でも同じ枠）。"""
    if precise:
        add_precise()
    pg = open_unit(browser, server)
    card = pg.locator('[data-part="perio-exam"]')
    nos = card.locator("tr.no td").all_inner_texts()
    assert nos == ["8", "7", "6", "5", "4", "3", "2", "1", "1", "2", "3", "4", "5", "6", "7", "8"]
    band = card.locator("tr.no td").first
    assert band.evaluate("e => getComputedStyle(e).backgroundColor") not in ("rgb(255, 255, 255)", "rgba(0, 0, 0, 0)")  # 薄い灰色の地
    assert band.evaluate("e => Number(getComputedStyle(e).fontWeight)") >= 700
    assert band.evaluate("e => parseFloat(getComputedStyle(e).fontSize)") >= 24  # 大きな太字
    # 真ん中（右1と左1の間）に、上から下まで太い縦線
    widths = card.locator("table.perio tr").evaluate_all(
        "rows => rows.map(r => getComputedStyle(r.querySelectorAll('td')[8]).borderLeftWidth)")
    assert set(widths) == {"3px"}
    thin = card.locator("table.perio tr").first.locator("td").nth(3).evaluate("e => getComputedStyle(e).borderLeftWidth")
    assert thin == "1px"
    # 無い歯は、その列のマスを空けて斜線（欠損の18・28・38・48・14・35）
    gone = card.locator("table.perio tr.mob").first.locator("td.gone").count()
    assert gone == 3  # 上の歯の欠損 18・14・28（下の欠損は 38・48・35）
    assert card.locator("td.gone").first.evaluate("e => getComputedStyle(e).backgroundImage").startswith("linear-gradient")
    assert card.locator("td.gone").first.inner_text() == ""
    # プラークは1本ずつ四角を4つの三角に分け、付いた面だけ赤
    one = card.locator('td.pl[data-tooth="17"]').first
    assert one.locator("polygon").count() == 4
    assert one.locator("polygon.pq-on").count() + one.locator("polygon.pq-off").count() == 4
    on = card.locator("polygon.pq-on").first
    assert on.evaluate("e => getComputedStyle(e).fill") == RED
    # 動揺度は1本に1マス
    assert card.locator('td[data-k="mob"]').count() == 26
    # 線は薄い灰色の細い線
    assert card.locator("table.perio td").nth(3).evaluate("e => getComputedStyle(e).borderTopColor") == "rgb(225, 230, 236)"
    pg.close()


def test_card_and_fullscreen_fit_without_scroll(server, browser):  # noqa: F811
    for precise in (False, True):
        if precise:
            add_precise()
        pg = open_unit(browser, server)
        card = pg.locator('[data-part="perio-exam"]')
        box = card.evaluate("e => ({c: e.getBoundingClientRect().bottom, t: e.querySelector('table.perio').getBoundingClientRect().bottom, "
                            "l: e.querySelector('.perio-legend').getBoundingClientRect().bottom, sh: e.scrollHeight, ch: e.clientHeight})")
        assert box["l"] <= box["c"] + 1 and box["t"] <= box["l"] and box["sh"] <= box["ch"] + 1, box
        assert pg.evaluate("document.documentElement.scrollHeight <= window.innerHeight + 1")
        card.locator('[data-action="fullscreen"]').click()
        pg.wait_for_selector('[data-fs-panel="perio-exam"] table.perio')
        fit = pg.locator('[data-fs-panel="perio-exam"]').evaluate(
            "p => { const s = p.querySelector('.fs-scroll'); const pg = p.querySelector('.fs-page'); "
            "const t = pg.querySelector('.perio-legend').getBoundingClientRect().bottom; "
            "return {sc: pg.scrollHeight <= pg.clientHeight + 1, legend: t <= s.getBoundingClientRect().bottom + 1, "
            "wide: pg.scrollWidth <= pg.clientWidth + 1}; }")
        assert fit == {"sc": True, "legend": True, "wide": True}, (precise, fit)
        pg.close()


def test_fullscreen_pages_newest_first(server, browser):  # noqa: F811
    add_precise()
    pg = open_unit(browser, server)
    pg.click('[data-part="perio-exam"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="perio-exam"] table.perio')
    pages = pg.locator('[data-fs-panel="perio-exam"] .fs-page')
    n = len(db("SELECT 1 FROM perio_exams WHERE patient_id = 1"))
    assert pages.count() == n >= 3
    assert pages.first.locator("table.perio").get_attribute("data-kind") == "precise"  # いちばん新しい検査が先頭
    assert pages.first.locator(".pdate b").inner_text() == "2026/11/5"
    assert pages.nth(1).locator("table.perio").get_attribute("data-kind") == "basic"
    assert pages.nth(1).locator(".pdate b").inner_text() == "2026/8/7"
    text = pg.inner_text('[data-fs-panel="perio-exam"]')
    assert "精密" not in text and "基本" not in text
    pg.close()


def test_old_basic_data_still_reads():
    """前の基本検査のデータは、足した列が空のままで壊れずに読める。"""
    old = db("SELECT t.pockets6, t.bops6, e.kind FROM perio_teeth t JOIN perio_exams e ON e.id = t.exam_id WHERE e.patient_id = 1")
    assert old and all(r[0] == "" and r[1] == "" and r[2] == "basic" for r in old)
    cols = {r[1] for r in db("PRAGMA table_info(perio_exams)")} | {r[1] for r in db("PRAGMA table_info(perio_teeth)")}
    assert {"kind", "exam_time", "pockets6", "bops6"} <= cols
    exams = D._perio(connect(), 1, None)
    assert exams[0]["kind"] == "basic" and exams[0]["n"] == 26 and exams[0]["bop"] == 15 and exams[0]["pcr"] == 18


def test_precise_numbers_use_six_points():
    """精密検査: 割合は6点で数える（BOP率＝出血の点÷(歯の数×6)）。基本検査は歯1本に1点。"""
    add_precise(bleed=tuple((t, i) for t in (16, 26) for i in range(6)))  # 2本とも6点が出血 = 12点
    ex = D._perio(connect(), 1, None)[0]
    assert ex["kind"] == "precise" and ex["n"] == 26
    assert ex["bop"] == D.percent(12, 26 * 6) == 8
    assert ex["teeth"][16]["pts"] == [2 + (16 + i) % 4 for i in range(6)] and ex["teeth"][16]["bops"] == [1] * 6
    assert ex["teeth"][16]["pocket"] == max(ex["teeth"][16]["pts"])


# ---------- 入力 ----------

def test_enter_and_cancel_keeps_the_table(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    before = pg.inner_html('[data-part="perio-exam"] table.perio')
    pg.click('[data-action="perio-input"]')
    pg.wait_for_selector("td.todo")
    assert pg.locator("td.todo").count() == 26  # 全部の歯が未入力（基本）
    assert pg.locator('[data-action="perio-input"]').is_disabled()
    # 最初に「基本検査｜精密検査」の2つ並び。選んでいる方（最初は基本）が赤で塗られる
    kinds = pg.locator(".perio-kind button")
    assert kinds.all_inner_texts() == ["基本検査", "精密検査"]
    assert kinds.nth(0).evaluate("e => getComputedStyle(e).backgroundColor") == RED
    assert kinds.nth(1).evaluate("e => getComputedStyle(e).backgroundColor") != RED
    pg.click('[data-action="perio-cancel"]')
    assert pg.inner_html('[data-part="perio-exam"] table.perio') == before
    assert pg.locator(".perio-bar").count() == 0
    pg.close()


def test_kind_switch_changes_only_the_pocket_rows(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.click('[data-action="perio-input"]')
    pg.wait_for_selector("td.todo")
    assert row_labels(pg) == ["動揺度", "PD", "プラーク", "", "プラーク", "PD", "動揺度"]
    pg.click('.perio-kind button[data-kind="precise"]')
    pg.wait_for_selector("span.todo")
    assert row_labels(pg) == ["動揺度", "頬側", "口蓋側", "プラーク", "", "プラーク", "舌側", "頬側", "動揺度"]
    assert pg.locator("span.todo").count() == 26 * 6
    kinds = pg.locator(".perio-kind button")
    assert kinds.nth(1).evaluate("e => getComputedStyle(e).backgroundColor") == RED
    assert kinds.nth(0).evaluate("e => getComputedStyle(e).backgroundColor") != RED
    pg.click('.perio-kind button[data-kind="basic"]')
    pg.wait_for_selector("td.todo")
    assert row_labels(pg)[1] == "PD"
    pg.close()


def test_basic_input_save_reload_and_numbers(server, browser, clean_exams):  # noqa: F811
    old = db("SELECT exam_id, tooth, pocket, bop, plaque, mobility FROM perio_teeth ORDER BY exam_id, tooth")
    pg = open_unit(browser, server)
    teeth = teeth_of(pg)
    assert len(teeth) == 26 and len(set(teeth)) == 26
    teeth = sorted(set(teeth))
    pg.click('[data-action="perio-input"]')
    pg.wait_for_selector("td.todo")

    # 未入力の歯があると保存を止める
    pick(pg, pg.locator(f'td[data-k="pocket"][data-tooth="{teeth[0]}"]').first, 3)
    pg.click('[data-action="perio-save"]')
    assert "入力していない歯があります（25本）" in pg.inner_text(".perio-bar .msg")
    assert pg.locator("td.flash").count() == 25
    assert db("SELECT COUNT(*) FROM perio_exams WHERE id > ?", clean_exams)[0][0] == 0

    # 4mm以上 6本、BOP 4本（赤く太い数字）、赤い面 19、動揺度
    deep, bops = set(teeth[:6]), set(teeth[3:7])
    for t in teeth:
        pick(pg, pg.locator(f'td[data-k="pocket"][data-tooth="{t}"]').first, 4 if t in deep else 3, bop=t in bops)
    cell = pg.locator(f'td[data-k="pocket"][data-tooth="{teeth[3]}"]').first
    assert "bop" in cell.get_attribute("class")
    assert cell.evaluate("e => getComputedStyle(e).color") == RED  # BOP は赤
    assert cell.evaluate("e => Number(getComputedStyle(e).fontWeight)") >= 700  # 太く
    for t in teeth[:19]:
        pg.locator(f'td[data-k="plq"][data-tooth="{t}"] polygon[data-side="t"]').first.click()  # 1面ずつ赤くする
    assert pg.locator("polygon.pq-on").count() == 19
    pg.locator(f'td[data-k="plq"][data-tooth="{teeth[0]}"] polygon[data-side="t"]').first.click()  # もう一度押すと戻る
    assert pg.locator("polygon.pq-on").count() == 18
    pg.locator(f'td[data-k="plq"][data-tooth="{teeth[0]}"] polygon[data-side="r"]').first.click()
    assert pg.locator("polygon.pq-on").count() == 19
    pg.locator(f'td[data-k="mob"][data-tooth="{teeth[5]}"]').first.click()
    pg.locator('.perio-pop button[data-mob="2"]').click()

    pg.click('[data-action="perio-save"]')
    pg.wait_for_function("document.querySelector('.perio-stats') && !document.querySelector('.perio-bar')")
    for page in (pg, None):
        if page is None:
            pg.reload()
            pg.wait_for_selector('[data-part="perio-exam"] table.perio')
        s = stats(pg)
        assert s["BOP率"][0] == "15%" and s["PCR"][0] == "18%", s
        assert s["動揺のある歯（本数）"][0] == "1" and s["検査した歯（本数）"][0] == "26"
        assert s["BOP率"][1] == ["前回 15%"] and s["PCR"][1] == ["前回 18%"]  # 前回（8月）と並ぶ
        assert pg.locator('[data-part="perio-exam"] .pdate b').inner_text() == "2026/11/6"
        assert pg.locator('[data-part="perio-exam"] .pdate .wd').inner_text() == "(金)"
        assert pg.locator('[data-part="perio-exam"] .pdate .tm').inner_text() != ""  # 保存した時刻
        assert pg.locator('[data-part="perio-exam"] table.perio').get_attribute("data-kind") == "basic"
        assert pg.locator("polygon.pq-on").count() == 19
    # 過去の検査は変わらない。新しい検査は今日の日付で1つ
    assert [tuple(r) for r in db("SELECT exam_id, tooth, pocket, bop, plaque, mobility FROM perio_teeth WHERE exam_id <= ? ORDER BY exam_id, tooth", clean_exams)] == [tuple(r) for r in old]
    new = db("SELECT id, exam_date, kind FROM perio_exams WHERE id > ?", clean_exams)
    assert len(new) == 1 and new[0]["exam_date"] == "2026-11-06" and new[0]["kind"] == "basic"
    pg.close()


def test_precise_input_save_and_show(server, browser, clean_exams):  # noqa: F811
    pg = open_unit(browser, server)
    teeth = sorted(set(teeth_of(pg)))
    pg.click('[data-action="perio-input"]')
    pg.wait_for_selector("td.todo")
    pg.click('.perio-kind button[data-kind="precise"]')
    pg.wait_for_selector("span.todo")
    # 1本分だけ入れて保存すると止まる
    first = teeth[0]
    for sp in pg.locator(f'td.p3[data-tooth="{first}"] span[data-k="pt"]').all():
        pick(pg, sp, 3)
    pg.click('[data-action="perio-save"]')
    assert "入力していない歯があります（25本）" in pg.inner_text(".perio-bar .msg")
    assert pg.locator("span.flash").count() == 25 * 6
    # 6点ずつ入れる。16 の舌側・口蓋側の中央（点4）に出血
    for t in teeth[1:]:
        for sp in pg.locator(f'td.p3[data-tooth="{t}"] span[data-k="pt"]').all():
            pick(pg, sp, 3)
    deep = pg.locator('td.p3[data-tooth="16"] span[data-i="1"]').first  # 16 の頬側の中央（点1）
    pick(pg, deep, 5, bop=True)
    inner = pg.locator('td.p3[data-tooth="16"] span[data-i="3"]').first  # 16 の口蓋側の遠心（点3）
    pick(pg, inner, 7)
    assert deep.evaluate("e => getComputedStyle(e).color") == RED
    pg.locator('td[data-k="plq"][data-tooth="16"] polygon[data-side="t"]').first.click()
    pg.click('[data-action="perio-save"]')
    pg.wait_for_function("document.querySelector('.perio-stats') && !document.querySelector('.perio-bar')")
    new = db("SELECT id, exam_date, kind FROM perio_exams WHERE id > ?", clean_exams)
    assert len(new) == 1 and new[0]["kind"] == "precise" and new[0]["exam_date"] == "2026-11-06"
    row = db("SELECT pocket, bop, plaque, pockets6, bops6 FROM perio_teeth WHERE exam_id = ? AND tooth = 16", new[0]["id"])[0]
    assert row["pockets6"] == "3,5,3,7,3,3" and row["bops6"] == "010000" and row["pocket"] == 7 and row["bop"] == 1
    assert row["plaque"] == "0010"
    assert db("SELECT pockets6 FROM perio_teeth WHERE exam_id = ? AND tooth = 11", new[0]["id"])[0][0] == "3,3,3,3,3,3"
    # 保存すると、その検査が欄に出る（3マスの形）。BOP率は 1 ÷ (26×6) = 1%
    card = pg.locator('[data-part="perio-exam"]')
    assert card.locator("table.perio").get_attribute("data-kind") == "precise"
    assert stats(pg)["BOP率"][0] == "1%"
    assert card.locator('td.p3[data-tooth="16"] span.bop').count() == 1
    assert card.locator('td.p3[data-tooth="16"]').first.locator("span").all_inner_texts() == ["3", "5", "3"]
    assert "精密" not in card.inner_text() and "基本" not in card.inner_text()
    # 同じ日に2つ目は入れられない
    pg.reload()
    pg.wait_for_selector('[data-part="perio-exam"] table.perio')
    pg.close()


def test_api_refuses_wrong_input(server):  # noqa: F811
    base = f"http://127.0.0.1:{server}"
    latest = db(LATEST_TEETH)
    good = {str(r[0]): {"pocket": 3, "bop": 0, "plaque": "0000", "mobility": 0} for r in latest}
    good6 = {str(r[0]): {"pts": [3] * 6, "bops": [0] * 6, "plaque": "0000", "mobility": 0} for r in latest}
    assert len(good) == 26
    with httpx.Client(base_url=base) as h:
        def post(teeth, kind="basic"):
            return h.post("/api/perio/save", json={"appt": H_HYG, "kind": kind, "teeth": teeth})

        r = post({**good, "18": {"pocket": 3}})  # 検査しない歯 (欠損)
        assert r.status_code == 400
        r = post({k: v for k, v in good.items() if k != "16"})
        assert r.status_code == 400 and r.json()["missing"] == [16]
        for bad in ({"pocket": 0}, {"pocket": 13}, {"pocket": 3, "bop": 2}, {"pocket": 3, "plaque": "12"}, {"pocket": 3, "mobility": 4}):
            r = post({**good, "16": bad})
            assert r.status_code == 400, bad
        assert post(good, kind="x").status_code == 400  # 検査の種類は基本か精密だけ
        # 精密検査: 6点そろっていない・範囲外・出血の形が違うものは保存しない
        for bad in ({"pts": [3] * 5, "bops": [0] * 6}, {"pts": [3] * 6, "bops": [0] * 5}, {"pts": [0] * 6, "bops": [0] * 6},
                    {"pts": [13] + [3] * 5, "bops": [0] * 6}, {"pts": [3] * 6, "bops": [2] + [0] * 5},
                    {"pts": [3, 3, 3, None, 3, 3], "bops": [0] * 6}):
            r = post({**good6, "16": {**bad, "plaque": "0000", "mobility": 0}}, kind="precise")
            assert r.status_code == 400, bad
        assert post(good6).status_code == 400  # 基本検査として6点の形を送ってもだめ（ポケットが無い）
        assert db("SELECT COUNT(*) FROM perio_exams WHERE exam_date = '2026-11-06'")[0][0] == 0
        assert h.post("/api/perio/save", json={"appt": 999999, "teeth": good}).status_code == 404
        ok = post(good6, kind="precise")
        assert ok.status_code == 200
        assert post(good).status_code == 409 and "今日の検査" in post(good).json()["error"]  # 1日に1回
        blank = h.get("/api/perio/blank", params={"appt": H_HYG, "kind": "precise"})
        assert blank.status_code == 200 and blank.text.count('data-k="pt"') == 26 * 6
        assert h.get("/api/perio/blank", params={"appt": H_HYG, "kind": "zzz"}).status_code == 400


def test_percent_rounds_half_up():
    assert D.percent(1, 8) == 13 and D.percent(4, 26) == 15 and D.percent(19, 104) == 18 and D.percent(0, 0) == 0
