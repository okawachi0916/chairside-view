from app.mockview.parts import DATE

ROWS = [
    ("14:30〜15:30", "0123", "見本 花子", "RCT"),
    ("14:30〜15:00", "0456", "見本 一郎", "SPT"),
    ("14:30〜15:00", "0789", "見本 太郎", "義歯調整"),
    ("15:00〜15:30", "1024", "見本 和子", "CR"),
    ("15:30〜16:00", "0123", "見本 花子", "SPT"),
    ("15:30〜16:00", "2048", "見本 美咲", "インレー"),
]
MASK = "●● ●●"


def render():
    body = ""
    for time, no, name, proc in ROWS:
        # 見本なので、どの患者様を押しても花子様の画面が開く
        href = "/mock/hygienist" if proc == "SPT" else "/mock/doctor"
        body += (
            f'<tr class="row" tabindex="0" role="link" data-href="{href}" data-proc="{proc}">'
            f'<td class="time">{time}</td><td class="no">{no}</td>'
            f'<td class="name"><span class="nm" data-name="{name}">{MASK}</span>'
            '<button type="button" class="mini reveal" data-action="reveal">表示</button></td>'
            f'<td class="proc">{proc}</td></tr>'
        )
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>予約一覧（見本）</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'>"
        "<link rel='stylesheet' href='/static/css/booklist.css'></head><body class='role-list'>"
        f'<header class="topbar"><span class="role-tag">予約一覧</span><span class="date">{DATE}</span></header>'
        '<main class="list" data-part="appointment-list"><table class="book">'
        "<thead><tr><th>時間</th><th>カルテ番号</th><th>氏名 "
        '<button type="button" class="mini" data-action="reveal-all">すべて表示</button></th>'
        f"<th>処置</th></tr></thead><tbody>{body}</tbody></table></main>"
        "<script src='/static/js/mock_nav.js'></script></body></html>"
    )
