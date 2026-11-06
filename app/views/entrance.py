"""入口の画面。作品を開いたときに最初に出る。受付モード（マウスだけ）と臨床モード（声とボタン）に分ける。
文言は院長が決めたとおり（G21n）。言い回しを変えない。"""
from app.today import today as app_today
from app.views import data as D


def _row(label, text):
    return f'<div class="door-row"><dt>{label}</dt><dd>{text}</dd></div>'


def entrance_page():
    reception = (
        '<a class="door door-reception" data-part="door-reception" href="/reception">'
        '<h2>受付モード</h2><p class="door-sub">受付の端末で使う</p><dl>'
        + _row("操作", "マウスだけ（声は使わない）")
        + _row("見るもの", "次回の予約・来院しやすい曜日・キャンセル傾向・受付メモ・過去の処方")
        + "</dl>"
        '<p class="door-note">キャンセル傾向など、患者様の前に出さない情報を含むため、ユニットの画面からは切り替えません。</p>'
        '<span class="door-go">受付用の患者様一覧へ　→</span></a>'
    )
    clinic = (
        '<a class="door door-clinic" data-part="door-clinic" href="/clinic">'
        '<h2>臨床モード</h2><p class="door-sub">ユニットで使う　歯科医師・歯科衛生士</p><dl>'
        + _row("操作", "手袋のまま（声と3つのボタン）")
        + _row("見るもの", "重要事項・今日の処置・写真・歯周検査。話した内容を記録する")
        + "</dl>"
        '<p class="door-note">「<span class="chip chip-doctor">歯科医師</span>」「<span class="chip chip-hygienist">歯科衛生士</span>」'
        "の切り替えは臨床モードの中で行います。</p>"
        '<span class="door-go">今日の予約一覧へ　→</span></a>'
    )
    return (
        "<!doctype html><html lang='ja'><head><meta charset='utf-8'><title>チェアサイドビュー</title>"
        "<link rel='stylesheet' href='/static/css/mock.css'>"
        "<link rel='stylesheet' href='/static/css/entrance.css'></head><body class='entrance' data-page='entrance'>"
        f'<main class="entrance-main"><p class="e-date">{D.ja_date(app_today(), week=True)}</p>'
        '<h1>チェアサイドビュー</h1><p class="e-en">CHAIRSIDE VIEW</p>'
        f'<div class="doors">{reception}{clinic}</div></main></body></html>'
    )
