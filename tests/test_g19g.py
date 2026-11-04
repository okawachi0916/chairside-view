"""G19g: 下書きの画面のボタンを、全部声で押せる（番号の札・言葉・敬語・使えない言葉の案内）。偽物の口。"""
from pathlib import Path

import pytest

from tests.screen_helper import browser, server  # noqa: F401
from tests.test_confirm_screen import clean, db_one, home, make_rec, open_draft, ready  # noqa: F401


def numbers(pg):
    """出ている札 { 番号: 印 }。"""
    pg.evaluate("window.cvNumbers(true)")
    return pg.evaluate("Object.fromEntries([...document.querySelectorAll('.num-badge')].map(b => [b.dataset.n, b.dataset.key]))")


def say_number(pg, n, word=None):
    """番号を出してから、番号の言葉を送る（声の受付のあと、と同じ手順）。"""
    pg.evaluate("window.cvNumbers(true)")
    return pg.evaluate("t => window.cvTyped(t)", word or f"{n}番")


def open_ready(browser, server, s, **kw):  # noqa: F811
    pg, _ = open_draft(browser, server, s["draft_id"], **kw)
    ready(pg)
    return pg


def test_button2_shows_numbers_on_every_button(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    m = numbers(pg)
    keys = list(m.values())
    assert keys[0] == "confirm" and keys[1] == "later" and keys[-1] == "back"  # 戻るは最後の番号
    assert [k for k in keys if k.startswith("del:")], "各行の消すに番号が出る"
    assert [k for k in keys if k.startswith("plan:")], "計画の削除するに番号が出る"
    assert [int(n) for n in m] == list(range(1, len(m) + 1))
    # 消すの数 = 行の数（画面に見えている分）、削除するの数 = 今の計画の数
    assert len([k for k in keys if k.startswith("del:")]) == pg.locator(".draft-sec li.row .del").count()
    assert len([k for k in keys if k.startswith("plan:")]) == pg.locator("#plan-rows input[data-key^=d]").count()
    assert pg.evaluate("document.body.dataset.numHidden") == "0"  # 画面の外で番号が付かないボタンは無い
    # 暗い幕が出る
    assert pg.locator("#num-dim").count() == 1
    pg.screenshot(path=str(Path(__file__).resolve().parents[1] / "docs" / "画面" / "G19g.png"))
    pg.evaluate("window.cvNumbers(false)")
    assert pg.locator(".num-badge").count() == 0
    pg.close()


def test_number_one_records_like_the_mouse(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s, back="/recordings")
    say_number(pg, 1)
    pg.wait_for_url(home(server))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "確定"
    pg.close()


def test_number_two_is_later(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s, back="/recordings")
    say_number(pg, 2, "2")
    pg.wait_for_url(home(server))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "後で直す"
    pg.close()


def test_number_deletes_a_row_from_the_top(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    before = pg.locator(".draft-sec li.row").count()
    m = numbers(pg)
    n = next(k for k, v in m.items() if v == "del:1")
    assert n == "3"  # 記録する・あとで直すの次が、上から1つ目の消す
    pg.evaluate("t => window.cvTyped(t)", f"{n}番")
    assert pg.locator(".draft-sec li.row").count() == before - 1
    pg.close()


def test_number_toggles_plan_delete_mark(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    box = pg.locator("#plan-rows input[data-key^=d]").first
    assert not box.is_checked()
    m = numbers(pg)
    n = next(k for k, v in m.items() if v == "plan:1")
    pg.evaluate("t => window.cvTyped(t)", f"{n}番")
    assert box.is_checked()
    # もう一度選ぶと外れる
    m = numbers(pg)
    n = next(k for k, v in m.items() if v == "plan:1")
    pg.evaluate("t => window.cvTyped(t)", f"{n}番")
    assert not pg.locator("#plan-rows input[data-key^=d]").first.is_checked()
    pg.close()


def test_last_number_is_back(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s, back="/today")
    m = numbers(pg)
    n = max(int(k) for k in m)
    assert m[str(n)] == "back"
    pg.evaluate("t => window.cvTyped(t)", f"{n}番")
    pg.wait_for_url(home(server, "/today"))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    pg.close()


def test_reorganize_button_gets_a_number_only_from_the_fix_screen(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    assert "reorg" not in numbers(pg).values()
    pg.close()
    pg = open_ready(browser, server, s, fix=True)
    m = numbers(pg)
    keys = list(m.values())
    assert "reorg" in keys and keys[-1] == "back" and keys.index("reorg") == len(keys) - 2
    pg.close()


def test_number_not_shown_or_wrong(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    pg.evaluate("window.cvTyped('3番')")  # 札を出していないとき
    assert "番号は出ていません" in pg.inner_text("#msg")
    pg.evaluate("window.cvNumbers(true)")
    pg.evaluate("window.cvTyped('99番')")
    assert "その番号はありません" in pg.inner_text("#msg")
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    pg.close()


@pytest.mark.parametrize("first,second", [("カルテに記録する", "記録"), ("カルテに記録して", "記録"), ("カルテに記録してください", "確定"),
                                          ("カルテに記録してください。", "記録"), ("確定する", "確定")])
def test_word_record_needs_two_times(server, browser, first, second):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    assert pg.evaluate("t => window.cvTyped(t)", second) == "need-first"  # いきなりは記録しない
    assert "先に「カルテに記録する」" in pg.inner_text("#msg")
    assert pg.evaluate("t => window.cvTyped(t)", first) == "armed"
    assert "もう一度「記録」と言ってください" in pg.inner_text("#msg")
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"  # 1回目だけでは記録されない
    pg.evaluate("t => window.cvTyped(t)", second)
    pg.wait_for_url(home(server))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"
    pg.close()


@pytest.mark.parametrize("word", ["あとで直す", "後で直す", "あとで直してください", "後で直してください。"])
def test_word_later(server, browser, word):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    assert pg.evaluate("t => window.cvTyped(t)", word) == "later"
    pg.wait_for_url(home(server))
    assert db_one("SELECT state FROM recordings WHERE id = ?", s["id"])[0] == "後で直す"
    pg.close()


@pytest.mark.parametrize("word", ["戻して", "戻る", "戻してください", "戻ってください"])
def test_word_back(server, browser, word):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    assert pg.evaluate("t => window.cvTyped(t)", word) == "back"
    pg.wait_for_url(home(server))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    pg.close()


def test_unusable_word_says_what_to_do_next(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    pg.evaluate("window.cvTyped('見せて')")
    msg = pg.inner_text("#msg")
    assert "「見せて」は使えません" in msg and "ボタン2で番号を出して選べます" in msg
    # 前の「使えません」の言い方で、記録や戻るが動かないこと
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "draft"
    pg.close()


def test_old_word_confirm_still_works_alone_after_arming(server, browser):  # noqa: F811
    s = make_rec(server)
    pg = open_ready(browser, server, s)
    pg.evaluate("window.cvTyped('確定する')")
    pg.evaluate("window.cvTyped('確定')")
    pg.wait_for_url(home(server))
    assert db_one("SELECT status FROM drafts WHERE id = ?", s["draft_id"])[0] == "confirmed"
    pg.close()
