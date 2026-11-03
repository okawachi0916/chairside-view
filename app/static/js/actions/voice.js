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
    "#num-dim{position:fixed;left:0;top:0;right:0;bottom:0;z-index:30;background:rgba(0,0,0,.5);pointer-events:none}" +
    ".num-badge{position:fixed;z-index:35;width:76px;height:76px;margin:-38px 0 0 -38px;border-radius:50%;box-sizing:border-box;" +
    "background:#ffd43b;color:#111;border:4px solid #fff;box-shadow:0 2px 10px rgba(0,0,0,.6);" +
    "font-size:52px;font-weight:800;line-height:68px;text-align:center;pointer-events:none}";
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
    b.textContent = "いま言える言葉";
    b.addEventListener("click", toggleList);
    top.insertBefore(b, mic);
    if (rec) setMic("rec");
  }

  function toggleList() {
    var l = document.getElementById("say-list");
    if (l) { l.hidden = !l.hidden; return; }
    fetch("/voice/commands", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
      l = document.createElement("div");
      l.id = "say-list";
      var ul = document.createElement("ul");
      d.words.forEach(function (w) { var li = document.createElement("li"); li.textContent = w; ul.appendChild(li); });
      l.appendChild(ul);
      document.body.appendChild(l);
    });
  }

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
  // 番号の写真を左に出す。無い番号があれば何も変えず、言い方を返す。
  function showPhotos(numbers) {
    var list = [], bad = [];
    (numbers || []).forEach(function (n) {
      var it = byNumber(n);
      if (!it) bad.push(n);
      else if (list.indexOf(it) < 0) list.push(it);
    });
    if (bad.length || !list.length) return "その番号はありません";
    if (!photoPanel()) window.CVActions.run("fs-open", "intraoral-photos");
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

  // ---- 番号の呼び出し（聞き取り中だけ、画面を暗くして全画面ボタンの上に丸の番号を出す）----
  var numCfg = null;
  function loadNumbers() {
    return fetch("/voice/numbers", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (c) { numCfg = c; document.body.dataset.numbersReady = "1"; return c; }).catch(function () { return null; });
  }
  function inView(el) {
    var r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight && r.right > 0 && r.left < window.innerWidth;
  }
  // 数字を付ける先: ふだんの画面にある全画面ボタン。全画面の中には付けない（戻すときは「戻して」）
  function numberTargets() {
    if (!numCfg || window.CVActions.isHidden() || document.querySelector(".fs-panel")) return [];
    var out = [];
    Object.keys(numCfg.parts).forEach(function (part) {
      var btn = document.querySelector('[data-part="' + part + '"] [data-action="fullscreen"]');
      if (btn && inView(btn)) out.push({ n: numCfg.parts[part], key: part, el: btn });
    });
    return out;
  }
  function showNumbers() {
    hideNumbers();
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
      b.textContent = x.n;
      b.style.left = Math.round(r.left + r.width / 2) + "px";
      b.style.top = Math.round(r.top + r.height / 2) + "px";
      document.body.appendChild(b);
    });
    document.body.dataset.numbers = "1";
  }
  function hideNumbers() {
    document.querySelectorAll("#num-dim, .num-badge").forEach(function (e) { e.remove(); });
    delete document.body.dataset.numbers;
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
    if (!document.querySelector('template[data-fs="' + key + '"]')) { say("「" + t + "」 まだ開けません"); return; }
    say("「" + t + "」");
    window.CVActions.run("fs-open", key);
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
      window.CVActions.run(res.action, res.arg);
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
        apply_ms: Math.round(t4 - T.t2), total_ms: Math.round(t4 - T.t0), kind: kind || "",
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

  function startRec() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMic("none");
      return fail("機器", "この接続ではマイクを使えません。https で開いてください");
    }
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      var chunks = [];
      try {
        var recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
        recorder.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
        recorder.onerror = function (e) { fail("録音", String(e.error && e.error.name)); };
        recorder.onstop = function () { finish(chunks, stream); };
        rec = { recorder: recorder, stream: stream, timer: setTimeout(stopRec, MAX_MS) };
        recorder.start();
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
    stream.getTracks().forEach(function (t) { t.stop(); });
    var T = { t0: (rec && rec.t0) || performance.now() };
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
})();
