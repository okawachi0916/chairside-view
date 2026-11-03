"""QR の中の長い文字列（トークン）と、患者様・期限の結び付け。画面・取得・送信の全部で毎回ここで調べる。
トークンそのものは保存せず、sha256 の値だけをデータベースに置く。"""
import hashlib
import json
import os
import re
import secrets
import socket
import time
from pathlib import Path

from app.db import connect
from app.views import data as D

ROOT = Path(__file__).resolve().parents[2]


def db(path=None):
    """データベース。無ければ作り、古ければ足りない分を足してから開く。"""
    return connect(path) if path else D.con()


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{40,64}$")

OK, EXPIRED, NONE = "ok", "expired", "none"


def config() -> dict:
    return json.loads((ROOT / "config" / "mobile.json").read_text(encoding="utf-8"))


def mobile_port() -> int:
    try:
        return int(os.environ.get("CV_MOBILE_PORT") or config()["default_port"])
    except ValueError:
        return int(config()["default_port"])


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)  # 43 文字、256 ビットの乱数


def now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def create_link(patient_id: int, ttl: int | None = None, now: float | None = None, path=None):
    """(トークン, 期限の秒) を返す。期限は作ってから ttl 秒（既定 config の 600 秒 = 10 分）。"""
    now = int(now if now is not None else time.time())
    ttl = int(ttl if ttl is not None else config()["ttl_seconds"])
    token = new_token()
    con = db(path)
    try:
        con.execute("DELETE FROM phone_links WHERE expires_at < ?", (now - 86400,))  # 古い物は1日たったら捨てる
        con.execute("INSERT INTO phone_links (patient_id, token_hash, created_at, expires_at) VALUES (?, ?, ?, ?)",
                    (patient_id, hash_token(token), now, now + ttl))
        con.commit()
    finally:
        con.close()
    return token, now + ttl


def lookup(token: str, now: float | None = None, path=None):
    """(状態, 行) を返す。状態は ok / expired / none。ok のときだけ行（link id、患者様、期限）が入る。"""
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        return NONE, None
    now = time.time() if now is None else now
    con = db(path)
    try:
        row = con.execute(
            "SELECT l.id, l.patient_id, l.expires_at, p.chart_no FROM phone_links l JOIN patients p ON p.id = l.patient_id "
            "WHERE l.token_hash = ?", (hash_token(token),)).fetchone()
    finally:
        con.close()
    if not row:
        return NONE, None
    if now >= row["expires_at"]:
        return EXPIRED, None
    return OK, dict(row)


def log_event(con, link_id: int, patient_id: int, kind: str, number: int | None = None):
    con.execute("INSERT INTO phone_events (link_id, patient_id, kind, photo_number, at) VALUES (?, ?, ?, ?, ?)",
                (link_id, patient_id, kind, number, now_text()))


def lan_ip() -> str:
    """院内のこのパソコンのアドレス（スマホから届く側）。取れないときは localhost。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # 送信はしない。使う側の口を調べるだけ
            return s.getsockname()[0]
    except OSError:
        return "localhost"


def public_base() -> str:
    """QR に入れるアドレスの頭。public_url.txt があればそれ、無ければ院内のアドレス。"""
    f = os.environ.get("CV_PUBLIC_URL_FILE") or config().get("public_url_file") or ""
    try:
        text = Path(f).read_text(encoding="utf-8").strip().splitlines()[0].strip() if f else ""
    except (OSError, IndexError):
        text = ""
    if re.fullmatch(r"https?://[A-Za-z0-9._:\-\[\]]+(/[A-Za-z0-9._~\-/]*)?", text):
        return text.rstrip("/")
    return f"http://{lan_ip()}:{mobile_port()}"


def link_url(token: str) -> str:
    return f"{public_base()}/m/{token}"
