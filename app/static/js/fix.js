// 後で直す画面（下書きがまだ無い録音）。音声を聞きながら話したままの文字を直し、整理し直す。
(function () {
  var recId = document.body.dataset.recId;
  var msg = document.getElementById("fix-msg");
  function api(url, data) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data || {}) })
      .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error(b.error || r.status); return b; }); });
  }
  function wait() {
    var t = setInterval(function () {
      fetch("/api/recordings/" + recId, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (r) {
        if (r.state === "文字起こし中" || r.state === "整理中") { msg.textContent = r.state + "…"; return; }
        clearInterval(t);
        if (r.state === "下書き" && r.draft_id) location.href = "/drafts/" + r.draft_id; // 人が見てから確定する
        else msg.textContent = r.state === "失敗" ? "失敗しました（" + r.error + "）" : r.state;
      });
    }, 600);
  }
  document.getElementById("fix-reorg").addEventListener("click", function () {
    msg.textContent = "整理しています…";
    api("/rec/" + recId + "/reorganize", { transcript: document.getElementById("fix-text").value }).then(wait).catch(function (e) { msg.textContent = e.message; });
  });
  document.getElementById("fix-retry").addEventListener("click", function () {
    msg.textContent = "やり直しています…";
    api("/rec/" + recId + "/retry").then(wait).catch(function (e) { msg.textContent = e.message; });
  });
})();
