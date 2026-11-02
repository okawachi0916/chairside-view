// /voice-test: キー → 録音 → サーバー → 文字 の通り道だけを確かめる。
(function () {
  const $ = (id) => document.getElementById(id);
  const MAX_MS = 6000;
  let rec = null; // { recorder, chunks, stream, timer }

  function setMic(state, label) {
    $("mic").dataset.state = state;
    $("mic").textContent = state === "none" ? "×" : "";
    $("mic-label").textContent = label;
  }
  function fail(stage, msg) {
    $("error").textContent = "止まった場所: " + stage + "（" + msg + "）";
  }

  async function checkDevices() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) {
      setMic("none", "マイクにつながっていません");
      return fail("機器", "この接続ではマイクを使えません。https で開いてください");
    }
    const list = await navigator.mediaDevices.enumerateDevices();
    if (!list.some((d) => d.kind === "audioinput")) {
      setMic("none", "マイクにつながっていません");
      return fail("機器", "マイクが見つかりません");
    }
    setMic("idle", "ボタン待ち");
  }

  async function start() {
    $("error").textContent = "";
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMic("none", "マイクにつながっていません");
      return fail("機器", "この接続ではマイクを使えません。https で開いてください");
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      if (e.name === "NotAllowedError" || e.name === "SecurityError") return fail("マイクの許可", "ブラウザでマイクを許可してください");
      setMic("none", "マイクにつながっていません");
      return fail("機器", e.name);
    }
    try {
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      const chunks = [];
      recorder.ondataavailable = (ev) => { if (ev.data.size) chunks.push(ev.data); };
      recorder.onerror = (ev) => fail("録音", String(ev.error && ev.error.name));
      recorder.onstop = () => finish(chunks, stream);
      rec = { recorder, chunks, stream, timer: setTimeout(stop, MAX_MS) };
      recorder.start();
      setMic("rec", "録音中");
    } catch (e) {
      stream.getTracks().forEach((t) => t.stop());
      fail("録音", e.name || String(e));
    }
  }

  function stop() {
    if (!rec) return;
    clearTimeout(rec.timer);
    const r = rec.recorder;
    rec.stoppedAt = performance.now();
    window.__stoppedAt = rec.stoppedAt;
    if (r.state !== "inactive") r.stop();
  }

  async function finish(chunks, stream) {
    const t0 = rec ? rec.stoppedAt : performance.now();
    stream.getTracks().forEach((t) => t.stop());
    rec = null;
    setMic("idle", "ボタン待ち");
    $("text").textContent = "聞き取り中…";
    let res;
    try {
      res = await fetch("/voice/transcribe", { method: "POST", body: new Blob(chunks, { type: "audio/webm" }) });
    } catch (e) {
      $("text").textContent = "";
      return fail("接続", "サーバーにつながりません");
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      $("text").textContent = "";
      return fail(body.stage === "audio" ? "録音" : "文字起こし", body.error || res.status);
    }
    $("text").textContent = body.text;
    $("seconds").textContent = ((performance.now() - t0) / 1000).toFixed(2) + " 秒";
    $("model").textContent = body.model + "（認識だけ " + body.seconds + " 秒）";
    document.body.dataset.done = String(Number(document.body.dataset.done || 0) + 1);
  }

  VoiceKeys.init({
    band: $("band"),
    onKey: (name) => { $("last-key").textContent = name; },
    isActive: (n) => n === 2 && !!rec,
    onAction: (n) => {
      if (n !== 2) { $("error").textContent = ""; return; } // ボタン1と3は、この確認ページでは何もしない
      if (rec) stop(); else start();
    },
  });
  checkDevices().catch(() => setMic("none", "マイクにつながっていません"));
})();
