"""G13: ボタン2の受付から全画面まで（偽マイク。文字起こしに GPU を使う）。"""
import json
import time

import pytest

from app.views import data as D
from tests.screen_helper import ROOT, server  # noqa: F401
from tests.test_voice_test import phrase_wav  # noqa: F401

H_DOC = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]


@pytest.mark.gpu
def test_button2_listens_and_opens_fullscreen(server, phrase_wav):  # noqa: F811
    from playwright.sync_api import sync_playwright

    key2 = json.loads((ROOT / "config" / "keys.json").read_text(encoding="utf-8"))["button2"].replace("Ctrl", "Control")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", args=[
            "--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream",
            f"--use-file-for-fake-audio-capture={phrase_wav}",
        ])
        ctx = b.new_context(viewport={"width": 1920, "height": 1030})
        ctx.grant_permissions(["microphone"], origin=f"http://127.0.0.1:{server}")
        pg = ctx.new_page()
        pg.goto(f"http://127.0.0.1:{server}/unit?appt={H_DOC}&role=doctor")
        pg.wait_for_selector('[data-part="important"]')
        pg.wait_for_function("window.VoiceKeys && document.getElementById('band')")
        time.sleep(0.4)
        pg.keyboard.press(key2)
        time.sleep(0.1)
        pg.keyboard.press(key2)
        pg.wait_for_selector(".topbar .mic.rec")
        time.sleep(4.5)
        pg.keyboard.press(key2)  # 1回で止まる
        pg.wait_for_selector('[data-fs-panel="important"]', timeout=120000)
        assert pg.locator(".topbar .mic.rec").count() == 0
        b.close()
