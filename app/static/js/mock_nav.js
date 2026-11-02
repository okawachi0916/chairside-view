// 見本画面のつなぎ。予約一覧、患者様を変える、役割を変える、氏名の伏せ字。
(function () {
  var MASK = "●● ●●";

  function setName(row, show) {
    var nm = row.querySelector(".nm");
    var btn = row.querySelector(".reveal");
    nm.textContent = show ? nm.dataset.name : MASK;
    btn.textContent = show ? "伏せ字" : "表示";
  }

  var rows = document.querySelectorAll("tr.row");
  rows.forEach(function (row) {
    row.addEventListener("click", function () {
      location.href = row.dataset.href;
    });
    row.addEventListener("keydown", function (e) {
      if (e.key === "Enter") location.href = row.dataset.href;
    });
    var btn = row.querySelector(".reveal");
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      setName(row, row.querySelector(".nm").textContent === MASK);
    });
  });

  var all = document.querySelector('[data-action="reveal-all"]');
  if (all) {
    all.addEventListener("click", function () {
      var show = all.textContent === "すべて表示";
      rows.forEach(function (row) { setName(row, show); });
      all.textContent = show ? "すべて伏せ字" : "すべて表示";
    });
  }

  // 患者様を変える → 予約一覧へ
  var change = document.querySelector('[data-action="change-patient"]');
  if (change) change.addEventListener("click", function () { location.href = "/mock/"; });

  // 役割を変える → 歯科医師と歯科衛生士を切り替える。受付へは切り替えない
  var role = document.querySelector('[data-action="change-role"]');
  if (role) {
    role.addEventListener("click", function () {
      location.href = location.pathname.indexOf("/mock/hygienist") === 0 ? "/mock/doctor" : "/mock/hygienist";
    });
  }
})();
