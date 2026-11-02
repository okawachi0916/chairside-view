"""見本画面の試験で共通に使う道具。Edge を 1920×1030 で開く。"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

PORT = int(os.environ.get("CV_PORT", "8840"))
ROOT = Path(__file__).resolve().parent.parent


def _up(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _serves_mock(port):
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/mock/doctor", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


@pytest.fixture(scope="session")
def server():
    # 前の試験のサーバーが止まりきるのを待ってから、自分で起動する
    if _up(PORT) and _serves_mock(PORT):
        yield PORT
        return
    for _ in range(50):
        if not _up(PORT):
            break
        time.sleep(0.2)
    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)], cwd=ROOT
    )
    for _ in range(100):
        if _up(PORT):
            break
        time.sleep(0.2)
    yield PORT
    p.terminate()
    p.wait()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        yield b
        b.close()


def open_page(browser, port, path):
    pg = browser.new_page(viewport={"width": 1920, "height": 1030})
    pg.goto(f"http://127.0.0.1:{port}{path}")
    return pg


def check_screen(pg, parts, words, png=None, skip_overflow=("past-notes",)):
    """data-part、言葉、スクロール、はみ出しを確かめる。"""
    for part in parts:
        assert pg.locator(f'[data-part="{part}"]').count() >= 1, f"data-part {part} が無い"
    text = pg.inner_text("body")
    missing = [w for w in words if w not in text]
    assert not missing, f"画面に無い言葉: {missing}"
    de = pg.evaluate(
        "() => [document.documentElement.scrollWidth, document.documentElement.scrollHeight,"
        " document.body.scrollHeight]"
    )
    assert de[0] <= 1920 and de[1] <= 1030 and de[2] <= 1030, f"ページ全体にスクロール: {de}"
    skips = list(skip_overflow)
    bad = pg.evaluate(
        """(skips) => [...document.querySelectorAll('.card, .band, .topbar, .card *')]
          .filter(e => !e.closest(skips.map(s => `[data-part="${s}"]`).join(',') || 'x'))
          .filter(e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1)
          .filter(e => !(e instanceof SVGElement) && e.tagName !== 'TR' && getComputedStyle(e).display !== 'inline')
          .map(e => (e.getAttribute('data-part') || e.className || e.tagName) + ':' + e.scrollWidth + 'x' + e.scrollHeight
                    + '/' + e.clientWidth + 'x' + e.clientHeight)""",
        skips,
    )
    assert not bad, f"はみ出し: {bad[:5]}"
    if png:
        out = ROOT / "docs" / "画面" / png
        out.parent.mkdir(parents=True, exist_ok=True)
        pg.screenshot(path=str(out))
