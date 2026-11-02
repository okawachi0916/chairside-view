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
  }

  // 端末に一時的に置いた情報を消す。診療の記録はサーバーにあり、ここでは消さない。
  function clearTransient() {
    hidden = null;
    try { sessionStorage.clear(); localStorage.clear(); } catch (e) { /* 使えなくてもよい */ }
  }

  register("hide-toggle", function () { if (hidden) restore(); else hide(); });
  register("clear-transient", clearTransient);
  register("pick-patient", function () { clearTransient(); location.href = "/"; });

  // ボタン3は隠す・戻す。ボタン1・2は、録音と声の窓が register("button1") などで足す。
  register("button3", function () { run("hide-toggle"); });

  window.CVActions = { register: register, run: run, isHidden: isHidden };
})();
