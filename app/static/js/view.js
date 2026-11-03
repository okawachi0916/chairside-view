// /unit と /reception の画面。中身は毎回サーバーから読み、ブラウザには保存しない。
(function () {
  var root = document.getElementById("view");
  var kind = document.body.dataset.kind;
  var MASK = "●● ●●";
  var seq = 0; // 新しく読み始めるたびに増やす。古い応答は番号が合わないので捨てる
  var state = { appt: null, role: null };

  function load(url, after) {
    var my = ++seq;
    root.innerHTML = ""; // 前の患者様の表示を先に消す
    fetch(url, { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(function (d) {
        if (my !== seq) return;
        document.body.className = "role-" + d.role;
        document.title = d.title;
        state.role = d.role;
        window.cv.chart = d.chart_no || "";
        root.innerHTML = d.html;
        if (after) after();
      })
      .catch(function () {
        if (my !== seq) return;
        root.innerHTML = '<div class="err">読み込めませんでした</div>';
      });
  }

  // 下書きを記録したあと、録音を始めたときの全画面（と並べた写真）をそのまま開き直す。履歴は増やさない・消さない
  function reopenFullscreen(part, photos) {
    return function () {
      if (!part || !window.CVActions) return;
      CVActions.run("fs-open", part);
      var ns = String(photos || "").split(",").map(Number).filter(function (n) { return n > 0; });
      if (part === "intraoral-photos" && ns.length) CVActions.run("photo-show", ns);
    };
  }

  function openUnit(appt, role, after) {
    if (window.CVActions) CVActions.run("clear-transient"); // 前の患者様の隠した画面や一時の情報を消す
    state.appt = appt;
    var q = "appt=" + appt + (role ? "&role=" + role : "");
    history.replaceState(null, "", "/unit?" + q);
    load("/api/view/unit?" + q, after);
  }

  // 話した内容の整理の欄だけ読み直す (録音から下書きができたとき)。ほかの欄・全画面以外の状態は替えない。
  // 画面を隠している間は読み直さず、戻したときに読み直す (隠した画面に新しい内容を出さないため)。
  var stale = false;
  function refreshSummary(appt) {
    if (kind !== "unit" || String(state.appt) !== String(appt)) return;
    if (window.CVActions && CVActions.isHidden()) { stale = true; return; }
    stale = false;
    var my = seq;
    fetch("/api/view/unit?appt=" + state.appt + (state.role ? "&role=" + state.role : ""), { cache: "no-store" })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        if (my !== seq) return;
        if (window.CVActions && CVActions.isHidden()) { stale = true; return; }
        var t = document.createElement("div");
        t.innerHTML = d.html;
        var open = root.querySelector('[data-fs-panel="spoken-summary"]');
        ['[data-part="spoken-summary"]', 'template[data-fs="spoken-summary"]'].forEach(function (sel) {
          var o = root.querySelector(sel), n = t.querySelector(sel);
          if (o && n) o.replaceWith(n);
        });
        if (open && window.CVActions) CVActions.run("fs-open", "spoken-summary");
      })
      .catch(function () { /* 読み直せなければ今の表示のまま */ });
  }

  function openReception(patient) {
    history.replaceState(null, "", patient ? "/reception?patient=" + patient : "/reception");
    load("/api/view/reception" + (patient ? "?patient=" + patient : ""));
  }

  function setName(row, show) {
    var nm = row.querySelector(".nm");
    nm.textContent = show ? nm.dataset.name : MASK;
    row.querySelector(".reveal").textContent = show ? "伏せ字" : "表示";
  }

  document.addEventListener("click", function (e) {
    var pick = e.target.closest('[data-action="pick-patient"]');
    if (pick) return window.CVActions.run("pick-patient");
    var reveal = e.target.closest('[data-action="reveal"]');
    if (reveal) {
      e.stopPropagation();
      var row = reveal.closest("tr");
      setName(row, row.querySelector(".nm").textContent === MASK);
      return;
    }
    var a = e.target.closest("[data-action]");
    if (a) {
      var act = a.dataset.action;
      if (act === "fullscreen") {
        var part = a.closest("[data-part]");
        if (part && window.CVActions) CVActions.run("fs-open", part.dataset.part);
        return;
      }
      if (/^fs-/.test(act)) {
        if (window.CVActions) CVActions.run(act, a);
        return;
      }
      if (act === "change-patient") {
        if (kind === "reception") openReception(0);
        else window.CVActions.run("pick-patient"); // 録音で患者様を固定している間は進めない
      } else if (act === "change-role" && kind === "unit") {
        openUnit(state.appt, state.role === "hygienist" ? "doctor" : "hygienist");
      }
      return;
    }
    var pr = e.target.closest("tr[data-patient]");
    if (pr) openReception(pr.dataset.patient);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    var pr = e.target.closest && e.target.closest("tr[data-patient]");
    if (pr) openReception(pr.dataset.patient);
  });

  window.cv = {
    openUnit: openUnit,
    openReception: openReception,
    cancel: function () { seq++; }, // 読み込み中の応答を捨てる
    refreshSummary: refreshSummary,
    restored: function () { if (stale) refreshSummary(state.appt); }, // 隠している間に下書きができていたら、戻したときに読み直す
    chart: "",
  };

  var q = new URLSearchParams(location.search);
  if (kind === "unit") {
    // ボタン1・2・3。押したときの処理は CVActions.run に集める
    VoiceKeys.init({
      band: document.getElementById("band"),
      onAction: function (n) { CVActions.run("button" + n); },
      onCombo: function (info) { CVActions.run("combo-back", info); }, // ボタン1と2の同時押し = 「戻して」
      isActive: function (n) { return !!(window.CVActive && window.CVActive[n] && window.CVActive[n]()); }, // 録音中・受付中は1回で止まる
      textFor: function (n) {
        return n === 3 && CVActions.isHidden() ? "もう一度【隠】を押したら画面を戻します" : null;
      },
    });
    if (q.get("appt")) openUnit(q.get("appt"), q.get("role"), reopenFullscreen(q.get("fs"), q.get("ph")));
    else location.href = "/";
  } else {
    openReception(q.get("patient"));
  }
})();
