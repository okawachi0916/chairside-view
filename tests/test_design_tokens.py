"""G07d: 見た目の決まり。色、文字、行間は :root の変数だけ。書体は同梱でネットなしでも出る。"""
import re
from pathlib import Path

from tests.screen_helper import browser, open_page, server  # noqa: F401

CSS_DIR = Path(__file__).resolve().parent.parent / "app" / "static" / "css"
FONT_DIR = CSS_DIR.parent / "fonts"


def _css():
    out = {}
    for p in sorted(CSS_DIR.glob("*.css")):
        out[p.name] = re.sub(r"/\*.*?\*/", "", p.read_text(encoding="utf-8"), flags=re.S)
    return out


def _split_root(text):
    roots = re.findall(r":root\s*\{([^}]*)\}", text)
    body = re.sub(r":root\s*\{[^}]*\}", "", text)
    body = re.sub(r"@font-face\s*\{[^}]*\}", "", body)
    return "\n".join(roots), body


def _root_vars():
    v = {}
    for text in _css().values():
        root, _ = _split_root(text)
        for k, val in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root):
            v[k] = val.strip()
    return v


def test_one_root_holds_tokens():
    roots = [n for n, t in _css().items() if ":root" in t]
    assert roots == ["mock.css"], roots


def test_no_color_literals_outside_root():
    bad = []
    for name, text in _css().items():
        _, body = _split_root(text)
        for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(|(?<![-\w])(white|black|red)(?![-\w])", body):
            bad.append(f"{name}: {m.group(0)}")
    assert not bad, bad


def test_palette_has_at_most_14_colors():
    colors = {val.lower() for val in _root_vars().values() if re.fullmatch(r"#[0-9a-fA-F]{3,8}", val)}
    assert 0 < len(colors) <= 14, colors


def test_type_scale_weights_and_line_heights():
    v = _root_vars()
    sizes = {val for k, val in v.items() if k.startswith("--fs-")}
    weights = {val for k, val in v.items() if k.startswith("--fw-")}
    lhs = {val for k, val in v.items() if k.startswith("--lh-")}
    assert len(sizes) <= 7 and min(int(s[:-2]) for s in sizes) >= 14, sizes
    assert weights == {"400", "500", "700"}, weights
    assert len(lhs) == 3, lhs
    for name, text in _css().items():
        _, body = _split_root(text)
        for prop, pat in [("font-size", r"var\(--fs-\d\)|inherit"), ("font-weight", r"var\(--fw-\w+\)"),
                          ("line-height", r"var\(--lh-\w+\)"), ("letter-spacing", r"var\(--ls-\w+\)")]:
            for val in re.findall(rf"(?<![-\w]){prop}\s*:\s*([^;}}]+)", body):
                assert re.fullmatch(pat, val.strip()), f"{name}: {prop}: {val}"
        assert not re.search(r"box-shadow", body), f"{name}: 影は使わない"
        for val in re.findall(r"border-radius\s*:\s*([^;}]+)", body):
            assert val.strip() in ("var(--r-s)", "var(--r-l)", "50%"), f"{name}: {val}"


def _lum(hex_):
    h = hex_.lstrip("#")
    rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a, b):
    la, lb = sorted([_lum(a), _lum(b)], reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_contrast_is_at_least_4_5():
    v = _root_vars()
    pairs = [
        ("--c-ink", "--c-surface"), ("--c-ink", "--c-canvas"), ("--c-sub", "--c-surface"),
        ("--c-sub", "--c-canvas"), ("--c-surface", "--c-sub"), ("--c-surface", "--c-doctor"),
        ("--c-surface", "--c-hygienist"), ("--c-surface", "--c-reception"), ("--c-surface", "--c-alert"),
        ("--c-alert", "--c-alert-soft"), ("--c-alert", "--c-warn-soft"), ("--c-warn", "--c-warn-soft"),
        ("--c-surface", "--c-warn"), ("--c-surface", "--c-ink"), ("--c-doctor", "--c-canvas"),
    ]
    low = [(a, b, round(_contrast(v[a], v[b]), 2)) for a, b in pairs if _contrast(v[a], v[b]) < 4.5]
    assert not low, low


def test_fonts_bundled_with_license():
    names = sorted(p.name for p in FONT_DIR.glob("*.woff2"))
    assert names == ["NotoSansJP-400.woff2", "NotoSansJP-500.woff2", "NotoSansJP-700.woff2"]
    assert "SIL Open Font License" in (FONT_DIR / "OFL.txt").read_text(encoding="utf-8")


def test_font_loads_without_internet(server, browser):  # noqa: F811
    ctx = browser.new_context(viewport={"width": 1920, "height": 1030})
    outside = []

    def block(route):
        url = route.request.url
        if url.startswith(f"http://127.0.0.1:{server}/"):
            route.continue_()
        else:
            outside.append(url)
            route.abort()

    ctx.route("**/*", block)
    pg = ctx.new_page()
    pg.goto(f"http://127.0.0.1:{server}/mock/doctor")
    pg.evaluate("document.fonts.ready")
    loaded = pg.evaluate(
        "[...document.fonts].filter(f => f.family.includes('Noto Sans JP') && f.status === 'loaded')"
        ".map(f => f.weight)"
    )
    assert loaded, "Noto Sans JP が読み込まれていない"
    assert pg.evaluate("document.fonts.check('700 16px \"Noto Sans JP\"')")
    assert not outside, outside
    ctx.close()
