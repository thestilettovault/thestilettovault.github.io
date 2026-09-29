/* Research & learning screen — plain-Hebrew insight cards + slicer + trends */
(function () {
  "use strict";
  var CC = window.CC;
  var h = CC.h, esc = CC.esc, api = CC.api, safeFetch = CC.safeFetch, toast = CC.toast;
  var emptyState = CC.emptyState, skeletonBlock = CC.skeletonBlock, unavailableCard = CC.unavailableCard, card = CC.card;

  var ATTR_HE = { price_band: "טווח מחיר", program: "תוכנית שותפים", discount_band: "אחוז הנחה", has_video: "וידאו", weekday: "יום בשבוע" };
  var VAL_HE = { "true": "עם וידאו", "false": "בלי וידאו", "none": "בלי הנחה", "unknown": "לא ידוע" };
  function vlabel(v) { return VAL_HE[String(v).toLowerCase()] !== undefined ? VAL_HE[String(v).toLowerCase()] : v; }

  var state = { shoes: [], activeFilters: {} };

  function renderResearch() {
    var content = CC.content();
    content.innerHTML =
      '<h1 class="page-title">מחקר ולמידה</h1>' +
      '<div class="kpi-sub" id="res-meta" style="margin-bottom:6px"></div>' +
      '<details style="margin-bottom:16px"><summary style="cursor:pointer;font-size:13px;color:var(--text-dim)">איך לקרוא את זה</summary>' +
        '<div class="kpi-sub" style="margin-top:6px;line-height:1.7">' +
        'כל נעל שיוצאה לאתר נספרת פעם אחת. "קליקים" = כמה פעמים לחצו על הקישור שלה ' +
        '(מקור: Admitad). כרטיסי התובנות משווים כל קבוצה (למשל טווח מחיר) לממוצע הכללי — ' +
        'ריבוי גדול מ-1 אומר שהקבוצה מקבלת יותר קליקים מהממוצע לנעל.</div></details>' +
      '<div class="section" id="res-insights">' + skeletonBlock(2) + "</div>" +
      '<div class="section"><h2 class="section-title">פילוח (לחץ לסינון)</h2><div id="res-slicer">' + skeletonBlock(3) + "</div></div>" +
      '<div class="section">' +
        '<div class="row" style="align-items:center;justify-content:space-between">' +
          '<h2 class="section-title" style="margin:0">נעליים תואמות</h2>' +
          '<button class="btn small secondary" id="res-csv" type="button">הורד CSV</button>' +
        '</div>' +
        '<div id="res-shoes">' + skeletonBlock(4) + "</div>" +
      "</div>" +
      '<div class="section"><h2 class="section-title">טרנדים</h2><div id="res-trends">' + skeletonBlock(4) + "</div></div>";

    document.getElementById("res-csv").addEventListener("click", downloadCsv);

    safeFetch(api("/learning")).then(function (res) {
      var insightsEl = document.getElementById("res-insights");
      var metaEl = document.getElementById("res-meta");
      if (!res.ok) { insightsEl.innerHTML = unavailableCard("תובנות"); return; }
      var d = res.data || {};
      metaEl.textContent = (d.shoes_count || 0) + " נעליים · מקור: Admitad";

      var insights = d.insights || [];
      if (!insights.length) {
        insightsEl.innerHTML = emptyState("אין עדיין מספיק נתונים לתובנות. תובנות יופיעו אחרי שיצטברו קליקים.");
      } else {
        insightsEl.innerHTML = '<div class="cards-grid">' + insights.map(function (ins, idx) {
          return '<div class="card"><div style="font-size:13px;line-height:1.5">' + esc(ins.text) + "</div>" +
            '<button class="btn small secondary" data-insight="' + idx + '" type="button" style="margin-top:10px">הצג את הנעליים</button></div>';
        }).join("") + "</div>";
        insightsEl.querySelectorAll("[data-insight]").forEach(function (btn, idx) {
          btn.addEventListener("click", function () {
            var ins = insights[idx];
            state.activeFilters = {};
            state.activeFilters[ins.attribute] = ins.value;
            renderSlicer(d.rows || []);
            applyFiltersAndRender();
            document.getElementById("res-shoes").scrollIntoView({ behavior: "smooth", block: "start" });
          });
        });
      }

      renderSlicer(d.rows || []);
    });

    safeFetch(api("/learning/shoes")).then(function (res) {
      if (!res.ok) { document.getElementById("res-shoes").innerHTML = unavailableCard("נעליים"); return; }
      state.shoes = Array.isArray(res.data) ? res.data : [];
      applyFiltersAndRender();
    });

    safeFetch(api("/trends")).then(function (res) {
      var el = document.getElementById("res-trends");
      if (!res.ok) { el.innerHTML = unavailableCard("טרנדים"); return; }
      var items = Array.isArray(res.data) ? res.data : (res.data.trends || []);
      if (!items.length) { el.innerHTML = emptyState("אין נתוני טרנד"); return; }
      el.innerHTML = '<div class="cards-grid">' + items.map(function (t) {
        return '<div class="card">' +
          '<div style="font-weight:700;font-size:13px">' + esc(t.name || "—") + "</div>" +
          '<div class="kpi-sub">' + (t.views ?? "—") + " צפיות · " + esc(t.domain || "—") + "</div>" +
          "<div style='margin-top:6px'>" + CC.statusBadgeHtml(t.affiliate_status) + "</div>" +
          '<div class="row" style="margin-top:8px">' +
            (t.url ? '<a href="' + esc(t.url) + '" target="_blank" rel="noopener" class="kpi-sub">מקור ↗</a>' : "") +
            '<a href="#affiliates" class="btn small secondary">פתח מותג בשותפים</a>' +
          "</div></div>";
      }).join("") + "</div>";
    });
  }

  function renderSlicer(rows) {
    var el = document.getElementById("res-slicer");
    if (!rows.length) { el.innerHTML = emptyState("אין עדיין נתוני למידה"); return; }
    var byAttr = {};
    rows.forEach(function (r) { (byAttr[r.attribute] = byAttr[r.attribute] || []).push(r); });
    var html = "";
    Object.keys(byAttr).forEach(function (attr) {
      var attrRows = byAttr[attr];
      var maxClicks = Math.max.apply(null, attrRows.map(function (r) { return r.clicks_per_shoe || 0; }).concat([1]));
      var avg = attrRows.reduce(function (s, r) { return s + (r.clicks_per_shoe || 0) * r.shoes; }, 0) /
        Math.max(1, attrRows.reduce(function (s, r) { return s + r.shoes; }, 0));
      html += '<div class="card" style="margin-bottom:12px"><h3>' + esc(ATTR_HE[attr] || attr) + "</h3>";
      attrRows.forEach(function (r) {
        var pct = Math.round(((r.clicks_per_shoe || 0) / maxClicks) * 100);
        var avgPct = Math.round((avg / maxClicks) * 100);
        var active = state.activeFilters[attr] === r.value;
        html += '<button type="button" class="res-bar" data-attr="' + esc(attr) + '" data-value="' + esc(r.value) +
          '" style="display:block;width:100%;text-align:right;background:none;border:none;padding:0;margin-bottom:8px;font-size:13px;cursor:pointer;color:var(--text);font-family:inherit' +
          (active ? ";outline:2px solid var(--accent);border-radius:6px" : "") + '">' +
          '<div style="display:flex;justify-content:space-between"><span>' + esc(vlabel(r.value)) + "</span>" +
          '<span class="kpi-sub">' + (r.shoes ?? 0) + " פריטים · " + (r.clicks_per_shoe ?? 0) + " קליקים/נעל</span></div>" +
          '<div class="bar-track" style="position:relative">' +
            '<div class="bar-fill" style="width:' + pct + '%"></div>' +
            '<div style="position:absolute;top:-3px;bottom:-3px;right:' + avgPct + '%;width:2px;background:var(--text-faint)"></div>' +
          "</div></button>";
      });
      html += "</div>";
    });
    el.innerHTML = html;
    el.querySelectorAll(".res-bar").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var attr = btn.dataset.attr, value = btn.dataset.value;
        if (state.activeFilters[attr] === value) delete state.activeFilters[attr];
        else state.activeFilters[attr] = value;
        renderSlicer(rowsCache);
        applyFiltersAndRender();
      });
    });
    rowsCache = rows;
  }
  var rowsCache = [];

  function matchesFilters(shoe) {
    return Object.keys(state.activeFilters).every(function (attr) {
      return String(shoe.features && shoe.features[attr]) === String(state.activeFilters[attr]);
    });
  }

  function applyFiltersAndRender() {
    var list = state.shoes.filter(matchesFilters);
    var target = document.getElementById("res-shoes");
    if (!list.length) { target.innerHTML = emptyState("אין נעליים תואמות לסינון"); return; }
    list.sort(function (a, b) { return (b.clicks || 0) - (a.clicks || 0); });
    target.innerHTML = '<div class="cards-grid">' + list.map(function (s) {
      return '<div class="card">' +
        CC.productImg(s.image_url, s.url || s.aff_link, s.slug, 120) +
        '<div style="font-size:12px;font-weight:600;margin-top:6px">' + esc(s.title || "—") + "</div>" +
        '<div class="kpi-sub">' + CC.money(s.price) + " · " + (s.clicks || 0) + " קליקים · " + (s.sales || 0) + " מכירות</div>" +
        "<div style='margin:4px 0'>" + CC.statusBadgeHtml(s.status) + "</div>" +
        '<div class="row">' +
          (s.url ? '<a href="' + esc(s.url) + '" target="_blank" rel="noopener" class="kpi-sub">מוצר ↗</a>' : "") +
        "</div></div>";
    }).join("") + "</div>";
  }

  function downloadCsv() {
    var list = state.shoes.filter(matchesFilters);
    var header = ["slug", "title", "price", "clicks", "sales", "status", "price_band", "program", "discount_band", "has_video", "weekday"];
    var lines = [header.join(",")];
    list.forEach(function (s) {
      var f = s.features || {};
      var row = [s.slug, s.title, s.price, s.clicks, s.sales, s.status,
        f.price_band, f.program, f.discount_band, f.has_video, f.weekday];
      lines.push(row.map(function (v) {
        var str = v === null || v === undefined ? "" : String(v);
        return '"' + str.replace(/"/g, '""') + '"';
      }).join(","));
    });
    var blob = new Blob(["﻿" + lines.join("\n")], { type: "text/csv;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "shoes-slice.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  CC.registerRoute("research", renderResearch);
})();
