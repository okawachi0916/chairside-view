"""G19m: 画面で確かめる。印は初めから付いている・「3番 外す」・1回で記録・記録のあと画面がそろう・「記録を取り消す」で下書きへ戻る。
前後の写真を docs/画面/G19m に置く。"""
import json
from pathlib import Path

import pytest

from app.ai import memo
from tests.screen_helper import browser, open_page, server  # noqa: F401
from tests.test_confirm_screen import appt_of, clean, db_one, home, make_rec, open_draft, ready, set_fake  # noqa: F401
from tests.test_g19g import numbers
from tests.test_g19l_screen import tooth_ready

SHOTS = Path(__file__).resolve().parents[1] / "docs" / "画面" / "G19m"
TALK = "今日は右下6番の根管充填をしました。次回は二週間後に土台の形成をします。今後の方針は経過を見て被せ物を考えます。"
REPLY = json.dumps({**{k: [] for k in memo.KEYS},
                    "done": [{"text": "右下6番の根管充填", "quote": "右下6番の根管充填をしました"}],
                    "next_plan": [{"text": "二週間後に土台の形成をする", "quote": "次回は二週間後に土台の形成をします"}],
                    "future_policy": [{"text": "経過を見て被せ物を考える", "quote": "経過を見て被せ物を考えます"}]}, ensure_ascii=False)


def shoot(pg, name, part=None):
    SHOTS.mkdir(parents=True, exist_ok=True)
    (pg.locator(f'[data-part="{part}"]').first if part else pg).screenshot(path=str(SHOTS / name))


def doctor_url(server):
    return f"/unit?appt={appt_of('0123', 'doctor')}&role=doctor&typed=1&hide=1"


def doctor_page(browser, server):  # noqa: F811
    pg = open_page(browser, server, doctor_url(server))
    pg.wait_for_selector('[data-part="tooth-chart"] .tc-tooth[data-tooth="46"]')
    return pg


def test_everything_is_checked_then_one_word_records_and_screens_follow_then_cancel(server, browser):  # noqa: F811
    set_fake(reply=REPLY, transcript=TALK)
    s = make_rec(server)
    dp = doctor_page(browser, server)
    assert dp.locator('[data-part="today-treatment"] .main').inner_text() == "右下6番 根管充填"   # 記録する前は予約の予定
    shoot(dp, "前_今日の処置.png", "today-treatment")
    shoot(dp, "前_歯の絵.png", "tooth-chart")
    dp.close()

    pg, _ = open_draft(browser, server, s["draft_id"], back=doctor_url(server))
    ready(pg)
    tooth_ready(pg)
    boxes = pg.locator("#tooth-rows input")
    assert boxes.count() == 3 and all(b.is_checked() for b in boxes.all())                # 歯の処置・次回・治療方針。全部、初めから印あり
    titles = pg.locator("#tooth-rows tr td:first-child").all_inner_texts()
    assert titles == ["右下6番 根管充填", "次回の予定", "治療方針"]
    shoot(pg, "下書き_印.png")
    # ボタン2の番号 → 「N番 外す」で外し、「N番 付ける」で付け直す。印の付いた分だけ入る
    m = numbers(pg)
    n3 = next(k for k, v in m.items() if v == "pick:3")
    assert pg.evaluate("t => window.cvTyped(t)", f"{n3}番 外す").startswith("off:")
    assert not boxes.nth(2).is_checked() and boxes.nth(0).is_checked()
    pg.evaluate("window.cvNumbers(true)")
    assert pg.evaluate("t => window.cvTyped(t)", f"{n3}番 付ける").startswith("on:")
    assert boxes.nth(2).is_checked()
    pg.evaluate("window.cvNumbers(true)")
    shoot(pg, "下書き_番号.png")
    assert pg.evaluate("t => window.cvTyped(t)", "カルテに記録する") == "confirm"                     # 1回で記録する
    pg.wait_for_url(lambda u: "/drafts/" not in u)
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"

    dp = doctor_page(browser, server)
    assert dp.locator('[data-part="today-treatment"] .main').inner_text() == "右下6番の根管充填"      # 記録した「やったこと」
    assert dp.locator('.tc-tooth[data-tooth="46"]').get_attribute("data-root") == "根充済"
    assert "右下6番" in dp.locator('[data-part="treatment-history"] tbody tr').first.inner_text()
    shoot(dp, "後_今日の処置.png", "today-treatment")
    shoot(dp, "後_歯の絵.png", "tooth-chart")
    shoot(dp, "後_治療歴.png", "treatment-history")
    # 「記録を取り消す」（ユニットの画面。その日のうち）→ 下書きの画面へ
    assert dp.evaluate("t => window.cvTyped(t)", "記録を取り消す") is not None
    dp.wait_for_url(lambda u: f"/drafts/{s['draft_id']}" in u)
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    assert db_one("SELECT root FROM tooth_status WHERE tooth = 46 AND patient_id = 1")[0] == "根治中"
    assert db_one("SELECT status FROM appointments WHERE id = ?", appt_of("0123", "doctor"))[0] == "booked"
    dp.wait_for_selector("#tooth-rows tr")
    assert dp.locator("#tooth-rows input").count() == 3 and dp.locator("#btn-confirm").count() == 1   # 直してもう一度記録できる
    shoot(dp, "取り消し後_下書き.png")
    dp.close()


def test_cancel_word_next_day_says_only_same_day(server, browser):  # noqa: F811
    set_fake(reply=REPLY, transcript=TALK)
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"], back=doctor_url(server))
    ready(pg)
    tooth_ready(pg)
    pg.evaluate("t => window.cvTyped(t)", "記録")
    pg.wait_for_url(lambda u: "/drafts/" not in u)
    pg.close()
    # 記録した日を昨日にして、「次の日」にする（記録した日の印は日付をずらさないので、ずらすだけ）
    from app.db import connect

    c = connect()
    c.execute("UPDATE record_changes SET recorded_on = '2026-11-05'")
    c.commit()
    c.close()
    dp = doctor_page(browser, server)
    dp.evaluate("t => window.cvTyped(t)", "記録を取り消す")
    dp.wait_for_function("document.body.dataset.heard !== undefined && document.getElementById('heard').textContent.includes('その日のうちだけ取り消せます')")
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"   # 何も戻らない
    dp.close()
