// 操作の入口。ボタン1・2・3、画面のボタン、声の操作は、全部ここの run(名前) を通す。
// ほかの窓の操作は actions/担当.js に書いて register で足す。
(function () {
  var table = {};
  var hidden = null; // 隠している間の { frag, scrolls, chart }

  function register(name, fn) { table[name] = fn; }
  function run(name, arg) {
    var f = table[name];
    if (!f) return false;
    f(arg);
    return true;
  }
  function root() { return document.getElementById("view"); }
  function isHidden() { return !!hidden; }

  // ---- 隠す・戻す (ボタン3) ----
  function hide() {
    if (hidden) return;
    if (window.CVPhone && document.getElementById("phone-modal")) window.CVPhone.close(); // QR が出たまま残さない
    var r = root();
    if (window.cv && window.cv.cancel) window.cv.cancel(); // 読み込み中の応答が隠した画面へ入らないようにする
    var scrolls = [];
    r.querySelectorAll("*").forEach(function (el) {
      if (el.scrollTop > 0) scrolls.push([el, el.scrollTop]);
    });
    var frag = document.createDocumentFragment();
    while (r.firstChild) frag.appendChild(r.firstChild); // 画面から外す。ページの文字には何も残らない
    var chart = (window.cv && window.cv.chart) || "";
    hidden = { frag: frag, scrolls: scrolls, chart: chart };
    var p = document.createElement("div");
    p.className = "hide-panel";
    p.setAttribute("data-part", "hidden-screen");
    var m = document.createElement("div");
    m.className = "hide-msg";
    m.textContent = "カルテ番号 " + chart + " 様に戻る場合は、ボタン3を2回押してください";
    var b = document.createElement("button");
    b.type = "button";
    b.className = "hide-pick";
    b.setAttribute("data-action", "pick-patient");
    b.textContent = "予約一覧から選ぶ";
    p.appendChild(m);
    p.appendChild(b);
    r.appendChild(p);
  }

  function restore() {
    if (!hidden) return;
    var r = root(), h = hidden;
    hidden = null;
    while (r.firstChild) r.removeChild(r.firstChild);
    r.appendChild(h.frag);
    h.scrolls.forEach(function (s) { s[0].scrollTop = s[1]; });
    if (window.cv && window.cv.restored) window.cv.restored();
  }

  // ---- 全画面 (重要事項・写真・話した内容の整理) ----
  function panel() { return root().querySelector(".fs-panel"); }
  function scrollers(p) { return p.querySelectorAll(".fs-scroll"); }

  function fsUpdate() {
    var p = panel();
    if (!p) return;
    var over = false, atTop = true, atEnd = true;
    scrollers(p).forEach(function (el) {
      if (el.scrollHeight > el.clientHeight + 1) {
        over = true;
        if (el.scrollTop > 0) atTop = false;
        if (el.scrollTop + el.clientHeight < el.scrollHeight - 1) atEnd = false;
      }
    });
    var prev = p.querySelector('[data-action="fs-prev"]'), next = p.querySelector('[data-action="fs-next"]');
    prev.hidden = next.hidden = !over;
    prev.disabled = atTop;
    next.disabled = atEnd;
  }

  function fsOpen(part) {
    var tpl = root().querySelector('template[data-fs="' + part + '"]');
    if (!tpl) return; // ほかの部品の全画面は作らない
    fsClose();
    var p = document.createElement("section");
    p.className = "fs-panel";
    p.setAttribute("data-fs-panel", part);
    var head = document.createElement("div");
    head.className = "fs-head";
    var h = document.createElement("h2");
    h.textContent = tpl.dataset.title;
    head.appendChild(h);
    var sp = document.createElement("span");
    sp.className = "fs-spacer";
    head.appendChild(sp);
    if (part === "intraoral-photos") {
      var ph = document.createElement("button");
      ph.type = "button";
      ph.className = "phone-btn";
      ph.setAttribute("data-action", "phone");
      ph.textContent = "スマホで写真をやり取り";
      head.appendChild(ph);
    }
    [["fs-prev", "前のページ"], ["fs-next", "次のページ"], ["fs-close", "もとに戻す"]].forEach(function (b) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("data-action", b[0]);
      btn.textContent = b[1];
      head.appendChild(btn);
    });
    p.appendChild(head);
    p.appendChild(tpl.content.cloneNode(true));
    root().appendChild(p);
    document.body.classList.add("fs-mode");
    scrollers(p).forEach(function (el) { el.addEventListener("scroll", fsUpdate); });
    if (part === "intraoral-photos") run("photos-opened", p); // 写真の見せ方は actions/voice.js
    fsUpdate();
  }

  function fsClose() {
    var p = panel();
    if (p) p.remove();
    document.body.classList.remove("fs-mode");
  }

  function fsPage(dir) {
    var p = panel();
    if (!p) return;
    scrollers(p).forEach(function (el) {
      // 1ページに1回分の表 (歯周検査) は1組ずつ、ほかは9割ずつ送る
      el.scrollTop += dir * (el.hasAttribute("data-pages") ? el.clientHeight : Math.max(40, Math.floor(el.clientHeight * 0.9)));
    });
    fsUpdate();
  }

  window.addEventListener("resize", fsUpdate);
  register("fs-open", fsOpen);
  register("fs-close", fsClose);
  register("fs-next", function () { fsPage(1); });
  register("fs-prev", function () { fsPage(-1); });

  // 端末に一時的に置いた情報を消す。診療の記録はサーバーにあり、ここでは消さない。
  function clearTransient() {
    hidden = null;
    fsClose();
    try {
      // 患者様の情報は残さない。ただし「cv.pref.」で始まる端末の設定（使うマイクなど。患者様の情報ではない）は残す。
      // これを一緒に消すと、患者様を開くたびにマイクの選択が消えて既定の機器に戻る（G14p）。
      var keep = {};
      for (var i = 0; i < localStorage.length; i++) { var k = localStorage.key(i); if (k.indexOf("cv.pref.") === 0) keep[k] = localStorage.getItem(k); }
      sessionStorage.clear(); localStorage.clear();
      Object.keys(keep).forEach(function (k) { localStorage.setItem(k, keep[k]); });
    } catch (e) { /* 使えなくてもよい */ }
  }

  register("hide-toggle", function () { if (hidden) restore(); else hide(); });
  register("clear-transient", clearTransient);
  register("pick-patient", function () { clearTransient(); location.href = "/clinic"; });

  // ボタン3は隠す・戻す。ボタン1・2は、録音と声の窓が register("button1") などで足す。
  register("button3", function () { run("hide-toggle"); });

  window.CVActions = { register: register, run: run, isHidden: isHidden };
})();
