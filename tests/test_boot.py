import os
import socket
import subprocess
import sys
import time

import pytest

PORT = int(os.environ.get("CV_PORT", "8840"))


def _up(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(scope="module")
def server():
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


def test_ready_in_edge(server):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        pg = b.new_page(viewport={"width": 1920, "height": 1030})
        pg.goto(f"http://localhost:{server}")
        assert "準備OK" in pg.inner_text("body")
        b.close()
