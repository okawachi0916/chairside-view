"""写真の欄の「スマホ」ボタン。QR を作る・入れた写真を見せる（メインの画面側）。
スマホから開く側は別のポートの小さなサーバー app/mobile/server.py。ここでは起動だけ受け持つ。"""
import io
import os
import re
import threading
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from app import errlog
from app.db import data_dir
from app.mobile import links

router = APIRouter()
mobile_status = {"error": ""}  # 起動に失敗したときの理由。空なら問題なし
NAME_RE = re.compile(r"^[0-9]+_[0-9a-f]{16}\.jpg$")


class LinkIn(BaseModel):
    appt: int


def _qr_svg(url: str) -> str:
    import segno

    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=1, border=2, xmldecl=False, svgns=True, nl=False, omitsize=True,
                                    dark="#000000", light="#ffffff")
    return buf.getvalue().decode("utf-8")


@router.post("/api/phone-link")
def make_link(body: LinkIn):
    """今開いている患者様のQRを作る。有効期限は10分。氏名は返さない。"""
    con = links.db()
    try:
        r = con.execute("SELECT a.patient_id, p.chart_no FROM appointments a JOIN patients p ON p.id = a.patient_id WHERE a.id = ?",
                        (body.appt,)).fetchone()
    finally:
        con.close()
    if not r:
        raise HTTPException(404, "予約がありません")
    if mobile_status["error"]:
        raise HTTPException(503, "スマホ用の受け口が動いていません。院内の担当者にお知らせください")
    token, expires = links.create_link(r["patient_id"])
    url = links.link_url(token)
    return JSONResponse({"svg": _qr_svg(url), "url": url, "chart_no": r["chart_no"], "expires_at": expires,
                         "seconds_left": max(0, expires - int(time.time()))}, headers={"Cache-Control": "no-store"})


@router.get("/api/phone-photos/count")
def photo_count(appt: int):
    """この患者様の写真の枚数。スマホから入れた写真を、画面が気づくために使う。"""
    con = links.db()
    try:
        r = con.execute("SELECT COUNT(*) AS n FROM photos WHERE patient_id = (SELECT patient_id FROM appointments WHERE id = ?)",
                        (appt,)).fetchone()
    finally:
        con.close()
    return JSONResponse({"count": r["n"]}, headers={"Cache-Control": "no-store"})


@router.get("/photo-up/{name}")
def uploaded_photo(name: str):
    """スマホから入れた写真。データベースに載っている名前だけ返す。"""
    if not NAME_RE.match(name):
        raise HTTPException(404)
    con = links.db()
    try:
        ok = con.execute("SELECT 1 FROM photos WHERE file = ?", (name,)).fetchone()
    finally:
        con.close()
    path = data_dir() / "photos" / name
    if not ok or not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "no-store"})


def start_mobile_server():
    """スマホ用のサーバーを、別のポートで裏から動かす。ポートが使えなくてもメインは止めない。"""
    if os.environ.get("CV_MOBILE_AUTOSTART") == "0":
        return None
    try:
        import uvicorn

        from app.mobile.server import app as mobile_app

        server = uvicorn.Server(uvicorn.Config(mobile_app, host="0.0.0.0", port=links.mobile_port(), log_level="warning"))

        def run():
            try:
                server.run()
                if not server.started:  # ポートが使えないときは、例外でなく終了で返ってくる
                    raise OSError(f"ポート {links.mobile_port()} で待ち受けられません")
            except BaseException as e:  # noqa: BLE001  SystemExit も含めて、止まった理由を残す
                mobile_status["error"] = f"{type(e).__name__}: {str(e)[:80]}"
                errlog.record("スマホ用サーバー", "スマホ用の受け口が起動できませんでした（メインは続けます）", e)

        t = threading.Thread(target=run, name="mobile-server", daemon=True)
        t.start()
        return server
    except Exception as e:  # noqa: BLE001  メインは止めない。理由は記録に残し、QR を出すときに画面に出す
        mobile_status["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        errlog.record("スマホ用サーバー", "スマホ用の受け口を準備できませんでした（メインは続けます）", e)
        return None


_mobile = start_mobile_server()
