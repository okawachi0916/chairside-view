// 新しい版が入ったら画面の下に横いっぱいの帯「新しい版があります　更新」を出す。勝手には読み直さず、押したときだけ読み直す。
// 同じブラウザの全部の画面（ほかのタブ）にも知らせる。録音・下書きの途中は、終わるまで待ってから読み直す。
(function () {
  if (window.__cvUpdater) return;
  window.__cvUpdater = true;

  var shown = window.CV_VERSION;
  var url = window.CV_VERSION_URL || "/version";
  var dirty = false;
  var info = null;
  var btn = null;
  var waiting = null;
  var ch = null;
  try { ch = window.BroadcastChannel ? new BroadcastChannel("cv-update") : null; } catch (e) { ch = null; }
  var isTop = true;
  try { isTop = window.top === window; } catch (e) { isTop = false; }

  // 下書きを直している途中の印（入力があったら、その画面を離れるまで待たせる）
  document.addEventListener("input", function () {
    if (/^\/(drafts|fix)\b/.test(location.pathname)) dirty = true;
  }, true);

  function ownBusy() {
    try {
      if (window.CVRec && window.CVRec.mode && window.CVRec.mode() !== "idle") return true; // 録音中・保存中
    } catch (e) { /* 録音の部品が無い */ }
    return dirty || !!document.querySelector(".perio-editing");
  }

  function busy() {
    if (ownBusy()) return true;
    var fr = document.querySelectorAll("iframe");
    for (var i = 0; i < fr.length; i++) {
      try {
        var u = fr[i].contentWindow.CVUpdate;
        if (u && u.busy()) return true;
      } catch (e) { /* ほかの出どころの枠は見ない */ }
    }
    return false;
  }

  window.CVUpdate = { busy: ownBusy, version: function () { return shown; } };
  if (!isTop) return; // 出すのも知らせるのも、いちばん外の画面だけ。中の画面は外が読み直すと一緒に新しくなる

  function reloadNow(i) {
    window.name = "cv-updated:" + (i.time || ""); // タブにだけ残る。sessionStorage は患者様を開くたびに消えるので使わない
    var inner = document.getElementById("inner"); // 録音の親の画面は、中の画面を開いたまま読み直す
    if (inner) {
      try {
        var l = inner.contentWindow.location, p = l.pathname + l.search;
        if (!/^\/app/.test(p) && p !== "/") { location.href = "/app?go=" + encodeURIComponent(p); return; }
        if (p === "/") { location.href = "/app"; return; }
      } catch (e) { /* そのまま読み直す */ }
    }
    location.reload();
  }

  function apply(i) {
    if (waiting) return;
    if (btn) btn.classList.toggle("waiting", busy());
    waiting = setInterval(function () {
      if (busy()) { if (btn) btn.classList.add("waiting"); return; }
      clearInterval(waiting);
      waiting = null;
      setTimeout(function () { // 止めた直後の保存や転送が始まるのを待ってから
        if (busy()) { apply(i); return; }
        reloadNow(i);
      }, 800);
    }, 500);
  }

  function show(i) {
    info = i;
    if (!btn) {
      btn = document.createElement("button");
      btn.type = "button";
      btn.id = "cv-update";
      btn.textContent = "新しい版があります　更新";
      btn.addEventListener("click", function () {
        if (ch) { try { ch.postMessage({ v: info.v, time: info.time }); } catch (e) { /* 知らせられない */ } }
        apply(info);
      });
      document.body.appendChild(btn);
    }
    btn.hidden = false;
    lift();
  }

  // 下の質問のボタン（#num-questions）が出ているあいだは、その上に帯を出す。中の画面にあっても見る
  function lift() {
    if (!btn || btn.hidden) return;
    var top = 0, docs = [document], fr = document.querySelectorAll("iframe");
    for (var i = 0; i < fr.length; i++) { try { docs.push(fr[i].contentDocument); } catch (e) { /* 見ない */ } }
    docs.forEach(function (d) {
      var q = d && d.getElementById("num-questions");
      if (!q || !q.children.length) return;
      var r = q.getBoundingClientRect();
      if (r.height > 0) top = Math.max(top, window.innerHeight - r.top + 4);
    });
    btn.style.bottom = top + "px";
  }
  setInterval(lift, 300);

  function check() {
    fetch(url, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      if (d && d.v && d.v !== shown) show(d);
    }).catch(function () { /* つながらないときは次の回に */ });
  }

  if (ch) ch.onmessage = function (e) { if (e.data && e.data.v) { info = e.data; apply(e.data); } };
  setInterval(check, window.CV_POLL_MS || 30000);

  // 読み直したあと、版の時刻を3秒だけ出す
  if (String(window.name).indexOf("cv-updated:") === 0) {
    var t = window.name.slice("cv-updated:".length);
    window.name = "";
    var d = document.createElement("div");
    d.id = "cv-updated";
    d.textContent = "更新しました " + t;
    document.body.appendChild(d);
    setTimeout(function () { d.remove(); }, 3000);
  }
})();
