"""画面の版の印（G21b）。app と config の中で一番新しいファイルの時刻。main に新しい版が入ると必ず変わる。
HTML に ?v=版 を付け、更新ボタンの部品（updater.js）を足し、/static と /config を使い回さないようにする。"""
import re
import time
from datetime import datetime
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

ROOT = Path(__file__).resolve().parent.parent
WATCH = ("app", "config")
EXT = {".py", ".js", ".css", ".json", ".html", ".svg"}
TTL = 1.0  # 秒。毎回ファイルを調べすぎない

_cache = {"at": 0.0, "mtime": 0}

STATIC_RE = re.compile(r"(/static/[^'\"\s>?]+\.(?:js|css))(?=['\"])")


def _scan() -> int:
    top = 0
    for name in WATCH:
        base = ROOT / name
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if "__pycache__" in p.parts or p.suffix not in EXT:
                continue
            try:
                m = int(p.stat().st_mtime)
            except OSError:
                continue
            if m > top:
                top = m
    return top


def current() -> dict:
    """{"v": 版の印, "time": "20:15"}"""
    now = time.monotonic()
    if now - _cache["at"] > TTL or not _cache["mtime"]:
        _cache["mtime"] = _scan()
        _cache["at"] = now
    m = _cache["mtime"]
    return {"v": str(m), "time": datetime.fromtimestamp(m).strftime("%H:%M")}


def _inject(html: str, mobile: bool) -> str:
    ver = current()
    html = STATIC_RE.sub(lambda m: f"{m.group(1)}?v={ver['v']}", html)
    if "</body>" not in html:
        return html
    base = "/m/version" if mobile else "/version"
    boot = f"<script>window.CV_VERSION={ver['v']!r};window.CV_VERSION_URL={base!r};</script>"
    if mobile:  # スマホの画面は /static を持たないので、部品をそのまま中に入れる
        js = (ROOT / "app" / "static" / "js" / "updater.js").read_text(encoding="utf-8")
        tags = boot + "<style>" + MOBILE_CSS + "</style><script>" + js + "</script>"
    else:
        tags = (boot + f"<link rel='stylesheet' href='/static/css/updater.css?v={ver['v']}'>"
                f"<script src='/static/js/updater.js?v={ver['v']}'></script>")
    i = html.rindex("</body>")
    return html[:i] + tags + html[i:]


MOBILE_CSS = (
    "#cv-update{position:fixed;left:0;right:0;bottom:0;width:100%;z-index:2147483600;font:inherit;font-size:24px;font-weight:700;"
    "line-height:1.2;padding:6px 12px;border:0;border-radius:0;background:#d9480f;color:#fff;cursor:pointer;text-align:center}"
    "#cv-update[hidden]{display:none}#cv-update.waiting{opacity:.5}"
    "#cv-updated{position:fixed;top:0;right:0;z-index:2147483600;font-size:14px;font-weight:700;line-height:20px;"
    "padding:0 12px;border-radius:0 0 0 8px;background:#1c2a33;color:#fff}"
)


class VersionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, mobile: bool = False):
        super().__init__(app)
        self.mobile = mobile

    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        path = request.url.path
        if path.startswith("/static/") or path.startswith("/config/"):
            resp.headers["Cache-Control"] = "no-cache"  # 毎回、新しいか確かめてから使う
            return resp
        ctype = resp.headers.get("content-type", "")
        if not ctype.startswith("text/html"):
            return resp
        body = b""
        async for chunk in resp.body_iterator:
            body += chunk
        try:
            text = _inject(body.decode("utf-8"), self.mobile)
        except Exception:
            text = body.decode("utf-8", "replace")
        headers = {k: v for k, v in resp.headers.items() if k.lower() not in ("content-length", "content-type")}
        return Response(text, status_code=resp.status_code, headers=headers, media_type="text/html")


def install(app, mobile: bool = False):
    app.add_middleware(VersionMiddleware, mobile=mobile)
