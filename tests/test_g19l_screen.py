"""G19l: 下書きの画面で「歯ごとの処置」を選び、確定したら歯の絵と治療歴が変わる（画面の試験・Edge）。
声だけで（ボタン2 → 番号 → 声）選んで確定できること、前後の写真を docs/画面/G19l に置くこと。"""
import json
from pathlib import Path

import pytest

from app.db import connect
from tests.screen_helper import browser, open_page, server  # noqa: F401
from tests.test_confirm_screen import (GOOD, appt_of, clean, db_one, home, make_rec, open_draft, ready, set_fake)  # noqa: F401
from tests.test_g19g import numbers, say_number

SHOTS = Path(__file__).resolve().parents[1] / "docs" / "画面" / "G19l"


@pytest.fixture(autouse=True)
def tooth_clean():
    """歯の状態と治療歴は clean が戻さないので、ここで戻す。"""
    c = connect()
    saved = [tuple(r) for r in c.execute("SELECT id, status, crown, root, caries FROM tooth_status")]
    max_hist = c.execute("SELECT COALESCE(MAX(id), 0) FROM treatment_history").fetchone()[0]
    c.close()
    yield
    c = connect()
    for i, st, cr, ro, ca in saved:
        c.execute("UPDATE tooth_status SET status = ?, crown = ?, root = ?, caries = ? WHERE id = ?", (st, cr, ro, ca, i))
    c.execute("DELETE FROM tooth_status WHERE id > ?", (max(r[0] for r in saved),))
    c.execute("DELETE FROM tooth_status_history")
    c.execute("DELETE FROM treatment_history WHERE id > ?", (max_hist,))
    c.commit()
    c.close()


def doctor_page(browser, server):  # noqa: F811
    pg = open_page(browser, server, f"/unit?appt={appt_of('0123', 'doctor')}&role=doctor&typed=1&hide=1")
    pg.wait_for_selector('[data-part="tooth-chart"] .tc-tooth[data-tooth="46"]')
    return pg


def shoot(pg, name, part=None):
    SHOTS.mkdir(parents=True, exist_ok=True)
    if part:
        pg.locator(f'[data-part="{part}"]').first.screenshot(path=str(SHOTS / name))
    else:
        pg.screenshot(path=str(SHOTS / name))


def tooth_ready(pg):
    pg.wait_for_function("document.body.dataset.toothReady")


def test_candidates_are_shown_unchecked_and_voice_picks_and_records(server, browser):  # noqa: F811
    s = make_rec(server)
    # 前: 歯科医師の画面（右下6番は根の治療中、治療歴に今日の行は無い）
    dp = doctor_page(browser, server)
    assert dp.locator('.tc-tooth[data-tooth="46"]').get_attribute("data-root") == "根治中"
    shoot(dp, "前_歯の絵.png", "tooth-chart")
    shoot(dp, "前_治療歴.png", "treatment-history")
    dp.close()

    pg, _ = open_draft(browser, server, s["draft_id"], back="/recordings")
    ready(pg)
    tooth_ready(pg)
    rows = pg.locator("#tooth-rows tr")
    assert rows.count() == 1
    text = rows.first.inner_text()
    assert "右下6番 根管充填" in text and "健全、根治中 → 健全、根充済" in text
    assert not pg.locator("#tooth-rows input").first.is_checked()          # 初めは「反映しない」
    shoot(pg, "下書き_選ぶ欄.png")
    # ボタン2 → 番号 → 声: 候補の「反映する」にも番号が出る（記録する・あとで直す・各行の消す・計画の削除するの次）
    m = numbers(pg)
    n = next(k for k, v in m.items() if v == "tooth:1")
    pg.evaluate("t => window.cvTyped(t)", f"{n}番")
    assert pg.locator("#tooth-rows input").first.is_checked()
    assert db_one("SELECT root FROM tooth_status WHERE tooth = 46 AND patient_id = 1")[0] == "根治中"  # 選んだだけでは書かない
    pg.evaluate("window.cvNumbers(true)")
    shoot(pg, "下書き_番号.png")
    pg.evaluate("t => window.cvTyped(t)", "1番")                            # 記録する
    pg.wait_for_url(home(server))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"
    assert db_one("SELECT root FROM tooth_status WHERE tooth = 46 AND patient_id = 1")[0] == "根充済"
    assert db_one("SELECT COUNT(*) FROM treatment_history WHERE content = '根管充填' AND site = '右下6番' AND done_date = '2026-11-06'")[0] == 1
    pg.close()
    # 後: 歯の絵と治療歴
    dp = doctor_page(browser, server)
    assert dp.locator('.tc-tooth[data-tooth="46"]').get_attribute("data-root") == "根充済"
    first = dp.locator('[data-part="treatment-history"] tbody tr').first.inner_text()
    assert "右下6番" in first and "根管充填" in first and "11/6" in first.replace("2026/", "")
    shoot(dp, "後_歯の絵.png", "tooth-chart")
    shoot(dp, "後_治療歴.png", "treatment-history")
    dp.close()


def test_not_picking_changes_nothing_on_the_screen_either(server, browser):  # noqa: F811
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"], back="/recordings")
    ready(pg)
    tooth_ready(pg)
    pg.click("#btn-confirm")
    pg.wait_for_url(home(server))
    assert db_one("SELECT root FROM tooth_status WHERE tooth = 46 AND patient_id = 1")[0] == "根治中"
    assert db_one("SELECT COUNT(*) FROM tooth_status_history")[0] == 0
    pg.close()


def test_rows_without_a_decided_tooth_or_known_word_show_no_section(server, browser):  # noqa: F811
    talk = "今日は歯石除去をしました。下顎の抜歯をしました。"
    set_fake(reply=json.dumps({"done": [{"text": "歯石除去をした", "quote": "歯石除去をしました"}, {"text": "下顎の抜歯", "quote": "下顎の抜歯をしました"}],
                               "explained": [], "next_plan": [], "future_plan": [], "future_policy": []}, ensure_ascii=False), transcript=talk)
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    tooth_ready(pg)
    assert pg.locator("#tooth-rows tr").count() == 0
    assert not pg.locator("#tooth-compare").is_visible()
    # 行を直して候補が出る（直すたびに作り直す）
    pg.locator("[data-section=done] .tx").first.fill("右下6番の抜髄")
    pg.wait_for_selector("#tooth-rows tr")
    assert "抜髄" in pg.locator("#tooth-rows tr").first.inner_text()
    pg.close()
