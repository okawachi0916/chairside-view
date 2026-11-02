"""Claude へ送る前の伏字。送信ごとに別の対応表（Table）を持つので、同時に送っても混ざらない。

- 氏名・姓・名・読みがな・カルテ番号・電話・住所・生年月日・スタッフ・医療機関を置き換える。
- 全角半角、ひらがなカタカナ、空白やハイフンの違い、ゼロ幅文字が混ざっても拾う。
- 長い文字列を先に置き換える（1回の走査で、長い候補を先に試す）。
- 置き換えたあと、別の方法（正規化して部分一致）で残りを調べ、あれば RedactionFailed。
"""
import re
import unicodedata
from dataclasses import dataclass, field

FAIL_MESSAGE = "伏字に失敗しました"

_ZW = "​‌‍﻿⁠"
_SPACE = r"\s　" + _ZW
_DASH = r"\-‐‑‒–—―−ー－ｰ"
_PLACEHOLDER = re.compile(r"\[[^\[\]]+\]")


class RedactionFailed(Exception):
    def __init__(self):
        super().__init__(FAIL_MESSAGE)


@dataclass
class Patient:
    name: str = ""
    kana: str = ""
    family: str = ""
    given: str = ""
    family_kana: str = ""
    given_kana: str = ""
    chart_no: str = ""
    phone: str = ""
    address: str = ""
    birth_date: str = ""  # YYYY-MM-DD

    def __post_init__(self):
        if self.name and not (self.family or self.given):
            self.family, self.given = _split(self.name)
        if self.kana and not (self.family_kana or self.given_kana):
            self.family_kana, self.given_kana = _split(self.kana)


@dataclass
class Sensitive:
    patients: list = field(default_factory=list)
    staff: list = field(default_factory=list)
    clinics: list = field(default_factory=list)


def _split(full: str):
    parts = re.split(r"[\s　]+", full.strip(), maxsplit=1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


def _hira(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def _norm(s: str) -> str:
    """残りの検査用: 全角半角・かなの種類・空白・ハイフン・ゼロ幅を無くす。"""
    s = _hira(unicodedata.normalize("NFKC", s)).lower()
    return re.sub(f"[{_SPACE}{_DASH}]", "", s)


def _char_class(c: str) -> str:
    forms = {c}
    n = unicodedata.normalize("NFKC", c)
    forms.add(n)
    if "!" <= n <= "~":  # 半角の英数記号に対応する全角
        forms.add(chr(ord(n) + 0xFEE0))
    h = _hira(n)
    forms.add(h)
    if "ぁ" <= h <= "ゖ":
        forms.add(chr(ord(h) + 0x60))
    forms |= {f.lower() for f in forms} | {f.upper() for f in forms}
    return "[" + "".join(re.escape(f) for f in sorted(forms)) + "]"


def _pattern(s: str, gap: str) -> str:
    skip = " 　" + (_DASH.replace("\\", "") if _DASH in gap else "")
    chars = [c for c in unicodedata.normalize("NFKC", s) if c not in skip]
    return f"[{gap}]*".join(_char_class(c) for c in chars)


def _date_variants(iso: str):
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", iso.strip())
    if not m:
        return [iso]
    y, mo, d = (int(x) for x in m.groups())
    out = []
    for sep in ("-", "/", "."):
        out += [f"{y}{sep}{mo:02d}{sep}{d:02d}", f"{y}{sep}{mo}{sep}{d}"]
    out += [f"{y}年{mo}月{d}日", f"{y}年{mo:02d}月{d:02d}日"]
    for era, start in (("令和", 2019), ("平成", 1989), ("昭和", 1926), ("大正", 1912)):
        if y >= start:
            e = y - start + 1
            out += [f"{era}{e}年{mo}月{d}日", f"{era}{e:02d}年{mo:02d}月{d:02d}日"]
            if e == 1:
                out.append(f"{era}元年{mo}月{d}日")
            break
    return out


def _entries(s: Sensitive):
    """(種類, 本人を表す値, 照合する文字列, 空白の許し方) の一覧。"""
    out = []

    def add(kind, canon, text, gap=_SPACE):
        if text and text.strip():
            out.append((kind, canon, text, gap))

    for p in s.patients:
        if p.name:
            full = p.name
            joined = (p.family + p.given) if (p.family or p.given) else full
            add("氏名", p.name, full)
            add("氏名", p.name, joined)
        add("姓", p.family, p.family)
        add("名", p.given, p.given)
        if p.kana:
            add("読み", p.kana, p.kana)
            add("読み", p.kana, p.family_kana + p.given_kana)
        add("姓読み", p.family_kana, p.family_kana)
        add("名読み", p.given_kana, p.given_kana)
        add("番号", p.chart_no, p.chart_no, _SPACE + _DASH)
        add("電話", p.phone, p.phone, _SPACE + _DASH)
        add("住所", p.address, p.address)
        for v in _date_variants(p.birth_date) if p.birth_date else []:
            add("生年月日", p.birth_date, v)
    for n in s.staff:
        full = n
        add("職員", n, full)
        a, b = _split(n)
        if b:
            add("職員", n, a + b)
            add("職員", a, a)
            add("職員", b, b)
    for c in s.clinics:
        add("医院", c, c)
    return out


class Table:
    """1回の送信だけで使う対応表。作ったものを使い回さない。"""

    def __init__(self, sensitive: Sensitive):
        self._sensitive = sensitive
        ents = _entries(sensitive)
        # 長い文字列を先に試す（同じ長さなら先に登録されたもの）
        ents.sort(key=lambda e: -len(_norm(e[2])))
        self._ents = ents
        self._groups = {}
        parts = []
        for i, (kind, canon, text, gap) in enumerate(ents):
            self._groups[f"g{i}"] = (kind, canon)
            parts.append(f"(?P<g{i}>{_pattern(text, gap)})")
        self._rx = re.compile("|".join(parts)) if parts else None
        self._index = {}   # (種類, 値) -> 番号
        self._seen = {}    # (種類, 値) -> 表記の一覧
        self.back = {}     # 印 -> 元の文字

    def _placeholder(self, kind, canon, surface):
        key = (kind, canon)
        if key not in self._index:
            self._index[key] = 1 + sum(1 for k in self._index if k[0] == kind)
            self._seen[key] = []
        surfaces = self._seen[key]
        if surface not in surfaces:
            surfaces.append(surface)
        n = surfaces.index(surface)
        suffix = "" if n == 0 else chr(ord("a") + n)  # 同じ人の別の書き方は 1b, 1c ...
        ph = f"[{kind}{self._index[key]}{suffix}]"
        self.back[ph] = surface
        return ph

    def mask(self, text: str) -> str:
        if not self._rx or not text:
            return text

        def sub(m):
            kind, canon = self._groups[m.lastgroup]
            return self._placeholder(kind, canon, m.group(0))

        return self._rx.sub(sub, text)

    def restore(self, text: str) -> str:
        return _PLACEHOLDER.sub(lambda m: self.back.get(m.group(0), m.group(0)), text)

    def leftovers(self, masked: str):
        """伏字のあとに残っている指定情報（種類のみ返す。中身は返さない）。"""
        body = _norm(_PLACEHOLDER.sub("|", masked))
        found = []
        for kind, _canon, text, _gap in self._ents:
            t = _norm(text)
            if t and t in body:
                found.append(kind)
        return found


def check_clean(table: Table, masked: str):
    if table.leftovers(masked):
        raise RedactionFailed()
