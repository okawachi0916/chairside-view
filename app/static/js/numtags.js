// 番号の札と暗い幕（ボタンの所だけ穴を開けて明るいまま見せる）。声の窓の仕組み（G14j・G14k）をそのまま取り出したもの。
// 親の画面（actions/voice.js）と下書きの画面（draft.js）が同じものを使う。
(function () {
  var style = document.createElement("style");
  style.textContent =
    "#num-dim{position:fixed;left:0;top:0;right:0;bottom:0;z-index:30;background:rgba(0,0,0,.55);pointer-events:none}" +
    ".num-badge{position:fixed;z-index:35;height:76px;padding:0 16px;border-radius:38px;box-sizing:border-box;white-space:nowrap;" +
    "background:#ffd43b;color:#111;border:4px solid #fff;box-shadow:0 2px 10px rgba(0,0,0,.6);" +
    "font-size:48px;font-weight:800;line-height:68px;text-align:center;pointer-events:none}" +
    "#num-band{position:fixed;z-index:36;left:0;top:0;right:0;box-sizing:border-box;display:flex;align-items:center;gap:20px;padding:0 24px;background:rgba(8,10,14,.94);pointer-events:none;overflow:hidden}" +
    ".ex-chip{color:#fff;font-size:30px;font-weight:700;white-space:nowrap;border:2px solid #ffd43b;border-radius:10px;padding:2px 16px;line-height:1.3}" +
    ".ex-msg{color:#ffd43b;font-size:28px;font-weight:700}" +
    "#num-band[data-screen=draft] .ex-chip{font-size:20px;padding:0 10px;border-width:2px}#num-band[data-screen=draft] .ex-msg{font-size:18px}";
  document.head.appendChild(style);

  function inView(el) {
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth;
  }
  function rectOf(el) { var r = el.getBoundingClientRect(); return { l: r.left, t: r.top, r: r.right, b: r.bottom }; }
  function hit(a, b) { return a.l < b.r && a.r > b.l && a.t < b.b && a.b > b.t; }
  // 札はボタンの少し上へ。上の端からはみ出すときだけ下へ。札どうし・ボタンとは重ねない
  function placeBadges(items) {
    var GAP = 8, W = window.innerWidth;
    var taken = [];
    var obstacles = [];
    document.querySelectorAll("button, [data-action], a[href]").forEach(function (e) { if (inView(e)) obstacles.push(rectOf(e)); });
    items.forEach(function (x) {
      var r = rectOf(x.el), bw = x.badge.offsetWidth, bh = x.badge.offsetHeight;
      var cands = [];
      [-1, 1].forEach(function (side) { // -1 上、1 下
        var top = side < 0 ? r.t - GAP - bh : r.b + GAP;
        if (side < 0 && top < 0) return; // 上からはみ出すときだけ下
        [0, -1, 1, -2, 2, -3, 3].forEach(function (k) {
          var left = (r.l + r.r) / 2 - bw / 2 + k * (bw / 2 + GAP + (r.r - r.l) / 2);
          cands.push({ l: left, t: top, r: left + bw, b: top + bh });
        });
      });
      var inside = function (c) { return c.l >= 0 && c.r <= W && c.t >= 0 && c.b <= window.innerHeight; };
      var pick = null;
      for (var i = 0; i < cands.length && !pick; i++) {
        var c = cands[i];
        if (!inside(c)) continue;
        if (taken.some(function (t) { return hit(c, t); })) continue;
        if (obstacles.some(function (o) { return hit(c, o); })) continue;
        pick = c;
      }
      if (!pick) { // どこも空かないときは、ほかの札とボタンの両方を避ける所だけ探し、無ければ真上
        pick = cands.filter(inside).filter(function (c) { return !taken.some(function (t) { return hit(c, t); }); })[0] || cands[0] || { l: r.l, t: r.t - GAP - bh, r: r.l + bw, b: r.t - GAP };
      }
      taken.push(pick);
      x.badge.style.left = Math.round(pick.l) + "px";
      x.badge.style.top = Math.round(pick.t) + "px";
    });
  }
  // 暗い幕。ボタンの所だけ穴を開けて、ボタンは明るいまま見せる
  function holePath(items) {
    var W = window.innerWidth, H = window.innerHeight;
    var d = "M0 0H" + W + "V" + H + "H0Z";
    items.forEach(function (x) {
      var r = x.el.getBoundingClientRect();
      d += "M" + Math.round(r.left) + " " + Math.round(r.top) + "h" + Math.round(r.width) + "v" + Math.round(r.height) + "h-" + Math.round(r.width) + "Z";
    });
    return 'path(evenodd, "' + d + '")';
  }
  function dimWithHoles(items, z) {
    var dim = document.createElement("div");
    dim.id = "num-dim";
    dim.style.clipPath = holePath(items);
    if (z) dim.style.zIndex = z;
    document.body.appendChild(dim);
  }
  // ボタンが動いたら（上の段の印の出入り・窓の大きさ・全画面の出入り）、穴と札を今の位置に合わせ直す
  var lit = null, litSig = "", litRaf = 0;
  function sigOf(items) {
    return window.innerWidth + "x" + window.innerHeight + ":" + items.map(function (x) {
      var r = x.el.getBoundingClientRect();
      return [r.left, r.top, r.width, r.height].map(Math.round).join(",");
    }).join(";");
  }
  function relayout() {
    if (!lit) return;
    var dim = document.getElementById("num-dim");
    if (dim) dim.style.clipPath = holePath(lit);
    placeBadges(lit);
    litSig = sigOf(lit);
  }
  function watchLayout() {
    cancelAnimationFrame(litRaf);
    if (!lit) return;
    var tick = function () {
      if (!lit) return;
      if (sigOf(lit) !== litSig) relayout();
      litRaf = requestAnimationFrame(tick);
    };
    litRaf = requestAnimationFrame(tick);
  }
  function addBadges(list, z) {
    var items = list.map(function (x) {
      var b = document.createElement("div");
      b.className = "num-badge";
      b.dataset.n = x.n;
      b.dataset.key = x.key;
      b.textContent = x.n + "番";
      b.style.left = "0px";
      b.style.top = "0px";
      if (z) b.style.zIndex = z + 1;
      document.body.appendChild(b);
      return { el: x.el, badge: b };
    });
    placeBadges(items);
    lit = items;
    litSig = sigOf(items);
    watchLayout();
  }
  // 札と幕を消す（番号の追い掛けも止める）
  function clear() {
    lit = null;
    cancelAnimationFrame(litRaf);
    document.querySelectorAll("#num-dim, .num-badge").forEach(function (e) { e.remove(); });
  }
  // 出ている札を { 番号: 印 } にして返し、札と幕を消す。札が無ければ null
  function take() {
    var badges = document.querySelectorAll(".num-badge");
    var map = null;
    if (badges.length) {
      map = {};
      badges.forEach(function (b) { map[b.dataset.n] = b.dataset.key; });
    }
    clear();
    return map;
  }

  window.CVNumTags = { inView: inView, dimWithHoles: dimWithHoles, addBadges: addBadges, clear: clear, take: take };
})();
