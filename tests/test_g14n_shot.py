"""G14n: 番号の振り直しの前後の画面の写真（ボタン2を押した状態の歯科医師の画面・写真の全画面）。CV_SHOT_TAG=before で前の写真。"""
import os

from app.views import data as D
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

APPT = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
OUT = ROOT / "docs" / "画面" / "G14n"


def test_shots(server, browser):  # noqa: F811
    tag = os.environ.get("CV_SHOT_TAG", "after")
    pg = open_page(browser, server, f"/unit?appt={APPT}&role=doctor&typed=1&hide=1")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("!!(window.cvNumbers && document.body.dataset.numbersReady)")
    pg.evaluate("window.cvNumbers(true)")
    pg.wait_for_function("document.querySelectorAll('.num-badge').length > 0")
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(OUT / f"{tag}_button2.png"))
    pg.evaluate("window.cvNumbers(false)")
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-item img')
    pg.wait_for_function("[...document.querySelectorAll('.fs-panel img')].every(i => i.complete)")
    pg.screenshot(path=str(OUT / f"{tag}_photos.png"))
    pg.close()
