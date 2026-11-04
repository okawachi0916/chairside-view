"""G14l: 話した内容の整理でもボタン2で番号を出して声で選ぶ／敬語でも動く／写真は番号だけで拡大。Claude は使わない。"""
from datetime import datetime

import pytest

from app.ai import recpipe
from app.views import data as D
from tests.screen_helper import browser, open_page, server  # noqa: F401

APPT = [r for r in D.today_list() if r["patient_id"] == 1][0]["id"]
UNIT = f"/unit?appt={APPT}&role=doctor&typed=1&hide=1"
SEL = '[data-fs-panel="spoken-summary"]'


@pytest.fixture
def segs():
    """今日の、まだ要約していない区切りを3つ入れる（終わったら消す）。"""
    c = D.con()
    pid, vid = recpipe.visit_for(c, APPT)
    ids = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for i in range(3):
        n = c.execute("SELECT COALESCE(MAX(rec_no), 0) + 1 FROM recordings").fetchone()[0]
        cur = c.execute("INSERT INTO recordings (rec_no, started_at, patient_id, visit_id, state, transcript, role, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (n, now, pid, vid, "文字起こし済み", f"試験の区切り{i}です。", "doctor", now))
        ids.append(cur.lastrowid)
    c.commit()
    yield ids
    c = D.con()
    c.execute(f"DELETE FROM recordings WHERE id IN ({','.join('?' * len(ids))})", ids)
    c.commit()


def open_panel(browser, server):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped && document.body.dataset.numbersReady)")
    pg.click('[data-part="spoken-summary"] [data-action="fullscreen"]')
    pg.wait_for_selector(SEL)
    pg.wait_for_timeout(300)
    return pg


def badge_map(pg):
    return pg.evaluate("Object.fromEntries(Array.from(document.querySelectorAll('.num-badge')).map(b => [b.dataset.n, b.dataset.key]))")


def kind_of(key):
    return "close" if "fs-close" in key else key.split('data-seg="')[1].split('"')[0]


def test_every_button_gets_a_number_and_bright_hole(server, browser, segs):  # noqa: F811
    pg = open_panel(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    m = badge_map(pg)
    kinds = [kind_of(m[str(i)]) for i in range(1, len(m) + 1)]
    assert kinds == ["combine", "delete", "delete", "delete", "close"]  # もとに戻すは最後
    for n, key in m.items():  # 札はボタンに重ならず、穴はボタンの所にある
        btn = pg.locator(key[4:]).bounding_box()
        b = pg.locator(f'.num-badge[data-n="{n}"]').bounding_box()
        assert not (b["x"] < btn["x"] + btn["width"] and b["x"] + b["width"] > btn["x"] and b["y"] < btn["y"] + btn["height"] and b["y"] + b["height"] > btn["y"])
    clip = pg.locator("#num-dim").evaluate("e => e.style.clipPath")
    assert clip.count("Z") == len(m) + 1
    pg.close()


def test_voice_number_does_the_same_as_clicking(server, browser, segs):  # noqa: F811
    pg = open_panel(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    key = badge_map(pg)["2"]
    assert kind_of(key) == "delete"
    rid = key.split('data-id="')[1].split('"')[0]
    pg.evaluate("window.cvTyped('2番')")
    pg.wait_for_selector(f'{SEL} .seg-gone[data-seg-id="{rid}"]')  # マウスで押したときと同じく「消しました」と元に戻す
    assert pg.locator(f'{SEL} .seg-gone [data-seg="undelete"][data-id="{rid}"]').count() == 1
    pg.close()


def test_number_for_close_returns(server, browser, segs):  # noqa: F811
    pg = open_panel(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    last = max(int(n) for n in badge_map(pg))
    pg.evaluate("n => window.cvTyped(n + '番')", last)
    pg.wait_for_function("!document.querySelector('.fs-panel')")
    pg.close()


def test_more_than_ten_buttons_are_numbered_and_selectable(server, browser):  # noqa: F811
    pg = open_panel(browser, server)
    # 区切りが多い画面を、本物と同じ部品で作る
    pg.evaluate("""() => {
      const list = document.querySelector('%s .fs-scroll') || document.querySelector('%s');
      window.__clicked = [];
      document.addEventListener('click', e => { const b = e.target.closest('[data-x]'); if (b) window.__clicked.push(b.dataset.x); }, true);
      const box = document.createElement('div');
      box.id = 'many';
      for (let i = 1; i <= 12; i++) {
        const b = document.createElement('button'); b.type = 'button';
        b.setAttribute('data-seg', 'delete'); b.setAttribute('data-id', String(9000 + i)); b.dataset.x = 'del' + i;
        b.style.cssText = 'display:block;margin:2px'; b.textContent = 'この区切りを消す';
        box.appendChild(b);
      }
      list.prepend(box);
    }""" % (SEL, SEL))
    pg.evaluate("window.cvNumbers(true)")
    m = badge_map(pg)
    assert len(m) >= 11 and max(int(n) for n in m) > 10
    pg.evaluate("window.cvTyped('11番')")  # 10を超えても選べる
    pg.wait_for_function("window.__clicked.length >= 1")
    assert pg.evaluate("window.__clicked")[0].startswith("del")
    pg.close()


def test_numbers_hidden_again_by_button2_state(server, browser, segs):  # noqa: F811
    pg = open_panel(browser, server)
    pg.evaluate("window.cvNumbers(true)")
    assert pg.locator(".num-badge").count() == 5
    pg.evaluate("window.cvNumbers(false)")
    assert pg.locator(".num-badge, #num-dim").count() == 0
    pg.close()


# ---------- 敬語でも今の言葉と同じ動き ----------
from app.ai import quick  # noqa: E402
from app.voice.interpret import interpret  # noqa: E402


def same(polite, plain):
    a, b = interpret(polite), interpret(plain)
    assert a["kind"] == b["kind"] == "操作", polite
    assert (a["action"], a.get("arg"), a.get("numbers")) == (b["action"], b.get("arg"), b.get("numbers")), polite


@pytest.mark.parametrize("polite,plain", [
    ("戻してください", "戻して"), ("戻して下さい", "戻して"), ("戻してもらえますか", "戻して"), ("戻していただけますか", "戻して"),
    ("戻してお願いします", "戻して"), ("戻してもらえませんか", "戻して"), ("すみません、戻してください", "戻して"),
    ("閉じてください", "閉じて"), ("閉じてください", "閉じる"), ("もとに戻してください", "もとに戻す"),
    ("1番と3番を並べてください", "1番と3番を並べて"), ("1番と3番を並べてもらえますか", "1番と3番を並べて"),
    ("1番と3番を並べてお願いします", "1番と3番を並べて"), ("写真の2番を拡大してください", "写真の2番を拡大して"),
    ("写真の2番を拡大して下さい", "写真の2番を拡大して"), ("2番を拡大してください", "2番を拡大して"),
    ("重要事項を拡大してください", "重要事項を拡大して"), ("口腔内写真を全画面にしてください", "口腔内写真を全画面にして"),
    ("3番をお願いします", "3番"), ("5番を開いてください", "5番を開いて"), ("スマホをお願いします", "スマホ"),
])
def test_polite_words_act_like_plain(polite, plain):
    same(polite, plain)


@pytest.mark.parametrize("text", ["前回は何をしましたか", "前回は何をなさいましたか", "アレルギーはありますか", "アレルギーはございますか",
                                  "お薬は", "お薬を教えてください", "お薬を教えていただけますか", "次回はどうしますか", "次回の予定を教えてください"])
def test_polite_questions_still_hit_quick_answers(text):
    assert interpret(text)["kind"] == "質問"
    assert quick.pick_entry(text) is not None


@pytest.mark.parametrize("text", ["今日はいい天気ですね", "お大事にしてください", "おはようございます", "ありがとうございます",
                                  "痛かったら手を挙げてください", "口を開けてください", "少し冷たいですよ", "うがいをしてください",
                                  "戻してほしいものはありますか"])
def test_ordinary_talk_does_not_act(text):
    r = interpret(text)
    assert r["kind"] != "操作", text


# ---------- 写真の画面では番号だけで拡大 ----------
def photos_panel(browser, server):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped && document.body.dataset.numbersReady)")
    pg.click('[data-part="intraoral-photos"] [data-action="fullscreen"]')
    pg.wait_for_selector('[data-fs-panel="intraoral-photos"]')
    return pg


def figs(pg):
    return pg.evaluate("Array.from(document.querySelectorAll('.fs-fig')).map(e => Number(e.dataset.n))")


@pytest.mark.parametrize("word,want", [("1番と3番", [1, 3]), ("2番、4番", [2, 4]), ("1番3番", [1, 3]), ("1番と2番と4番", [1, 2, 4]),
                                       ("1番と3番を並べてください", [1, 3]), ("3番", [3]), ("三番をお願いします", [3])])
def test_numbers_alone_open_photos(server, browser, word, want):  # noqa: F811
    pg = photos_panel(browser, server)
    pg.evaluate("w => window.cvTyped(w)", word)
    pg.wait_for_function("document.querySelectorAll('.fs-fig').length > 0")
    assert figs(pg) == want
    assert pg.locator('[data-fs-panel="intraoral-photos"]').count() == 1
    pg.close()


def test_numbers_alone_do_not_collide_with_other_number_rules(server, browser):  # noqa: F811
    pg = open_page(browser, server, UNIT)
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped && document.body.dataset.numbersReady)")
    pg.evaluate("window.cvNumbers(true)")  # 札が出ている間は、今までどおりボタンの番号
    pg.evaluate("window.cvTyped('1番')")
    pg.wait_for_selector('[data-fs-panel="important"]')  # 札が出ていれば 1番 は重要事項（写真ではない）
    pg.close()
    pg = open_page(browser, server, UNIT)
    pg.wait_for_function("!!(window.cvNumbers && window.cvTyped && document.body.dataset.numbersReady)")
    pg.evaluate("window.cvTyped('1番と3番')")  # 札が無いふだんの画面では何も開かない
    pg.wait_for_timeout(400)
    assert pg.locator(".fs-panel").count() == 0
    pg.close()
