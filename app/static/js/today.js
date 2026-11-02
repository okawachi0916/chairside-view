// 今日の診療一覧 /today。氏名は伏せ字。追記が必要な人には赤く点滅する印を出し、確定すると消える。
(function () {
  var rows = document.getElementById("today-rows");
  var MASK = "●● ●●";
  var shown = {};

  function td(text, cls) { var e = document.createElement("td"); e.textContent = text; if (cls) e.className = cls; return e; }

  function render(d) {
    rows.innerHTML = "";
    d.rows.forEach(function (r) {
      var tr = document.createElement("tr");
      tr.className = "row";
      tr.dataset.appt = r.id;
      tr.dataset.chart = r.chart_no;
      tr.tabIndex = 0;
      tr.setAttribute("role", "link");
      tr.appendChild(td(r.time, "time"));
      tr.appendChild(td(r.chart_no, "no"));
      var name = document.createElement("td");
      name.className = "name";
      var nm = document.createElement("span");
      nm.className = "nm";
      nm.textContent = shown[r.id] ? r.name : MASK;
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "mini reveal";
      btn.textContent = shown[r.id] ? "伏せ字" : "表示";
      btn.addEventListener("click", function (e) { e.stopPropagation(); shown[r.id] = !shown[r.id]; render(d); });
      name.appendChild(nm);
      name.appendChild(btn);
      tr.appendChild(name);
      tr.appendChild(td(r.treatment, "proc"));
      var st = td(r.state, "state");
      if (r.mark) {
        var m = document.createElement("span");
        m.className = "addendum";
        m.setAttribute("data-part", "addendum-mark");
        m.textContent = r.mark;
        st.appendChild(m);
      }
      tr.appendChild(st);
      tr.addEventListener("click", function () { location.href = "/unit?appt=" + r.id + "&role=" + r.role; });
      rows.appendChild(tr);
    });
    document.body.dataset.loaded = "1";
  }

  function load() {
    fetch("/api/today", { cache: "no-store" }).then(function (r) { return r.json(); }).then(render).catch(function () { /* 前の表のまま */ });
  }
  load();
  setInterval(load, 2000);
})();
