// ユニットの画面から、親の画面 (/app) の録音を動かす。録音そのものは親が持つので、この画面が替わっても切れない。
(function () {
  function rec() {
    try { return window.parent !== window ? window.parent.CVRec : null; } catch (e) { return null; }
  }
  function say(text) {
    var h = document.getElementById("heard");
    if (h) { h.textContent = text; h.title = text; }
    document.body.dataset.heard = text;
  }

  window.CVActive = window.CVActive || {};
  window.CVActive[1] = function () { var r = rec(); return !!(r && r.active()); }; // 録音中・OK待ちは1回で動く

  CVActions.register("button1", function () {
    var r = rec();
    if (r) r.press();
    else say("録音は /app から開いたときに使えます");
  });

  var style = document.createElement("style");
  style.textContent =
    "#memo-block{position:fixed;inset:0;z-index:90;background:var(--c-ink);display:flex;align-items:center;justify-content:center}" +
    "#memo-block .box{background:var(--c-surface);color:var(--c-ink);border-radius:var(--r-l);padding:var(--sp-8) var(--sp-10);max-width:640px}" +
    "#memo-block h2{margin:0 0 var(--sp-4);font-size:var(--fs-5)}" +
    "#memo-block p{margin:0 0 var(--sp-6);font-size:var(--fs-3);line-height:var(--lh-text)}" +
    "#memo-block button{font-family:inherit;font-size:var(--fs-4);font-weight:var(--fw-bold);padding:var(--sp-3) var(--sp-8);margin-right:var(--sp-4);border:2px solid var(--c-doctor);border-radius:var(--r-s);background:var(--c-surface);color:var(--c-doctor);cursor:pointer}" +
    "#memo-block button.main{background:var(--c-doctor);color:var(--c-surface)}";
  document.head.appendChild(style);

  // 下書きがあるまま次の患者様を開こうとしたら止める
  function blockDialog(memos, appt, leave) {
    var first = memos[0];
    var d = document.createElement("div");
    d.id = "memo-block";
    d.setAttribute("data-part", "memo-block");
    d.innerHTML = "<div class='box'><h2>確定していない診療メモがあります</h2>" +
      "<p>このまま次の患者様へ進むと、メモは下書きのまま残ります。</p>" +
      "<button type='button' class='main' data-action='memo-open'>メモを開く</button>" +
      "<button type='button' data-action='memo-later'>後で直す</button></div>";
    document.body.appendChild(d);
    d.querySelector("[data-action=memo-open]").addEventListener("click", function () {
      var here = encodeURIComponent(location.pathname + location.search);   // 記録したあと、この診療の画面へ戻る
      location.href = first.draft_id ? "/drafts/" + first.draft_id + "?back=" + here : "/recordings";
    });
    d.querySelector("[data-action=memo-later]").addEventListener("click", function () {
      fetch("/api/pending-memo/later", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ appt: Number(appt) }) })
        .then(function () { d.remove(); leave(); }).catch(function () { d.remove(); leave(); });
    });
  }

  // 患者様を固定した録音の間は、次の患者様へ進めない。確定していない診療メモがあれば止める
  CVActions.register("pick-patient", function () {
    var r = rec();
    if (r && r.locked()) { r.toast("録音中は次の患者様へ進めません。先に録音を止めてください", 4000); return; }
    var appt = new URLSearchParams(location.search).get("appt");
    function leave() { CVActions.run("clear-transient"); location.href = "/"; }
    if (!appt) return leave();
    fetch("/api/pending-memo?appt=" + appt, { cache: "no-store" }).then(function (x) { return x.json(); }).then(function (d) {
      if (d.memos && d.memos.length) blockDialog(d.memos, appt, leave);
      else leave();
    }).catch(leave);
  });
})();
