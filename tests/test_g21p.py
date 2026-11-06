"""G21p: 入口の画面の見た目。文と行き先は G21n の試験が見る。ここは形と収まりを見る。"""
from pathlib import Path

import pytest

from tests.screen_helper import browser, server  # noqa: F401

SHOTS = Path(__file__).resolve().parent.parent / "docs" / "画面" / "G21p"
WHITE = "rgb(255, 255, 255)"


def _open(browser, port, w, h):  # noqa: F811
    pg = browser.new_page(viewport={"width": w, "height": h})
    pg.goto(f"http://127.0.0.1:{port}/")
    pg.wait_for_selector("h1")
    pg.evaluate("document.fonts.ready")
    return pg


def _style(loc, prop):
    return loc.evaluate(f"e => getComputedStyle(e).{prop}")


@pytest.mark.parametrize("size", [(1920, 1080), (1920, 1030)])
def test_fits_without_scroll_and_buttons_line_up(server, browser, size):  # noqa: F811
    pg = _open(browser, server, *size)
    over = pg.evaluate("""() => { const s = document.scrollingElement;
        return [s.scrollHeight - s.clientHeight, s.scrollWidth - s.clientWidth]; }""")
    assert over[0] <= 0 and over[1] <= 0, over
    h = size[1]
    for sel in [".e-bar", "h1", ".door-reception", ".door-clinic"]:
        b = pg.locator(sel).bounding_box()
        assert b["y"] >= 0 and b["y"] + b["height"] <= h, sel
    rec, cli = pg.locator(".door-reception"), pg.locator(".door-clinic")
    rb, cb = rec.bounding_box(), cli.bounding_box()
    assert abs(rb["height"] - cb["height"]) < 1 and abs(rb["y"] - cb["y"]) < 1  # 同じ高さで横に並ぶ
    gr, gc = rec.locator(".door-go").bounding_box(), cli.locator(".door-go").bounding_box()
    assert abs(gr["y"] - gc["y"]) < 1 and abs(gr["height"] - gc["height"]) < 1  # ボタンの高さがそろう
    for card, go in [(rb, gr), (cb, gc)]:
        assert card["y"] + card["height"] - (go["y"] + go["height"]) < 48  # カードの下の端
        assert go["width"] > card["width"] * 0.85  # カードの幅いっぱい
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(SHOTS / f"after_{size[0]}x{size[1]}.png"))
    pg.close()


def test_card_look(server, browser):  # noqa: F811
    pg = _open(browser, server, 1920, 1080)
    # 上の帯に日付（白い太字）。題の上の日付は無い
    bar = pg.locator(".e-bar")
    assert bar.bounding_box()["y"] == 0 and bar.bounding_box()["width"] == 1920
    date = bar.locator(".e-date")
    assert _style(date, "color") == WHITE and _style(date, "fontWeight") == "700"
    assert pg.locator(".entrance-main .e-date").count() == 0
    # 題は大きく太く、英字は字間を空けて灰色
    assert _style(pg.locator("h1"), "fontSize") == "84px" and _style(pg.locator("h1"), "fontWeight") == "700"
    en = pg.locator(".e-en")
    assert float(_style(en, "letterSpacing")[:-2]) >= 4 and _style(en, "color") == "rgb(88, 100, 116)"
    for kind in ["reception", "clinic"]:
        card = pg.locator(f".door-{kind}")
        assert _style(card, "boxShadow") != "none" and _style(card, "borderTopLeftRadius") == "12px"
        assert _style(card.locator(".door-body"), "backgroundColor") == WHITE  # 帯の下は白い地
        assert _style(card.locator("h2"), "color") == WHITE and _style(card.locator(".door-sub"), "fontWeight") == "700"
        assert _style(card.locator("dt").first, "color") == "rgb(88, 100, 116)"
        assert float(_style(card.locator(".door-see"), "fontSize")[:-2]) > float(_style(card.locator("dt").first, "fontSize")[:-2])
        assert _style(card.locator(".door-note"), "borderLeftStyle") == "solid"
        assert _style(card.locator(".door-go"), "color") == WHITE
        # 括弧は見えない（幅0）
        for p in card.locator(".paren").all():
            assert p.bounding_box()["width"] < 1
    assert "gradient" in _style(pg.locator(".door-clinic"), "backgroundImage")
    assert _style(pg.locator(".door-reception .door-go"), "backgroundColor") == "rgb(99, 70, 153)"
    assert _style(pg.locator(".door-clinic .door-go"), "backgroundColor") == "rgb(45, 79, 134)"
    tags = pg.locator(".door-reception .tag").all_inner_texts()
    assert tags == ["マウスだけ", "声は使わない"]
    assert pg.locator(".door-clinic .tag").all_inner_texts() == ["手袋のまま", "声と3つのボタン"]
    assert _style(pg.locator(".tag-reception"), "color") == "rgb(99, 70, 153)"
    assert _style(pg.locator(".tag-clinic").first, "color") == "rgb(45, 79, 134)"
    assert _style(pg.locator(".chip-doctor"), "color") == WHITE
    pg.close()
