// G07e: 全画面と答えの画面を1画面に収める。手袋のまま見るので、スクロールは出さない。
// 入りきらないときは、幅いっぱい（CSS）→ 2列 → 字を少し小さく、の順。それでも入らない分は、
// 今あるページ送り（actions.js の「次のページ」）で見せる。形は CSS（unit.css の fit-2col と --fit）で決める。
(function () {
  var SMALL = [0.95, 0.9, 0.85];          // 全画面の字を小さくする段（本文 22px が 18.7px まで）
  var SMALL_ANSWER = [0.9, 0.8, 0.7, 0.62]; // 答えの字（36px）は本文の大きさ 22px まで
  var quiet = false;

  function over(el) { return el.scrollHeight > el.clientHeight + 4 || el.scrollWidth > el.clientWidth + 1; }

  // 2列にしてよい箱。写真の一覧と、組で1ページの表と、もう2列に並んだ欄の中は、そのまま
  function canTwo(el) {
    return !el.classList.contains("fs-list") && !el.hasAttribute("data-pages") && !el.closest(".fs-col");
  }

  function fitBox(el, steps) {
    el.classList.remove("fit-2col");
    el.style.removeProperty("--fit");
    if (!over(el)) return;
    if (canTwo(el)) {
      el.classList.add("fit-2col");
      if (!over(el)) return;
    }
    for (var i = 0; i < steps.length; i++) {
      el.style.setProperty("--fit", steps[i]);
      if (!over(el)) return;
    }
    // それでも入らない。2列のままだと横に逃げるので、1列に戻して縦のページ送りにする（答えは2列のまま）
    if (el.classList.contains("fit-2col") && !el.classList.contains("ai-body")) {
      el.classList.remove("fit-2col");
      el.scrollLeft = 0;
    }
  }

  function fit() {
    // 下書きの画面: 2つの列と治療計画の変更は、そろって字を少し小さくして収める（2列にはしない）
    var draft = document.querySelector("body[data-page=draft]");
    if (draft) {
      var cols = draft.querySelectorAll(".draft-left, .draft-right");
      var full = function () { return [].some.call(cols, over); };
      draft.style.removeProperty("--fit");
      for (var i = 0; i < SMALL.length && full(); i++) draft.style.setProperty("--fit", SMALL[i]);
    }
    var p = document.querySelector(".fs-panel");
    if (!p) return;
    p.querySelectorAll(".ai-body").forEach(function (el) { fitBox(el, SMALL_ANSWER); });
    p.querySelectorAll(".fs-scroll").forEach(function (el) {
      if (el.classList.contains("fs-list") || el.hasAttribute("data-pages")) return; // ページ送りの物
      fitBox(el, SMALL);
    });
    // ページ送りのボタンの出し入れを、入口（actions.js）にやり直してもらう
    quiet = true;
    window.dispatchEvent(new Event("resize"));
    quiet = false;
  }

  var pending = 0;
  function later() {
    if (pending) return;
    pending = requestAnimationFrame(function () { pending = 0; fit(); });
  }

  // 全画面が開いたら収める。中身を入れ替えたとき（歯周の入力など）も収め直す
  new MutationObserver(function (list) {
    for (var i = 0; i < list.length; i++) {
      var t = list[i].target;
      if (t.nodeType === 1 && (t.closest(".fs-panel, .draft-left, .draft-right, .plan-block") || [].some.call(list[i].addedNodes, function (n) {
        return n.nodeType === 1 && n.classList.contains("fs-panel");
      }))) { fit(); return; } // すぐ収める（声で開いてもマウスで開いても同じ画面になるように）
    }
  }).observe(document.body, { childList: true, subtree: true });
  window.addEventListener("resize", function () { if (!quiet) later(); });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(later);
  later();

  // スクロールの帯は出さないが、マウスのホイールでは今までどおり送れるようにする
  document.addEventListener("wheel", function (e) {
    var el = e.target.closest && e.target.closest(".fs-scroll, .sent-main");
    if (!el || el.scrollHeight <= el.clientHeight + 1) return;
    el.scrollTop += e.deltaY;
    e.preventDefault();
  }, { passive: false });

  // /sent（Claude へ送った文）も1画面にして、ページ送りのボタンで見る
  var sent = document.querySelector("body.sent-page .sent-main");
  if (sent) {
    var head = document.querySelector(".sent-head");
    var sp = document.createElement("span");
    sp.className = "fs-spacer";
    head.appendChild(sp);
    var btns = [["前のページ", -1], ["次のページ", 1]].map(function (b) {
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sent-page-btn";
      btn.setAttribute("data-action", b[1] < 0 ? "fs-prev" : "fs-next");
      btn.textContent = b[0];
      btn.addEventListener("click", function () {
        sent.scrollTop += b[1] * Math.max(40, Math.floor(sent.clientHeight * 0.9));
      });
      head.appendChild(btn);
      return btn;
    });
    var upd = function () {
      var many = sent.scrollHeight > sent.clientHeight + 1;
      btns.forEach(function (b) { b.hidden = !many; });
      btns[0].disabled = sent.scrollTop <= 0;
      btns[1].disabled = sent.scrollTop + sent.clientHeight >= sent.scrollHeight - 1;
    };
    sent.addEventListener("scroll", upd);
    sent.addEventListener("toggle", upd, true); // 指示文を開いたとき
    window.addEventListener("resize", upd);
    upd();
  }
})();
