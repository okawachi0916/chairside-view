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

  // 患者様を固定した録音の間は、次の患者様へ進めない
  CVActions.register("pick-patient", function () {
    var r = rec();
    if (r && r.locked()) { r.toast("録音中は次の患者様へ進めません。先に録音を止めてください", 4000); return; }
    CVActions.run("clear-transient");
    location.href = "/";
  });
})();
