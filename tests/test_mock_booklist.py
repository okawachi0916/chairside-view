from tests.screen_helper import browser, open_page, server  # noqa: F401

MASK = "●● ●●"


def test_list_names_masked_and_toggle(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/mock/")
    rows = pg.locator("tr.row")
    assert rows.count() == 6
    text = pg.inner_text("body")
    assert "見本 花子" not in text
    assert text.count(MASK) == 6
    for w in ["時間", "カルテ番号", "氏名", "処置", "0123", "0456", "0789", "1024", "2048"]:
        assert w in text
    # 1人だけ表示
    rows.nth(1).locator("button.reveal").click()
    assert pg.url.endswith("/mock/")
    assert "見本 一郎" in rows.nth(1).inner_text()
    assert rows.nth(1).locator("button.reveal").inner_text() == "伏せ字"
    assert MASK in rows.nth(0).inner_text()
    rows.nth(1).locator("button.reveal").click()
    assert MASK in rows.nth(1).inner_text()
    # 全員まとめて
    all_btn = pg.locator("[data-action=reveal-all]")
    all_btn.click()
    assert MASK not in pg.inner_text("tbody")
    all_btn.click()
    assert pg.inner_text("tbody").count(MASK) == 6
    pg.close()


def test_row_opens_right_screen(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/mock/")
    expect = ["/mock/hygienist" if p == "SPT" else "/mock/doctor"
              for p in ["RCT", "SPT", "義歯調整", "CR", "SPT", "インレー"]]
    for i, path in enumerate(expect):
        pg.goto(f"http://127.0.0.1:{server}/mock/")
        pg.locator("tr.row").nth(i).click()
        pg.wait_for_url(f"**{path}")
    pg.close()


def test_change_patient_and_role(server, browser):  # noqa: F811
    pg = open_page(browser, server, "/mock/doctor")
    pg.click("button:has-text('役割を変える')")
    pg.wait_for_url("**/mock/hygienist")
    assert "歯科衛生士用" in pg.inner_text("body")
    pg.click("button:has-text('役割を変える')")
    pg.wait_for_url("**/mock/doctor")
    assert "歯科医師用" in pg.inner_text("body")
    pg.click("button:has-text('患者様を変える')")
    pg.wait_for_url("**/mock/")
    # 受付へ行くボタンはどこにも無い
    for path in ("/mock/", "/mock/doctor", "/mock/hygienist"):
        pg.goto(f"http://127.0.0.1:{server}{path}")
        assert pg.locator("a[href*=reception], [data-href*=reception]").count() == 0
        assert "受付" not in pg.inner_text("body")
    # 受付の画面から患者様を変える → 予約一覧
    pg.goto(f"http://127.0.0.1:{server}/mock/reception")
    pg.click("button:has-text('患者様を変える')")
    pg.wait_for_url("**/mock/")
    pg.close()
