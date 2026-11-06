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
    let shown = null;   // { n, until, tick, hide, t }
    const held = {};    // いま押したままのボタン { n: 押した時刻 }（離した信号が来るまで）
    const codeOf = (name) => name.split("+").pop();
    const byCode = {};
    Object.keys(keys).forEach((name) => { byCode[codeOf(name)] = { n: keys[name], name }; });

    // 実物のボタンが、どんな信号をどんな順で送るかの記録（ボタン1〜3のキーだけ。軽い）
    function keyLog(e, kind, n, name) {
      if (e.__cvKeyLogged) return;
      e.__cvKeyLogged = true;
      try {
        fetch("/voice/keylog", { method: "POST", headers: { "Content-Type": "application/json" }, keepalive: true,
          body: JSON.stringify({ kind, key: name, button: n, repeat: !!e.repeat, t: Date.now() }) }).catch(() => {});
      } catch (err) { /* 記録できなくても操作は続ける */ }
    }

    function hideBand() {
      if (shown) { clearInterval(shown.tick); clearTimeout(shown.hide); shown = null; }
      band.hidden = true;
    }
    function clearPending() {
      if (pending) { clearTimeout(pending.timer); pending = null; }
    }
    function showBand(n, t) {
      const until = Date.now() + cfg.double_press_ms;
      band.hidden = false;
      const text = band.querySelector("[data-band-text]");
      const left = band.querySelector("[data-band-left]");
      text.textContent = (opts.textFor && opts.textFor(n)) || texts[n];
      const paint = () => { left.textContent = Math.max(0, Math.ceil((until - Date.now()) / 1000)) + "秒"; };
      paint();
      shown = { n, until, t: t || Date.now(), tick: setInterval(paint, 200), hide: setTimeout(hideBand, cfg.double_press_ms) };
    }
    function act(n) {
      clearPending();
      hideBand();
      opts.onAction(n);
    }

    window.addEventListener("keyup", (e) => {
      const b = byCode[e.code];
      if (!b) return;
      delete held[b.n];
      keyLog(e, "keyup", b.n, b.name);
    });
    window.addEventListener("blur", () => { for (const k in held) delete held[k]; }); // 離した信号を受け損ねた押したままを残さない

    window.addEventListener("keydown", (e) => {
      const name = keyName(e);
      if (!name) return;
      if (keys[name]) keyLog(e, "keydown", keys[name], name);
      if (e.repeat) { if (keys[name]) e.preventDefault(); return; } // 押し続けは1回
      if (opts.onKey) opts.onKey(name);
      const n = keys[name];
      if (!n) return;
      held[n] = Date.now();
      e.preventDefault();
      if (opts.isActive && opts.isActive(n)) return act(n); // 録音中などは1回で止まる
      const now = Date.now();
      // ボタン1と2の同時押し: 1つ目はまだ帯も出ていない1回目の押しなので、何も動いていない。帯を消して「戻して」だけを動かす
      // 同時押しは、①1つ目をまだ離していない ②1つ目から combo_ms 以内（帯が出ていても）、のどちらか。実物のボタンは信号を順に送ることがある
      const f = pending || shown; // 1つ目（まだ動いていない1回目の押し）
      if (opts.onCombo && f && f.n !== n && f.n <= 2 && n <= 2 && (held[f.n] !== undefined || now - f.t <= comboMs)) {
        const gap = now - f.t, first = f.n;
        clearPending();
        hideBand();
        return opts.onCombo({ first, second: n, gap_ms: gap });
      }
      if (shown && shown.n === n) return act(n);            // 帯が出ている間の2回目
      if (pending && pending.n === n) return act(n);        // 0.4秒以内の2回目: 帯なしで動く
      clearPending();
      hideBand();                                            // 別のボタンなら切り替え
      pending = { n, t: now, timer: setTimeout(() => { pending = null; showBand(n, now); }, cfg.quick_press_ms) };
    });
    return cfg;
  }

  window.VoiceKeys = { init, keyName };
})();

/* マイクが使えなかったとき、何が起きたかと、次にすることを日本語で返す共通の部品（G14p）。
   録音・声の操作・下書き・状況の画面が同じ言葉を出す。機器の名前や1台のマイクには決め打ちしない（ブラウザが返す失敗の種類で分ける）。
   CVMicError.explain(e) → Promise<文字>   失敗（getUserMedia の例外）の説明
   CVMicError.unsupported() → 文字          navigator.mediaDevices が無いときの説明
   CVMicError.silent(stream) → 文字 or ""   つないだが、ミュート・無効で音が来ない状態の説明 */
(function () {
  var USE_BLOCKED = "ブラウザがこのサイトのマイクを止めています。アドレス欄の左のアイコン →「マイク」→「許可」に変えて、ページを開き直してください";
  var USE_ASK = "マイクの許可が出ていません。確認の表示が出たら「許可」を選んでください（出ないときはアドレス欄の左のアイコン →「マイク」→「許可」）";

  function unsupported() {
    if (window.isSecureContext === false) {
      return "この接続（http の別のパソコンから）ではブラウザがマイクを使わせません。マイクのあるパソコンで http://localhost:ポート番号/ を開いてください";
    }
    return "このブラウザではマイクを使えません。Edge か Chrome の新しい版で開いてください";
  }

  function explain(e) {
    var name = (e && e.name) || "";
    if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
      if (navigator.permissions && navigator.permissions.query) {
        return navigator.permissions.query({ name: "microphone" }).then(function (st) {
          return st.state === "denied" ? USE_BLOCKED : USE_ASK;
        }).catch(function () { return USE_BLOCKED; });
      }
      return Promise.resolve(USE_BLOCKED);
    }
    if (name === "NotFoundError" || name === "OverconstrainedError" || name === "DevicesNotFoundError") {
      return Promise.resolve("マイクが見つかりません。USB の差し込みと、Windows の「既定の録音機器」を確かめてください");
    }
    if (name === "NotReadableError" || name === "AbortError" || name === "TrackStartError") {
      return Promise.resolve("マイクを使えません: ほかのアプリがつかんでいるか、機器が応答していません。Zoom・OBS・Discord・Voicemeeter など音を使うアプリを閉じて、もう一度お試しください");
    }
    return Promise.resolve("マイクを使えません（" + (name || (e && e.message) || "原因不明") + "）");
  }

  function silent(stream) {
    var tracks = stream && stream.getAudioTracks ? stream.getAudioTracks() : [];
    if (!tracks.length) return "マイクから音の通り道が来ません。機器を確かめてください";
    if (tracks.every(function (t) { return t.readyState === "ended"; })) return "マイクが外れました。差し込みを確かめてください";
    if (tracks.every(function (t) { return t.enabled === false; })) return "マイクが無効になっています";
    if (tracks.every(function (t) { return t.muted; })) return "マイクがミュートになっています。マイク本体のミュートや、Windows のマイクの音量を確かめてください";
    return "";
  }

  // 録音している間の音の大きさを測る。機器がミュート・別の機器・音の入らない仮想機器のとき、音が全く来ない（ほぼ 0）ことで分かる。
  // 無音の録音を文字起こしに回すと「ご視聴ありがとうございました」のような幻の言葉が出るので、先に止めて理由を知らせる。
  var SILENT_PEAK = 0.001;
  function label(stream) {
    var t = stream && stream.getAudioTracks ? stream.getAudioTracks()[0] : null;
    return (t && t.label) || "（名前が分かりません）";
  }
  function meter(stream) {
    var peak = 0, timer = null, ctx = null;
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      ctx = new AC();
      var an = ctx.createAnalyser();
      an.fftSize = 1024;
      ctx.createMediaStreamSource(stream).connect(an);
      var buf = new Float32Array(an.fftSize);
      timer = setInterval(function () {
        an.getFloatTimeDomainData(buf);
        for (var i = 0; i < buf.length; i++) { var v = Math.abs(buf[i]); if (v > peak) peak = v; }
      }, 50);
    } catch (e) { peak = -1; } // 測れないときは、無音とは言わない
    return {
      peak: function () { return peak; },
      silent: function () { return peak >= 0 && peak < SILENT_PEAK; },
      label: function () { return label(stream); },
      stop: function () { clearInterval(timer); if (ctx && ctx.state !== "closed") ctx.close().catch(function () {}); },
    };
  }
  function silentText(lbl) {
    return "マイクから音が入っていません（いま使っている機器: " + lbl + "）。マイクのミュート、Windows の既定の録音機器、"
      + "ブラウザのマイクの選択を確かめてください。/voice-test の「マイクの選択」で機器を選べます";
  }

  // 使うマイクは、/voice-test で選んだ機器（このブラウザの localStorage に機器の ID だけ保存）。選んでいなければブラウザの既定。
  // 選んだ機器が見つからないときは既定に戻す。どの画面も、マイクはここから開く（機器の名前は決め打ちしない）。
  var KEY = "cv.micId";
  function chosen() { try { return localStorage.getItem(KEY) || ""; } catch (e) { return ""; } }
  function choose(id) { try { if (id) localStorage.setItem(KEY, id); else localStorage.removeItem(KEY); } catch (e) { /* 保存できなくても動く */ } }
  function open() {
    var md = navigator.mediaDevices, id = chosen();
    if (!id) return md.getUserMedia({ audio: true });
    return md.getUserMedia({ audio: { deviceId: { exact: id } } }).catch(function (e) {
      if (e && (e.name === "OverconstrainedError" || e.name === "NotFoundError")) return md.getUserMedia({ audio: true });
      throw e;
    });
  }

  window.CVMicError = { open: open, chosen: chosen, choose: choose, explain: explain, unsupported: unsupported, silent: silent, meter: meter, silentText: silentText, label: label };
})();
