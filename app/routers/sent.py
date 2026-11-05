"""Claude へ送った文を見る画面 /sent。data/runtime/sent_log を新しい順に出す。伏字にした所に色を付ける。

ログには伏字にした文だけが残るが、念のため、出す前にもう一度伏字にする（元の名前は画面に出さない）。
"""
import html
import json
import re
import sqlite3

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.ai.gateway import sensitive_from_db
from app.ai.redact import NameListUnreadable, RedactionFailed, Sensitive, Table
from app.db import connect, data_dir

router = APIRouter()
h = html.escape
PURPOSES = {"question": "質問", "memo": "下書き（5つに分ける）", "polish": "清書（聞き違いを直す）", "fix": "聞き違いの直し（前の版）"}
PLACEHOLDER = re.compile(r"\[[^\[\]]+\]")  # 伏字は [患者1] のような形（app/ai/redact.py）
MAX_SHOWN = 200


def read_entries(limit: int = MAX_SHOWN) -> list:
    """新しい順。壊れた行は飛ばす。"""
    d = data_dir() / "sent_log"
    out = []
    for f in sorted(d.glob("*.jsonl"), reverse=True) if d.exists() else []:
        for line in reversed(f.read_text(encoding="utf-8", errors="replace").splitlines()):
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict):
                out.append(e)
            if len(out) >= limit:
                return out
    return out


def _mask_again(table, text) -> str:
    try:
        return table.mask(str(text or ""))
    except RedactionFailed:
        return "（表示できません）"


def _show(text: str) -> str:
    """HTML にして、伏字の所に色を付ける。"""
    out, pos = [], 0
    for m in PLACEHOLDER.finditer(text):
        out.append(h(text[pos:m.start()]))
        out.append(f"<mark class='masked'>{h(m.group(0))}</mark>")
        pos = m.end()
    out.append(h(text[pos:]))
    return "".join(out)


@router.get("/sent", response_class=HTMLResponse)
def sent_page(n: int = MAX_SHOWN):
    try:
        con = connect()
        try:
            sens = sensitive_from_db(con)
        finally:
            con.close()
    except (sqlite3.Error, NameListUnreadable):  # 記録の入れ物が無い・名前の一覧が読めないときも、ログは見られる（ログは伏字のまま。表示のときの伏字し直しだけ効かない）
        sens = Sensitive(patients=[], staff=[], clinics=[])
    table = Table(sens)
    entries = read_entries(max(1, min(n, 1000)))
    cards = ""
    for e in entries:
        purpose = str(e.get("purpose") or "")
        cards += (
            f"<article class='sent-item' data-purpose='{h(purpose, quote=True)}'>"
            f"<header><span class='when'>{h(str(e.get('time') or ''))}</span> "
            f"<b class='what'>{h(PURPOSES.get(purpose, purpose or '不明'))}</b></header>"
            f"<h3>送った文</h3><pre class='user'>{_show(_mask_again(table, e.get('user')))}</pre>"
            f"<details><summary>指示文</summary><pre class='system'>{_show(_mask_again(table, e.get('system')))}</pre></details>"
            "</article>")
    if not cards:
        cards = "<p class='none'>まだ Claude へ送った文はありません</p>"
    return HTMLResponse(
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>Claude へ送った文</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'><link rel='stylesheet' href='/static/css/sent.css'></head>"
        "<body class='sent-page' data-page='sent'>"
        "<header class='sent-head'><a class='back' href='/'>戻る</a><span>Claude へ送った文（新しい順）</span></header>"
        "<main class='sent-main' data-part='sent-log'>"
        "<p class='sent-note'>名前・カルテ番号・生年月日などは伏せ字にして送っています。<mark class='masked'>色が付いた所</mark>が伏字です。元の名前はここにも出しません。</p>"
        f"{cards}</main><script src='/static/js/actions/look.js'></script></body></html>",
        headers={"Cache-Control": "no-store"})
