"""入口の画面。作品を開いたときに最初に出る。受付モード（マウスだけ）と臨床モード（声とボタン）に分ける。
文言は院長が決めたとおり（G21n）。言い回しを変えない。見た目は G21p（白いカード、上だけ色の帯）。
括弧（「」や（））は文の一部として残し、見た目では札に置き換える（.paren。読み上げと写しでは元の文のまま）。"""
from app.today import today as app_today
from app.views import data as D


def _paren(ch):
    return f'<span class="paren">{ch}</span>'


def _tag(text, kind):
    return f'<span class="tag tag-{kind}">{text}</span>'


def _chip(text, role):
    return f'<span class="chip chip-{role}">{text}</span>'


def _row(label, inner, cls):
    return f'<div class="door-row"><dt>{label}</dt><dd class="{cls}">{inner}</dd></div>'


def _door(kind, href, title, sub, ops, see, note, go):
    return (
        f'<a class="door door-{kind}" data-part="door-{kind}" href="{href}">'
        f'<div class="door-head"><h2>{title}</h2><p class="door-sub">{sub}</p></div>'
        '<div class="door-body"><dl>'
        + _row("操作", ops, "door-ops")
        + _row("見るもの", see, "door-see")
        + f'</dl><p class="door-note">{note}</p><span class="door-go">{go}</span></div></a>'
    )


def entrance_page():
    reception = _door(
        "reception", "/reception", "受付モード", "受付の端末で使う",
        _tag("マウスだけ", "reception") + _paren("（") + _tag("声は使わない", "plain") + _paren("）"),
        "次回の予約・来院しやすい曜日・キャンセル傾向・受付メモ・過去の処方",
        "キャンセル傾向など、患者様の前に出さない情報を含むため、ユニットの画面からは切り替えません。",
        "受付用の患者様一覧へ　→",
    )
    clinic = _door(
        "clinic", "/clinic", "臨床モード", "ユニットで使う　歯科医師・歯科衛生士",
        _tag("手袋のまま", "clinic") + _paren("（") + _tag("声と3つのボタン", "clinic") + _paren("）"),
        "重要事項・今日の処置・写真・歯周検査。話した内容を記録する",
        _paren("「") + _chip("歯科医師", "doctor") + _paren("」") + _paren("「") + _chip("歯科衛生士", "hygienist")
        + _paren("」") + "の切り替えは臨床モードの中で行います。",
        "今日の予約一覧へ　→",
    )
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>チェアサイドビュー</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'>"
        "<link rel='stylesheet' href='/static/css/entrance.css'></head><body class='entrance' data-page='entrance'>"
        f'<header class="e-bar"><span class="e-date">{D.ja_date(app_today(), week=True)}</span></header>'
        '<main class="entrance-main"><h1>チェアサイドビュー</h1><p class="e-en">CHAIRSIDE VIEW</p>'
        f'<div class="doors">{reception}{clinic}</div></main></body></html>'
    )
