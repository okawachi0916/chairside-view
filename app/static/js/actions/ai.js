// 自由な質問への答え。声の窓が「質問」と分けた言葉だけをここへ渡す。
// 画面に出す本文はサーバーがデータベースから返した文字だけ。Claude の文は出さない。
(function () {
  var seq = 0; // 質問のたびに増やす。古い答えは番号が合わないので捨てる

  var style = document.createElement("style");
  style.textContent =
    "body.fs-mode:has(.fs-panel[data-fs-panel=answer]){background:var(--c-ink)}" +
    ".fs-panel[data-fs-panel=answer]{background:var(--c-ink);border-color:var(--c-ink);color:var(--c-surface)}" +
    ".fs-panel[data-fs-panel=answer] .fs-head h2{color:var(--c-line)}" +
    ".ai-wrap{flex:1;min-height:0;display:flex;justify-content:center;padding:10px 0 4px}" +
    ".ai-frame{width:640px;max-width:100%;height:100%;box-sizing:border-box;background:var(--c-surface);color:var(--c-ink);border-radius:var(--r-l);padding:36px 44px 18px;display:flex;flex-direction:column;overflow:hidden}" +
    ".ai-kind{font-size:var(--fs-4);color:var(--c-sub);margin-bottom:18px}" +
    ".ai-body{flex:1;min-height:0;overflow-y:auto}" +
    ".ai-body p{margin:0 0 20px;font-size:var(--fs-6);line-height:var(--lh-text);font-weight:var(--fw-bold)}" +
    ".ai-src{flex:none;font-size:var(--fs-1);color:var(--c-sub);border-top:1px solid var(--c-line);padding-top:10px}";
  document.head.appendChild(style);

  function say(text) {
    var h = document.getElementById("heard");
    if (h) { h.textContent = text; h.title = text; }
    document.body.dataset.heard = text;
  }

  function apptNow() { return new URLSearchParams(location.search).get("appt"); }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function showFound(res) {
    window.CVActions.run("fs-close");
    var p = el("section", "fs-panel");
    p.setAttribute("data-fs-panel", "answer");
    var head = el("div", "fs-head");
    head.appendChild(el("h2", "", "聞いた情報"));
    head.appendChild(el("span", "fs-spacer"));
    [["fs-prev", "前のページ", true], ["fs-next", "次のページ", true], ["fs-close", "もとに戻す", false]].forEach(function (b) {
      var btn = el("button", "", b[1]);
      btn.type = "button";
      btn.setAttribute("data-action", b[0]);
      btn.hidden = b[2];
      head.appendChild(btn);
    });
    p.appendChild(head);
    var wrap = el("div", "ai-wrap");
    var frame = el("div", "ai-frame");
    frame.setAttribute("data-answer-ref", res.ref || "");
    frame.appendChild(el("div", "ai-kind", res.title));
    var body = el("div", "ai-body");
    (res.lines || []).forEach(function (t) { body.appendChild(el("p", "", t)); });
    frame.appendChild(body);
    frame.appendChild(el("div", "ai-src", res.source));
    wrap.appendChild(frame);
    p.appendChild(wrap);
    document.getElementById("view").appendChild(p);
    document.body.classList.add("fs-mode");
  }

  function ask(text) {
    var my = ++seq, appt = apptNow();
    document.body.dataset.answer = "waiting";
    return fetch("/ai/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, appt: Number(appt) }),
    }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (res) {
        if (my !== seq || appt !== apptNow()) { document.body.dataset.answer = "discarded"; return; } // 患者様が変わった
        if (window.CVActions.isHidden()) { document.body.dataset.answer = "hidden"; return; }
        document.body.dataset.answer = res.result;
        if (res.result === "found") { showFound(res); say("「" + text + "」"); }
        else say("「" + text + "」 " + (res.message || "もう一度お願いします"));
      })
      .catch(function () {
        if (my !== seq) return;
        document.body.dataset.answer = "retry";
        say("「" + text + "」 もう一度お願いします");
      });
  }

  window.CVAsk = ask;
})();
