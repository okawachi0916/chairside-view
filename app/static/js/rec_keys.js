// 予約一覧など、ユニットの画面以外で【REC】を使えるようにする。録音は親の画面 (/app) が持つ。
(function () {
  function rec() {
    try { return window.parent !== window ? window.parent.CVRec : null; } catch (e) { return null; }
  }
  if (!rec() || !window.VoiceKeys) return;
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
    isActive: function (n) { var r = rec(); return n === 1 && !!(r && r.active()); },
    onAction: function (n) { var r = rec(); if (n === 1 && r) r.press(); },
  });
})();
