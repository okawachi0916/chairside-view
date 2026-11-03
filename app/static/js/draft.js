// 下書きの画面。5つの項目をキーボードで直し（直した所はその場で自動で保存する）、「カルテに記録する」か「あとで直す」で、来た画面へ戻る。
// 記録するまで診療メモにも治療計画にも入らない。
// 声（ボタン2）か文字（window.cvTyped）で「確定する」と言ったあと、もう一度「確定」と言うと記録する。「戻して」は戻る。
(function () {
  var body = document.body;
  var draftId = body.dataset.draftId;
  var recId = body.dataset.recId;
  var confirmed = body.dataset.status === "confirmed";
  var msg = document.getElementById("msg");
  var plans = [];                 // 今の治療計画
  var picked = {};                // 反映の選び方 { "c3": true, "d4": true, "a:文字": false }
  var armed = 0;                  // 「確定する」と言った時刻。もう一度「確定」を待つ
  var back = body.dataset.back || "/";   // 来た画面（?back=）。診療の画面・録音の一覧・今日の診療一覧のどれか
  var saveTimer = null, saving = Promise.resolve();

  function say(t) { msg.textContent = t; body.dataset.msg = t; }
  function api(method, url, data) {
    return fetch(url, { method: method, headers: { "Content-Type": "application/json" }, body: data ? JSON.stringify(data) : undefined })
      .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error(b.error || r.status); return b; }); });
  }

  // ---- 項目 ----
  function collect() {
    var items = {};
    document.querySelectorAll(".draft-sec[data-section]").forEach(function (sec) {
      items[sec.dataset.section] = Array.prototype.map.call(sec.querySelectorAll("li.row"), function (li) {
        return { text: li.querySelector(".tx").value, quote: li.dataset.quote || "" };
      });
    });
    return items;
  }
  function addRow(sec) {
    var li = document.createElement("li");
    li.className = "row";
    li.dataset.quote = "";
    li.innerHTML = "<input class='tx' type='text'><button type='button' class='del'>消す</button>";
    sec.querySelector("ul").appendChild(li);
    li.querySelector(".tx").focus();
    return li;
  }
  document.addEventListener("click", function (e) {
    var del = e.target.closest(".del");
    if (del && !confirmed) { del.closest("li").remove(); renderPlans(); autosave(); return; }
    var add = e.target.closest(".add");
    if (add && !confirmed) { addRow(add.closest(".draft-sec")); }
  });
  document.addEventListener("input", function (e) {
    if (e.target.closest("[data-section=future_plan]")) renderPlans();
    if (e.target.closest(".draft-sec .tx")) autosave();
  });

  // ---- 治療計画: 今の計画と新しい計画を並べる ----
  function toothKey(t) {
    var m = (t || "").match(/(右上|右下|左上|左下)\s*[1-8]\s*番/);
    return m ? m[0].replace(/\s/g, "") : "";
  }
  function newPlans() {
    return Array.prototype.map.call(document.querySelectorAll("[data-section=future_plan] .tx"), function (i) { return i.value.trim().replace(/[。.]+$/, ""); })
      .filter(function (t) { return t; });
  }
  function cell(text) { var td = document.createElement("td"); td.textContent = text; return td; }
  function check(key, label, on) {
    var l = document.createElement("label");
    var c = document.createElement("input");
    c.type = "checkbox";
    c.dataset.key = key;
    c.checked = key in picked ? picked[key] : on;
    c.disabled = confirmed;
    c.addEventListener("change", function () { picked[key] = c.checked; });
    l.appendChild(c);
    l.appendChild(document.createTextNode(" " + label + "　"));
    return l;
  }
  var matched = []; // 描いたときの対応 [{ old_id, text }]、追加の文字
  var addTexts = [];
  function renderPlans() {
    var rows = document.getElementById("plan-rows");
    rows.innerHTML = "";
    var news = newPlans(), used = {};
    matched = []; addTexts = [];
    plans.forEach(function (p) {
      var key = toothKey(p.body), hit = -1;
      if (key) news.forEach(function (t, i) { if (hit < 0 && !used[i] && toothKey(t) === key) hit = i; });
      if (hit >= 0) used[hit] = true;
      var tr = document.createElement("tr");
      tr.dataset.planId = p.id;
      tr.appendChild(cell(p.body));
      tr.appendChild(cell(hit >= 0 ? news[hit] : "そのまま残す"));
      var td = document.createElement("td");
      if (hit >= 0) { td.appendChild(check("c" + p.id, "変更する", false)); matched.push({ old_id: p.id, text: news[hit] }); }
      td.appendChild(check("d" + p.id, "削除する", false));
      tr.appendChild(td);
      rows.appendChild(tr);
    });
    news.forEach(function (t, i) {
      if (used[i]) return;
      var tr = document.createElement("tr");
      tr.className = "add";
      tr.appendChild(cell("（なし）"));
      tr.appendChild(cell(t));
      var td = document.createElement("td");
      td.appendChild(check("a:" + t, "追加する", true));
      tr.appendChild(td);
      rows.appendChild(tr);
      addTexts.push(t);
    });
  }
  function planChoice() {
    var on = function (k, d) { return k in picked ? picked[k] : d; };
    return {
      changes: matched.filter(function (m) { return on("c" + m.old_id, false); }),
      deletes: plans.filter(function (p) { return on("d" + p.id, false); }).map(function (p) { return p.id; }),
      adds: addTexts.filter(function (t) { return on("a:" + t, true); }),
    };
  }

  // ---- 自動で保存・記録する・あとで直す ----
  function save() {
    if (confirmed) return Promise.resolve();
    body.dataset.autosave = "saving";
    saving = api("PUT", "/api/drafts/" + draftId + "/items", { items: collect() })
      .then(function () { if (!saveTimer) body.dataset.autosave = "saved"; })
      .catch(function (e) { say(e.message); });
    return saving;
  }
  function autosave() {       // 直した所は、その場で（少し待って）自動で保存する
    if (confirmed) return;
    body.dataset.autosave = "pending";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () { saveTimer = null; save(); }, 500);
  }
  function flush() {          // まだ保存していない直しがあれば、いま保存する
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; return save(); }
    return saving;
  }
  function goBack() { location.href = back; }
  function leave() {          // 下書きのまま来た画面へ戻る
    flush().then(goBack);
    return "back";
  }
  function doConfirm() {
    return flush().then(function () {
      var choice = planChoice();
      // 計画の変更・削除は、画面で選んだものだけ送る
      return api("POST", "/api/drafts/" + draftId + "/confirm", { items: collect(), plan: choice });
    }).then(function () {
      confirmed = true;
      body.dataset.status = "confirmed";
      document.querySelector("[data-part=draft-mark]").textContent = "確定済み（診療メモに入りました）";
      document.querySelectorAll(".tx, .del, .add, #plan-rows input").forEach(function (e) { e.disabled = true; });
      var bar = document.querySelector(".draft-actions");
      if (bar) bar.remove();
      say("カルテに記録しました");
      goBack();
    }).catch(function (e) { say(e.message); });
  }
  function later() {
    if (!recId) return say("録音がありません");
    return flush().then(function () { return api("POST", "/rec/" + recId + "/later"); })
      .then(function () { body.dataset.recState = "後で直す"; goBack(); })
      .catch(function (e) { say(e.message); });
  }
  var b;
  if ((b = document.getElementById("btn-confirm"))) b.addEventListener("click", doConfirm);
  if ((b = document.getElementById("btn-later"))) b.addEventListener("click", later);
  if ((b = document.getElementById("btn-back"))) b.addEventListener("click", function (e) { e.preventDefault(); leave(); });

  // ---- 整理し直す（話したままの文字を直したとき）----
  if ((b = document.getElementById("fix-reorg"))) {
    b.addEventListener("click", function () {
      say("整理しています…");
      api("POST", "/rec/" + recId + "/reorganize", { transcript: document.getElementById("fix-text").value }).then(function () {
        var t = setInterval(function () {
          fetch("/api/recordings/" + recId, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (r) {
            if (r.state === "整理中") return;
            clearInterval(t);
            if (r.state === "下書き") { say("新しい下書きができました。内容を見てから確定してください"); location.href = "/drafts/" + draftId + "?back=" + encodeURIComponent(back) + (body.dataset.fix === "1" ? "&fix=1" : ""); }
            else say("整理に失敗しました（" + (r.error || r.state) + "）");
          });
        }, 600);
      }).catch(function (e) { say(e.message); });
    });
  }

  // ---- 声と文字の言葉 ----
  function handle(text) {
    var n = (text || "").replace(/[\s。、，．,.！!？?「」]/g, "");
    body.dataset.heard = text;
    if (n === "確定する") { armed = Date.now(); say("もう一度「確定」と言ってください"); return "armed"; }
    if (n === "確定") {
      if (armed && Date.now() - armed < 20000) { armed = 0; doConfirm(); return "confirm"; }
      say("先に「確定する」と言ってください");
      return "need-first";
    }
    armed = 0;
    if (n === "後で直す" || n === "あとで直す") { later(); return "later"; }
    if (n === "戻して" || n === "戻る") { return leave(); }
    say("「" + text + "」は使えません");
    return "ignored";
  }
  window.cvTyped = function (text) {
    if (confirmed) {      // 記録済みでも「戻して」は戻る
      var n = (text || "").replace(/[\s。、，．,.！!？?「」]/g, "");
      if (n === "戻して" || n === "戻る") { goBack(); return "back"; }
      return "ignored";
    }
    return handle(text);
  };

  var rec = null; // 声の録音
  function holdRec(on) { try { if (window.parent !== window && window.parent.CVRec) window.parent.CVRec.hold(on); } catch (e) { /* 親が無い */ } }
  function voice() {
    if (confirmed) return;
    if (rec) { clearTimeout(rec.timer); if (rec.recorder.state !== "inactive") rec.recorder.stop(); return; }
    if (!navigator.mediaDevices) return say("この接続ではマイクを使えません");
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      var chunks = [], recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      recorder.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
      recorder.onstop = function () {
        stream.getTracks().forEach(function (t) { t.stop(); });
        rec = null;
        say("聞き取り中…");
        fetch("/voice/transcribe", { method: "POST", body: new Blob(chunks, { type: "audio/webm" }) })
          .then(function (r) { return r.json(); }).then(function (r) { holdRec(false); handle(r.text || ""); })
          .catch(function () { holdRec(false); say("声を聞き取れませんでした"); });
      };
      rec = { recorder: recorder, timer: setTimeout(voice, 6000) };
      recorder.start();
      holdRec(true);
      say("聞いています…");
    }).catch(function () { say("マイクを使えません"); });
  }
  window.CVKeyHooks = { 2: voice };
  window.CVActive = { 2: function () { return !!rec; } };
  window.CVActions = { run: function (name) { if (name === "button2") voice(); if (name === "button1" && window.parent !== window) window.parent.CVRec.press(); } };

  // ---- はじめ ----
  fetch("/api/drafts/" + draftId, { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (d) {
    plans = d.plans || [];
    renderPlans();
    body.dataset.ready = "1";
  });
})();
