// 話した内容の整理の全画面: 録音の区切りごとの「この区切りを要約」「この区切りを消す」と、全体の「今日の分をまとめて要約」。
// 画面の中身はサーバーが作る。ここは押したときの処理と、待っている間の読み直しだけ。
(function () {
  var timer = null, undoTimer = null;

  function root() { return document.querySelector("[data-fs-panel='spoken-summary'] [data-seg-root]"); }
  function say(text) { var m = document.querySelector(".seg-msg"); if (m) m.textContent = text || ""; }

  function post(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error(b.error || r.status); return b; }); });
  }

  function reload(appt) { if (window.cv) window.cv.refreshSummary(appt); }

  // 元に戻せる間だけ「元に戻す」を出す。過ぎたら読み直して消す
  function armUndo() {
    clearTimeout(undoTimer);
    var gone = [].slice.call(document.querySelectorAll(".seg-gone[data-undo]"));
    if (!gone.length) return;
    var left = Math.max.apply(null, gone.map(function (g) { return parseFloat(g.dataset.undo) || 0; }));
    var r = root();
    undoTimer = setTimeout(function () { if (r) reload(r.dataset.appt); }, Math.max(300, left * 1000 + 200));
  }

  // 文字にしている・要約している区切りがある間は、読み直して進みを見せる。まとめの要約ができたら下書きの画面へ
  function watch(appt, openWhenDone, role) {
    clearTimeout(timer);
    timer = setTimeout(function () {
      fetch("/api/segments?appt=" + appt + (role ? "&role=" + role : ""), { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
        var segs = d.segments || [];
        var busy = segs.some(function (s) { return s.state === "文字起こし中" || s.state === "整理中"; });
        if (busy) return watch(appt, openWhenDone, role);
        reload(appt);
        if (openWhenDone && d.combined_draft) openDraft(d.combined_draft);
        else if (openWhenDone) say(((segs.filter(function (s) { return s.error; })[0] || {}).error) || "要約できませんでした");
      }).catch(function () { watch(appt, openWhenDone, role); });
    }, 700);
  }

  function openDraft(id) {
    var back = window.CVReturn ? window.CVReturn.here() : "/";   // 記録したあとは、この全画面へ戻る
    location.href = "/drafts/" + id + "?back=" + encodeURIComponent(back);
  }

  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-seg]");
    if (!b || b.disabled) return;
    var r = root();
    var appt = r ? r.dataset.appt : null;
    var act = b.dataset.seg;
    if (act === "open") return openDraft(b.dataset.draft);
    b.disabled = true;
    if (act === "summarize") {
      say("この区切りを要約しています…");
      post("/rec/" + b.dataset.id + "/summarize").then(function () { reload(appt); watch(appt, false); })
        .catch(function (x) { b.disabled = false; say(x.message); });
    } else if (act === "combine") {
      say("今日の分をまとめて要約しています…");
      post("/rec/combine", { appt: Number(appt), role: b.dataset.role || "" }).then(function () { watch(appt, true, b.dataset.role); })
        .catch(function (x) { b.disabled = false; say(x.message); });
    } else if (act === "delete") {
      post("/rec/" + b.dataset.id + "/delete").then(function () { reload(appt); })
        .catch(function (x) { b.disabled = false; say(x.message); });
    } else if (act === "undelete") {
      post("/rec/" + b.dataset.id + "/undelete").then(function () { reload(appt); })
        .catch(function (x) { b.disabled = false; say(x.message); reload(appt); });
    }
  });

  // 全画面が開いたら、消した直後の区切りの時計と、作業中の区切りの見張りを始める
  new MutationObserver(function () {
    var r = root();
    if (!r) return;
    armUndo();
    if (r.querySelector("[data-working]") && !r.dataset.watching) { r.dataset.watching = "1"; watch(r.dataset.appt, false); }
  }).observe(document.body, { childList: true, subtree: true });
})();
