// 写真の欄の「スマホ」ボタン。QR を出し、残り時間を数える。
// スマホから入った写真を画面に取り込む見張りは、QR の窓とは別に、ユニットの画面が開いている間ずっと動かす（G19m。QR を閉じたあとの写真も出る）。
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

  var cur = null; // { timer, expires }

  function apptNow() { return new URLSearchParams(location.search).get("appt"); }
  function mmss(s) { return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }

  function close() {
    if (cur) { clearInterval(cur.timer); cur = null; }
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
  }

  // 写真の数の見張り。画面が開いている間ずっと動く。数が変わったら画面を読み直す（番号付きで欄に出る）。患者様が替わったら数え直す
  var watch = { appt: null, base: null };
  function watchPhotos() {
    var appt = apptNow();
    if (!appt) return;
    if (watch.appt !== appt) { watch.appt = appt; watch.base = null; }
    fetch("/api/phone-photos/count?appt=" + appt, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      if (watch.appt !== appt) return;
      if (watch.base === null) { watch.base = d.count; return; }
      if (d.count !== watch.base) {
        watch.base = d.count;
        var role = /role-hygienist/.test(document.body.className) ? "hygienist" : "doctor";
        if (window.cv && window.cv.openUnit && !window.CVActions.isHidden()) window.cv.openUnit(appt, role);
      }
    }).catch(function () { /* つながらないときは次の回に */ });
  }
  setInterval(watchPhotos, 2500);
  watchPhotos();

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
      .then(function (r) {
        if (r.ok) return r.json();
        return r.json().catch(function () { return {}; }).then(function (j) { var e = new Error(r.status); e.detail = j.detail; throw e; });
      })
      .then(function (d) {
        if (!document.getElementById("phone-modal")) return;
        m.querySelector(".qr").innerHTML = d.svg;
        m.dataset.url = d.url;
        cur = { expires: d.expires_at };
        cur.timer = setInterval(paint, 500);
        paint();
      })
      .catch(function (e) { m.querySelector(".left").textContent = (e && e.detail) || "QRを作れませんでした"; });
  }

  document.addEventListener("click", function (e) {
    var b = e.target.closest('[data-action="phone"]');
    if (b) { e.stopPropagation(); open(); }
  });
  window.CVPhone = { open: open, close: close };
  if (window.CVActions) CVActions.register("phone-open", open);
})();
