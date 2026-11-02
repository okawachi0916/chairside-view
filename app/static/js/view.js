// /unit と /reception の画面。中身は毎回サーバーから読み、ブラウザには保存しない。
(function () {
  var root = document.getElementById("view");
  var kind = document.body.dataset.kind;
  var MASK = "●● ●●";
  var seq = 0; // 新しく読み始めるたびに増やす。古い応答は番号が合わないので捨てる
  var state = { appt: null, role: null };

  function load(url) {
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
      })
      .catch(function () {
        if (my !== seq) return;
        root.innerHTML = '<div class="err">読み込めませんでした</div>';
      });
  }

  function openUnit(appt, role) {
    if (window.CVActions) CVActions.run("clear-transient"); // 前の患者様の隠した画面や一時の情報を消す
    state.appt = appt;
    var q = "appt=" + appt + (role ? "&role=" + role : "");
    history.replaceState(null, "", "/unit?" + q);
    load("/api/view/unit?" + q);
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
      if (act === "change-patient") {
        if (kind === "reception") openReception(0);
        else location.href = "/";
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
    chart: "",
  };

  var q = new URLSearchParams(location.search);
  if (kind === "unit") {
    // ボタン1・2・3。押したときの処理は CVActions.run に集める
    VoiceKeys.init({
      band: document.getElementById("band"),
      onAction: function (n) { CVActions.run("button" + n); },
      textFor: function (n) {
        return n === 3 && CVActions.isHidden() ? "もう一度【隠】を押したら画面を戻します" : null;
      },
    });
    if (q.get("appt")) openUnit(q.get("appt"), q.get("role"));
    else location.href = "/";
  } else {
    openReception(q.get("patient"));
  }
})();
