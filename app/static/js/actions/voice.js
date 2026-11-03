// 声の操作。ボタン2で受付を始め、聞き取った言葉を手元で照合して、操作の入口 CVActions.run に渡す。
// 質問と無関係な言葉は画面を動かさない。受付の画面では読み込まない。
(function () {
  var MAX_MS = 6000;
  var q = new URLSearchParams(location.search);
  var rec = null; // 録音中の { recorder, stream, timer, stoppedAt }

  var style = document.createElement("style");
  style.textContent =
    "#heard{position:fixed;top:60px;right:14px;z-index:40;font-size:14px;max-width:560px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;background:rgba(255,255,255,.94);color:#222;border:1px solid #888;border-radius:5px;padding:1px 10px}#heard:empty{display:none}" +
    "#say-list-btn{flex:none;font:inherit;font-size:13px;padding:3px 10px;margin-right:10px;border:1px solid #fff;border-radius:5px;background:transparent;color:#fff;cursor:pointer}" +
    "#say-list{position:fixed;top:64px;right:12px;z-index:60;width:520px;max-height:70vh;overflow:auto;background:#fff;color:#222;border:2px solid #444;border-radius:8px;padding:10px 16px;font-size:16px}" +
    "#say-list[hidden]{display:none}#say-list li{padding:2px 0}" +
    "#typed-box{position:fixed;right:12px;bottom:12px;z-index:60;background:#fff;border:2px solid #444;border-radius:8px;padding:8px;display:flex;gap:6px}" +
    "#typed-box input{font:inherit;font-size:16px;width:320px}" +
    ".topbar .mic{flex:none;min-width:30px}.topbar .mic.rec{fill:#ff4d4d;animation:cvblink .8s infinite}.topbar .mic.none{fill:#999}" +
    "@keyframes cvblink{50%{opacity:.15}}" +
    "body[data-numbers] .ph .no{display:none}" +
    "#num-dim{position:fixed;left:0;top:0;right:0;bottom:0;z-index:30;background:rgba(0,0,0,.55);pointer-events:none}" +
    ".num-badge{position:fixed;z-index:35;transform:translate(-50%,-50%);height:76px;padding:0 22px;border-radius:38px;box-sizing:border-box;white-space:nowrap;" +
    "background:#ffd43b;color:#111;border:4px solid #fff;box-shadow:0 2px 10px rgba(0,0,0,.6);" +
    "font-size:48px;font-weight:800;line-height:68px;text-align:center;pointer-events:none}" +
    "#num-questions{position:fixed;z-index:35;left:0;right:0;bottom:36px;display:flex;justify-content:center;gap:20px;pointer-events:none}" +
    ".q-btn{background:#fff;color:#111;border:3px solid #ffd43b;border-radius:14px;padding:12px 26px;font-size:32px;font-weight:700}" +
    "#num-band{position:fixed;z-index:36;left:0;top:0;right:0;box-sizing:border-box;display:flex;align-items:center;gap:20px;padding:0 24px;background:rgba(8,10,14,.94);pointer-events:none;overflow:hidden}" +
    ".ex-chip{color:#fff;font-size:30px;font-weight:700;white-space:nowrap;border:2px solid #ffd43b;border-radius:10px;padding:2px 16px;line-height:1.3}" +
    ".ex-msg{color:#ffd43b;font-size:28px;font-weight:700}" +
    ".say-list-body h3{margin:14px 0 4px;font-size:22px}.say-list-body ul{margin:0 0 6px;padding-left:28px;font-size:22px;line-height:1.5}" +
    "body[data-numbers] .ph .no{display:none}";
  document.head.appendChild(style);

  var heard = document.createElement("div");
  heard.id = "heard";
  document.body.appendChild(heard);

  function micEl() { return document.querySelector(".topbar .mic"); }
  function setMic(state) {
    var m = micEl();
    if (!m) return;
    m.setAttribute("data-state", state);
    m.setAttribute("class", "mic" + (state === "rec" ? " rec" : state === "none" ? " none" : ""));
  }
  function say(text) {
    var h = document.getElementById("heard");
    if (h) { h.textContent = text; h.title = text; }
    document.body.dataset.heard = text;
  }

  // 上の行に「聞き取った言葉」と「いま言える言葉」を入れる。画面を読み直すたびに入れ直す。
  function ensureUi() {
    var top = document.querySelector(".topbar");
    var mic = micEl();
    if (!top || !mic || top.querySelector("#say-list-btn")) return;
    var b = document.createElement("button");
    b.type = "button";
    b.id = "say-list-btn";
    b.textContent = "言える言葉";
    b.addEventListener("click", function () { CVActions.run("say-list-open"); });
    top.insertBefore(b, mic);
    if (rec) setMic("rec");
  }

  // 言える言葉の一覧は全画面で出す（番号 8 でも開く）。中身は config/examples.json
  function openSayList() {
    var done = function (ex) {
      CVActions.run("fs-close");
      var p = document.createElement("section");
      p.className = "fs-panel";
      p.setAttribute("data-fs-panel", "say-list");
      var head = document.createElement("div");
      head.className = "fs-head";
      var h = document.createElement("h2");
      h.textContent = "言える言葉";
      head.appendChild(h);
      var sp = document.createElement("span");
      sp.className = "fs-spacer";
      head.appendChild(sp);
      [["fs-prev", "前のページ"], ["fs-next", "次のページ"], ["fs-close", "もとに戻す"]].forEach(function (x) {
        var btn = document.createElement("button");
        btn.type = "button";
        btn.setAttribute("data-action", x[0]);
        btn.textContent = x[1];
        btn.hidden = x[0] !== "fs-close";
        head.appendChild(btn);
      });
      p.appendChild(head);
      var body = document.createElement("div");
      body.className = "fs-scroll say-list-body";
      (ex.say_list || []).forEach(function (sec) {
        var t = document.createElement("h3");
        t.textContent = sec.title;
        var ul = document.createElement("ul");
        sec.words.forEach(function (w) { var li = document.createElement("li"); li.textContent = w; ul.appendChild(li); });
        body.appendChild(t);
        body.appendChild(ul);
      });
      p.appendChild(body);
      document.getElementById("view").appendChild(p);
      document.body.classList.add("fs-mode");
    };
    if (exCfg) done(exCfg); else loadExamples().then(function (ex) { done(ex || {}); });
  }
  CVActions.register("say-list-open", openSayList);

  // ---- 口腔内写真（番号で呼ぶ）----
  function photoPanel() { return document.querySelector('[data-fs-panel="intraoral-photos"]'); }
  function photoItems() {
    var p = photoPanel();
    if (p) return p.querySelectorAll(".fs-item");
    var t = document.querySelector('template[data-fs="intraoral-photos"]');
    return t ? t.content.querySelectorAll(".fs-item") : [];
  }
  function selectPhotos(items) {
    var p = photoPanel();
    if (!p || !items.length) return;
    var box = p.querySelector(".fs-big-box");
    box.textContent = "";
    p.querySelectorAll(".fs-item").forEach(function (el) { el.classList.toggle("sel", items.indexOf(el) >= 0); });
    items.forEach(function (it) {
      var fig = document.createElement("figure");
      fig.className = "fs-fig";
      fig.setAttribute("data-n", it.dataset.n);
      var img = document.createElement("img");
      img.src = it.dataset.src;
      img.alt = "";
      var cap = document.createElement("figcaption");
      cap.textContent = "写真 " + it.dataset.n + " " + it.dataset.date;
      fig.appendChild(img);
      fig.appendChild(cap);
      box.appendChild(fig);
    });
    items[0].scrollIntoView({ block: "nearest" });
  }
  function byNumber(n) {
    var found = null;
    photoItems().forEach(function (it) { if (Number(it.dataset.n) === n) found = it; });
    return found;
  }
  // 部品を全画面にする。マウスで「全画面」を押したときと同じ道（view.js の click → fs-open）を通す。
  // 声で開いても、マウスで開いても、まったく同じ画面になる。全画面のボタンが無い部品だけ、入口を直接呼ぶ。
  function openPart(key) {
    var btn = document.querySelector('[data-part="' + key + '"] [data-action="fullscreen"]');
    if (btn) btn.click();
    else window.CVActions.run("fs-open", key);
  }
  // 番号の写真を左に出す。無い番号があれば何も変えず、言い方を返す。
  function showPhotos(numbers) {
    var list = [], bad = [];
    (numbers || []).forEach(function (n) {
      var it = byNumber(n);
      if (!it) bad.push(n);
      else if (list.indexOf(it) < 0) list.push(it);
    });
    if (bad.length || !list.length) return "その番号はありません";
    if (!photoPanel()) openPart("intraoral-photos");
    selectPhotos(list.map(function (it) { return byNumber(Number(it.dataset.n)); }));
    return "";
  }
  CVActions.register("photos-opened", function (p) {
    var items = p.querySelectorAll(".fs-item");
    if (items.length) selectPhotos([items[0]]); // 一覧は新しい順。一番新しい写真から
  });
  CVActions.register("fs-photo", function (el) { selectPhotos([el]); });
  CVActions.register("photo-show", showPhotos);
  CVActions.register("photo-list", function () { CVActions.run("fs-close"); });

  // ---- 暗くして例文を出す（聞き取り中だけ）----
  // いつもの画面: 画面全体を暗くして、全画面ボタンの上に「1番」、下に質問のボタンを出す。
  // 全画面の中: 見ている物は暗くせず、上の帯だけ暗くして、その画面で動く例文を出す。例文は config/examples.json の表。
  var numCfg = null, exCfg = null;
  function loadNumbers() {
    return fetch("/voice/numbers", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (c) { numCfg = c; document.body.dataset.numbersReady = "1"; return c; }).catch(function () { return null; });
  }
  function loadExamples() {
    return fetch("/voice/examples", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (c) { exCfg = c; return c; }).catch(function () { return null; });
  }
  function inView(el) {
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth;
  }
  // 番号を付ける先: ふだんの画面にある全画面ボタンと「言える言葉」。全画面の中には付けない
  function numberTargets() {
    if (!numCfg || window.CVActions.isHidden() || document.querySelector(".fs-panel")) return [];
    var out = [];
    Object.keys(numCfg.parts).forEach(function (part) {
      var btn = part === "say-list" ? document.getElementById("say-list-btn")
        : part === "change-role" ? document.querySelector('[data-action="change-role"]')
        : document.querySelector('[data-part="' + part + '"] [data-action="fullscreen"]');
      if (btn && inView(btn)) out.push({ n: numCfg.parts[part], key: part, el: btn });
    });
    return out;
  }
  function chip(parent, text, cls) {
    var c = document.createElement("span");
    c.className = cls;
    c.textContent = text;
    parent.appendChild(c);
    return c;
  }
  // いま開いている画面の名前（例文の表の引き方）
  function screenKey() {
    if (window.CVActions.isHidden()) return "hidden";
    var p = document.querySelector(".fs-panel");
    return p ? (p.getAttribute("data-fs-panel") || "") : "";
  }
  function bandWords(key) {
    var ex = exCfg || {};
    var sc = (ex.screens && ex.screens[key]) || ex.fallback || { words: ["戻して"], pages: true };
    var words = [];
    var panel = document.querySelector(".fs-panel");
    var next = panel && panel.querySelector('[data-action="fs-next"]');
    if (sc.pages && next && !next.hidden) words = words.concat(ex.page_words || []);
    return { words: words.concat(sc.words || []), message: sc.message || "" };
  }
  function showNumbers() {
    hideNumbers();
    var key = screenKey();
    if (key) { // 全画面（と隠した画面）: 上の帯だけ暗くする
      var top = document.querySelector(".topbar");
      var h = top ? Math.round(top.getBoundingClientRect().height) : 56;
      var band = document.createElement("div");
      band.id = "num-band";
      band.dataset.screen = key;
      band.style.height = Math.max(h, 52) + "px";
      var bw = bandWords(key);
      bw.words.forEach(function (w) { chip(band, "「" + w + "」", "ex-chip"); });
      if (bw.message) chip(band, bw.message, "ex-msg");
      document.body.appendChild(band);
      document.body.dataset.guide = key;
      return;
    }
    var list = numberTargets();
    if (!list.length) return;
    var dim = document.createElement("div");
    dim.id = "num-dim";
    document.body.appendChild(dim);
    list.forEach(function (x) {
      var r = x.el.getBoundingClientRect();
      var b = document.createElement("div");
      b.className = "num-badge";
      b.dataset.n = x.n;
      b.dataset.key = x.key;
      b.textContent = x.n + "番";
      b.style.left = Math.round(r.left + r.width / 2) + "px";
      b.style.top = Math.round(r.top + r.height / 2) + "px";
      document.body.appendChild(b);
    });
    var qs = (exCfg && exCfg.normal && exCfg.normal.questions) || [];
    if (qs.length) {
      var bar = document.createElement("div");
      bar.id = "num-questions";
      qs.forEach(function (q) { chip(bar, q, "q-btn"); });
      document.body.appendChild(bar);
    }
    document.body.dataset.numbers = "1";
    document.body.dataset.guide = "normal";
  }
  function hideNumbers() {
    document.querySelectorAll("#num-dim, #num-band, #num-questions, .num-badge").forEach(function (e) { e.remove(); });
    delete document.body.dataset.numbers;
    delete document.body.dataset.guide;
  }
  // 出ている番号を取って消す。この言葉の間だけ、番号だけの言葉が効く
  function takeNumbers() {
    var badges = document.querySelectorAll(".num-badge");
    var map = null;
    if (badges.length) {
      map = {};
      badges.forEach(function (b) { map[b.dataset.n] = b.dataset.key; });
    }
    hideNumbers();
    return map;
  }
  function callNumber(n, shown, t) {
    if (!shown) { say("「" + t + "」 番号は出ていません"); return; }
    var key = shown[n];
    if (!key) { say("「" + t + "」 その番号はありません"); return; }
    if (key === "say-list") { say("「" + t + "」"); window.CVActions.run("say-list-open"); return; }
    if (key === "change-role") { // マウスで「役割を変える」を押したのと同じ（view.js の click）
      var rb = document.querySelector('[data-action="change-role"]');
      if (!rb) { say("「" + t + "」 まだ開けません"); return; }
      say("「" + t + "」");
      rb.click();
      return;
    }
    if (!document.querySelector('template[data-fs="' + key + '"]')) { say("「" + t + "」 まだ開けません"); return; }
    say("「" + t + "」");
    openPart(key);
  }

  // ---- 聞き取った言葉を操作にする ----
  function apply(res, shown) {
    var t = res.text || "";
    if (res.kind === "操作" && res.action) {
      if (window.CVActions.isHidden()) { say("「" + t + "」 画面を隠しています"); return res; }
      var nums = res.numbers || (res.arg ? [res.arg] : []);
      if (res.action === "part-number" || res.action === "photo-show") {
        if (photoPanel()) { // 写真の番号は、口腔内写真の全画面の中でだけ効く
          var m = showPhotos(nums);
          say("「" + t + "」" + (m ? " " + m : ""));
        } else if (nums.length === 1) {
          callNumber(nums[0], shown, t); // いつもの画面で丸が出ている間は、部品の番号
        } else {
          say("「" + t + "」 番号は出ていません");
        }
        return res;
      }
      if (res.action === "photo-open") { // 「口腔内写真の3番を拡大して」はいつもの画面からでも開く
        var m2 = showPhotos(nums);
        say("「" + t + "」" + (m2 ? " " + m2 : ""));
        return res;
      }
      say("「" + t + "」");
      if (res.action === "fs-open") openPart(res.arg);
      else window.CVActions.run(res.action, res.arg);
    } else if (res.kind === "質問" && window.CVAsk && !window.CVActions.isHidden()) {
      say("「" + t + "」 調べています");
      window.CVAsk(t); // 質問だけ Claude に聞く（actions/ai.js）。無関係と聞き取り失敗は送らない
    } else {
      say("「" + t + "」 " + (res.message || ""));
    }
    return res;
  }

  // 声のあと画面が変わるまでの時間を、文字起こし・判定・画面の反映に分けてログへ1行送る（言葉の中身は送らない）
  function logTiming(T, kind) {
    var t3 = performance.now();
    requestAnimationFrame(function () {
      var t4 = performance.now();
      var body = {
        transcribe_ms: Math.round(T.t1 - T.t0), interpret_ms: Math.round(T.t2 - T.t1),
        apply_ms: Math.round(t4 - T.t2), total_ms: Math.round(t4 - T.t0), mic_ms: T.mic || 0, kind: kind || "",
      };
      document.body.dataset.timing = JSON.stringify(body);
      fetch("/voice/timing", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), keepalive: true })
        .catch(function () { /* ログが書けなくても操作は続ける */ });
    });
    return t3;
  }

  function interpret(text, shown, T) {
    return fetch("/voice/interpret", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, screen: "unit" }),
    }).then(function (r) { return r.json(); }).then(function (res) {
      if (T) T.t2 = performance.now();
      var out = apply(res, shown);
      if (T) logTiming(T, res.kind);
      return out;
    })
      .catch(function () { say("サーバーにつながりません"); });
  }

  // ---- 受付（ボタン2）----
  // 録音（親の画面）が動いているときは、声の指示を聞いている間だけ止める。指示の言葉は録音に入れない
  function holdRec(on) {
    try { if (window.parent !== window && window.parent.CVRec) window.parent.CVRec.hold(on); } catch (e) { /* 親が無ければ何もしない */ }
  }
  function fail(stage, msg) { holdRec(false); hideNumbers(); say("止まった場所: " + stage + "（" + msg + "）"); }

  // マイクは開くのに時間がかかる機器がある。最初のボタン押しで先に開き、使ったあとも60秒はそのまま持って、すぐ録音を始められるようにする
  // （持っている間も録音はしない。録音するのは聞き取りの間だけ）
  var warm = null;
  function releaseWarm() {
    if (!warm) return;
    clearTimeout(warm.timer);
    warm.stream.getTracks().forEach(function (t) { t.stop(); });
    warm = null;
  }
  function keepWarm(stream) {
    releaseWarm();
    warm = { stream: stream, timer: setTimeout(releaseWarm, 60000) };
  }
  function liveStream(st) { return st.getTracks().length > 0 && st.getTracks().every(function (t) { return t.readyState === "live"; }); }
  function getStream() {
    if (warm && liveStream(warm.stream)) {
      var st = warm.stream;
      clearTimeout(warm.timer);
      warm = null;
      return Promise.resolve(st);
    }
    releaseWarm();
    return navigator.mediaDevices.getUserMedia({ audio: true });
  }
  function prewarm() {
    if (warm || rec || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      if (warm || rec) stream.getTracks().forEach(function (t) { t.stop(); });
      else keepWarm(stream);
    }).catch(function () { /* 許可が無いときは、始めるときに知らせる */ });
  }
  var lastBtn1 = 0; // ボタン1を最後に押した時刻（ボタン2がこれに続くときは同時押しなので、マイクを開かない）
  fetch("/config/keys.json").then(function (r) { return r.json(); }).then(function (cfg) {
    var comboMs = Number(cfg.combo_ms) || 300;
    window.addEventListener("keydown", function (e) {
      if (e.repeat || !window.VoiceKeys) return;
      var name = window.VoiceKeys.keyName(e);
      if (name === cfg.button1) lastBtn1 = Date.now();
      if (name === cfg.button2 && Date.now() - lastBtn1 > comboMs) prewarm(); // 1回目の押しで先にマイクを開く
    });
  }).catch(function () { /* 先に開けなくても動く */ });
  window.addEventListener("beforeunload", releaseWarm);

  function startRec() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMic("none");
      return fail("機器", "この接続ではマイクを使えません。https で開いてください");
    }
    var tPress = performance.now();
    getStream().then(function (stream) {
      var chunks = [];
      try {
        var recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
        recorder.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
        recorder.onerror = function (e) { fail("録音", String(e.error && e.error.name)); };
        recorder.onstop = function () { finish(chunks, stream); };
        rec = { recorder: recorder, stream: stream, timer: setTimeout(stopRec, MAX_MS) };
        recorder.start();
        rec.micMs = Math.round(performance.now() - tPress); // 押してから録音が始まるまで
        holdRec(true);
        showNumbers();
        setMic("rec");
        say("聞いています…");
      } catch (e) {
        stream.getTracks().forEach(function (t) { t.stop(); });
        fail("録音", e.name || String(e));
      }
    }).catch(function (e) {
      if (e.name === "NotAllowedError" || e.name === "SecurityError") return fail("マイクの許可", "ブラウザでマイクを許可してください");
      setMic("none");
      fail("機器", e.name);
    });
  }

  function stopRec() {
    if (!rec) return;
    if (!rec.t0) rec.t0 = performance.now(); // 止めた時刻（ここから画面が変わるまでを測る）
    clearTimeout(rec.timer);
    if (rec.recorder.state !== "inactive") rec.recorder.stop();
  }

  function finish(chunks, stream) {
    if (liveStream(stream)) keepWarm(stream); else stream.getTracks().forEach(function (t) { t.stop(); });
    var T = { t0: (rec && rec.t0) || performance.now(), mic: rec && rec.micMs };
    rec = null;
    var shown = takeNumbers(); // 聞き取りが終わったら番号と暗さを消す。この言葉は、いま出ていた番号で受ける
    setMic("idle");
    say("聞き取り中…");
    fetch("/voice/transcribe", { method: "POST", body: new Blob(chunks, { type: "audio/webm" }) })
      .then(function (r) { return r.json().then(function (b) { return [r.ok, b]; }); })
      .then(function (x) {
        if (!x[0]) return fail(x[1].stage === "audio" ? "録音" : "文字起こし", x[1].error || "");
        T.t1 = performance.now();
        return interpret(x[1].text, shown, T).then(function () { holdRec(false); });
      })
      .catch(function () { fail("接続", "サーバーにつながりません"); });
  }

  window.CVActive = window.CVActive || {};
  window.CVActive[2] = function () { return !!rec; }; // 受付中は1回で止まる
  CVActions.register("button2", function () { if (rec) stopRec(); else startRec(); });
  // ボタン1と2の同時押し（voice_keys.js）= 「戻して」と同じ動き。帯も録音も声の受付も始めない
  CVActions.register("combo-back", function (info) {
    releaseWarm(); // 2つ目が先にマイクを開いていたら閉じる（録音はしていない）
    say("「戻して」（ボタン1+2）");
    interpret("戻して", null).then(function (res) {
      var body = {
        first: (info && info.first) || 0, second: (info && info.second) || 0, gap_ms: Math.round((info && info.gap_ms) || 0),
        action: (res && res.action) || "", kind: (res && res.kind) || "",
      };
      document.body.dataset.combo = JSON.stringify(body);
      fetch("/voice/combo", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), keepalive: true })
        .catch(function () { /* ログが書けなくても操作は続ける */ });
    });
  });
  CVActions.register("voice-role", function (role) {
    var appt = new URLSearchParams(location.search).get("appt");
    if (appt && window.cv) window.cv.openUnit(appt, role);
  });

  // ---- 文字の口（試験と、声が使えないとき）----
  if (q.get("typed") === "1") {
    // 文字の口でも、番号を出してから言葉を送れる（cvNumbers(true) か、入力欄の「番号」ボタン）
    window.cvNumbers = function (on) { if (on) showNumbers(); else hideNumbers(); return document.querySelectorAll(".num-badge").length; };
    window.cvTyped = function (text) { return interpret(text, takeNumbers()); };
    if (q.get("hide") !== "1") {
      var box = document.createElement("form");
      box.id = "typed-box";
      box.innerHTML = '<input type="text" id="typed-input" placeholder="言葉を打つ" autocomplete="off"><button type="button" id="typed-num">番号</button><button type="submit">送る</button>';
      box.querySelector("#typed-num").addEventListener("click", function () { if (document.querySelector(".num-badge")) hideNumbers(); else showNumbers(); });
      box.addEventListener("submit", function (e) {
        e.preventDefault();
        var i = document.getElementById("typed-input");
        interpret(i.value, takeNumbers());
        i.value = "";
      });
      document.body.appendChild(box);
    }
  }

  new MutationObserver(ensureUi).observe(document.getElementById("view"), { childList: true });
  ensureUi();
  loadNumbers();
  loadExamples();
})();
