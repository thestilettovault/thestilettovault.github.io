/* Automations screen — one-click workflows (Section C) */
(function () {
  "use strict";
  var CC = window.CC;
  var h = CC.h, esc = CC.esc, api = CC.api, safeFetch = CC.safeFetch, toast = CC.toast;
  var card = CC.card, unavailableCard = CC.unavailableCard, emptyState = CC.emptyState, skeletonBlock = CC.skeletonBlock;

  function statusLine(last, active) {
    if (active) return '<span class="badge warn">רץ עכשיו</span>';
    if (!last) return '<span class="kpi-sub">מעולם לא רץ</span>';
    var map = { done: ["ok", "הצליח"], failed: ["err", "נכשל"], cancelled: ["neutral", "בוטל"] };
    var m = map[last.status] || ["neutral", last.status];
    return '<span class="badge ' + m[0] + '">' + esc(m[1]) + "</span> " +
      '<span class="kpi-sub">' + CC.relTime(last.finished_at ? new Date(last.finished_at * 1000).toISOString() : null) + "</span>";
  }

  function renderAutomations() {
    var content = CC.content();
    content.innerHTML =
      '<h1 class="page-title">⚡ אוטומציות</h1>' +
      '<div class="grid" id="wf-grid" style="grid-template-columns:repeat(auto-fit,minmax(320px,1fr))">' + skeletonBlock(4) + "</div>" +
      '<div class="section" id="wf-job-panel" style="display:none">' +
        '<h2 class="section-title">עבודה פעילה</h2>' +
        '<div class="card" id="wf-job-card"></div>' +
      "</div>";

    load();

    function load() {
      safeFetch(api("/workflows")).then(function (res) {
        var grid = document.getElementById("wf-grid");
        if (!res.ok) { grid.innerHTML = unavailableCard("אוטומציות"); return; }
        var list = res.data || [];
        if (!list.length) { grid.innerHTML = emptyState("אין אוטומציות מוגדרות"); return; }
        grid.innerHTML = list.map(function (wf) {
          return card(wf.title_he,
            '<p class="kpi-sub">' + esc(wf.description_he) + "</p>" +
            '<p class="kpi-sub">⏱ ' + esc(wf.est_duration) + "</p>" +
            '<div class="wf-status" style="margin:8px 0">' + statusLine(wf.last_run, wf.active) + "</div>" +
            '<div class="row">' +
              '<button class="btn small secondary wf-preview" type="button" data-wf="' + esc(wf.name) + '">תצוגה מקדימה</button>' +
              '<button class="btn small wf-run" type="button" data-wf="' + esc(wf.name) +
                '" data-confirm="' + (wf.needs_confirm ? "1" : "0") + '"' +
                (wf.active ? " disabled" : "") + ">הפעל</button>" +
            "</div>" +
            '<pre class="output wf-plan" data-wf-plan="' + esc(wf.name) + '" style="display:none;margin-top:8px"></pre>');
        }).join("");

        grid.querySelectorAll(".wf-preview").forEach(function (btn) {
          btn.addEventListener("click", function () { preview(btn.dataset.wf, btn); });
        });
        grid.querySelectorAll(".wf-run").forEach(function (btn) {
          btn.addEventListener("click", function () { runWorkflow(btn.dataset.wf, btn.dataset.confirm === "1", btn); });
        });
      });
    }

    function preview(name, btn) {
      var out = document.querySelector('[data-wf-plan="' + name + '"]');
      btn.disabled = true;
      api("/workflows/" + name, { method: "POST", body: { dry_run: true } })
        .then(function (data) {
          out.style.display = "block";
          var lines = data.plan || [];
          var txt = lines.map(function (l) { return "• " + l; }).join("\n");
          if (data.report) txt += "\n\n" + JSON.stringify(data.report, null, 2);
          out.textContent = txt || "(אין תוכנית)";
        })
        .catch(function (err) { toast(err.message, "err"); })
        .finally(function () { btn.disabled = false; });
    }

    function runWorkflow(name, needsConfirm, btn) {
      function go() {
        btn.disabled = true;
        api("/workflows/" + name, { method: "POST", body: { dry_run: false } })
          .then(function (data) {
            if (data.job_id) {
              toast("האוטומציה הופעלה", "ok");
              showJobPanel(data.job_id);
              CC.startJobsPolling();
            } else if (data.report) {
              toast("דוח מוכן", "ok");
              var out = document.querySelector('[data-wf-plan="' + name + '"]');
              out.style.display = "block";
              out.textContent = JSON.stringify(data.report, null, 2);
            } else {
              toast("בוצע", "ok");
            }
          })
          .catch(function (err) { toast(err.message, "err"); })
          .finally(function () { btn.disabled = false; load(); });
      }
      if (!needsConfirm) { go(); return; }
      api("/workflows/" + name, { method: "POST", body: { dry_run: true } })
        .then(function (data) {
          var plan = (data.plan || []).map(function (l) { return "• " + l; }).join("\n");
          if (confirm("להפעיל את האוטומציה?\n\n" + plan)) go();
        })
        .catch(function (err) { toast(err.message, "err"); });
    }

    function showJobPanel(jobId) {
      var panel = document.getElementById("wf-job-panel");
      var jobCard = document.getElementById("wf-job-card");
      panel.style.display = "block";
      var poll = setInterval(function () {
        safeFetch(api("/jobs/" + jobId)).then(function (res) {
          if (!res.ok) { clearInterval(poll); return; }
          var j = res.data;
          var stepsHtml = (j.steps || []).map(function (s) {
            var mark = { pending: "○", running: "◐", done: "✓", failed: "✗", cancelled: "⊘" }[s.status] || "○";
            return "<li>" + mark + " " + esc(s.title) + "</li>";
          }).join("");
          jobCard.innerHTML = "<strong>" + esc(j.name) + "</strong> — " + esc(j.status) +
            (j.status === "running" || j.status === "queued"
              ? ' <button class="btn small secondary" id="wf-cancel-btn" type="button">בטל</button>' : "") +
            "<ol>" + stepsHtml + "</ol>" +
            '<pre class="output">' + esc((j.log || []).join("\n")) + "</pre>";
          var cancelBtn = document.getElementById("wf-cancel-btn");
          if (cancelBtn) {
            cancelBtn.addEventListener("click", function () {
              api("/jobs/" + jobId + "/cancel", { method: "POST", body: {} })
                .then(function () { toast("בוטל", "ok"); })
                .catch(function (err) { toast(err.message, "err"); });
            });
          }
          if (j.status !== "queued" && j.status !== "running") clearInterval(poll);
        });
      }, 1500);
    }
  }

  CC.registerRoute("automations", renderAutomations);
})();
