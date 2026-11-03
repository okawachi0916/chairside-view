// 予約一覧など、ユニットの画面以外で【REC】を使えるようにする。録音は親の画面 (/app) が持つ。
(function () {
  function rec() {
    try { return window.parent !== window ? window.parent.CVRec : null; } catch (e) { return null; }
  }
  if (!window.VoiceKeys) return;
  if (!rec()) { // 親の画面が無い: ボタン1で /app の中に同じ画面を開いて録音を始める
    var st = document.createElement("style");
    st.textContent = "[hidden]{display:none!important}";
    document.head.appendChild(st);
    var skip = new URLSearchParams(location.search).get("noapp") === "1";
    VoiceKeys.init({
      band: (function () {
        var b = document.createElement("div");
        b.hidden = true;
        b.setAttribute("style", "position:absolute;top:0;left:0;right:0;z-index:50;background:#1f3b73;color:#fff;padding:14px 24px;font-size:22px;display:flex;justify-content:space-between");
        b.innerHTML = "<span data-band-text></span><span data-band-left></span>";
        document.body.appendChild(b);
        return b;
      })(),
      isActive: function () { return false; },
      onAction: function (n) {
        if (n === 1 && !skip) location.href = "/app?start=1&go=" + encodeURIComponent(window.CVReturn ? window.CVReturn.here() : location.pathname + location.search);
        else if (n === 2 && window.CVKeyHooks && window.CVKeyHooks[2]) window.CVKeyHooks[2]();
      },
    });
    return;
  }
  var band = document.createElement("div");
  band.hidden = true;
  band.setAttribute("style", "position:fixed;top:0;left:0;right:0;z-index:50;background:#1f3b73;color:#fff;padding:14px 24px;font-size:22px;display:flex;justify-content:space-between");
  band.innerHTML = "<span data-band-text></span><span data-band-left></span>";
  document.body.appendChild(band);
  new MutationObserver(function () { /* hidden 属性だけで見え方を決める */ }).observe(band, { attributes: true });
  var style = document.createElement("style");
  style.textContent = "[hidden]{display:none!important}";
  document.head.appendChild(style);
  VoiceKeys.init({
    band: band,
    isActive: function (n) {
      var r = rec();
      if (n === 2) return !!(window.CVActive && window.CVActive[2] && window.CVActive[2]()); // 声の指示を聞いている間は1回で止まる
      return n === 1 && !!(r && r.active());
    },
    onAction: function (n) {
      var r = rec();
      if (n === 1 && r) r.press();
      else if (n === 2 && window.CVKeyHooks && window.CVKeyHooks[2]) window.CVKeyHooks[2](); // 下書きの画面の声（draft.js）
    },
  });
})();
