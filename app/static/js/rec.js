// 録音と右下の窓を持つ親の画面。中の画面 (iframe) だけが替わるので、画面が替わっても録音は切れない。
// 録音を始めたときの患者様と診療回をサーバーに固定する。患者様を開いていなければ「患者様なし」。
(function () {
  var q = new URLSearchParams(location.search);
  var inner = document.getElementById("inner");
  var win = document.getElementById("rec-win");
  var msg = win.querySelector(".msg");

  // mode: idle / recording / paused / saving（止めて音声を保存している間）
  var mode = "idle";
  var cur = null;      // { id, fixed, appt, recorder, stream, chunks, activeMs, last }
  var jobs = [];       // 止めたあと、自動で転送して下書きになるのを待っている録音 { id, appt }
  var ready = null;    // 下書きができた最新の録音 { id, draftId, appt }
  var pending = 0;     // 転送待ちの件数（患者様なしの録音）
  var flash = null;    // 一時の知らせ { text, until }
  var tick = null;

  function mmss(ms) {
    var s = Math.floor(ms / 1000);
    return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0");
  }

  function setMode(m) { mode = m; document.body.dataset.rec = m; }

  function paint() {
    var text = "", wmode = "";
    if (flash && Date.now() < flash.until) {
      text = flash.text; wmode = "flash";
    } else if (mode === "recording" || mode === "paused") {
      var ms = cur.activeMs + (mode === "recording" ? Date.now() - cur.last : 0);
      text = (mode === "paused" ? "一時停止中 " : "録音中 ") + mmss(ms);
      wmode = mode;
    } else if (ready) {
      text = "下書きができました"; wmode = "ready";
    } else if (jobs.length > 0 || mode === "saving") {
      text = "下書きにしています…"; wmode = "working";
    } else if (pending > 0) {
      text = "転送待ち " + pending + "件"; wmode = "waiting";
    }
    win.hidden = !text;
    win.dataset.mode = wmode;
    msg.textContent = text;
    document.body.dataset.recText = text;
    document.body.dataset.draftReady = ready ? String(ready.draftId) : "";
  }

  function toast(text, ms) { flash = { text: text, until: Date.now() + (ms || 3000) }; paint(); setTimeout(paint, (ms || 3000) + 50); }

  function post(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error(b.error || r.status); return b; }); });
  }

  function refreshPending() {
    return fetch("/api/recordings/pending", { cache: "no-store" }).then(function (r) { return r.json(); })
      .then(function (d) { pending = d.pending; paint(); }).catch(function () { /* つながらないときは前の数のまま */ });
  }

  // いま中の画面で開いている患者様の予約 (/unit?appt=…)。開いていなければ null
  function context() {
    try {
      var l = inner.contentWindow.location;
      if (l.pathname === "/unit") { var a = new URLSearchParams(l.search).get("appt"); if (a) return Number(a); }
    } catch (e) { /* 別の場所の画面は患者様なし */ }
    return null;
  }

  function start() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) return toast("この接続ではマイクを使えません");
    var appt = context(); // 押した瞬間の画面で固定する
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      return post("/rec/start", { appt: appt }).then(function (r) {
        var recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
        cur = { id: r.id, fixed: r.patient_id != null, appt: appt, recorder: recorder, stream: stream, chunks: [], activeMs: 0, last: Date.now() };
        recorder.ondataavailable = function (e) { if (e.data.size) cur.chunks.push(e.data); };
        recorder.start(1000);
        setMode("recording");
        document.body.dataset.recId = String(r.id);
        document.body.dataset.recFixed = cur.fixed ? "1" : "0";
        clearInterval(tick); tick = setInterval(paint, 250);
        paint();
      }).catch(function (e) { stream.getTracks().forEach(function (t) { t.stop(); }); throw e; });
    }).catch(function (e) { toast("録音を始められません（" + (e.name || e.message) + "）", 4000); });
  }

  function stop() {
    var c = cur;
    if (!c) return;
    if (mode === "recording") c.activeMs += Date.now() - c.last;
    clearInterval(tick);
    c.recorder.onstop = function () {
      c.stream.getTracks().forEach(function (t) { t.stop(); });
      var blob = new Blob(c.chunks, { type: "audio/webm" });
      var dur = c.activeMs / 1000;
      fetch("/rec/" + c.id + "/audio?dur=" + dur.toFixed(1), { method: "POST", body: blob })
        .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error(b.error || r.status); return b; }); })
        .then(function () { saved(c); })
        .catch(function (e) { setMode("idle"); cur = null; toast("録音を保存できませんでした（" + e.message + "）", 5000); });
    };
    setMode("saving");
    cur = null;
    if (c.recorder.state !== "inactive") c.recorder.stop(); else c.recorder.onstop();
    paint();
  }

  // 止めて音声を保存できたら、OK を待たずに自動で転送し、文字起こしと下書きまで進める。
  // 患者様なしの録音は、患者様と診療回を選ぶまで転送待ちにする。
  function saved(c) {
    setMode("idle");
    if (!c.fixed) { toast("転送待ちにしました"); refreshPending(); return; }
    post("/rec/" + c.id + "/transfer", {}).then(function () {
      jobs.push({ id: c.id, appt: c.appt });
      paint();
      watch();
    }).catch(function (e) { toast("転送できません（" + e.message + "）", 5000); refreshPending(); });
  }

  var watching = null;
  function watch() {
    if (watching || !jobs.length) return;
    watching = setInterval(function () {
      jobs.slice().forEach(function (j) {
        fetch("/api/recordings/" + j.id, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (s) {
          if (s.state === "文字起こし中" || s.state === "整理中" || s.state === "転送待ち") return;
          jobs = jobs.filter(function (x) { return x.id !== j.id; });
          if (s.state === "下書き" && s.draft_id) {
            ready = { id: j.id, draftId: s.draft_id, appt: j.appt };
            refreshInner(j.appt);
          } else {
            toast("下書きにできませんでした（録音の一覧で直せます）", 5000);
          }
          paint();
          if (!jobs.length) { clearInterval(watching); watching = null; }
        }).catch(function () { /* つながらないときは次の回に */ });
      });
    }, 700);
  }

  // いま中の画面に同じ患者様 (予約) が開いていれば、話した内容の整理の欄だけ読み直す。画面全体は替えない
  function refreshInner(appt) {
    try {
      if (context() === appt && inner.contentWindow.cv) inner.contentWindow.cv.refreshSummary(appt);
    } catch (e) { /* 中の画面が別の物のとき */ }
  }

  function openDraft() {
    if (!ready) return false;
    var id = ready.draftId;
    ready = null;
    paint();
    inner.src = "/drafts/" + id;
    return true;
  }

  function press() {
    if (mode === "idle") start();
    else if (mode === "recording" || mode === "paused") stop();
  }

  // 声の指示を聞いている間だけ、録音を止める (ボタン2)。指示の言葉は録音に入れない
  function hold(on) {
    if (!cur) return;
    if (on && mode === "recording") {
      cur.activeMs += Date.now() - cur.last;
      cur.recorder.pause();
      setMode("paused");
    } else if (!on && mode === "paused") {
      cur.last = Date.now();
      cur.recorder.resume();
      setMode("recording");
    }
    paint();
  }

  win.addEventListener("click", function () {
    if (mode !== "idle") return;
    if (ready) openDraft();
    else if (pending > 0) inner.src = "/recordings";
  });

  window.CVRec = {
    press: press, hold: hold, toast: toast, openDraft: openDraft,
    hasDraft: function () { return !!ready; },
    active: function () { return mode === "recording" || mode === "paused"; }, // 1回で止まる
    locked: function () { return !!cur && cur.fixed && (mode === "recording" || mode === "paused"); }, // 患者様を固定した録音の間
    mode: function () { return mode; },
  };

  // 親が持つボタン。中の画面が持たない場所 (一覧など) でも、親にフォーカスがあるときに効くようにする
  VoiceKeys.init({
    band: document.getElementById("band"),
    isActive: function (n) { return n === 1 && window.CVRec.active(); },
    onAction: function (n) {
      if (n === 1) return press();
      try { inner.contentWindow.CVActions.run("button" + n); } catch (e) { /* 中の画面に無い */ }
    },
  });

  setMode("idle");
  refreshPending();
  setInterval(function () { if (mode === "idle") refreshPending(); }, 3000);
  window.addEventListener("beforeunload", function () {
    if (cur) cur.stream.getTracks().forEach(function (t) { t.stop(); });
  });
})();
