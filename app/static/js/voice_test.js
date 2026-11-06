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
      return fail("マイク", window.CVMicError.unsupported());
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
      return fail("マイク", window.CVMicError.unsupported());
    }
    let stream;
    try {
      stream = await window.CVMicError.open();
    } catch (e) {
      setMic("none", "マイクにつながっていません");
      return window.CVMicError.explain(e).then(function (why) { fail("マイク", why); });
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
  fetch("/voice/status").then((r) => r.json()).then((s) => {
    $("engine").textContent = s.device + (s.fallback_reason ? "（GPU で読めず CPU に切り替えました: " + s.fallback_reason + "）" : "");
  }).catch(() => { $("engine").textContent = "状況を読めません"; });
  // マイクの選択と音の大きさ: 選んだ機器（この画面で選ぶと、全部の画面で使われる）を開いて、音が入るかを目で確かめる
  let probe = null;
  function stopProbe() { if (probe) { probe.meter.stop(); probe.stream.getTracks().forEach((t) => t.stop()); probe = null; } }
  async function startProbe() {
    stopProbe();
    let stream;
    try { stream = await window.CVMicError.open(); } catch (e) { $("level-text").textContent = await window.CVMicError.explain(e); return; }
    const meter = window.CVMicError.meter(stream);
    probe = { stream, meter };
    $("level-text").textContent = "使っている機器: " + meter.label();
    const tick = setInterval(() => {
      if (probe && probe.meter === meter) {
        const p = Math.max(0, meter.peak());
        $("level").style.width = Math.min(100, Math.round(Math.sqrt(p) * 140)) + "%";
        $("level").dataset.peak = String(p);
      } else clearInterval(tick);
    }, 100);
  }
  async function fillDevices() {
    const sel = $("mic-select");
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    const list = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
    const cur = window.CVMicError.chosen();
    sel.innerHTML = "";
    const o0 = document.createElement("option"); o0.value = ""; o0.textContent = "ブラウザの既定"; sel.appendChild(o0);
    list.forEach((d) => { const o = document.createElement("option"); o.value = d.deviceId; o.textContent = d.label || "（名前は許可のあとに出ます）"; sel.appendChild(o); });
    sel.value = list.some((d) => d.deviceId === cur) ? cur : "";
  }
  $("mic-select").addEventListener("change", (e) => { window.CVMicError.choose(e.target.value); startProbe(); });
  $("mic-refresh").addEventListener("click", async () => { await startProbe(); await fillDevices(); });
  startProbe().then(fillDevices).catch(() => {});
  window.addEventListener("beforeunload", stopProbe);

  checkDevices().catch(() => setMic("none", "マイクにつながっていません"));
})();
