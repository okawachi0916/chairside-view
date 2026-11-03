// 歯周基本検査の入力。「入力」を押すと表が入力できる状態になり、保存すると今日の新しい検査として入る。
// 声の入力は無い。入力の途中の値は画面の中だけにあり、保存するまでどこにも送らない。
(function () {
  var pop = null;

  function card() { return document.querySelector('[data-part="perio-exam"]'); }
  function editing(c) { return c && c.classList.contains("perio-editing"); }
  function closePop() { if (pop) { pop.remove(); pop = null; } }

  function setPocket(td, v, bop) {
    td.textContent = String(v);
    td.dataset.v = String(v);
    td.dataset.bop = bop ? "1" : "0";
    td.classList.remove("todo", "flash");
    td.classList.toggle("deep", v >= 4);
    td.classList.toggle("bop", !!bop);
  }

  function enter() {
    var c = card();
    if (!c || editing(c)) return;
    var table = c.querySelector("table.perio");
    if (!table) return;
    c.__orig = table.outerHTML;
    c.classList.add("perio-editing");
    table.querySelectorAll('td[data-k="pocket"]').forEach(function (td) {
      td.textContent = "";
      td.classList.remove("deep", "bop");
      td.classList.add("todo");
      td.dataset.v = "";
      td.dataset.bop = "0";
    });
    table.querySelectorAll('td[data-k="mob"]').forEach(function (td) { td.textContent = "0"; td.dataset.v = "0"; });
    table.querySelectorAll("polygon").forEach(function (p) { p.setAttribute("class", "pq-off"); });
    var bar = document.createElement("div");
    bar.className = "perio-bar";
    bar.innerHTML = '<span class="msg">ポケットの数字を押して選びます。出血があるときは、赤い数字を選びます。プラークは四角を押します。</span>' +
      '<button type="button" data-action="perio-cancel">やめる</button>' +
      '<button type="button" class="main" data-action="perio-save">保存</button>';
    c.insertBefore(bar, table);
    var btn = c.querySelector('[data-action="perio-input"]');
    if (btn) btn.disabled = true;
  }

  function leave(c) {
    closePop();
    var bar = c.querySelector(".perio-bar");
    if (bar) bar.remove();
    c.classList.remove("perio-editing");
    var btn = c.querySelector('[data-action="perio-input"]');
    if (btn) btn.disabled = false;
  }

  function cancel() {
    var c = card();
    if (!editing(c)) return;
    var t = document.createElement("div");
    t.innerHTML = c.__orig;
    c.querySelector("table.perio").replaceWith(t.firstChild);
    leave(c);
  }

  function say(c, text) { var m = c.querySelector(".perio-bar .msg"); if (m) m.textContent = text; }

  function openPop(td) {
    closePop();
    var c = card();
    pop = document.createElement("div");
    pop.className = "perio-pop";
    var html = "";
    if (td.dataset.k === "pocket") {
      var n = "", b = "";
      for (var i = 1; i <= 10; i++) {
        n += '<button type="button" data-pocket="' + i + '" data-bop="0">' + i + "</button>";
        b += '<button type="button" class="bleed" data-pocket="' + i + '" data-bop="1">' + i + "</button>";
      }
      html = '<div>ポケット（mm）</div><div class="row">' + n + '</div><div>出血あり（BOP）</div><div class="row">' + b + "</div>";
    } else {
      html = '<div>動揺度</div><div class="row">' + [0, 1, 2, 3].map(function (i) {
        return '<button type="button" data-mob="' + i + '">' + i + "</button>";
      }).join("") + "</div>";
    }
    pop.innerHTML = html;
    pop.__td = td;
    c.appendChild(pop);
    var r = td.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    var left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
    var top = r.bottom + 4 + h > window.innerHeight ? Math.max(8, r.top - h - 4) : r.bottom + 4;
    pop.style.left = left + "px";
    pop.style.top = top + "px";
  }

  function collect(c) {
    var teeth = {}, missing = [];
    c.querySelectorAll('td[data-k="pocket"]').forEach(function (td) {
      var t = td.dataset.tooth, v = td.dataset.v;
      if (!v) missing.push(td);
      teeth[t] = { pocket: v ? Number(v) : null, bop: Number(td.dataset.bop || 0), plaque: "0000", mobility: 0 };
    });
    var SIDE = { l: 0, r: 1, t: 2, b: 3 }; // 近心・遠心・頬側・舌側 → 四角の4辺
    c.querySelectorAll('td[data-k="plq"]').forEach(function (td) {
      var f = ["0", "0", "0", "0"];
      td.querySelectorAll("polygon.pq-on").forEach(function (p) { f[SIDE[p.dataset.side]] = "1"; });
      if (teeth[td.dataset.tooth]) teeth[td.dataset.tooth].plaque = f.join("");
    });
    c.querySelectorAll('td[data-k="mob"]').forEach(function (td) {
      if (teeth[td.dataset.tooth]) teeth[td.dataset.tooth].mobility = Number(td.dataset.v || 0);
    });
    return { teeth: teeth, missing: missing };
  }

  function save() {
    var c = card();
    if (!editing(c)) return;
    closePop();
    var got = collect(c);
    c.querySelectorAll("td.flash").forEach(function (td) { td.classList.remove("flash"); });
    if (got.missing.length) {
      got.missing.forEach(function (td) { td.classList.add("flash"); });
      say(c, "入力していない歯があります（" + got.missing.length + "本）。保存していません");
      return;
    }
    var q = new URLSearchParams(location.search);
    fetch("/api/perio/save", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ appt: Number(q.get("appt")), teeth: got.teeth }),
    })
      .then(function (r) { return r.json().then(function (b) { return [r.ok, b]; }); })
      .then(function (x) {
        if (!x[0]) {
          (x[1].missing || []).forEach(function (t) {
            var td = c.querySelector('td[data-k="pocket"][data-tooth="' + t + '"]');
            if (td) td.classList.add("flash");
          });
          say(c, x[1].error || "保存できませんでした");
          return;
        }
        leave(c);
        if (window.cv) window.cv.openUnit(q.get("appt"), q.get("role")); // 数字を計算し直して、前回と並べる
      })
      .catch(function () { say(c, "保存できませんでした（つながりません）"); });
  }

  document.addEventListener("click", function (e) {
    var c = card();
    if (!c) return;
    var t = e.target;
    var act = t.closest && t.closest("[data-action]");
    if (act && act.dataset.action === "perio-input") { enter(); return; }
    if (!editing(c)) return;
    if (act && act.dataset.action === "perio-save") { save(); return; }
    if (act && act.dataset.action === "perio-cancel") { cancel(); return; }
    var b = t.closest(".perio-pop button");
    if (b && pop) {
      var td = pop.__td;
      if (b.dataset.pocket) setPocket(td, Number(b.dataset.pocket), b.dataset.bop === "1");
      else { td.textContent = b.dataset.mob; td.dataset.v = b.dataset.mob; }
      closePop();
      return;
    }
    if (t.closest(".perio-pop")) return;
    var poly = t.closest && t.closest("polygon");
    if (poly && c.contains(poly)) {
      closePop();
      poly.setAttribute("class", poly.getAttribute("class") === "pq-on" ? "pq-off" : "pq-on");
      return;
    }
    var cell = t.closest && t.closest('td[data-k="pocket"], td[data-k="mob"]');
    if (cell && c.contains(cell)) { openPop(cell); return; }
    closePop();
  });
})();
