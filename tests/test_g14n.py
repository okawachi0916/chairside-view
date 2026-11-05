"""G14n: 声で呼ぶ番号は 5 と 8 を飛ばす（音楽の中で聞き取れないため）。決まりは1か所（app/numbering.py と numrule.js）。"""
import json

import pytest

from app import numbering as N
from app.views import data as D
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401
from tests.test_confirm_screen import clean, make_rec, open_draft, ready  # noqa: F401

APPT = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
UNIT = f"/unit?appt={APPT}&role=doctor&typed=1&hide=1"
HYG = f"/unit?appt={APPT}&role=hygienist&typed=1&hide=1"


def open_unit(browser, server, path=UNIT):  # noqa: F811
    pg = open_page(browser, server, path)
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("!!(window.cvTyped && window.cvNumbers && window.CVNumRule)")
    pg.wait_for_function("document.body.dataset.numbersReady")
    return pg


def badge_numbers(pg):
    pg.evaluate("window.cvNumbers(true)")
    return pg.evaluate("[...document.querySelectorAll('.num-badge')].map(b => Number(b.dataset.n))")


def say(pg, word):
    pg.evaluate("window.cvNumbers(true)")
    pg.evaluate("w => window.cvTyped(w)", word)


# ---- 決まり（Python）----
def test_rule_order_and_round_trip():
    seq = [N.label(i) for i in range(1, 21)]
    assert seq[:12] == [1, 2, 3, 4, 6, 7, 9, 10, 11, 12, 13, 14]
    assert 5 not in seq and 8 not in seq and 15 in seq and 18 in seq  # 飛ばすのは 5 と 8 の2つだけ
    for i in range(1, 400):
        assert N.seq_of(N.label(i)) == i
    assert N.seq_of(5) is None and N.seq_of(8) is None and N.seq_of(0) is None and N.seq_of("x") is None


# ---- 決まり（JS）は Python と同じ答え ----
def test_js_rule_matches_python(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    js = pg.evaluate("[...Array(300).keys()].map(i => [i + 1, CVNumRule.label(i + 1), CVNumRule.seqOf(i + 1)])")
    for seq, lab, back in js:
        assert lab == N.label(seq), seq
        assert back == N.seq_of(seq), seq
    pg.close()


# ---- 画面のボタンの番号 ----
EXPECT = {"important": 1, "medical-history": 2, "today-treatment": 3, "treatment-history": 4, "intraoral-photos": 6,
          "spoken-summary": 7, "perio-exam": 9, "say-list": 10, "change-role": 11, "phone": 12}


@pytest.mark.parametrize("path", [UNIT, HYG])
def test_normal_screen_badges_skip_5_and_8(server, browser, path):  # noqa: F811
    pg = open_unit(browser, server, path)
    cfg = pg.evaluate("fetch('/voice/numbers').then(r => r.json())")["parts"]
    assert cfg == EXPECT
    pg.evaluate("window.cvNumbers(true)")
    got = pg.evaluate("Object.fromEntries([...document.querySelectorAll('.num-badge')].map(b => [b.dataset.key, Number(b.dataset.n)]))")
    assert got and all(EXPECT[k] == n for k, n in got.items())
    assert not ({5, 8} & set(got.values()))
    pg.close()


def test_say_list_numbers_match_the_screen():
    ex = json.loads((ROOT / "config" / "examples.json").read_text(encoding="utf-8"))
    words = ex["say_list"][0]["words"]
    names = {"重要事項": "important", "全身既往・服薬": "medical-history", "今日の処置": "today-treatment", "治療歴": "treatment-history",
             "写真": "intraoral-photos", "話した内容の整理": "spoken-summary", "歯周基本検査": "perio-exam", "言える言葉": "say-list",
             "役割を変える": "change-role", "スマホで写真をやり取り": "phone"}
    got = {}
    for w in words:
        n, name = w.split("番 ")
        got[names[name]] = int(n)
    assert got == EXPECT


def test_voice_numbers_follow_the_badges(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, "4番")
    pg.wait_for_selector('[data-fs-panel="treatment-history"]')
    pg.evaluate("window.cvTyped('戻して')")
    pg.wait_for_selector(".fs-panel", state="detached")
    say(pg, "6番")  # 6 = 写真
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    pg.evaluate("window.cvTyped('戻して')")
    pg.wait_for_selector(".fs-panel", state="detached")
    say(pg, "7番")  # 7 = 話した内容の整理
    pg.wait_for_selector('[data-fs-panel="spoken-summary"]')
    pg.evaluate("window.cvTyped('戻して')")
    pg.wait_for_selector(".fs-panel", state="detached")
    pg.close()


@pytest.mark.parametrize("word", ["5番", "8番", "ごばん", "はちばん", "5番を開いて", "8番を拡大して"])
def test_5_and_8_open_nothing(server, browser, word):  # noqa: F811
    pg = open_unit(browser, server)
    say(pg, word)
    pg.wait_for_timeout(300)
    assert pg.locator(".fs-panel").count() == 0 and pg.locator("#phone-modal").count() == 0
    assert "その番号はありません" in pg.inner_text("#heard") or "その番号" in pg.evaluate("document.body.innerText")
    pg.close()


# ---- 写真 ----
def photo_labels(pg):
    return pg.evaluate("[...document.querySelectorAll('[data-fs-panel=\"intraoral-photos\"] .fs-item')].map(e => Number(e.dataset.n))")


def test_photo_tiles_and_voice_use_the_rule(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    tiles = pg.evaluate("[...document.querySelectorAll('[data-part=\"intraoral-photos\"] .ph')].map(e => [Number(e.dataset.n), e.querySelector('.no').textContent])")
    assert tiles and all(str(n) == t for n, t in tiles) and not ({5, 8} & {n for n, _ in tiles})
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"] .fs-item')
    labels = sorted(photo_labels(pg))
    assert labels == [N.label(i) for i in range(1, 18)]  # 花子様の写真は通し番号 1〜17
    assert labels[:8] == [1, 2, 3, 4, 6, 7, 9, 10]
    shown = pg.evaluate("[...document.querySelectorAll('.fs-item .no')].map(e => Number(e.textContent))")
    assert sorted(shown) == labels
    # 「写真の10番」は札が10の写真（通し番号 8）
    pg.evaluate("window.cvTyped('写真の10番を拡大して')")
    pg.wait_for_function("document.querySelector('.fs-fig img')")
    assert pg.evaluate("document.querySelector('.fs-fig').dataset.n") == "10"
    assert pg.evaluate("document.querySelector('.fs-fig img').getAttribute('src')") == "/photo-files/photo08.jpg"
    assert "写真 10" in pg.inner_text(".fs-fig figcaption")
    # 1番と3番を並べて
    pg.evaluate("window.cvTyped('1番と3番を並べて')")
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length === 2")
    # 5番・8番は何も変えない
    for w in ["写真の5番を拡大して", "写真の8番を拡大して", "5番と8番を並べて"]:
        pg.evaluate("w => window.cvTyped(w)", w)
        assert pg.evaluate("[...document.querySelectorAll('.fs-fig')].map(f => f.dataset.n)") == ["1", "3"], w
    # 開き直しの印（ph）も札の番号
    assert pg.evaluate("CVReturn.here()").endswith("&ph=1,3") or "ph=1,3" in pg.evaluate("CVReturn.here()")
    pg.close()


def test_photo_open_from_outside_uses_label(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.cvTyped('写真の6番を拡大して')")  # 札6 = 通し番号5 = photo05
    pg.wait_for_function("document.querySelector('.fs-fig img')")
    assert pg.evaluate("document.querySelector('.fs-fig img').getAttribute('src')") == "/photo-files/photo05.jpg"
    pg.close()


# ---- 話した内容の整理・QR・下書き ----
def test_phone_modal_close_badge(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.evaluate("window.CVActions.run('phone-open')")
    pg.wait_for_selector("#phone-modal")
    nums = badge_numbers(pg)
    assert nums and not ({5, 8} & set(nums)) and nums[0] == 1
    pg.close()


def test_draft_badges_use_the_rule(server, browser):  # noqa: F811
    s = make_rec(server)
    pg, _ = open_draft(browser, server, s["draft_id"])
    ready(pg)
    nums = badge_numbers(pg)
    assert len(nums) >= 6, nums  # 記録する・あとで直す・消す…・整理し直す・戻る
    assert nums == [N.label(i) for i in range(1, len(nums) + 1)]
    assert not ({5, 8} & set(nums))
    pg.close()


def test_spoken_summary_badges_use_the_rule(server, browser):  # noqa: F811
    pg = open_unit(browser, server)
    pg.click('[data-part="spoken-summary"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="spoken-summary"]')
    nums = badge_numbers(pg)
    assert nums == [N.label(i) for i in range(1, len(nums) + 1)] and not ({5, 8} & set(nums))
    pg.close()


def test_hygienist_9_is_perio(server, browser):  # noqa: F811
    pg = open_unit(browser, server, HYG)
    say(pg, "9番")
    pg.wait_for_selector('[data-fs-panel="perio-exam"]')
    pg.close()
