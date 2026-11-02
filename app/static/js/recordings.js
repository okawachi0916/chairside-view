// 録音の一覧 /recordings。転送待ちの行では患者様と診療回を選んで転送できる。失敗の行では再試行・後で直す。
(function () {
  var rows = document.getElementById("rows");
  var options = [];
  var busy = false;

  function post(url, body) {
    return fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().then(function (b) { if (!r.ok) throw new Error(b.error || r.status); return b; }); });
  }
  function el(tag, text, cls) {
    var e = document.createElement(tag);
    if (text != null) e.textContent = text;
    if (cls) e.className = cls;
    return e;
  }
  function apptSelect() {
    var s = el("select");
    s.setAttribute("data-role", "target");
    s.appendChild(new Option("患者様と診療回を選ぶ", ""));
    options.forEach(function (p) {
      var g = document.createElement("optgroup");
      g.label = "カルテ番号 " + p.chart_no;
      p.appts.forEach(function (a) { g.appendChild(new Option(a.label, String(a.id))); });
      s.appendChild(g);
    });
    return s;
  }
  function act(label, fn) {
    var b = el("button", label);
    b.type = "button";
    b.addEventListener("click", function () { busy = true; fn().catch(function (e) { alert(e.message); }).then(function () { busy = false; load(); }); });
    return b;
  }

  function render(d) {
    var keep = {};
    rows.querySelectorAll("tr").forEach(function (tr) { var s = tr.querySelector("[data-role=target]"); if (s) keep[tr.dataset.id] = s.value; });
    rows.innerHTML = "";
    d.recordings.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.dataset.id = r.id;
      tr.dataset.state = r.state;
      tr.appendChild(el("td", r.time.replace("T", " ")));
      tr.appendChild(el("td", r.duration));
      tr.appendChild(el("td", r.chart_no));
      var st = el("td", r.state, "st-" + r.state);
      if (r.state === "失敗" && r.error) st.appendChild(el("div", r.error, "err"));
      tr.appendChild(st);
      var ops = el("td");
      if (r.state === "転送待ち") {
        if (r.fixed) {
          ops.appendChild(act("転送", function () { return post("/rec/" + r.id + "/transfer", {}); }));
        } else {
          var sel = apptSelect();
          sel.value = keep[r.id] || "";
          ops.appendChild(sel);
          ops.appendChild(act("転送", function () {
            if (!sel.value) return Promise.reject(new Error("患者様と診療回を選んでください"));
            return post("/rec/" + r.id + "/transfer", { appt: Number(sel.value) });
          }));
        }
      } else if (r.state === "失敗") {
        ops.appendChild(act("再試行", function () { return post("/rec/" + r.id + "/retry"); }));
        ops.appendChild(act("後で直す", function () { return post("/rec/" + r.id + "/later"); }));
      } else if (r.state === "後で直す") {
        var fx = el("a", "直す");
        fx.href = "/fix/" + r.id;
        ops.appendChild(fx);
      } else if (r.state === "下書き" && r.draft_id) {
        var a = el("a", "下書きを見る");
        a.href = "/drafts/" + r.draft_id;
        ops.appendChild(a);
        ops.appendChild(act("後で直す", function () { return post("/rec/" + r.id + "/later"); }));
      } else if (r.state === "確定") {
        ops.appendChild(el("span", "診療メモに入りました"));
      }
      tr.appendChild(ops);
      rows.appendChild(tr);
    });
    document.body.dataset.loaded = "1";
  }

  function load() {
    if (busy) return;
    fetch("/api/recordings", { cache: "no-store" }).then(function (r) { return r.json(); }).then(render)
      .catch(function () { /* つながらないときは前の表のまま */ });
  }

  fetch("/api/rec/options", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (o) {
    options = o;
    var t = document.getElementById("paste-target");
    o.forEach(function (p) {
      var g = document.createElement("optgroup");
      g.label = "カルテ番号 " + p.chart_no;
      p.appts.forEach(function (a) { g.appendChild(new Option(a.label, String(a.id))); });
      t.appendChild(g);
    });
    load();
  });

  document.getElementById("paste-go").addEventListener("click", function () {
    var text = document.getElementById("paste-text").value;
    var v = document.getElementById("paste-target").value;
    var m = document.getElementById("paste-msg");
    m.textContent = "";
    post("/rec/paste", { text: text, appt: v ? Number(v) : null })
      .then(function () { document.getElementById("paste-text").value = ""; load(); })
      .catch(function (e) { m.textContent = e.message; });
  });

  setInterval(load, 1500);
})();
