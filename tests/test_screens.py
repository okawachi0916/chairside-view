"""本物の画面 (/ /unit /reception) の試験。"""
import pytest

from app.views import data as D
from tests.screen_helper import browser, check_screen, open_page, server  # noqa: F401

DOCTOR_PARTS = ["today-appointment", "important", "medical-history", "today-treatment", "treatment-plan",
                "past-notes", "treatment-history", "intraoral-photos", "tooth-chart", "spoken-summary", "photo-list"]
HYG_PARTS = ["today-appointment", "important", "medical-history", "intraoral-photos", "photo-list",
             "spoken-summary", "perio-exam"]
REC_PARTS = ["today-appointment", "important", "next-appointment", "booked-appointment"]


def people():
    """5人それぞれの (患者番号, 名前, カルテ番号, 今日の予約番号, 重要事項の1行目)。"""
    out = {}
    with D.con() as c:
        for p in c.execute("SELECT id, name, chart_no FROM patients ORDER BY id"):
            appt = c.execute("SELECT id FROM appointments WHERE patient_id=? AND appt_date='2026-11-06' "
                             "AND status='booked' ORDER BY start_time", (p["id"],)).fetchone()[0]
            imp = [r[0] for r in c.execute("SELECT body FROM important_notes WHERE patient_id=? ORDER BY seq", (p["id"],))]
            out[p["id"]] = (p["name"], p["chart_no"], appt, imp)
    return out


PEOPLE = people()
H_ROWS = [r for r in D.today_list() if r['patient_id'] == 1]
H_DOC, H_HYG = H_ROWS[0]['id'], H_ROWS[1]['id']


@pytest.mark.parametrize("pid", sorted(PEOPLE))
@pytest.mark.parametrize("screen", ["doctor", "hygienist", "reception"])
def test_five_people_three_screens(server, browser, pid, screen):  # noqa: F811
    name, chart, appt, imp = PEOPLE[pid]
    path = f"/reception?patient={pid}" if screen == "reception" else f"/unit?appt={appt}&role={screen}"
    pg = open_page(browser, server, path)
    pg.wait_for_selector('[data-part="important"]')
    text = pg.inner_text("body")
    assert name in text and f"No. {chart}" in text
    for line in imp:
        assert line in text
    parts = {"doctor": DOCTOR_PARTS, "hygienist": HYG_PARTS, "reception": REC_PARTS}[screen]
    for part in parts:
        assert pg.locator(f'[data-part="{part}"]').count() >= 1, part
    if screen == "reception":
        assert "受付メモ" in text and "来院しやすい曜日・時間帯" in text
    else:
        for w in ("受付メモ", "来院しやすい曜日", "キャンセル傾向", "過去の処方", "過去の物品購入"):
            assert w not in text
    pg.close()


def test_hanako_screens_fit(server, browser):  # noqa: F811
    for path, parts, words in [
        (f"/unit?appt={H_DOC}&role=doctor", DOCTOR_PARTS, ["右下6番 根管充填", "根管治療 3回目", "治療計画", "過去の診療メモ",
                                                    "その他粘膜疾患 舌左縁 白板症", "経過期間 6か月"]),
    ]:
        pg = open_page(browser, server, path)
        pg.wait_for_selector('[data-part="important"]')
        check_screen(pg, parts, words)
        pg.close()
    h_appt = H_HYG
    pg = open_page(browser, server, f"/unit?appt={h_appt}&role=hygienist")
    pg.wait_for_selector('[data-part="perio-exam"]')
    check_screen(pg, HYG_PARTS, ["歯周検査", "PCR", "前回 24%", "2026/8/7", "検査した歯（本数）", "3か月ごと"])
    pg.close()
    pg = open_page(browser, server, "/reception?patient=1")
    pg.wait_for_selector('[data-part="important"]')
    check_screen(pg, REC_PARTS, ["金曜の午後", "過去1年の来院13回", "予約14回のうち", "2026/3/12(木) 当日の朝に電話あり",
                                "支台築造＋形成印象", "2027年2月5日 歯科衛生士 佐藤"])
    pg.close()


def test_appointment_time_follows_row(server, browser):  # noqa: F811
    rows = [r for r in D.today_list() if r["patient_id"] == 1]
    assert len(rows) == 2
    texts = []
    for r in rows:
        pg = open_page(browser, server, f"/unit?appt={r['id']}")
        pg.wait_for_selector('[data-part="today-appointment"]')
        texts.append(pg.inner_text('[data-part="today-appointment"]'))
        pg.close()
    assert "14:30〜15:30（1時間）" in texts[0] and "15:30〜16:00 SPT" in texts[0]
    assert "15:30〜16:00（30分）" in texts[1] and "前の予約 14:30〜15:30 RCT" in texts[1]


def test_list_to_unit_and_back(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/")
    rows = pg.locator("tr.row")
    assert rows.count() == 6
    assert "見本 花子" not in pg.inner_text("body")
    for i, role in enumerate(["doctor", "hygienist", "doctor", "doctor", "hygienist", "doctor"]):
        pg.goto(f"http://127.0.0.1:{server}/")
        pg.locator("tr.row").nth(i).click()
        pg.wait_for_url("**/unit?appt=*")
        assert f"role={role}" in pg.url
        pg.wait_for_selector('[data-part="important"]')
        assert "/reception" not in pg.content()
    # 役割を変える
    pg.locator("[data-action=change-role]").click()
    pg.wait_for_function("document.body.className === 'role-hygienist'")
    assert pg.locator('[data-part="perio-exam"]').count() == 1
    pg.locator("[data-action=change-role]").click()
    pg.wait_for_function("document.body.className === 'role-doctor'")
    assert pg.locator('[data-part="today-treatment"]').count() == 1
    pg.locator("[data-action=change-patient]").click()
    pg.wait_for_url(f"http://127.0.0.1:{server}/")
    assert pg.locator("tr.row").count() == 6
    pg.close()


def test_nothing_in_browser_storage(server, browser):  # noqa: F811
    pg = open_page(browser, server, f"/unit?appt={H_DOC}&role=doctor")
    pg.wait_for_selector('[data-part="important"]')
    assert pg.evaluate("[localStorage.length, sessionStorage.length, document.cookie]") == [0, 0, ""]
    pg.close()


def test_switch_person_clears_previous(server, browser):  # noqa: F811
    pg = open_page(browser, server, f"/unit?appt={H_DOC}&role=doctor")
    pg.wait_for_selector('[data-part="important"]')
    assert "見本 花子" in pg.inner_text("body")
    pg.evaluate(f"cv.openUnit({PEOPLE[2][2]}, 'hygienist')")
    pg.wait_for_function("document.body.innerText.includes('見本 一郎')")
    text = pg.inner_text("body")
    for w in ("見本 花子", "0123", "ペニシリン", "ビスホスホネート", "白板症"):
        assert w not in text
    pg.close()


def test_late_response_of_previous_person_is_dropped(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/reception")
    pg.wait_for_selector("tr[data-patient]")
    held = []
    pg.route("**/api/view/reception?patient=1", lambda route: held.append(route))
    pg.evaluate("cv.openReception(1)")
    pg.wait_for_timeout(300)
    assert held, "花子様の応答を止められなかった"
    pg.evaluate("cv.openReception(2)")
    pg.wait_for_function("document.body.innerText.includes('見本 一郎')")
    held[0].continue_()  # 遅れて前の人の応答が返る
    pg.wait_for_timeout(800)
    text = pg.inner_text("body")
    assert "見本 一郎" in text and "見本 花子" not in text and "ペニシリン" not in text
    pg.close()


def test_reception_choose_inside_screen(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/reception")
    pg.wait_for_selector("tr[data-patient]")
    assert pg.locator("tr[data-patient]").count() == 5
    assert "見本 花子" not in pg.inner_text("body")
    pg.locator("tr[data-patient]").nth(2).click()
    pg.wait_for_function("document.body.innerText.includes('見本 太郎')")
    assert "ワルファリン" in pg.inner_text("body")
    pg.locator("[data-action=change-patient]").click()
    pg.wait_for_selector("tr[data-patient]")
    assert "見本 太郎" not in pg.inner_text("body")
    pg.close()


def test_important_shrinks_with_lines(server, browser):  # noqa: F811
    pg = open_page(browser, server, f"/unit?appt={H_DOC}&role=doctor")
    pg.wait_for_selector('[data-part="important"]')
    assert pg.locator('[data-part="important"] .lines.n2').count() == 1
    pg.close()
    from app.views import render as R
    d = {"important": ["a", "b", "c", "d", "e", "f"]}
    html = R.important(d)
    assert "lines n4" in html and "ほか 3件" in html and "<br>" in html
    assert "lines n3" in R.important({"important": ["a", "b", "c"]})
    assert "lines n1" in R.important({"important": ["a"]})
