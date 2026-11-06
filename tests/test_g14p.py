"""G14p: マイクが使えないとき、画面が黙らず、何が起きたかと次にすることを日本語で出す。Claude は使わない。
ブラウザの getUserMedia を、種類ごとの失敗に差し替えて確かめる（機器・許可には決め打ちしない）。"""
import pytest

from app.views import data as D
from tests.screen_helper import server  # noqa: F401
from tests.test_g14i import APPT, double

UNIT = f"/unit?appt={APPT}&role=doctor"

CASES = [
    ("NotAllowedError", ["許可", "マイク"]),
    ("SecurityError", ["許可", "マイク"]),
    ("NotFoundError", ["見つかりません", "既定の録音機器"]),
    ("NotReadableError", ["ほかのアプリ", "Zoom", "閉じて"]),
    ("AbortError", ["ほかのアプリ", "閉じて"]),
    ("SomethingNewError", ["SomethingNewError"]),
]


def fake_failure(name):
    return """(name) => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('x', name)); }""", name


@pytest.fixture
def ctx_page(server):  # noqa: F811
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge")
        ctx = b.new_context(viewport={"width": 1920, "height": 1030})
        yield ctx, server
        b.close()


@pytest.mark.parametrize("name,words", CASES)
def test_unit_voice_says_why(ctx_page, name, words):
    ctx, port = ctx_page
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}{UNIT}")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("window.VoiceKeys && document.getElementById('band') && window.CVMicError")
    pg.evaluate("(name) => { navigator.mediaDevices.getUserMedia = () => Promise.reject(new DOMException('x', name)); }", name)
    pg.wait_for_timeout(300)
    double(pg, 2)
    pg.wait_for_function("(document.body.dataset.heard || '').includes('止まった場所')", timeout=5000)
    heard = pg.evaluate("document.body.dataset.heard")
    for w in words:
        assert w in heard, (name, heard)
    assert "止まった場所: マイク" in heard


def test_no_media_devices_over_plain_http_explains(ctx_page):
    """別のパソコンから http で開くとブラウザがマイクを隠す。その理由と、localhost で開く案内を出す。"""
    ctx, port = ctx_page
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}{UNIT}")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("window.VoiceKeys && document.getElementById('band') && window.CVMicError")
    pg.evaluate("() => { Object.defineProperty(navigator, 'mediaDevices', { value: undefined, configurable: true }); }")
    pg.wait_for_timeout(300)
    double(pg, 2)
    pg.wait_for_function("(document.body.dataset.heard || '').includes('止まった場所')", timeout=5000)
    assert "マイク" in pg.evaluate("document.body.dataset.heard")


def test_explain_unit(ctx_page):
    """説明の部品そのもの。許可の拒否は「ブラウザが止めている」と案内し、secure でないときは localhost を案内する。"""
    ctx, port = ctx_page
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{port}{UNIT}")
    pg.wait_for_function("window.CVMicError")
    out = pg.evaluate("""async () => ({
      denied: await CVMicError.explain({name: 'NotAllowedError'}),
      busy: await CVMicError.explain({name: 'NotReadableError'}),
      none: await CVMicError.explain({name: 'NotFoundError'}),
      http: (Object.defineProperty(window, 'isSecureContext', {value: false, configurable: true}), CVMicError.unsupported()),
      muted: CVMicError.silent({getAudioTracks: () => [{readyState: 'live', enabled: true, muted: true}]}),
      fine: CVMicError.silent({getAudioTracks: () => [{readyState: 'live', enabled: true, muted: false}]}),
      ended: CVMicError.silent({getAudioTracks: () => [{readyState: 'ended', enabled: true, muted: false}]}),
    })""")
    assert "許可" in out["denied"]
    assert "ほかのアプリ" in out["busy"]
    assert "見つかりません" in out["none"]
    assert "localhost" in out["http"]
    assert "ミュート" in out["muted"]
    assert out["fine"] == ""
    assert "外れ" in out["ended"]


def test_all_mic_pages_load_the_explainer(server):  # noqa: F811
    import urllib.request
    for path in [UNIT, "/voice-test", "/recordings", "/app"]:
        with urllib.request.urlopen(f"http://127.0.0.1:{server}{path}", timeout=10) as r:
            html = r.read().decode("utf-8")
        if "voice_test.js" in html or "/static/js/rec.js" in html or "/static/js/actions/voice.js" in html or "/static/js/draft.js" in html:
            assert "mic_error.js" in html and html.index("mic_error.js") < html.index("static/js/", html.index("mic_error.js") + 5) + 1, path
