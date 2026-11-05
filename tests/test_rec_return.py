"""G26d: 録音を始めた画面そのものへ戻る試験（Edge。マイクは偽物の機器）。

診療の画面で録音 → 下書きを開く → 「あとで直す」で、始めた画面へ戻る。口腔内写真の全画面（並べた写真つき）から
始めたときは、その全画面へ戻る。そこで「戻して」（fs-close）を実行すると、全画面を開く前の診療の画面へ戻る。
"""
import json
import time
from pathlib import Path

from tests.test_rec_screen import (  # noqa: F401
    F6, UNIT, appt_of, browser, clean, inner, open_app, server, start_rec, stop_rec,
)

ROOT = Path(__file__).resolve().parents[1]


def _to_draft(pg):
    pg.wait_for_function("document.body.dataset.draftReady", timeout=20000)
    pg.locator("#rec-win").click()
    pg.wait_for_function("((d) => !!(d && d.body && d.body.dataset.page === 'draft'))(document.getElementById('inner').contentDocument)")


def _inner_path(pg):
    return pg.evaluate("(() => { const l = document.getElementById('inner').contentWindow.location; return l.pathname + l.search })()")


def _wait_unit(pg):
    pg.wait_for_function("((d) => !!(d && d.body && d.body.dataset.kind === 'unit' && d.querySelector('[data-part=important]')))"
                         "(document.getElementById('inner').contentDocument)", timeout=10000)
    time.sleep(0.4)


def _go(pg, url):
    pg.evaluate("u => { document.getElementById('inner').src = u }", url)
    _wait_unit(pg)


def _fs(pg):
    return inner(pg).evaluate("(document.querySelector('.fs-panel[data-fs-panel]') || {getAttribute: () => ''}).getAttribute('data-fs-panel')")


def _photos(pg):
    return inner(pg).evaluate("[].map.call(document.querySelectorAll('[data-fs-panel=intraoral-photos] .fs-fig'), f => f.dataset.n)")


def test_later_returns_to_the_unit_screen_not_the_appointment_list(server, browser):  # noqa: F811
    pg = open_app(browser, server)
    _go(pg, UNIT("0123"))
    where = _inner_path(pg)
    assert where.startswith("/unit?appt=")
    start_rec(pg)
    time.sleep(0.8)
    stop_rec(pg)
    _to_draft(pg)
    assert "back=" in _inner_path(pg)
    inner(pg).click("#btn-later")
    _wait_unit(pg)
    assert _inner_path(pg) == where  # 予約一覧 "/" ではなく、始めた診療の画面
    assert _fs(pg) == ""
    pg.context.close()


def test_returns_to_the_intraoral_photo_fullscreen_with_the_same_photos(server, browser):  # noqa: F811
    pg = open_app(browser, server)
    _go(pg, UNIT("0123"))
    f = inner(pg)
    f.evaluate("window.cvTyped('口腔内写真を全画面にして')")
    f.wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-fig')
    f.evaluate("window.CVActions.run('photo-show', [3, 6])")
    assert _photos(pg) == ["3", "6"]
    start_rec(pg)
    time.sleep(0.8)
    stop_rec(pg)
    _to_draft(pg)
    inner(pg).click("#btn-later")
    _wait_unit(pg)
    inner(pg).wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-fig')
    assert _fs(pg) == "intraoral-photos"
    assert _photos(pg) == ["3", "6"]  # 並べていた写真もそのまま

    # 「戻して」は、全画面を開く前の診療の画面へ戻る（録音や下書きの途中には戻らない）
    cmds = json.loads((ROOT / "config" / "commands.json").read_text(encoding="utf-8"))
    back = [c for c in cmds if c.get("言葉") == "戻して" and "unit" in c.get("使える画面", [])]
    assert back and back[0]["結果"]["action"] == "fs-close"
    inner(pg).evaluate("window.CVActions.run('fs-close')")
    assert _fs(pg) == ""
    assert inner(pg).locator("[data-part=important]").count() == 1
    assert _inner_path(pg).startswith("/unit?appt=") and "fs=" not in _inner_path(pg)
    pg.context.close()


def test_returns_to_a_fullscreen_when_recording_started_from_a_screen_without_parent(server, browser):  # noqa: F811
    """親の画面（/app）の外の診療の画面でボタン1を押したときも、全画面へ戻る。"""
    ctx = browser.new_context(viewport={"width": 1920, "height": 1030}, permissions=["microphone"])
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{server}{UNIT('0123')}")
    pg.wait_for_selector("[data-part=important]")
    time.sleep(0.4)
    pg.evaluate("window.cvTyped('口腔内写真を全画面にして')")
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-fig')
    pg.evaluate("window.CVActions.run('photo-show', [2, 4])")
    pg.evaluate("window.CVActions.run('button1')")  # 親の無い画面 → /app へ移って録音を始める
    pg.wait_for_function("document.body.dataset.rec === 'recording'")
    assert "fs%3Dintraoral-photos" in pg.url and "ph%3D2%2C4" in pg.url
    time.sleep(0.8)
    stop_rec(pg)
    _to_draft(pg)
    inner(pg).click("#btn-later")
    _wait_unit(pg)
    inner(pg).wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-fig')
    assert _photos(pg) == ["2", "4"]
    ctx.close()


def test_here_is_plain_without_a_fullscreen(server, browser):  # noqa: F811
    """全画面でない診療の画面には fs を付けない。"""
    pg = open_app(browser, server)
    appt = appt_of("0123")
    _go(pg, f"/unit?appt={appt}&role=hygienist")
    assert inner(pg).evaluate("window.CVReturn.here()") == f"/unit?appt={appt}&role=hygienist"
    inner(pg).evaluate("window.CVActions.run('fs-open', 'important')")
    assert inner(pg).evaluate("window.CVReturn.here()") == f"/unit?appt={appt}&role=hygienist&fs=important"
    pg.context.close()
