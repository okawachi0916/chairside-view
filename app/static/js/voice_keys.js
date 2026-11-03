// 3つのボタンの2回押し判定と帯。3つのボタンで同じものを使う。
(function () {
  const BAND_TEXT = {
    1: "もう一度【REC】を押したら録音がはじまります",
    2: "もう一度【操】を押したら声の指示を受け付けます",
    3: "もう一度【隠】を押したら画面を隠します",
  };

  function keyName(e) {
    const parts = [];
    if (e.ctrlKey) parts.push("Ctrl");
    if (e.altKey) parts.push("Alt");
    if (e.shiftKey) parts.push("Shift");
    if (e.metaKey) parts.push("Meta");
    const k = /^(Control|Shift|Alt|Meta)$/.test(e.key) ? "" : (e.code || e.key);
    if (k) parts.push(k.replace(/^Key/, ""));
    return parts.join("+");
  }

  async function init(opts) {
    // opts: { onKey(name), onAction(n), onCombo(info) 省略可: ボタン1と2の同時押し, isActive(n) -> 1回で止まる状態か, band: 帯の要素, texts }
    const cfg = await (await fetch("/config/keys.json")).json();
    const keys = { [cfg.button1]: 1, [cfg.button2]: 2, [cfg.button3]: 3 };
    const texts = Object.assign({}, BAND_TEXT, opts.texts || {});
    const band = opts.band;
    const comboMs = Number(cfg.combo_ms) || 300; // ボタン1と2が、この時間以内に続いたら同時押し
    let pending = null; // { n, timer, t }
    let shown = null;   // { n, until, tick, hide }

    function hideBand() {
      if (shown) { clearInterval(shown.tick); clearTimeout(shown.hide); shown = null; }
      band.hidden = true;
    }
    function clearPending() {
      if (pending) { clearTimeout(pending.timer); pending = null; }
    }
    function showBand(n) {
      const until = Date.now() + cfg.double_press_ms;
      band.hidden = false;
      const text = band.querySelector("[data-band-text]");
      const left = band.querySelector("[data-band-left]");
      text.textContent = (opts.textFor && opts.textFor(n)) || texts[n];
      const paint = () => { left.textContent = Math.max(0, Math.ceil((until - Date.now()) / 1000)) + "秒"; };
      paint();
      shown = { n, until, tick: setInterval(paint, 200), hide: setTimeout(hideBand, cfg.double_press_ms) };
    }
    function act(n) {
      clearPending();
      hideBand();
      opts.onAction(n);
    }

    window.addEventListener("keydown", (e) => {
      const name = keyName(e);
      if (!name) return;
      if (e.repeat) { if (keys[name]) e.preventDefault(); return; } // 押し続けは1回
      if (opts.onKey) opts.onKey(name);
      const n = keys[name];
      if (!n) return;
      e.preventDefault();
      if (opts.isActive && opts.isActive(n)) return act(n); // 録音中などは1回で止まる
      const now = Date.now();
      // ボタン1と2の同時押し: 1つ目はまだ帯も出ていない1回目の押しなので、何も動いていない。帯を消して「戻して」だけを動かす
      if (opts.onCombo && pending && pending.n !== n && pending.n <= 2 && n <= 2 && now - pending.t <= comboMs) {
        const gap = now - pending.t, first = pending.n;
        clearPending();
        hideBand();
        return opts.onCombo({ first, second: n, gap_ms: gap });
      }
      if (shown && shown.n === n) return act(n);            // 帯が出ている間の2回目
      if (pending && pending.n === n) return act(n);        // 0.4秒以内の2回目: 帯なしで動く
      clearPending();
      hideBand();                                            // 別のボタンなら切り替え
      pending = { n, t: now, timer: setTimeout(() => { pending = null; showBand(n); }, cfg.quick_press_ms) };
    });
    return cfg;
  }

  window.VoiceKeys = { init, keyName };
})();
