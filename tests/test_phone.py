"""G25: スマホで写真を受け渡す。QR の文字列と期限を毎回調べる小さなサーバー（試験ではポート 8861）。"""
import io
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from app.db import TODAY
from app.mobile import links
from app.views import data as D
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

MPORT = int(os.environ.get("CV_MOBILE_PORT", "8861"))
ROWS = [r for r in D.today_list() if r["patient_id"] == 1]
APPT = ROWS[0]["id"]
UNIT = f"/unit?appt={APPT}&role=doctor"


def _up(port):
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(scope="module")
def mobile():
    for _ in range(50):
        if not _up(MPORT):
            break
        time.sleep(0.2)
    env = dict(os.environ, CV_MOBILE_PORT=str(MPORT))
    p = subprocess.Popen([sys.executable, "-m", "app.mobile"], cwd=ROOT, env=env)
    for _ in range(100):
        if _up(MPORT):
            break
        time.sleep(0.2)
    yield MPORT
    p.terminate()
    p.wait()


@pytest.fixture(autouse=True)
def clean():
    """試験で入れた写真・QR・記録を片付ける（ほかの試験の写真の数を変えないため）。"""
    yield
    con = links.db()
    try:
        for r in con.execute("SELECT file FROM photos WHERE file != ''").fetchall():
            (ROOT / "data" / "runtime" / "photos" / r["file"]).unlink(missing_ok=True)
        con.execute("DELETE FROM photos WHERE file != ''")
        con.execute("DELETE FROM phone_events")
        con.execute("DELETE FROM phone_links")
        con.commit()
    finally:
        con.close()


def png(color=(200, 30, 30), size=(64, 48)):
    from PIL import Image

    b = io.BytesIO()
    Image.new("RGB", size, color).save(b, "PNG")
    return b.getvalue()


def http(method, port, path, data=None, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        try:
            body = e.read()
        except OSError:
            body = b""
        return e.code, body, {k.lower(): v for k, v in e.headers.items()}
    except (ConnectionError, OSError):  # 大きすぎる送りは、サーバーが途中で切ることがある
        return 0, b"", {}


def link(patient_id=1, ttl=None, now=None):
    return links.create_link(patient_id, ttl=ttl, now=now)[0]


def upload(port, token, body, ctype="application/octet-stream"):
    return http("POST", port, f"/m/{token}/upload", data=body, headers={"Content-Type": ctype})


# ---------- 文字列と期限 ----------
def test_token_is_long_random_and_only_hash_is_stored():
    t1, exp = links.create_link(1)
    t2, _ = links.create_link(1)
    assert t1 != t2 and len(t1) >= 40 and links.TOKEN_RE.match(t1)
    assert abs(exp - int(time.time()) - 600) <= 2  # 有効期限は10分
    con = links.db()
    try:
        dump = json.dumps([tuple(r) for r in con.execute("SELECT * FROM phone_links")])
    finally:
        con.close()
    assert t1 not in dump and links.hash_token(t1) in dump


def test_lookup_states_and_binding():
    t, exp = links.create_link(2)
    state, row = links.lookup(t)
    assert state == links.OK and row["patient_id"] == 2 and row["chart_no"] == "0456"
    assert links.lookup(t, now=exp)[0] == links.EXPIRED  # 期限の瞬間から使えない
    assert links.lookup(t, now=exp - 1)[0] == links.OK
    for bad in ["", "abc", "x" * 43, "../" * 20, t[:-1], t + "a", None]:
        assert links.lookup(bad)[0] == links.NONE


def test_public_url_file_decides_qr_address(tmp_path, monkeypatch):
    f = tmp_path / "public_url.txt"
    f.write_text("https://phone.example.net/\n", encoding="utf-8")
    monkeypatch.setenv("CV_PUBLIC_URL_FILE", str(f))
    assert links.link_url("T" * 43) == "https://phone.example.net/m/" + "T" * 43
    f.write_text("javascript:alert(1)", encoding="utf-8")
    assert links.public_base().startswith("http://") and f":{MPORT}" in links.public_base()  # 変なものは使わず院内のアドレス
    monkeypatch.setenv("CV_PUBLIC_URL_FILE", str(tmp_path / "missing.txt"))
    assert links.public_base() == f"http://{links.lan_ip()}:{MPORT}"


# ---------- 画面 ----------
def test_page_shows_only_chart_number_and_two_buttons(mobile):
    code, body, h = http("GET", mobile, f"/m/{link()}")
    text = body.decode("utf-8")
    assert code == 200 and "No. 0123" in text and "写真を入れる" in text and "写真を取り出す" in text
    assert "見本 花子" not in text and "花子" not in text  # 名前は出さない
    assert h.get("cache-control") == "no-store"


def test_expired_link_opens_nothing(mobile):
    t = link(ttl=-5)  # もう期限が切れている
    for method, path, data in [("GET", f"/m/{t}", None), ("GET", f"/m/{t}/photos", None), ("GET", f"/m/{t}/photo/1", None),
                               ("POST", f"/m/{t}/upload", png())]:
        code, body, _ = http(method, mobile, path, data=data)
        assert code == 410, (path, code)
        assert "期限が切れました" in body.decode("utf-8")
    con = links.db()
    try:
        assert con.execute("SELECT COUNT(*) FROM photos WHERE file != ''").fetchone()[0] == 0  # 期限切れでは入らない
    finally:
        con.close()


def test_unknown_or_malformed_link_is_404(mobile):
    for path in ["/m/" + "A" * 43, "/m/short", "/m/" + "A" * 43 + "/photos", "/m/" + "A" * 43 + "/photo/1"]:
        assert http("GET", mobile, path)[0] == 404, path
    assert http("POST", mobile, "/m/" + "A" * 43 + "/upload", data=png())[0] == 404


def test_link_expires_in_the_middle(mobile):
    t = link(ttl=2)
    assert http("GET", mobile, f"/m/{t}/photos")[0] == 200
    time.sleep(2.2)
    assert http("GET", mobile, f"/m/{t}/photos")[0] == 410
    assert upload(mobile, t, png())[0] == 410


# ---------- 入れる・取り出す ----------
def test_upload_goes_into_photo_list_with_number_and_is_logged(mobile, server):  # noqa: F811
    t = link()
    con = links.db()
    before = con.execute("SELECT MAX(number) FROM photos WHERE patient_id = 1").fetchone()[0]
    con.close()
    code, body, _ = upload(mobile, t, png())
    assert code == 200 and json.loads(body)["number"] == before + 1
    code2, body2, _ = upload(mobile, t, png((10, 200, 10)))
    assert json.loads(body2)["number"] == before + 2
    # 口腔内写真の欄（メインの画面）に番号付きで入る
    code, html, _ = http("GET", server, f"/api/view/unit?appt={APPT}&role=doctor")
    page = json.loads(html)["html"]
    assert f'data-n="{before + 1}"' in page and f'data-n="{before + 2}"' in page and "/photo-up/" in page
    con = links.db()
    try:
        ev = con.execute("SELECT kind, photo_number, at FROM phone_events ORDER BY id").fetchall()
        row = con.execute("SELECT taken_on, kind FROM photos WHERE number = ? AND patient_id = 1", (before + 1,)).fetchone()
    finally:
        con.close()
    assert [e["kind"] for e in ev] == ["入れた", "入れた"] and ev[0]["photo_number"] == before + 1
    assert len(ev[0]["at"]) == 19 and ev[0]["at"][4] == "-" and "T" in ev[0]["at"]  # 入れた時刻
    assert row["taken_on"] == TODAY and row["kind"] == "intraoral"
    # 保存した画像は main からも見られる
    name = page.split("/photo-up/")[1].split('"')[0]
    assert http("GET", server, f"/photo-up/{name}")[0] == 200
    assert http("GET", server, "/photo-up/..%2F..%2Fapp.db")[0] == 404
    assert http("GET", server, "/photo-up/1_0000000000000000.jpg")[0] == 404


def test_retrieve_lists_only_todays_photos_of_that_patient_and_logs(mobile):
    t1, t2 = link(1), link(2)
    n = json.loads(upload(mobile, t1, png())[1])["number"]
    code, body, _ = http("GET", mobile, f"/m/{t1}/photos")
    assert json.loads(body)["photos"] == [n]  # 今日の写真だけ（古い日の写真は出ない）
    code, img, h = http("GET", mobile, f"/m/{t1}/photo/{n}")
    assert code == 200 and h["content-type"] == "image/jpeg" and img[:3] == b"\xff\xd8\xff"
    con = links.db()
    try:
        assert con.execute("SELECT COUNT(*) FROM phone_events WHERE kind = '取り出した'").fetchone()[0] == 0  # 見るだけでは記録しない
    finally:
        con.close()
    assert http("GET", mobile, f"/m/{t1}/photo/{n}?dl=1")[0] == 200
    con = links.db()
    try:
        ev = con.execute("SELECT photo_number, at FROM phone_events WHERE kind = '取り出した'").fetchall()
    finally:
        con.close()
    assert len(ev) == 1 and ev[0]["photo_number"] == n and "T" in ev[0]["at"]
    # 別の患者様のQRでは、その写真は開けない（番号が同じでも）
    assert json.loads(http("GET", mobile, f"/m/{t2}/photos")[1])["photos"] == []
    assert http("GET", mobile, f"/m/{t2}/photo/{n}")[0] == 404
    # 古い日の写真（番号1）は、その患者様のQRでも開けない
    assert http("GET", mobile, f"/m/{t1}/photo/1")[0] == 404
    assert http("GET", mobile, f"/m/{t1}/photo/9999")[0] == 404


def test_only_images_with_a_size_limit(mobile):
    t = link()
    ok = {"image/jpeg", "image/png"}
    assert upload(mobile, t, png(), "image/png")[0] == 200
    assert upload(mobile, t, b"<html><script>alert(1)</script></html>", "image/png")[0] == 415  # 名前を画像にしても中身が違う
    assert upload(mobile, t, b"<svg xmlns='http://www.w3.org/2000/svg'><script>1</script></svg>", "image/svg+xml")[0] == 415
    assert upload(mobile, t, b"%PDF-1.4 fake", "application/pdf")[0] == 415
    assert upload(mobile, t, b"\xff\xd8\xff" + b"not really a jpeg", "image/jpeg")[0] == 415  # 見出しだけ画像
    assert upload(mobile, t, b"", "image/png")[0] == 415
    big = b"\xff\xd8\xff" + b"\0" * (links.config()["max_bytes"] + 1)
    assert upload(mobile, t, big, "image/jpeg")[0] in (413, 0)  # 大きさの上限
    con = links.db()
    try:
        assert con.execute("SELECT COUNT(*) FROM photos WHERE file != ''").fetchone()[0] == 1  # 入ったのは最初の1枚だけ
    finally:
        con.close()
    assert ok


def test_uploaded_file_has_no_original_metadata(mobile):
    from PIL import Image

    t = link()
    img = Image.new("RGB", (40, 30), (1, 2, 3))
    exif = Image.Exif()
    exif[0x010F] = "SecretMaker"
    b = io.BytesIO()
    img.save(b, "JPEG", exif=exif)
    n = json.loads(upload(mobile, t, b.getvalue(), "image/jpeg")[1])["number"]
    saved = http("GET", mobile, f"/m/{t}/photo/{n}")[1]
    assert b"SecretMaker" not in saved and Image.open(io.BytesIO(saved)).getexif().get(0x010F) is None


def test_count_limit_per_link(mobile):
    t = link()
    small = png(size=(2, 2))
    cap = links.config()["max_files_per_link"]
    codes = [upload(mobile, t, small)[0] for _ in range(cap + 1)]
    assert codes[:cap] == [200] * cap and codes[cap] == 429


def test_mobile_port_serves_nothing_but_m(mobile, server):  # noqa: F811
    t = link()
    for path in ["/", "/unit", f"/unit?appt={APPT}&role=doctor", f"/api/view/unit?appt={APPT}&role=doctor", "/api/phone-photos/count?appt=1",
                 "/photo-files/photo01.png", "/photo-up/x.jpg", "/static/css/mock.css", "/docs", "/openapi.json", "/recordings",
                 "/voice/commands", "/config/keys.json", "/m", "/m/", f"/m/{t}/../../unit", "/api/phone-link", "/api/recordings/pending"]:
        code = http("GET", mobile, path)[0]
        assert code in (404, 405), (path, code)
    for path in ["/api/phone-link", "/voice/interpret", "/ai/ask", "/rec/start"]:
        assert http("POST", mobile, path, data=b"{}", headers={"Content-Type": "application/json"})[0] in (404, 405), path
    # 患者様の一覧や名前が、どの答えにも出ない
    _, body, _ = http("GET", mobile, f"/m/{t}")
    assert "見本" not in body.decode("utf-8") and "0456" not in body.decode("utf-8")


# ---------- メインの画面とスマホの画面 ----------
def test_phone_button_shows_qr_with_countdown(server, browser, mobile):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_selector('[data-part="intraoral-photos"] [data-action="phone"]')
    pg.click('[data-part="intraoral-photos"] [data-action="phone"]')
    pg.wait_for_selector("#phone-modal .qr svg")
    url = pg.evaluate("document.getElementById('phone-modal').dataset.url")
    assert url == f"http://{links.lan_ip()}:{MPORT}/m/" + url.split("/m/")[1] and len(url.split("/m/")[1]) >= 43
    left = pg.inner_text("#phone-modal .left")
    assert left.startswith("残り ") and left.split()[1].startswith(("9:5", "10:0"))
    txt = pg.inner_text("#phone-modal")
    assert "花子" not in txt and "見本" not in txt
    assert http("GET", mobile, "/m/" + url.split("/m/")[1])[0] == 200  # QR の中のアドレスはそのまま開ける
    pg.click("#phone-modal [data-act=close]")
    assert pg.locator("#phone-modal").count() == 0


def test_qr_modal_says_expired_when_time_is_up(server, browser):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_selector('[data-part="intraoral-photos"] [data-action="phone"]')
    pg.click('[data-part="intraoral-photos"] [data-action="phone"]')
    pg.wait_for_selector("#phone-modal .qr svg")
    pg.evaluate("(() => { const o = Date.now; Date.now = () => o() + 11 * 60 * 1000; })()")
    pg.wait_for_function("document.querySelector('#phone-modal .left').textContent === '期限が切れました'")
    assert not pg.locator("#phone-modal .qr").is_visible() and pg.locator("#phone-modal [data-act=again]").is_visible()


def test_photo_from_phone_appears_on_screen_with_number(server, browser, mobile):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_selector('[data-part="photo-list"]')
    before = pg.locator('[data-part="photo-list"] .ph').count()
    pg.click('[data-part="intraoral-photos"] [data-action="phone"]')
    pg.wait_for_selector("#phone-modal .qr svg")
    url = pg.evaluate("document.getElementById('phone-modal').dataset.url")
    time.sleep(3)  # 最初の数え直しを待つ
    code, body, _ = upload(mobile, url.split("/m/")[1], png((30, 60, 200)))
    n = json.loads(body)["number"]
    pg.wait_for_function(f"document.querySelectorAll('[data-part=\"photo-list\"] .ph').length === {before + 1}", timeout=15000)
    assert pg.locator(f'[data-part="photo-list"] .ph[data-n="{n}"] .no').inner_text() == str(n)
    img = pg.locator(f'[data-part="photo-list"] .ph[data-n="{n}"] img')
    img.scroll_into_view_if_needed()
    pg.wait_for_function("e => e.complete && e.naturalWidth > 0", arg=img.element_handle())


def test_phone_side_flow_in_browser(browser, mobile, tmp_path):  # noqa: F811
    t = link()
    f = tmp_path / "shot.png"
    f.write_bytes(png((20, 120, 40), (200, 150)))
    pg = browser.new_page(viewport={"width": 390, "height": 800})
    pg.add_init_script("navigator.canShare = () => false")  # 共有の窓が無い機器では、ふつうに保存する
    pg.goto(f"http://127.0.0.1:{mobile}/m/{t}")
    assert "No. 0123" in pg.inner_text("h1")
    pg.set_input_files("#pick", str(f))
    pg.wait_for_function("document.getElementById('msg').textContent === '1枚入れました'")
    pg.click("#take")
    pg.wait_for_selector(".cell")
    assert pg.locator(".cell").count() == 1
    pg.click(".cell")
    with pg.expect_download() as dl:
        pg.click("#save")
    assert dl.value.suggested_filename.endswith(".jpg")
    pg.wait_for_function("document.getElementById('msg').textContent.includes('保存しました')")
    con = links.db()
    try:
        kinds = [r[0] for r in con.execute("SELECT kind FROM phone_events ORDER BY id")]
    finally:
        con.close()
    assert kinds == ["入れた", "取り出した"]
    pg.close()


def test_phone_page_without_photos_says_so(browser, mobile):  # noqa: F811
    pg = browser.new_page(viewport={"width": 390, "height": 800})
    pg.goto(f"http://127.0.0.1:{mobile}/m/{link(2)}")
    assert "No. 0456" in pg.inner_text("h1")
    pg.click("#take")
    pg.wait_for_function("document.getElementById('msg').textContent === '今日の写真はまだありません'")
    pg.close()


# ---------- G25b: QR の大きさとボタンの場所 ----------
def _qr_fills_box(pg):
    pg.wait_for_selector("#phone-modal .qr svg")
    r = pg.evaluate("""() => { const s = document.querySelector('#phone-modal .qr svg');
        const b = s.getBoundingClientRect(); const v = s.viewBox.baseVal; const inner = s.querySelector('path').getBBox();
        return {w: b.width, h: b.height, vw: v.width, vh: v.height, pw: inner.width, ih: innerHeight}; }""")
    assert r["vw"] > 20 and r["vh"] > 20  # viewBox が付いている（付いていないと絵が大きくならない）
    assert r["h"] >= r["ih"] * 0.55 and r["w"] >= r["ih"] * 0.55, r  # 画面の高さのおよそ6割
    assert r["pw"] >= r["vw"] * 0.85  # 絵が枠いっぱいに広がる（余白は白い縁だけ）


def test_qr_is_big_and_fills_its_box(server, browser, mobile):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_selector('[data-part="intraoral-photos"] [data-action="phone"]')
    pg.click('[data-part="intraoral-photos"] [data-action="phone"]')
    _qr_fills_box(pg)
    assert pg.evaluate("document.querySelector('#phone-modal .box').getBoundingClientRect().bottom") <= 1030


def test_phone_button_reachable_from_every_screen(server, browser, mobile):  # noqa: F811
    for role in ("doctor", "hygienist"):
        pg = open_page(browser, server, f"/unit?appt={APPT}&role={role}")
        pg.wait_for_selector(".phone-fab")
        assert pg.locator(".phone-fab").is_visible()
        pg.click(".phone-fab")
        pg.wait_for_selector("#phone-modal .qr svg")
        pg.click("#phone-modal [data-act=close]")
        # 全画面の中でも押せる: 口腔内写真は枠の中、そのほかは固定のボタン
        for part in ("intraoral-photos", "important", "medical-history"):
            pg.evaluate(f"CVActions.run('fs-open', '{part}')")
            pg.wait_for_selector(".fs-panel")
            btn = pg.locator(".fs-head .phone-btn") if part == "intraoral-photos" else pg.locator(".phone-fab")
            assert btn.is_visible(), (role, part)
            if part == "intraoral-photos":
                assert pg.locator(".phone-fab").is_hidden()
            btn.click()
            pg.wait_for_selector("#phone-modal .qr svg")
            _qr_fills_box(pg)
            pg.click("#phone-modal [data-act=close]")
            pg.evaluate("CVActions.run('fs-close')")
        pg.close()
