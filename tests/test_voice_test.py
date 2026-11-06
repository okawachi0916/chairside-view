"""G08: /voice-test。キーの2回押し・帯・録音は GPU なしで確かめ、文字起こしは gpu 試験で確かめる。"""
import os
import re
import socket
import subprocess
import sys
import time
import wave
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

PORT = int(os.environ.get("CV_PORT", "8840"))
PHRASE = "重要事項を全画面にして"


def _up(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(scope="module")
def server():
    for _ in range(15):  # 前の試験のサーバーが止まりきるのを少し待つ
        if not _up(PORT):
            break
        time.sleep(0.2)
    if _up(PORT):
        yield PORT
        return
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)])
    for _ in range(50):
        if _up(PORT):
            break
        time.sleep(0.2)
    yield PORT
    p.terminate()
    p.wait()


@pytest.fixture(scope="module")
def phrase_wav(tmp_path_factory):
    """Windows の音声合成で言葉の wav を作り、後ろに無音を足して6秒にする（偽マイクはくり返し再生するため）。"""
    d = tmp_path_factory.mktemp("wav")
    raw, out = d / "raw.wav", d / "phrase.wav"
    script = (
        "Add-Type -AssemblyName System.Speech;"
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -eq 'ja-JP' } | Select-Object -First 1;"
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name) };"
        f"$s.SetOutputToWaveFile('{raw}');"
        f"$s.Speak('{PHRASE}');"
        "$s.Dispose()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    with wave.open(str(raw), "rb") as r:
        params, frames = r.getparams(), r.readframes(r.getnframes())
    total = params.framerate * 6 * params.sampwidth * params.nchannels
    frames += b"\x00" * max(0, total - len(frames))
    with wave.open(str(out), "wb") as w:
        w.setparams(params)
        w.writeframes(frames)
    return out


@pytest.fixture()
def page(server, phrase_wav):
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", args=[
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream",
            f"--use-file-for-fake-audio-capture={phrase_wav}",
        ])
        ctx = b.new_context(viewport={"width": 1920, "height": 1030})
        ctx.grant_permissions(["microphone"], origin=f"http://localhost:{server}")
        pg = ctx.new_page()
        pg.goto(f"http://localhost:{server}/voice-test")
        pg.wait_for_function("document.getElementById('mic-label').textContent !== ''")
        yield pg
        b.close()


KEY2 = "Control+Shift+F7"


def mic(pg):
    return pg.get_attribute("#mic", "data-state")


def band_visible(pg):
    return pg.is_visible("#band")


def test_key_name_shown(page):
    page.keyboard.press("Control+Shift+F6")
    assert page.inner_text("#last-key") == "Ctrl+Shift+F6"
    page.keyboard.press("Control+Shift+F8")
    assert page.inner_text("#last-key") == "Ctrl+Shift+F8"


def test_single_press_shows_band_then_disappears(page):
    page.keyboard.press(KEY2)
    page.wait_for_selector("#band", state="visible", timeout=1500)
    assert "もう一度【操】" in page.inner_text("#band")
    assert mic(page) == "idle"
    page.wait_for_selector("#band", state="hidden", timeout=6500)
    assert mic(page) == "idle"


def test_slow_double_press_and_hold_do_not_record(page):
    page.keyboard.press(KEY2)
    page.wait_for_selector("#band", state="visible", timeout=1500)
    page.wait_for_selector("#band", state="hidden", timeout=6500)
    time.sleep(1)  # 最初の押下から6秒以上あける
    page.keyboard.press(KEY2)
    time.sleep(0.2)
    assert mic(page) == "idle"
    page.wait_for_selector("#band", state="visible", timeout=1500)
    page.wait_for_selector("#band", state="hidden", timeout=7000)
    # 押し続けは1回
    page.keyboard.down("Control")
    page.keyboard.down("Shift")
    for _ in range(4):
        page.keyboard.down("F7")
    page.keyboard.up("F7")
    page.keyboard.up("Shift")
    page.keyboard.up("Control")
    time.sleep(0.8)
    assert mic(page) == "idle"
    assert band_visible(page)


def test_second_press_while_band_starts_and_one_press_stops(page):
    page.keyboard.press(KEY2)
    page.wait_for_selector("#band", state="visible", timeout=1500)
    page.keyboard.press(KEY2)
    page.wait_for_function("document.getElementById('mic').dataset.state === 'rec'", timeout=5000)
    assert not band_visible(page)
    page.keyboard.press(KEY2)  # 録音中は1回で止まる
    page.wait_for_function("document.getElementById('mic').dataset.state === 'idle'", timeout=3000)


def test_quick_double_press_starts_without_band(page):
    page.keyboard.press(KEY2)
    time.sleep(0.2)
    page.keyboard.press(KEY2)
    assert not band_visible(page)
    page.wait_for_function("document.getElementById('mic').dataset.state === 'rec'", timeout=5000)
    assert not band_visible(page)


def test_auto_stop_after_6_seconds(page):
    page.keyboard.press(KEY2)
    time.sleep(0.1)
    page.keyboard.press(KEY2)
    page.wait_for_function("document.getElementById('mic').dataset.state === 'rec'", timeout=5000)
    page.wait_for_function("document.getElementById('mic').dataset.state === 'idle'", timeout=8000)


def test_no_microphone_shows_cross(server):
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page()
        # G27: マイクが無い機械を作る（ブラウザにマイクの入口が無い状態）。以前は idle でも通る条件でバツ印を確かめていなかった
        pg.add_init_script("Object.defineProperty(navigator, 'mediaDevices', {value: undefined})")
        pg.goto(f"http://localhost:{server}/voice-test")
        pg.wait_for_function("document.getElementById('mic-label').textContent !== ''")
        assert pg.get_attribute("#mic", "data-state") == "none"
        b.close()


def _norm(s):
    return re.sub(r"[\s\W_]+", "", s)


@pytest.mark.gpu
def test_recording_to_text(page):
    page.keyboard.press(KEY2)
    time.sleep(0.1)
    page.keyboard.press(KEY2)
    page.wait_for_function("document.getElementById('mic').dataset.state === 'rec'", timeout=5000)
    time.sleep(4.5)
    page.keyboard.press(KEY2)
    page.wait_for_function("document.body.dataset.done === '1'", timeout=120000)
    text = page.inner_text("#text")
    print("聞き取り:", text, page.inner_text("#seconds"), page.inner_text("#model"))
    assert _norm(text) == _norm(PHRASE)
