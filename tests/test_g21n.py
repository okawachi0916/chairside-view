"""G21n: 最初に入口の画面を置き、受付モードと臨床モードに分けて入る。"""
import re

import pytest

from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

TODAY_TEXT = "2026年11月6日 金曜日"


def test_entrance_at_opening_addresses(server, browser):  # noqa: F811
    for path in ["/", "/app"]:
        pg = open_page(browser, server, path)
        if path == "/app":
            pg = pg.frame_locator("#inner")
            pg.locator("h1").wait_for()
            text = pg.locator("body").inner_text()
        else:
            pg.wait_for_selector("h1")
            text = pg.inner_text("body")
        assert TODAY_TEXT in text
        assert "チェアサイドビュー" in text and "CHAIRSIDE VIEW" in text
        for w in ("受付モード", "受付の端末で使う", "マウスだけ（声は使わない）",
                  "次回の予約・来院しやすい曜日・キャンセル傾向・受付メモ・過去の処方",
                  "キャンセル傾向など、患者様の前に出さない情報を含むため、ユニットの画面からは切り替えません。",
                  "受付用の患者様一覧へ　→",
                  "臨床モード", "ユニットで使う　歯科医師・歯科衛生士", "手袋のまま（声と3つのボタン）",
                  "重要事項・今日の処置・写真・歯周検査。話した内容を記録する",
                  "「歯科医師」「歯科衛生士」の切り替えは臨床モードの中で行います。",
                  "今日の予約一覧へ　→"):
            assert w in text, w
        assert re.search(r"チェアサイドビュー\s*CHAIRSIDE VIEW", text)


def test_two_doors_are_whole_cards_with_role_colors(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/")
    pg.wait_for_selector("h1")
    rec = pg.locator("a.door-reception")
    cli = pg.locator("a.door-clinic")
    assert rec.count() == 1 and cli.count() == 1  # 札ごと押せる (札が1つのリンク)
    rb, cb = rec.bounding_box(), cli.bounding_box()
    assert rb["x"] < cb["x"] and abs(rb["y"] - cb["y"]) < 2  # 横に並ぶ
    assert rec.evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(99, 70, 153)"  # 受付の紫
    assert cli.evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(45, 79, 134)"  # 歯科医師の紺
    # G21p: 札は紺と緑の塗りに白い字になった
    assert pg.locator(".chip-doctor").evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(45, 79, 134)"
    assert pg.locator(".chip-hygienist").evaluate("e => getComputedStyle(e).backgroundColor") == "rgb(38, 105, 74)"
    pg.close()


def test_reception_door_to_patient_list_with_names(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/")
    pg.locator("a.door-reception").click()
    pg.wait_for_selector("tr[data-patient]")
    text = pg.inner_text("body")
    assert "受付用" in text and "患者様一覧" in text and TODAY_TEXT in text and "← 入口へ戻る" in text
    assert "●●" not in text
    assert pg.locator("button.reveal, [data-action=reveal], [data-action=reveal-all]").count() == 0
    heads = [t.strip() for t in pg.locator("table.book th").all_inner_texts()]
    assert heads == ["時間", "カルテ番号", "氏名", "今日の処置", "次回の予約", "来院しやすい曜日", "受付メモ"]
    rows = D.reception_list()
    assert pg.locator("tr[data-patient]").count() == len(rows) >= 5
    times = [t.split("〜")[0] for t in pg.locator("tr[data-patient] td.time").all_inner_texts()]
    assert times == sorted(times)  # 今日の予約の時間の順
    for p in rows:
        assert p["name"] in text
    # 花子様 (0123): 値は受付の画面と同じ出どころ
    hanako = pg.locator("tr[data-patient]", has_text="0123")
    cells = hanako.locator("td").all_inner_texts()
    d = next(p["d"] for p in rows if p["chart_no"] == "0123")
    assert cells[1].strip() == "0123" and "花子" in cells[2]
    assert re.fullmatch(r"\d+/\d+（.）|未定", cells[4].strip())
    assert cells[6].strip() == (d["memo_latest"] or "—")
    hanako.click()
    pg.wait_for_selector('[data-part="important"]')
    assert "見本 花子" in pg.inner_text("body") and "受付用" in pg.inner_text("body")
    # 受付の画面から一覧へ戻れる
    pg.get_by_role("button", name="患者様を変える").click()
    pg.wait_for_selector("tr[data-patient]")
    pg.close()


def test_next_and_heat_match_reception_screen(server, browser):  # noqa: F811
    """一覧の「次回の予約」「来院しやすい曜日」は、1人ずつの受付の画面と同じ値。"""
    pg = open_page(browser, server, "/reception")
    pg.wait_for_selector("tr[data-patient]")
    got = {}
    for row in pg.locator("tr[data-patient]").all():
        cells = row.locator("td").all_inner_texts()
        got[cells[1].strip()] = (cells[4].strip(), cells[5].strip())
    for p in D.reception_list():
        d = p["d"]
        screen = open_page(browser, server, f"/reception?patient={p['id']}")
        screen.wait_for_selector('[data-part="important"]')
        nxt, heat = got[p["chart_no"]]
        if d["booked"]:
            dt = d["booked"][0]["appt_date"]
            assert nxt == f"{int(dt[5:7])}/{int(dt[8:10])}（{D.WEEK[D.date.fromisoformat(dt).weekday()]}）"
            assert f"{int(dt[5:7])}月{int(dt[8:10])}日" in screen.inner_text("body")
        else:
            assert nxt == "未定"
        assert heat in screen.inner_text("body")
        screen.close()
    pg.close()


def test_latest_memo_picks_newest():
    full = [{"body": "古い", "written_on": "2026年8月"}, {"body": "新しい", "written_on": "2026年10月"},
            {"body": "中", "written_on": "2026年9月"}]
    assert D.latest_memo(full) == "新しい"
    assert D.latest_memo([{"body": "a", "written_on": ""}, {"body": "b", "written_on": ""}]) == "b"  # 読めなければ入れた順
    assert D.latest_memo([]) == ""


def test_clinic_door_to_masked_list(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/")
    pg.locator("a.door-clinic").click()
    pg.wait_for_selector("tr.row")
    assert pg.url.endswith("/clinic")
    assert "← 入口へ戻る" in pg.inner_text("body")
    n = pg.locator("tr.row").count()
    assert pg.locator(".nm", has_text="●● ●●").count() == n
    first = pg.locator("tr.row").first
    first.locator(".reveal").click()
    assert "●●" not in first.inner_text()
    assert pg.locator(".nm", has_text="●● ●●").count() == n - 1
    pg.get_by_role("button", name="すべて表示").click()
    assert "●●" not in pg.locator("table.book tbody").inner_text()
    pg.close()


@pytest.mark.parametrize("path", ["/clinic", "/reception"])
def test_back_to_entrance(server, browser, path):  # noqa: F811
    pg = open_page(browser, server, path)
    pg.get_by_role("link", name="← 入口へ戻る").click()
    pg.wait_for_selector("h1")
    assert pg.url.rstrip("/").endswith(str(server)) and "CHAIRSIDE VIEW" in pg.inner_text("body")
    pg.close()


def test_change_role_never_goes_to_reception(server, browser):  # noqa: F811
    rows = [r for r in D.today_list() if r["patient_id"] == 1]
    pg = open_page(browser, server, f"/unit?appt={rows[0]['id']}&role=doctor")
    pg.wait_for_selector('[data-part="important"]')
    for _ in range(3):  # 歯科医師 → 歯科衛生士 → 歯科医師 → 歯科衛生士
        before = pg.evaluate("document.body.className")
        pg.get_by_role("button", name="役割を変える").click()
        pg.wait_for_function("b => document.body.className !== b", arg=before)
        pg.wait_for_selector('[data-part="important"]')
        assert pg.evaluate("document.body.className") in ("role-doctor", "role-hygienist")
        assert "/reception" not in pg.url and "受付用" not in pg.inner_text("body")
    pg.close()


def test_old_addresses_do_not_lose_people(server, browser):  # noqa: F811
    # /app は入口を開く。/clinic と /reception は直接開ける。患者様なしの /unit は予約一覧へ
    pg = open_page(browser, server, "/unit")
    pg.wait_for_url(f"http://127.0.0.1:{server}/clinic")
    pg.close()
    pg = open_page(browser, server, "/app")
    pg.frame_locator("#inner").locator("a.door-clinic").click()
    pg.frame_locator("#inner").locator("tr.row").first.wait_for()
    pg.close()
