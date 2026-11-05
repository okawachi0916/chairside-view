// 歯周検査の入力。「入力」を押すと、最初に「基本検査｜精密検査」を選ぶ（選んだ方が赤）。表は入力できる状態になり、保存すると今日の新しい検査として入る。
// 表は見る画面と同じ部品（サーバーの perio_table）を /api/perio/blank で受け取る。声の入力は無い。入力の途中の値は画面の中だけにあり、保存するまでどこにも送らない。
(function () {
  var pop = null;
  var kind = "basic";

  function card() { return document.querySelector('[data-part="perio-exam"]'); }
  function editing(c) { return c && c.classList.contains("perio-editing"); }
  function closePop() { if (pop) { pop.remove(); pop = null; } }
  function appt() { return Number(new URLSearchParams(location.search).get("appt")); }

  function setCell(el, v, bop) {
    el.textContent = String(v);
    el.dataset.v = String(v);
    el.dataset.bop = bop ? "1" : "0";
    el.classList.remove("todo", "flash");
    el.classList.toggle("deep", v >= 4);
    el.classList.toggle("bop", !!bop);
  }

  function say(c, text) { var m = c.querySelector(".perio-bar .msg"); if (m) m.textContent = text; }

  function paintKind(c) {
    c.querySelectorAll(".perio-kind button").forEach(function (b) {
      var on = b.dataset.kind === kind;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  // 空の表を受け取って入れ替える。入れ替えたあと、未入力のマスに破線が付く（サーバーが todo を付ける）
  function loadTable(c, k, done) {
    fetch("/api/perio/blank?appt=" + appt() + "&kind=" + k, { cache: "no-store" })
      .then(function (r) { return r.text().then(function (t) { return [r.ok, t]; }); })
      .then(function (x) {
        if (!x[0]) { say(c, "表を作れませんでした"); return; }
        var wrap = document.createElement("div");
        wrap.innerHTML = x[1];
        var fresh = wrap.firstChild;
        var old = c.querySelector("table.perio");
        if (old) old.replaceWith(fresh);
        else c.appendChild(fresh);
        kind = k;
        paintKind(c);
        if (done) done();
      })
      .catch(function () { say(c, "表を作れませんでした（つながりません）"); });
  }

  function touched(c) {
    return !!c.querySelector('td[data-k="pocket"][data-v]:not([data-v=""]), span[data-k="pt"][data-v]:not([data-v=""]), td[data-k="mob"][data-v]:not([data-v="0"]), polygon.pq-on');
  }

  function enter() {
    var c = card();
    if (!c || editing(c)) return;
    var table = c.querySelector("table.perio");
    c.__orig = table ? table.outerHTML : null;
    c.classList.add("perio-editing");
    kind = "basic";
    var bar = document.createElement("div");
    bar.className = "perio-bar";
    bar.innerHTML =
      '<div class="perio-kind" role="group" aria-label="検査の種類">' +
      '<button type="button" data-action="perio-kind" data-kind="basic">基本検査</button>' +
      '<button type="button" data-action="perio-kind" data-kind="precise">精密検査</button></div>' +
      '<span class="msg">検査の種類を選び、数字を押して入れます。出血があるときは、赤い数字を選びます。プラークは四角を押します。</span>' +
      '<button type="button" data-action="perio-cancel">やめる</button>' +
      '<button type="button" class="main" data-action="perio-save">保存</button>';
    c.querySelector(".tools").insertAdjacentElement("afterend", bar);
    var btn = c.querySelector('[data-action="perio-input"]');
    if (btn) btn.disabled = true;
    paintKind(c);
    loadTable(c, "basic");
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
    var cur = c.querySelector("table.perio");
    if (c.__orig) {
      var t = document.createElement("div");
      t.innerHTML = c.__orig;
      if (cur) cur.replaceWith(t.firstChild); else c.appendChild(t.firstChild);
    } else if (cur) {
      cur.remove();
    }
    leave(c);
  }

  function switchKind(k) {
    var c = card();
    if (!editing(c) || k === kind) return;
    closePop();
    var had = touched(c);
    loadTable(c, k, function () {
      say(c, had ? "検査の種類を変えたので、入れた数字は消えました。" : "検査の種類を選び、数字を押して入れます。出血があるときは、赤い数字を選びます。プラークは四角を押します。");
    });
  }

  function openPop(el) {
    closePop();
    var c = card();
    pop = document.createElement("div");
    pop.className = "perio-pop";
    var html = "";
    if (el.dataset.k === "pocket" || el.dataset.k === "pt") {
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
    pop.__el = el;
    c.appendChild(pop);
    var r = el.getBoundingClientRect(), w = pop.offsetWidth, h = pop.offsetHeight;
    var left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8));
    var top = r.bottom + 4 + h > window.innerHeight ? Math.max(8, r.top - h - 4) : r.bottom + 4;
    pop.style.left = left + "px";
    pop.style.top = top + "px";
  }

  function collect(c) {
    var teeth = {}, missing = [];
    var SIDE = { l: 0, r: 1, t: 2, b: 3 }; // 近心・遠心・頬側・舌側 → 四角の4辺
    if (kind === "precise") {
      c.querySelectorAll("td.p3").forEach(function (td) { // 同じ歯が上下の2行にあるので、歯ごとに6点を集める
        var t = td.dataset.tooth;
        if (!teeth[t]) teeth[t] = { pts: [null, null, null, null, null, null], bops: [0, 0, 0, 0, 0, 0], plaque: "0000", mobility: 0 };
      });
      c.querySelectorAll('span[data-k="pt"]').forEach(function (sp) {
        var t = sp.parentNode.dataset.tooth, i = Number(sp.dataset.i);
        teeth[t].pts[i] = sp.dataset.v ? Number(sp.dataset.v) : null;
        teeth[t].bops[i] = Number(sp.dataset.bop || 0);
        if (!sp.dataset.v) missing.push(sp);
      });
    } else {
      c.querySelectorAll('td[data-k="pocket"]').forEach(function (td) {
        var t = td.dataset.tooth, v = td.dataset.v;
        if (!v) missing.push(td);
        teeth[t] = { pocket: v ? Number(v) : null, bop: Number(td.dataset.bop || 0), plaque: "0000", mobility: 0 };
      });
    }
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

  function teethCount(missing) {
    var seen = {};
    missing.forEach(function (el) { seen[(el.dataset.tooth || el.parentNode.dataset.tooth)] = 1; });
    return Object.keys(seen).length;
  }

  function flash(c, missingTeeth) {
    (missingTeeth || []).forEach(function (t) {
      c.querySelectorAll('[data-tooth="' + t + '"][data-k="pocket"], td.p3[data-tooth="' + t + '"] span[data-k="pt"]').forEach(function (e) {
        if (!e.dataset.v) e.classList.add("flash");
      });
    });
  }

  function save() {
    var c = card();
    if (!editing(c)) return;
    closePop();
    var got = collect(c);
    c.querySelectorAll(".flash").forEach(function (e) { e.classList.remove("flash"); });
    if (got.missing.length) {
      got.missing.forEach(function (e) { e.classList.add("flash"); });
      say(c, "入力していない歯があります（" + teethCount(got.missing) + "本）。保存していません");
      return;
    }
    var q = new URLSearchParams(location.search);
    fetch("/api/perio/save", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ appt: Number(q.get("appt")), kind: kind, teeth: got.teeth }),
    })
      .then(function (r) { return r.json().then(function (b) { return [r.ok, b]; }); })
      .then(function (x) {
        if (!x[0]) {
          flash(c, x[1].missing);
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
    if (act && act.dataset.action === "perio-kind") { switchKind(act.dataset.kind); return; }
    var b = t.closest(".perio-pop button");
    if (b && pop) {
      var el = pop.__el;
      if (b.dataset.pocket) setCell(el, Number(b.dataset.pocket), b.dataset.bop === "1");
      else { el.textContent = b.dataset.mob; el.dataset.v = b.dataset.mob; }
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
    var cell = t.closest && t.closest('td[data-k="pocket"], td[data-k="mob"], span[data-k="pt"]');
    if (cell && c.contains(cell)) { openPop(cell); return; }
    closePop();
  });
})();
