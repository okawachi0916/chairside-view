"""G12: 重要事項・口腔内写真・話した内容の整理の全画面。"""
import json
import time

from app.views import data as D
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

KEY3 = json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))["button3"].replace("Ctrl", "Control")
ROWS = [r for r in D.today_list() if r["patient_id"] == 1]
H_DOC, H_HYG = ROWS[0]["id"], ROWS[1]["id"]
PEN = "ペニシリン系抗菌薬アレルギー 2019年 全身の発疹。アモキシシリン服用後"


def open_unit(browser, server, appt, role, height=1030):  # noqa: F811
    pg = browser.new_page(viewport={"width": 1920, "height": height})
    pg.goto(f"http://127.0.0.1:{server}/unit?appt={appt}&role={role}")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("window.VoiceKeys && document.getElementById('band')")
    time.sleep(0.4)
    return pg


def open_fs(pg, part):
    pg.locator(f'[data-part="{part}"] [data-action="fullscreen"]').click()
    pg.wait_for_selector(f'[data-fs-panel="{part}"]')


def spy(pg):
    pg.evaluate("""() => { window.__calls = []; const run = CVActions.run;
                    CVActions.run = function (n, a) { window.__calls.push(n); return run.call(CVActions, n, a); }; }""")


def test_important_fullscreen_open_and_close(server, browser):  # noqa: F811
    pg = open_unit(browser, server, H_DOC, "doctor")
    spy(pg)
    assert PEN not in pg.inner_text("body")  # 開くまで出ない
    open_fs(pg, "important")
    text = pg.inner_text("body")
    # 題と中身は2行に分けて出す
    assert "ペニシリン系抗菌薬アレルギー\n2019年 全身の発疹。アモキシシリン服用後" in text
    assert "ビスホスホネート製剤服用中\n2021年" in text
    # 上の行だけ残り、帯（重要事項の帯も）と本体は隠れる。全画面のボタンは見えない
    assert pg.locator(".topbar").is_visible() and not pg.locator('.band[data-part="important"]').is_visible()
    assert pg.locator('[data-action="fullscreen"]:visible').count() == 0
    assert pg.locator('[data-fs-panel="important"] .fs-row').count() == 2  # 重要事項は1か所だけ
    assert not pg.locator('[data-part="medical-history"]').is_visible()
    assert not pg.locator('[data-part="today-treatment"]').is_visible()
    assert pg.locator("text=もとに戻す").is_visible()
    # 1画面に入るので、ページ送りのボタンは出ない
    assert not pg.locator('[data-action="fs-next"]').is_visible()
    pg.locator('[data-action="fs-close"]').click()
    assert pg.locator('[data-fs-panel]').count() == 0
    assert pg.locator('[data-part="today-treatment"]').is_visible()
    assert pg.locator('[data-part="medical-history"]').is_visible()
    assert pg.evaluate("window.__calls") == ["fs-open", "fs-close"]  # 入口を通っている
    pg.close()


def test_photos_fullscreen_select(server, browser):  # noqa: F811
    pg = open_unit(browser, server, H_DOC, "doctor")
    open_fs(pg, "intraoral-photos")
    panel = pg.locator('[data-fs-panel="intraoral-photos"]')
    assert panel.locator(".fs-item").count() == 17
    assert "写真 17" in panel.locator(".fs-big").inner_text()  # 一番新しい写真から
    # 左が選んだ写真、右が一覧
    big, lst = panel.locator(".fs-big").bounding_box(), panel.locator(".fs-list").bounding_box()
    assert big["x"] < lst["x"]
    # 1枚のときは左は1枚分の幅だけ。残りは一覧が使い、一覧は1段に何枚も並ぶ
    fig = panel.locator(".fs-fig img").bounding_box()
    assert big["width"] < fig["width"] + 60 and lst["width"] > 1920 / 2
    tops = panel.locator(".fs-item").evaluate_all("els => els.map(e => e.getBoundingClientRect().top)")
    assert tops.count(tops[0]) >= 5
    assert not pg.locator('.band[data-part="important"]').is_visible()  # 写真の全画面に重要事項の帯は出さない
    panel.locator('.fs-item[data-n="3"]').click()
    assert "写真 3" in panel.locator(".fs-big").inner_text()
    assert "2025年11月25日" in panel.locator(".fs-big").inner_text()
    assert panel.locator(".fs-item.sel").count() == 1
    pg.locator('[data-action="fs-close"]').click()
    assert pg.locator('[data-part="intraoral-photos"]').is_visible()
    pg.close()


def test_spoken_fullscreen_two_columns(server, browser):  # noqa: F811
    for appt, role, line, said in [
        (H_DOC, "doctor", "右下6番 根管充填、側方加圧", "根管充填をしました"),  # 歯科医師の診療回には見本の区切りがある
        (H_HYG, "hygienist", "右下奥の清掃を指導", "清掃の仕方をお伝えしました"),
    ]:
        pg = open_unit(browser, server, appt, role)
        open_fs(pg, "spoken-summary")
        cols = pg.locator(".fs-col")
        assert cols.count() == 2
        assert line in cols.nth(0).inner_text() and said in cols.nth(1).inner_text()
        assert ("録音の区切り" if role == "doctor" else "話したままの文字") in cols.nth(1).inner_text()
        b0, b1 = cols.nth(0).bounding_box(), cols.nth(1).bounding_box()
        assert b0["x"] < b1["x"]  # 左に要約、右に話したままの文字
        pg.close()


def test_every_fullscreen_button_opens_and_closes(server, browser):  # noqa: F811
    for appt, role, parts in [
        (H_DOC, "doctor", ["important", "medical-history", "today-treatment", "treatment-history",
                           "intraoral-photos", "spoken-summary"]),
        (H_HYG, "hygienist", ["important", "medical-history", "intraoral-photos", "spoken-summary", "perio-exam"]),
    ]:
        pg = open_unit(browser, server, appt, role)
        for part in parts:
            open_fs(pg, part)
            assert pg.locator(f'[data-fs-panel="{part}"]').is_visible()
            pg.locator('[data-action="fs-close"]').click()
            assert pg.locator("[data-fs-panel]").count() == 0
        pg.close()


def test_medical_history_table(server, browser):  # noqa: F811
    for appt, role in [(H_DOC, "doctor"), (H_HYG, "hygienist")]:
        pg = open_unit(browser, server, appt, role)
        open_fs(pg, "medical-history")
        panel = pg.locator('[data-fs-panel="medical-history"]')
        assert [t.strip() for t in panel.locator("th").all_inner_texts()] == ["病名", "薬", "いつから", "通院先"]
        rows = [r.split("	") for r in panel.locator("tbody tr").all_inner_texts()]
        assert ["高血圧", "アムロジピン内服中", "2015年", "みどり内科クリニック"] in rows
        assert len(rows) == 4
        pg.close()


def test_today_treatment_opens_four_things_together(server, browser):  # noqa: F811
    pg = open_unit(browser, server, H_DOC, "doctor")
    open_fs(pg, "today-treatment")
    text = pg.inner_text('[data-fs-panel="today-treatment"]')
    for want in ["今日の処置", "治療計画", "治療方針", "過去の診療メモ", "右下6番", "根管充填", "3か月様子を見る", "被せ物で噛める状態"]:
        assert want in text, want
    assert pg.locator('[data-fs-panel] .fs-col').count() == 2
    pg.close()


def test_treatment_history_goes_back_with_paging(server, browser):  # noqa: F811
    pg = open_unit(browser, server, H_DOC, "doctor", height=700)
    in_card = pg.locator('[data-part="treatment-history"] tbody tr').count()
    assert in_card == 10  # 欄には新しい10行だけ
    open_fs(pg, "treatment-history")
    panel = pg.locator('[data-fs-panel="treatment-history"]')
    assert panel.locator("tbody tr").count() == 22  # 全画面は行を増やして遡る
    nxt, prv = pg.locator('[data-action="fs-next"]'), pg.locator('[data-action="fs-prev"]')
    assert nxt.is_visible() and prv.is_disabled()
    last = panel.locator("tbody tr").last
    for _ in range(10):
        if nxt.is_disabled():
            break
        nxt.click()
    assert nxt.is_disabled() and last.is_visible() and "2024/12/6" in last.inner_text()
    assert not prv.is_disabled()  # 遡ったので、戻るボタンが効く
    pg.close()


def test_perio_pairs_and_pages(server, browser):  # noqa: F811
    pg = open_unit(browser, server, H_HYG, "hygienist")
    open_fs(pg, "perio-exam")
    panel = pg.locator('[data-fs-panel="perio-exam"]')
    pages = panel.locator(".fs-page")
    assert pages.count() == 3  # 4回の検査 → 3組
    first = pages.nth(0).locator(".pcol")
    assert "前回 2026年5月8日" in first.nth(0).inner_text() and "今回 2026年8月7日" in first.nth(1).inner_text()
    assert pages.nth(0).locator(".pcol").nth(0).bounding_box()["x"] < pages.nth(0).locator(".pcol").nth(1).bounding_box()["x"]
    assert "4mm以上 6本" in first.nth(1).inner_text() and "4mm以上 9本" in first.nth(0).inner_text()
    nxt, prv = pg.locator('[data-action="fs-next"]'), pg.locator('[data-action="fs-prev"]')
    assert nxt.is_visible() and prv.is_disabled()
    nxt.click()
    pg.wait_for_function("document.querySelector('.fs-scroll[data-pages]').scrollTop > 100")
    assert pages.nth(1).locator(".pcol").first.is_visible()
    assert "2026年5月8日" in pages.nth(1).inner_text()  # 一つ前の組が前後に並ぶ
    nxt.click()
    pg.wait_for_function("document.querySelector('[data-action=fs-next]').disabled")
    assert "2025年10月17日" in pages.nth(2).inner_text() and pages.nth(2).locator(".pcol").first.is_visible()
    prv.click()
    pg.wait_for_function("!document.querySelector('[data-action=fs-next]').disabled")
    pg.close()


def test_reception_fullscreens_by_mouse(server, browser):  # noqa: F811
    pg = open_page(browser, server, f"/reception?patient=1")
    pg.wait_for_selector('[data-part="reception-memo"]')
    assert "お子さん3人" not in pg.inner_text('[data-part="important"]')
    pg.locator('[data-part="reception-memo"] [data-action="fullscreen"]').click()
    panel = pg.locator('[data-fs-panel="reception-memo"]')
    panel.wait_for()
    text = panel.inner_text()
    assert "お子さん3人と同じ時間で予約を取る" in text and "2026年9月" in text  # 書いた時期も出る
    pg.locator('[data-action="fs-close"]').click()
    assert pg.locator("[data-fs-panel]").count() == 0
    pg.locator('[data-part="important"] [data-action="fullscreen"]').click()
    t = pg.inner_text('[data-fs-panel="important"]')
    assert "ペニシリン系抗菌薬アレルギー" in t and "2019年" in t
    assert pg.evaluate("typeof window.cvTyped") == "undefined"  # 受付に声の言葉は無い
    pg.close()


def test_paging_buttons_and_wheel(server, browser):  # noqa: F811
    pg = open_unit(browser, server, H_DOC, "doctor", height=470)  # 低い画面では一覧が1画面に入らない
    pg.set_viewport_size({"width": 1200, "height": 470})  # 一覧は残りの幅を全部使うので、幅も狭くする
    spy(pg)
    open_fs(pg, "intraoral-photos")
    nxt, prv = pg.locator('[data-action="fs-next"]'), pg.locator('[data-action="fs-prev"]')
    assert nxt.is_visible() and prv.is_visible()
    top = lambda: pg.evaluate("document.querySelector('.fs-list').scrollTop")  # noqa: E731
    for _ in range(10):  # 開いたときは一番新しい写真が見えている。先頭まで戻す
        if prv.is_disabled():
            break
        prv.click()
    assert prv.is_disabled() and not nxt.is_disabled() and top() == 0
    nxt.click()
    t1 = top()
    assert t1 > 0
    prv.click()
    assert top() < t1
    # マウスのスクロール
    box = pg.locator(".fs-list").bounding_box()
    pg.mouse.move(box["x"] + 50, box["y"] + 50)
    before = top()
    pg.mouse.wheel(0, 150)
    pg.wait_for_function(f"document.querySelector('.fs-list').scrollTop > {before}")
    # 最後まで送ると「次のページ」は押せなくなる
    for _ in range(10):
        if nxt.is_disabled():
            break
        nxt.click()
    assert nxt.is_disabled() and not prv.is_disabled()
    names = pg.evaluate("window.__calls")
    assert names.count("fs-next") >= 2 and "fs-prev" in names
    # 画面を高くすると、出ていたボタンが引っ込む
    pg.set_viewport_size({"width": 1920, "height": 1500})
    pg.wait_for_function("document.querySelector('[data-action=fs-next]').hidden")
    pg.close()


def test_hide_and_restore_returns_to_fullscreen(server, browser):  # noqa: F811
    pg = open_unit(browser, server, H_DOC, "doctor")
    open_fs(pg, "intraoral-photos")
    pg.locator('.fs-item[data-n="5"]').click()
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-part="hidden-screen"]')
    text = pg.inner_text("body")
    assert "写真 5" not in text and "見本 花子" not in text and PEN not in text
    pg.keyboard.press(KEY3)
    time.sleep(0.15)
    pg.keyboard.press(KEY3)
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    assert "写真 5" in pg.locator(".fs-big").inner_text()
    assert pg.locator(".fs-item.sel").get_attribute("data-n") == "5"
    assert not pg.locator('[data-part="today-treatment"]').is_visible()
    pg.close()


def test_new_patient_clears_fullscreen(server, browser):  # noqa: F811
    pg = open_unit(browser, server, H_DOC, "doctor")
    open_fs(pg, "important")
    other = D.today_list()[1]["id"]
    pg.evaluate(f"cv.openUnit({other}, 'hygienist')")
    pg.wait_for_function("document.body.innerText.includes('見本 一郎')")
    assert pg.locator("[data-fs-panel]").count() == 0
    assert "ペニシリン" not in pg.inner_text("body")
    assert pg.evaluate("document.body.classList.contains('fs-mode')") is False
    pg.close()
