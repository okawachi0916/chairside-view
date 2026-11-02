"""G16: 質問の答えの画面の試験（Edge）。サーバーは偽物の口で動く（tests/conftest.py）。"""
import json
import os
from pathlib import Path

import pytest

from app.ai.records import build_records
from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

FAKE = Path(os.environ["CHAIRSIDE_AI_FAKE_FILE"])


def appt_of(pid):
    with D.con() as c:
        return c.execute("SELECT id FROM appointments WHERE patient_id=? AND appt_date='2026-11-06' "
                         "AND status='booked' ORDER BY start_time", (pid,)).fetchone()[0]


def number(ref, pid=1):
    with D.con() as c:
        return next(r.number for r in build_records(c, pid) if r.ref == ref)


def reply(text, delay_ms=0):
    FAKE.write_text(json.dumps({"reply": text, "delay_ms": delay_ms}), encoding="utf-8")


@pytest.fixture(autouse=True)
def reset_fake():
    yield
    reply('{"result":"unclear"}')


def open_unit(browser, server, pid=1):  # noqa: F811
    pg = open_page(browser, server, f"/unit?appt={appt_of(pid)}&role=doctor&typed=1&hide=1")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("typeof window.cvTyped === 'function' && typeof window.CVAsk === 'function'")
    return pg


def ask(pg, text):
    pg.evaluate("t => window.cvTyped(t)", text)


def test_found_dims_surroundings_and_shows_tall_frame(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    reply(json.dumps({"result": "found", "record": number("important:1")}))
    ask(pg, "アレルギーは？")
    pg.wait_for_selector('[data-fs-panel="answer"]')
    frame = pg.locator(".ai-frame")
    text = frame.inner_text()
    assert "ペニシリン" in text and "出どころ: 重要事項" in text
    box = frame.bounding_box()
    assert box["height"] > box["width"] * 1.1, box  # 縦に長い大きな枠
    assert pg.evaluate("getComputedStyle(document.body).backgroundColor") == "rgb(27, 34, 43)"  # 周りが暗い
    band = pg.locator('[data-part="important"]')
    assert band.is_visible()  # 重要事項の帯は暗くしない
    assert pg.evaluate("getComputedStyle(document.querySelector('[data-part=important]')).backgroundColor") != "rgb(27, 34, 43)"
    assert pg.locator("main.body").is_hidden() or pg.locator("main.body").count() == 0
    # 小さい出どころ
    assert pg.evaluate("parseFloat(getComputedStyle(document.querySelector('.ai-src')).fontSize)") < 20
    pg.close()


def test_source_shows_date_for_notes(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    reply(json.dumps({"result": "found", "record": number("note:2026-10-23")}))
    ask(pg, "前回は何をした？")
    pg.wait_for_selector('[data-fs-panel="answer"]')
    assert "出どころ: 2026年10月23日の診療記録" in pg.inner_text(".ai-src")
    pg.close()


def test_restore_button_and_voice_close(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    for closer in ("button", "voice"):
        reply(json.dumps({"result": "found", "record": number("medical")}))
        ask(pg, "飲んでいる薬は？")
        pg.wait_for_selector('[data-fs-panel="answer"]')
        if closer == "button":
            pg.click('[data-fs-panel="answer"] [data-action="fs-close"]')
        else:
            ask(pg, "戻して")
        pg.wait_for_selector('[data-fs-panel="answer"]', state="detached")
        assert pg.locator("main.body").is_visible()
        assert "fs-mode" not in (pg.evaluate("document.body.className") or "")
    pg.close()


def test_none_and_unclear_messages(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    reply('{"result":"none"}')
    ask(pg, "インプラントの記録は？")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('記録がありません')")
    reply('{"result":"unclear"}')
    ask(pg, "インプラントの記録は？")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('もう一度お願いします')")
    assert pg.locator('[data-fs-panel="answer"]').count() == 0
    pg.close()


def test_bad_number_shows_retry_only(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    reply(json.dumps({"result": "found", "record": 9999}))
    ask(pg, "アレルギーは？")
    pg.wait_for_function("document.body.dataset.answer === 'retry'")
    assert "もう一度お願いします" in pg.inner_text("#heard")
    assert pg.locator('[data-fs-panel="answer"]').count() == 0
    pg.close()


def test_late_answer_after_patient_change_is_dropped(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    reply(json.dumps({"result": "found", "record": number("important:1")}), delay_ms=1500)
    ask(pg, "アレルギーは？")
    pg.wait_for_function("document.body.dataset.answer === 'waiting'")
    other = appt_of(2)
    pg.evaluate("a => window.cv.openUnit(a, 'doctor')", other)  # 待っている間に患者様を変える
    pg.wait_for_function("document.body.dataset.answer === 'discarded'", timeout=8000)
    assert pg.locator('[data-fs-panel="answer"]').count() == 0
    pg.close()


def test_unrelated_word_does_not_ask(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    seen = []
    pg.on("request", lambda r: seen.append(r.url) if "/ai/ask" in r.url else None)
    ask(pg, "大きく口を開けてください")
    ask(pg, "えっと")
    pg.wait_for_function("document.getElementById('heard').textContent.includes('もう一度お願いします')")
    pg.wait_for_timeout(300)
    assert seen == []
    pg.close()
