"""G21r: 番号の言葉の準備の印 (numbersReady) は、画面の部品が描かれたあとに付く。
前は番号の表を読み終えただけで付き、画面の描き込みが遅いと「1番」を言っても開く部品がまだ無かった
(試験が ときどき落ちた原因)。ここでは画面の応答をわざと遅らせて、その順番を確かめる。"""
import time

from app.views import data as D
from tests.screen_helper import browser, server  # noqa: F401


def test_numbers_ready_waits_for_the_view(server, browser):  # noqa: F811
    appt = D.today_list()[0]["id"]
    pg = browser.new_page(viewport={"width": 1920, "height": 1030})
    held = []

    pg.route("**/api/view/unit*", lambda route: held.append(route))  # 応答を止めておく
    pg.goto(f"http://127.0.0.1:{server}/unit?appt={appt}&role=doctor&typed=1&hide=1", wait_until="commit")
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped)")
    time.sleep(1.0)  # 番号の表は読み終わっているはずの時間
    assert pg.evaluate("document.body.dataset.numbersReady || ''") == ""  # 画面がまだ無いので準備中
    while not held:
        pg.wait_for_timeout(50)
    held[0].continue_()
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("document.body.dataset.numbersReady === '1'")
    pg.evaluate("window.cvNumbers(true)")
    pg.evaluate("window.cvTyped('1番')")
    pg.wait_for_selector('[data-fs-panel="important"]')
    pg.close()
