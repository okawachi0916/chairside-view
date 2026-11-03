// 口腔内写真の欄の「スマホ」ボタン。QR を出し、残り時間を数え、スマホから入った写真を画面に取り込む。
(function () {
  var style = document.createElement("style");
  style.textContent =
    "#phone-modal{position:fixed;inset:0;z-index:80;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center}" +
    "#phone-modal .box{background:#fff;color:#1c2a33;border-radius:12px;padding:24px 32px;text-align:center;min-width:360px}" +
    "#phone-modal h2{margin:0 0 12px;font-size:24px}" +
    "#phone-modal .qr svg{width:60vh;height:60vh;display:block;margin:0 auto 12px}" +
    "#phone-modal .left{font-size:28px;font-weight:700;margin:4px 0 12px}" +
    "#phone-modal .hint{font-size:16px;margin:0 0 14px;color:#4a5560}" +
    "#phone-modal button{font:inherit;font-size:20px;padding:8px 24px;margin:0 6px;border:2px solid #1f5fbf;border-radius:8px;background:#fff;color:#1f5fbf;cursor:pointer}";
  document.head.appendChild(style);

  var cur = null; // { timer, poll, expires, appt, count }

  function apptNow() { return new URLSearchParams(location.search).get("appt"); }
  function mmss(s) { return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }

  function close() {
    if (cur) { clearInterval(cur.timer); clearInterval(cur.poll); cur = null; }
    var m = document.getElementById("phone-modal");
    if (m) m.remove();
  }

  function paint() {
    var m = document.getElementById("phone-modal");
    if (!m || !cur) return;
    var left = Math.max(0, cur.expires - Math.floor(Date.now() / 1000));
    var gone = left <= 0;
    m.querySelector(".qr").hidden = gone;
    m.querySelector(".left").textContent = gone ? "期限が切れました" : "残り " + mmss(left);
    m.querySelector(".hint").textContent = gone ? "もう一度QRを出してください" : "スマホのカメラで読み取ってください";
    m.querySelector("[data-act=again]").hidden = !gone;
    m.dataset.left = String(left);
    if (gone) clearInterval(cur.poll);
  }

  function watchPhotos(appt) {
    var base = null;
    cur.poll = setInterval(function () {
      fetch("/api/phone-photos/count?appt=" + appt, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
        if (base === null) { base = d.count; return; }
        if (d.count !== base) { // スマホから写真が入った: 画面を読み直して、番号付きで欄に出す
          base = d.count;
          var role = /role-hygienist/.test(document.body.className) ? "hygienist" : "doctor";
          if (window.cv && window.cv.openUnit && !window.CVActions.isHidden()) window.cv.openUnit(appt, role);
        }
      }).catch(function () { /* つながらないときは次の回に */ });
    }, 2500);
  }

  function open() {
    var appt = apptNow();
    if (!appt) return;
    close();
    var m = document.createElement("div");
    m.id = "phone-modal";
    m.innerHTML = '<div class="box"><h2>スマホで写真をやり取り</h2><div class="qr"></div>' +
      '<div class="left"></div><p class="hint"></p>' +
      '<button type="button" data-act="again" hidden>QRをもう一度出す</button><button type="button" data-act="close">閉じる</button></div>';
    m.addEventListener("click", function (e) {
      var a = e.target.closest("[data-act]");
      if (a && a.dataset.act === "close") close();
      else if (a && a.dataset.act === "again") open();
    });
    document.body.appendChild(m);
    fetch("/api/phone-link", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ appt: Number(appt) }) })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        if (!document.getElementById("phone-modal")) return;
        m.querySelector(".qr").innerHTML = d.svg;
        m.dataset.url = d.url;
        cur = { expires: d.expires_at };
        cur.timer = setInterval(paint, 500);
        watchPhotos(appt);
        paint();
      })
      .catch(function () { m.querySelector(".left").textContent = "QRを作れませんでした"; });
  }

  document.addEventListener("click", function (e) {
    var b = e.target.closest('[data-action="phone"]');
    if (b) { e.stopPropagation(); open(); }
  });
  // どの画面からも押せる固定のボタン（歯科医師・歯科衛生士の画面と全画面。口腔内写真の全画面は枠の中にも置く）
  if (document.body.getAttribute("data-kind") === "unit" && !document.querySelector(".phone-fab")) {
    var fab = document.createElement("button");
    fab.type = "button";
    fab.className = "phone-fab";
    fab.setAttribute("data-action", "phone");
    fab.textContent = "スマホで写真をやり取り";
    document.body.appendChild(fab);
  }
  window.CVPhone = { open: open, close: close };
  if (window.CVActions) CVActions.register("phone-open", open);
})();
