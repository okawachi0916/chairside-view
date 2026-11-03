"""スマホ用の小さなサーバー。開けるのは /m/ の下だけ。患者様の一覧やほかの画面の情報は、ここからは取れない。
画面の表示・写真の取得・写真の送信のどれも、毎回 QR の文字列と期限を調べる。"""
import html as _html
import io
import secrets
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from app import versioning
from app.db import TODAY, data_dir
from app.mobile import links
from app.views import photos as PH

app = FastAPI(title="スマホの写真", docs_url=None, redoc_url=None, openapi_url=None)
versioning.install(app, mobile=True)

HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}
MAGIC = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a")


def _json(body: dict, status: int = 200):
    return JSONResponse(body, status_code=status, headers=HEADERS)


def _page(text: str, status: int):
    html = ("<!doctype html><html lang='ja'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'><title>写真</title></head>"
            "<body style='font-family:sans-serif;padding:32px;font-size:20px'>" + text + "</body></html>")
    return HTMLResponse(html, status_code=status, headers=HEADERS)


def _check(token: str):
    """(行, エラーの応答)。どちらか一方だけが入る。"""
    state, row = links.lookup(token)
    if state == links.OK:
        return row, None
    if state == links.EXPIRED:
        return None, ("この画面の期限が切れました。パソコンの画面でQRをもう一度出してください。", 410)
    return None, ("このアドレスは使えません。", 404)


def _deny(err, as_json: bool):
    msg, status = err
    return _json({"error": msg}, status) if as_json else _page(msg, status)


def _is_image(raw: bytes) -> bool:
    return raw.startswith(MAGIC) or (raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")


def _store(raw: bytes, patient_id: int) -> str:
    """画像だと確かめて、向きを直し、撮影場所などの付属の情報を捨てて JPEG で保存する。ファイル名を返す。"""
    from PIL import Image, ImageOps

    cfg = links.config()
    img = Image.open(io.BytesIO(raw))
    if img.width * img.height > cfg["max_pixels"]:
        raise ValueError("画像が大きすぎます")
    img.load()
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    d = data_dir() / "photos"
    d.mkdir(parents=True, exist_ok=True)
    name = f"{patient_id}_{secrets.token_hex(8)}.jpg"
    img.save(d / name, "JPEG", quality=92)
    return name


PAGE = """<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>写真</title>
<style>
body{font-family:sans-serif;margin:0;padding:20px;font-size:18px;color:#1c2a33;background:#f4f6f8}
h1{font-size:30px;margin:8px 0 4px}.sub{color:#555;margin:0 0 20px}
button,label.btn{display:block;width:100%;box-sizing:border-box;font-size:24px;font-weight:700;padding:22px 12px;margin:0 0 16px;
border:0;border-radius:14px;background:#1f5fbf;color:#fff;text-align:center}
button.sec{background:#fff;color:#1f5fbf;border:2px solid #1f5fbf}
#msg{min-height:28px;margin:8px 0;font-weight:700}.err{color:#b00020}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:16px}
.cell{position:relative;border:4px solid transparent;border-radius:8px;overflow:hidden;background:#ddd}
.cell.sel{border-color:#1f5fbf}.cell img{width:100%;display:block}
.cell b{position:absolute;left:6px;top:6px;background:rgba(0,0,0,.7);color:#fff;border-radius:12px;padding:0 10px;font-size:18px}
[hidden]{display:none!important}
</style></head><body>
<h1>No. __CHART__</h1><p class="sub">あと __MIN__ 分で使えなくなります</p>
<div id="home">
<label class="btn" for="pick">写真を入れる</label>
<input id="pick" type="file" accept="image/jpeg,image/png,image/webp" multiple hidden>
<button type="button" id="take" class="sec">写真を取り出す</button>
</div>
<div id="out" hidden>
<div id="grid" class="grid"></div>
<button type="button" id="save">選んだ写真を保存</button>
<button type="button" id="back" class="sec">もどる</button>
</div>
<div id="msg"></div>
<script>
(function () {
  var T = location.pathname.split("/")[2];
  var base = "/m/" + T;
  var msg = document.getElementById("msg");
  function say(t, bad) { msg.textContent = t; msg.className = bad ? "err" : ""; }
  function fail(r) { return r.json().then(function (b) { throw new Error(b.error || "送れませんでした"); }, function () { throw new Error("送れませんでした"); }); }
  var sel = {};
  document.getElementById("pick").addEventListener("change", function (e) {
    var files = Array.prototype.slice.call(e.target.files), ok = 0;
    e.target.value = "";
    (function next(i) {
      if (i >= files.length) { say(ok + "枚入れました"); return; }
      say((i + 1) + "/" + files.length + " を送っています…");
      fetch(base + "/upload", { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: files[i] })
        .then(function (r) { if (!r.ok) return fail(r); ok++; next(i + 1); })
        .catch(function (err) { say(err.message, true); });
    })(0);
  });
  function show(on) { document.getElementById("home").hidden = on; document.getElementById("out").hidden = !on; }
  document.getElementById("take").addEventListener("click", function () {
    say("");
    fetch(base + "/photos").then(function (r) { return r.ok ? r.json() : fail(r); }).then(function (d) {
      var g = document.getElementById("grid");
      g.textContent = "";
      sel = {};
      if (!d.photos.length) { say("今日の写真はまだありません"); return; }
      d.photos.forEach(function (n) {
        var c = document.createElement("div");
        c.className = "cell";
        c.innerHTML = '<img alt=""><b></b>';
        c.querySelector("img").src = base + "/photo/" + n;
        c.querySelector("b").textContent = n;
        c.addEventListener("click", function () { sel[n] = !sel[n]; c.classList.toggle("sel", !!sel[n]); });
        g.appendChild(c);
      });
      show(true);
    }).catch(function (err) { say(err.message, true); });
  });
  document.getElementById("back").addEventListener("click", function () { show(false); say(""); });
  document.getElementById("save").addEventListener("click", function () {
    var picked = Object.keys(sel).filter(function (n) { return sel[n]; });
    if (!picked.length) { say("保存する写真を選んでください", true); return; }
    picked.reduce(function (p, n) {
      return p.then(function () {
        return fetch(base + "/photo/" + n + "?dl=1").then(function (r) { return r.ok ? r.blob() : fail(r); }).then(function (b) {
          var f = new File([b], "photo" + n + ".jpg", { type: "image/jpeg" });
          if (navigator.canShare && navigator.canShare({ files: [f] })) return navigator.share({ files: [f] }).catch(function () {});
          var a = document.createElement("a");
          a.href = URL.createObjectURL(b);
          a.download = f.name;
          document.body.appendChild(a);
          a.click();
          a.remove();
        });
      });
    }, Promise.resolve()).then(function () { say(picked.length + "枚を保存しました"); }).catch(function (err) { say(err.message, true); });
  });
})();
</script></body></html>"""


@app.get("/m/version")
def version():
    """画面の版の印（更新ボタン用）。患者様の情報は無い。"""
    return _json(versioning.current())


@app.get("/m/{token}")
def page(token: str):
    row, err = _check(token)
    if err:
        return _deny(err, False)
    import time

    mins = max(1, int((row["expires_at"] - time.time() + 59) // 60))
    html = PAGE.replace("__CHART__", _html.escape(row["chart_no"])).replace("__MIN__", str(mins))
    return HTMLResponse(html, headers=HEADERS)


def _today_numbers(con, patient_id):
    return [r["number"] for r in con.execute(
        "SELECT number FROM photos WHERE patient_id = ? AND taken_on = ? ORDER BY number", (patient_id, TODAY))]


@app.get("/m/{token}/photos")
def photo_list(token: str):
    row, err = _check(token)
    if err:
        return _deny(err, True)
    con = links.db()
    try:
        return _json({"photos": _today_numbers(con, row["patient_id"])})
    finally:
        con.close()


@app.get("/m/{token}/photo/{number}")
def photo(token: str, number: int, dl: int = 0):
    row, err = _check(token)
    if err:
        return _deny(err, True)
    con = links.db()
    try:
        # その患者様の、今日の写真だけ。ほかの患者様の番号・今日でない写真は「無い」と同じ答え
        r = con.execute("SELECT file FROM photos WHERE patient_id = ? AND number = ? AND taken_on = ?",
                        (row["patient_id"], number, TODAY)).fetchone()
        if not r:
            return _json({"error": "写真がありません"}, 404)
        if r["file"]:
            path = data_dir() / "photos" / r["file"]
        else:
            items = PH.listing()
            if not items:
                return _json({"error": "写真がありません"}, 404)
            path = PH.photo_dir() / items[(number - 1) % len(items)]["file"]
        if not path.is_file():
            return _json({"error": "写真がありません"}, 404)
        if dl:
            links.log_event(con, row["id"], row["patient_id"], "取り出した", number)
            con.commit()
        return FileResponse(path, headers=HEADERS)
    finally:
        con.close()


@app.post("/m/{token}/upload")
async def upload(token: str, request: Request):
    row, err = _check(token)
    if err:
        return _deny(err, True)
    cfg = links.config()
    limit = int(cfg["max_bytes"])
    try:
        if int(request.headers.get("content-length") or 0) > limit:
            return _json({"error": "写真が大きすぎます（10MBまで）"}, 413)
    except ValueError:
        return _json({"error": "送り方が正しくありません"}, 400)
    chunks, size = [], 0
    async for part in request.stream():
        size += len(part)
        if size > limit:
            return _json({"error": "写真が大きすぎます（10MBまで）"}, 413)
        chunks.append(part)
    raw = b"".join(chunks)
    if not _is_image(raw):
        return _json({"error": "写真（画像）だけ送れます"}, 415)
    # 送っている間に期限が来ていないかを、もう一度調べる
    row, err = _check(token)
    if err:
        return _deny(err, True)
    con = links.db()
    try:
        sent = con.execute("SELECT COUNT(*) FROM phone_events WHERE link_id = ? AND kind = '入れた'", (row["id"],)).fetchone()[0]
        if sent >= int(cfg["max_files_per_link"]):
            return _json({"error": "この画面で入れられる枚数は上限です。QRをもう一度出してください"}, 429)
        try:
            name = _store(raw, row["patient_id"])
        except Exception:
            return _json({"error": "写真（画像）だけ送れます"}, 415)
        for _ in range(5):
            try:
                con.execute("BEGIN IMMEDIATE")
                n = con.execute("SELECT COALESCE(MAX(number), 0) + 1 FROM photos WHERE patient_id = ?", (row["patient_id"],)).fetchone()[0]
                con.execute("INSERT INTO photos (patient_id, number, taken_on, kind, file) VALUES (?, ?, ?, 'intraoral', ?)",
                            (row["patient_id"], n, TODAY, name))
                links.log_event(con, row["id"], row["patient_id"], "入れた", n)
                con.commit()
                return _json({"ok": True, "number": n})
            except sqlite3.IntegrityError:
                con.rollback()
        return _json({"error": "もう一度送ってください"}, 503)
    finally:
        con.close()
