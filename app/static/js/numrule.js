// 声で呼ぶ番号の決まり（G14n）。app/numbering.py と同じ決まり（5 と 8 の2つだけ飛ばす。15、18 などは使う）。
// 画面の番号の札・写真の番号は、全部ここの label() を通す。試験（tests/test_g14n.py）が Python 側と同じ答えか確かめる。
(function () {
  function callable(n) { return n > 0 && Math.floor(n) === n && n !== 5 && n !== 8; }
  // 何番目か（1から）→ 画面に出す番号
  function label(seq) {
    var n = 0;
    while (seq > 0) { n++; if (callable(n)) seq--; }
    return n;
  }
  // 声の番号 → 何番目か。飛ばす番号などは null
  function seqOf(n) {
    n = Number(n);
    if (!callable(n)) return null;
    var c = 0;
    for (var k = 1; k <= n; k++) if (callable(k)) c++;
    return c;
  }
  window.CVNumRule = { label: label, seqOf: seqOf, callable: callable };
})();
