"""G07e: 全画面と答えの画面にスクロールを出さない（Edge 1920×1030）。

5人の架空の患者様 × 歯科医師・歯科衛生士の画面のすべての全画面、声の質問4つの答え、
受付の画面の全画面、録音と下書きの画面、/sent、予約一覧を開き、縦と横のスクロールが無いことを見る。
入りきらない中身は、2列・字を小さく（全画面だけ）・ページ送りのボタン、の順で出す。
"""
import time

import pytest

from app.views import data as D
from tests.screen_helper import ROOT, browser, open_page, server  # noqa: F401

QUESTIONS = ["前回は何をした？", "アレルギーは？", "薬は？", "次回は？"]
SHOTS = ROOT / "docs" / "画面" / "G07e"

# 画面の中で、スクロールの出る箱（と、ページ全体）を挙げる。fs=1 なら全画面の中だけを見る
SCROLLBARS = """(fs) => {
  const out = [];
  const de = document.documentElement;
  if (de.scrollHeight > de.clientHeight + 1 || de.scrollWidth > de.clientWidth + 1)
    out.push('page:' + de.scrollWidth + 'x' + de.scrollHeight);
  const scope = fs ? document.querySelector('.fs-panel') : document.body;
  if (!scope) return ['no-panel'];
  for (const e of [scope, ...scope.querySelectorAll('*')]) {
    if (!e.getClientRects().length) continue;
    if (!fs && e.closest('[data-part="past-notes"]')) continue;  // いつもの画面の過去の診療メモは今回は対象外
    const cs = getComputedStyle(e);
    const can = v => v === 'auto' || v === 'scroll';
    const y = cs.overflowY === 'scroll' || (can(cs.overflowY) && e.scrollHeight > e.clientHeight + 1);
    const x = cs.overflowX === 'scroll' || (can(cs.overflowX) && e.scrollWidth > e.clientWidth + 1);
    if (x || y) out.push((e.getAttribute('data-part') || e.className || e.tagName) + ':'
                         + e.scrollWidth + 'x' + e.scrollHeight + '/' + e.clientWidth + 'x' + e.clientHeight);
  }
  return out;
}"""

# 全画面で、見えない所に残った中身があるのにページ送りが出ていないもの
HIDDEN_REST = """() => {
  const p = document.querySelector('.fs-panel');
  const next = p.querySelector('[data-action="fs-next"]');
  const paged = next && !next.hidden && next.getClientRects().length > 0;
  return [...p.querySelectorAll('.fs-scroll, .ai-body')]
    .filter(e => e.getClientRects().length && e.scrollHeight > e.clientHeight + 4 && !paged)
    .map(e => e.className + ':' + e.scrollHeight + '/' + e.clientHeight);
}"""


def appts():
    with D.con() as c:
        rows = c.execute("SELECT a.patient_id, MIN(a.id) FROM appointments a WHERE a.appt_date='2026-11-06' "
                         "AND a.status='booked' GROUP BY a.patient_id ORDER BY a.patient_id").fetchall()
    return [(r[0], r[1]) for r in rows]


def shot(pg, name):
    SHOTS.mkdir(parents=True, exist_ok=True)
    pg.screenshot(path=str(SHOTS / f"{name}.png"))


def check(pg, where, fs=True):
    time.sleep(0.25)  # 収める処理（actions/look.js）を待つ
    bars = pg.evaluate(SCROLLBARS, 1 if fs else 0)
    rest = pg.evaluate(HIDDEN_REST) if fs else []
    return [f"{where} スクロール {b}" for b in bars] + [f"{where} 隠れたまま {r}" for r in rest]


def open_unit(browser, server, appt, role):  # noqa: F811
    pg = open_page(browser, server, f"/unit?appt={appt}&role={role}&typed=1&hide=1")
    pg.wait_for_selector('[data-part="important"]')
    pg.wait_for_function("typeof window.cvTyped === 'function' && typeof window.CVAsk === 'function'")
    time.sleep(0.3)
    return pg


def fs_parts(pg):
    return pg.evaluate("() => [...document.querySelectorAll('template[data-fs]')].map(t => t.dataset.fs)")


def test_five_patients_unit_fullscreens(server, browser):  # noqa: F811
    bad, seen = [], 0
    for pid, appt in appts():
        for role in ("doctor", "hygienist"):
            pg = open_unit(browser, server, appt, role)
            for part in fs_parts(pg):
                pg.evaluate("p => CVActions.run('fs-open', p)", part)
                pg.wait_for_selector(f'[data-fs-panel="{part}"]')
                bad += check(pg, f"患者{pid} {role} {part}")
                if pid == 1:
                    shot(pg, f"{role}_{part}")
                seen += 1
                pg.evaluate("CVActions.run('fs-close')")
            pg.evaluate("CVActions.run('say-list-open')")
            pg.wait_for_selector('[data-fs-panel="say-list"]')
            bad += check(pg, f"患者{pid} {role} 言える言葉")
            if pid == 1 and role == "doctor":
                shot(pg, "say-list")
            pg.close()
    assert seen >= 5 * 2 * 5, seen
    assert not bad, "\n".join(bad[:15])


@pytest.mark.parametrize("q", QUESTIONS)
def test_answers_fit_without_scroll(server, browser, q):  # noqa: F811
    bad = []
    for pid, appt in appts():
        pg = open_unit(browser, server, appt, "doctor")
        pg.evaluate("t => window.cvTyped(t)", q)
        pg.wait_for_function("['found','none','retry','unclear'].includes(document.body.dataset.answer)")
        if pg.evaluate("document.body.dataset.answer") == "found":
            bad += check(pg, f"患者{pid} {q}")
            # 答えは全部見えている（ページ送りに逃げない）
            body = pg.evaluate("() => { const b = document.querySelector('.ai-body');"
                               " return [b.scrollHeight, b.clientHeight, b.scrollWidth, b.clientWidth]; }")
            if body[0] > body[1] + 4 or body[2] > body[3] + 1:
                bad.append(f"患者{pid} {q} 答えが入りきらない {body}")
            # 字は本文の大きさより小さくしない
            # 見えている字の大きさ = 字の大きさ × 縮め方（--fit の zoom）
            fs = pg.evaluate("() => Math.min(...[...document.querySelectorAll('.ai-body p')].map(p =>"
                             " parseFloat(getComputedStyle(p).fontSize) * (parseFloat(getComputedStyle(p).zoom) || 1)))")
            if fs < 22:
                bad.append(f"患者{pid} {q} 字が小さすぎる {fs}")
            # 枠は空いている所いっぱい
            w = pg.evaluate("document.querySelector('.ai-frame').getBoundingClientRect().width")
            if w < 1600:
                bad.append(f"患者{pid} {q} 枠が細い {w}")
            if pid == 1:
                shot(pg, f"answer_{QUESTIONS.index(q) + 1}")
        pg.close()
    assert not bad, "\n".join(bad[:15])


def test_reception_fullscreens(server, browser):  # noqa: F811
    bad = []
    for pid, appt in appts():
        pg = open_page(browser, server, f"/reception?patient={pid}")
        pg.wait_for_selector('[data-part="important"]')
        time.sleep(0.3)
        bad += check(pg, f"受付 患者{pid}", fs=False)
        for part in fs_parts(pg):
            pg.evaluate("p => CVActions.run('fs-open', p)", part)
            pg.wait_for_selector(f'[data-fs-panel="{part}"]')
            bad += check(pg, f"受付 患者{pid} {part}")
            if pid == 1:
                shot(pg, f"reception_{part}")
            pg.evaluate("CVActions.run('fs-close')")
        pg.close()
    assert not bad, "\n".join(bad[:15])


@pytest.mark.parametrize("path", ["/", "/clinic", "/reception", "/recordings", "/today", "/sent"])
def test_list_screens(server, browser, path):  # noqa: F811
    pg = open_page(browser, server, path)
    pg.wait_for_load_state("networkidle")
    bad = check(pg, path, fs=False)
    shot(pg, "page_" + {"/": "entrance", "/clinic": "booklist"}.get(path, path.strip("/")))
    pg.close()
    assert not bad, "\n".join(bad)


def test_recording_and_draft_screens(server, browser):  # noqa: F811
    """録音の画面（/app）と、下書きの画面・直す画面。"""
    from tests.test_confirm_screen import connect, make_rec, set_fake
    set_fake()
    bad = []
    try:
        s = make_rec(server)
        assert s["state"] == "下書き", s
        for path, name in [("/app", "rec_app"), ("/recordings", "rec_list"),
                           (f"/drafts/{s['draft_id']}?back=/recordings", "draft"),
                           (f"/drafts/{s['draft_id']}?back=/recordings&fix=1", "draft_fix"),
                           (f"/fix/{s['id']}?back=/today", "fix")]:
            pg = open_page(browser, server, path)
            pg.wait_for_load_state("networkidle")
            bad += check(pg, path, fs=False)
            shot(pg, name)
            pg.close()
    finally:
        c = connect()
        c.execute("DELETE FROM drafts WHERE recording_id IS NOT NULL")
        c.execute("DELETE FROM recordings")
        c.commit()
        c.close()
    assert not bad, "\n".join(bad)


def test_long_answer_goes_two_columns_then_smaller(server, browser):  # noqa: F811
    """項目が多い答え: 2列にし、それでも入らないときだけ字を小さく（下限は本文 22px）。スクロールは出さない。"""
    pid, appt = appts()[0]
    pg = open_unit(browser, server, appt, "doctor")
    pg.evaluate("t => window.cvTyped(t)", "薬は？")
    pg.wait_for_selector('[data-fs-panel="answer"]')
    for n, want_small in [(12, False), (24, True)]:
        pg.evaluate("""n => { const b = document.querySelector('.ai-body'); b.textContent = '';
                     for (let i = 1; i <= n; i++) { const p = document.createElement('p');
                       p.textContent = '架空の項目 ' + i + ' 高血圧、架空の薬を内服中'; b.appendChild(p); } }""", n)
        time.sleep(0.3)
        st = pg.evaluate("""() => { const b = document.querySelector('.ai-body'), p = b.querySelector('p');
                  const cs = getComputedStyle(p);
                  return {two: b.classList.contains('fit-2col'), over: b.scrollHeight > b.clientHeight + 4,
                          size: parseFloat(cs.fontSize) * (parseFloat(cs.zoom) || 1)}; }""")
        assert st["two"] and not st["over"], (n, st)
        assert (st["size"] < 36) == want_small and st["size"] >= 22, (n, st)
        assert not check(pg, f"答え{n}件")
        shot(pg, f"answer_many_{n}")
    pg.close()
