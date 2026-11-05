"""声で呼ぶ番号の決まり（G14n）。ここだけで決める。

ユニットは音楽が流れていて、マイクが「5番（ごばん）」「8番（はちばん）」を聞き違える。
そこで、5 と 8 の2つだけを飛ばす（15、18 など長い番号は言葉が長く聞き取れるので使う）。並びは 1、2、3、4、6、7、9、10、11、12、…
- label(seq):  何番目か（1から）→ 画面に出して声で呼ぶ番号
- seq_of(n):   声の番号 → 何番目か（飛ばす番号なら None）
JS 側の同じ決まりは app/static/js/numrule.js。2つが同じ答えを返すことは tests/test_g14n.py で確かめる。
"""

SKIP = frozenset({5, 8})


def callable_number(n: int) -> bool:
    """声で呼べる番号か（5 と 8 以外の正の整数）。"""
    return isinstance(n, int) and n > 0 and n not in SKIP


def label(seq: int) -> int:
    """何番目か（1から）→ 画面に出す番号。"""
    seq = int(seq)
    if seq < 1:
        raise ValueError("何番目かは 1 以上")
    n = 0
    while seq:
        n += 1
        if callable_number(n):
            seq -= 1
    return n


def seq_of(n) -> int | None:
    """声の番号 → 何番目か。5 と 8・0 以下・整数でないものは None。"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if not callable_number(n):
        return None
    return sum(1 for k in range(1, n + 1) if callable_number(k))
