/* Control Center — vanilla JS, hash router, Hebrew RTL */
(function () {
  "use strict";

  var TOKEN = document.querySelector('meta[name="control-token"]').getAttribute("content");
  var content = document.getElementById("content");
  var toastStack = document.getElementById("toast-stack");

  // ---------- helpers ----------

  function h(html) {
    var t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toast(msg, kind) {
    var el = h('<div class="toast ' + (kind || "") + '">' + esc(msg) + "</div>");
    toastStack.appendChild(el);
    setTimeout(function () {
      el.style.transition = "opacity .3s";
      el.style.opacity = "0";
      setTimeout(function () { el.remove(); }, 300);
    }, 4200);
  }

  function api(path, opts) {
    opts = opts || {};
    var headers = opts.headers || {};
    if (opts.method && opts.method !== "GET") {
      headers["X-Token"] = TOKEN;
      if (opts.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    }
    return fetch("/api" + path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined
    })
      .then(function (r) {
        return r
          .json()
          .catch(function () { return {}; })
          .then(function (data) {
            if (!r.ok || data.error) {
              var msg = (data && data.error) || ("שגיאת שרת (" + r.status + ")");
              throw new Error(msg);
            }
            return data;
          });
      })
      .catch(function (err) {
        if (err instanceof TypeError) {
          throw new Error("אין חיבור לשרת");
        }
        throw err;
      });
  }

  function safeFetch(promise) {
    // returns {ok:true, data} or {ok:false, error}
    return promise.then(
      function (data) { return { ok: true, data: data }; },
      function (err) { return { ok: false, error: err.message || String(err) }; }
    );
  }

  function relTime(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    var diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 0) diff = 0;
    if (diff < 60) return "לפני רגע";
    if (diff < 3600) return "לפני " + Math.floor(diff / 60) + " דק'";
    if (diff < 86400) return "לפני " + Math.floor(diff / 3600) + " שעות";
    return "לפני " + Math.floor(diff / 86400) + " ימים";
  }

  function fmtDateHe(iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    return d.toLocaleString("he-IL", {
      timeZone: "Asia/Jerusalem",
      day: "2-digit", month: "2-digit", year: "numeric"
    });
  }

  function fmtTimeHe(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return "";
    return d.toLocaleTimeString("he-IL", { timeZone: "Asia/Jerusalem", hour: "2-digit", minute: "2-digit" });
  }

  function money(n) {
    if (n === null || n === undefined || isNaN(n)) return "—";
    return "$" + Number(n).toLocaleString("he-IL", { maximumFractionDigits: 2 });
  }

  function card(titleText, innerHtml) {
    return '<div class="card"><h3>' + esc(titleText) + "</h3>" + innerHtml + "</div>";
  }

  function unavailableCard(titleText) {
    return card(titleText, '<div class="unavailable">לא זמין</div>');
  }

  function emptyState(text) {
    return '<div class="empty-state">' + esc(text) + "</div>";
  }

  function skeletonBlock(n) {
    var rows = "";
    for (var i = 0; i < (n || 3); i++) rows += '<div class="skeleton" style="margin-bottom:8px"></div>';
    return rows;
  }

  function statusBadgeHtml(status) {
    var map = {
      approved: ["ok", "אושר"], published: ["ok", "פורסם"],
      pending: ["warn", "ממתין"], rejected: ["err", "נדחה"],
      scheduled: ["warn", "מתוזמן"], failed: ["err", "נכשל"],
      pool: ["neutral", "מאגר"], producing: ["warn", "בהפקה"], produced: ["ok", "הופק"]
    };
    var m = map[status] || ["neutral", status || "—"];
    return '<span class="badge ' + m[0] + '">' + esc(m[1]) + "</span>";
  }

  // ---------- routing ----------
  // Screens overview/affiliates/tuning are defined below in this file.
  // Screens products/schedule/research are registered by control/static/screens/*.js
  // (loaded after this file, before boot()) via CC.registerRoute().

  var ROUTES = {
    overview: renderOverview,
    affiliates: renderAffiliates,
    tuning: renderTuning
  };

  function currentRoute() {
    var hash = (location.hash || "#overview").replace("#", "");
    return ROUTES[hash] ? hash : "overview";
  }

  function setActiveNav(route) {
    document.querySelectorAll(".sidebar a").forEach(function (a) {
      a.classList.toggle("active", a.dataset.route === route);
    });
  }

  function closeSidebarMobile() {
    document.getElementById("sidebar").classList.remove("open");
  }

  function route() {
    var r = currentRoute();
    setActiveNav(r);
    closeSidebarMobile();
    content.innerHTML = '<div class="loading-skeleton">טוען…</div>';
    try {
      ROUTES[r]();
    } catch (e) {
      console.error(e);
      content.innerHTML = emptyState("שגיאה בטעינת המסך: " + e.message);
    }
  }

  window.addEventListener("hashchange", route);

  // Screens in control/static/screens/*.js register themselves here (loaded
  // after this file, before CC.boot() runs) instead of editing ROUTES directly.
  function registerRoute(name, fn) {
    ROUTES[name] = fn;
  }

  // Shared helpers + state exposed for the screen modules.
  // Product picture: no referrer (AliExpress CDN 403s with one); missing/broken → /api/thumb
  // (local GELEM → pool → og:image, cached server-side → placeholder).
  function productImg(src, url, slug, h) {
    var fb = "/api/thumb?url=" + encodeURIComponent(url || "") + "&slug=" + encodeURIComponent(slug || "");
    return '<img class="thumb" loading="lazy" referrerpolicy="no-referrer" style="width:100%;height:' + (h || 150) +
      'px;object-fit:cover" src="' + esc(src || fb) + '" data-fb="' + esc(fb) + '" ' +
      'onerror="if(!this.dataset.done){this.dataset.done=1;this.src=this.dataset.fb}" alt="">';
  }

  window.CC = {
    productImg: productImg,
    h: h, esc: esc, toast: toast, api: api, safeFetch: safeFetch,
    relTime: relTime, fmtDateHe: fmtDateHe, fmtTimeHe: fmtTimeHe, money: money,
    card: card, unavailableCard: unavailableCard, emptyState: emptyState,
    skeletonBlock: skeletonBlock, statusBadgeHtml: statusBadgeHtml,
    registerRoute: registerRoute,
    content: function () { return content; },
    route: function () { route(); },
    boot: function () { loadHeader(); route(); scheduleAutoRefresh(); pollJobsIndicator(); },
    startJobsPolling: function () { startJobsPolling(); }
  };

  document.getElementById("hamburger").addEventListener("click", function () {
    document.getElementById("sidebar").classList.toggle("open");
  });

  // ---------- auto-refresh + jobs indicator (Section D) ----------

  var _knownJobIds = {};   // jobId -> true, jobs we've already toasted for when finished
  var _autoTimers = {};

  function clearAutoTimers() {
    Object.keys(_autoTimers).forEach(function (k) { clearInterval(_autoTimers[k]); });
    _autoTimers = {};
  }

  function scheduleAutoRefresh() {
    clearAutoTimers();
    if (document.visibilityState === "hidden") return;
    var r = currentRoute();
    if (r === "overview") {
      _autoTimers.overview = setInterval(function () {
        if (document.visibilityState !== "hidden" && currentRoute() === "overview") renderOverview();
      }, 30000);
    } else if (r === "schedule" && ROUTES.schedule) {
      _autoTimers.schedule = setInterval(function () {
        if (document.visibilityState !== "hidden" && currentRoute() === "schedule") ROUTES.schedule();
      }, 60000);
    }
  }

  window.addEventListener("hashchange", scheduleAutoRefresh);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") { clearAutoTimers(); if (_jobsPollTimer) { clearInterval(_jobsPollTimer); _jobsPollTimer = null; } }
    else { scheduleAutoRefresh(); pollJobsIndicator(); startJobsPolling(); }
  });

  var _jobsPollTimer = null;

  function renderJobsDrawer(jobs) {
    var drawer = document.getElementById("jobs-drawer");
    var all = (jobs.active || []).concat(jobs.recent || []);
    if (!all.length) { drawer.innerHTML = emptyState("אין עבודות"); return; }
    drawer.innerHTML = all.slice(0, 15).map(function (j) {
      var statusMap = { queued: "ממתין", running: "רץ", done: "הושלם", failed: "נכשל", cancelled: "בוטל" };
      return '<div class="job-row"><strong>' + esc(j.name) + "</strong> — " +
        esc(statusMap[j.status] || j.status) +
        (j.status === "running" ? ' <span class="spinner"></span>' : "") +
        '</div>';
    }).join("");
  }

  function pollJobsIndicator() {
    safeFetch(api("/jobs")).then(function (res) {
      if (!res.ok) return;
      var jobs = res.data || { active: [], recent: [] };
      var active = jobs.active || [];
      var countEl = document.getElementById("jobs-count");
      var spinEl = document.getElementById("jobs-spinner");
      if (active.length) {
        countEl.textContent = String(active.length);
        spinEl.style.display = "inline-block";
      } else {
        countEl.textContent = "⚡";
        spinEl.style.display = "none";
      }
      renderJobsDrawer(jobs);

      (jobs.recent || []).forEach(function (j) {
        if (j.status === "queued" || j.status === "running") return;
        if (_knownJobIds[j.id]) return;
        _knownJobIds[j.id] = true;
        if (j.status === "done") toast(j.name + " הושלם בהצלחה", "ok");
        else if (j.status === "failed") toast(j.name + " נכשל", "err");
      });
      active.forEach(function (j) { _knownJobIds[j.id] = _knownJobIds[j.id] || false; });

      if (active.length && !_jobsPollTimer) startJobsPolling();
      if (!active.length && _jobsPollTimer) { clearInterval(_jobsPollTimer); _jobsPollTimer = null; }
    });
  }

  function startJobsPolling() {
    if (_jobsPollTimer) return;
    _jobsPollTimer = setInterval(function () {
      if (document.visibilityState === "hidden") return;
      pollJobsIndicator();
    }, 1500);
  }

  document.getElementById("jobs-indicator").addEventListener("click", function () {
    var drawer = document.getElementById("jobs-drawer");
    drawer.style.display = drawer.style.display === "none" ? "block" : "none";
    if (drawer.style.display === "block") pollJobsIndicator();
  });

  // slower background poll always running (catches jobs started elsewhere)
  setInterval(function () {
    if (document.visibilityState !== "hidden") pollJobsIndicator();
  }, 5000);

  // ---------- header (niche identity + bot status) ----------

  function loadHeader() {
    safeFetch(api("/niche")).then(function (res) {
      if (res.ok && res.data && res.data.identity) {
        document.getElementById("niche-emoji").textContent = res.data.identity.emoji || "🦇";
        document.getElementById("niche-name").textContent = res.data.identity.name || "Control Center";
      } else {
        document.getElementById("niche-name").textContent = "מרכז שליטה";
      }
    });
    safeFetch(api("/health")).then(function (res) {
      var el = document.getElementById("bot-status");
      if (res.ok && res.data) {
        var alive = res.data.bot_alive === true;
        el.classList.toggle("alive", alive);
        el.classList.toggle("dead", !alive);
        el.title = alive ? "בוט פעיל" : "בוט לא פעיל";
      } else {
        el.title = "סטטוס בוט לא זמין";
      }
    });
  }

  // ================= SCREEN 1: OVERVIEW =================

  function renderOverview() {
    content.innerHTML =
      '<h1 class="page-title">סקירה</h1>' +
      '<div class="grid grid-kpi section" id="ov-kpis">' + skeletonBlock(4) + "</div>" +
      '<div class="section"><h2 class="section-title">מה דורש אותך עכשיו</h2><div id="ov-needs">' + skeletonBlock(2) + "</div></div>" +
      '<div class="section"><h2 class="section-title">בריאות המערכת</h2><div id="ov-health">' + skeletonBlock(3) + "</div></div>";

    safeFetch(api("/overview")).then(function (res) {
      var kpiEl = document.getElementById("ov-kpis");
      var needsEl = document.getElementById("ov-needs");
      if (!res.ok) {
        kpiEl.innerHTML = unavailableCard("KPIs");
        needsEl.innerHTML = unavailableCard("מה דורש אותך");
        toast(res.error, "err");
        return;
      }
      var d = res.data || {};
      var sales = d.sales || {};
      var postsSummary = d.posts_summary || d.posts || {};

      kpiEl.innerHTML =
        card("מכירות והכנסה", '<div class="kpi-value">' + (sales.total_sales ?? "—") + "</div>" +
          '<div class="kpi-sub">' + money(sales.total_revenue) + "</div>") +
        card("קליקים", '<div class="kpi-value">' + (sales.total_clicks ?? "—") + "</div>") +
        card("אחוז המרה", '<div class="kpi-value">' +
          (sales.conversion_rate !== undefined && sales.conversion_rate !== null
            ? (Number(sales.conversion_rate) * 100).toFixed(1) + "%"
            : "—") + "</div>") +
        card("פוסטים", '<div class="kpi-value">' + (postsSummary.scheduled ?? 0) + " מתוזמנים</div>" +
          '<div class="kpi-sub">' + (postsSummary.published ?? 0) + " פורסמו · " +
          (postsSummary.failed ?? 0) + " נכשלו</div>");

      var needs = d.needs_you || [];
      if (!needs.length) {
        needsEl.innerHTML = emptyState("אין פעולות דחופות כרגע 🎉");
      } else {
        var list = document.createElement("ul");
        list.className = "needs-list";
        var kindToWorkflow = {
          awaiting_choice: { wf: "resend_choices", label: "שלח שוב לטלגרם" },
          post_failed: { wf: "retry_failed", label: "נסה שוב" },
          affiliate_carded: null
        };
        needs.forEach(function (item) {
          var wfAction = kindToWorkflow[item.kind];
          var btnLabel = wfAction ? wfAction.label : "פתח";
          var li = h('<li class="needs-item">' +
            '<span class="txt">' + esc(item.text || item.kind || "") + "</span>" +
            '<button class="btn small" type="button">' + esc(btnLabel) + "</button></li>");
          li.querySelector("button").addEventListener("click", function () {
            if (wfAction) {
              api("/workflows/" + wfAction.wf, { method: "POST", body: { dry_run: false } })
                .then(function () { toast("הופעל: " + wfAction.label, "ok"); CC.startJobsPolling(); })
                .catch(function (err) { toast(err.message, "err"); });
            } else {
              location.hash = "#" + (item.action || "overview");
            }
          });
          list.appendChild(li);
        });
        needsEl.innerHTML = "";
        needsEl.appendChild(list);
      }
    });

    safeFetch(api("/health")).then(function (res) {
      var el = document.getElementById("ov-health");
      if (!res.ok) {
        el.innerHTML = unavailableCard("בריאות המערכת");
        return;
      }
      var d = res.data || {};
      var logs = d.logs || d.tasks || [];
      if (!Array.isArray(logs) || !logs.length) {
        el.innerHTML = emptyState("אין נתוני בריאות זמינים");
        return;
      }
      var html = '<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(240px,1fr))">';
      logs.forEach(function (log) {
        var name = log.name || log.task || "לא ידוע";
        var last = log.modified || log.last_run || log.last_run_at || log.updated;
        var lines = log.last_lines || log.tail || [];
        var id = "log-" + Math.random().toString(36).slice(2);
        html += card(name,
          '<div class="kpi-sub">' + relTime(last) + "</div>" +
          (lines && lines.length
            ? '<details style="margin-top:8px"><summary style="cursor:pointer;font-size:12px;color:var(--text-dim)">שורות אחרונות</summary>' +
              '<pre class="output">' + esc(Array.isArray(lines) ? lines.join("\n") : lines) + "</pre></details>"
            : ""));
      });
      html += "</div>";
      el.innerHTML = html;
    });
  }


  // ================= SCREEN 4: AFFILIATES & HUB =================

  var affTab = "registry";

  function renderAffiliates() {
    content.innerHTML =
      '<h1 class="page-title">שותפים ו-Hub</h1>' +
      '<div class="tabs" id="aff-tabs">' +
        '<button class="tab-btn" data-tab="registry" type="button">תוכניות</button>' +
        '<button class="tab-btn" data-tab="accounts" type="button">חשבונות</button>' +
        '<button class="tab-btn" data-tab="keys" type="button">מפתחות</button>' +
        '<button class="tab-btn" data-tab="links" type="button">קישורים</button>' +
      "</div>" +
      '<div id="aff-body">' + skeletonBlock(5) + "</div>";

    document.querySelectorAll("#aff-tabs .tab-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        affTab = btn.dataset.tab;
        renderTab();
      });
    });
    renderTab();

    function renderTab() {
      document.querySelectorAll("#aff-tabs .tab-btn").forEach(function (b) {
        b.classList.toggle("active", b.dataset.tab === affTab);
      });
      var body = document.getElementById("aff-body");
      body.innerHTML = skeletonBlock(4);
      if (affTab === "registry") loadRegistry(body);
      else if (affTab === "accounts") loadAccounts(body);
      else if (affTab === "keys") loadKeys(body);
      else loadLinks(body);
    }

    function loadRegistry(body) {
      safeFetch(api("/registry")).then(function (res) {
        if (!res.ok) { body.innerHTML = unavailableCard("תוכניות"); return; }
        var items = Array.isArray(res.data) ? res.data : (res.data.registry || []);
        var addRow = '<div class="card section"><div class="row">' +
          '<input type="text" id="reg-add-domain" placeholder="דומיין (למשל gthic.com)">' +
          '<button class="btn" id="reg-add-btn" type="button" style="flex:0 0 auto">הוסף מותג</button>' +
          "</div></div>";
        if (!items.length) {
          body.innerHTML = addRow + emptyState("אין תוכניות רשומות");
        } else {
          var rows = items.map(function (r) {
            var statusMap = { active: ["ok", "פעיל ✅"], carded: ["warn", "ממתין 🟡"], to_register: ["warn", "לרשום 🟡"], no_program: ["err", "אין תוכנית ❌"] };
            var m = statusMap[r.status] || ["neutral", r.status || "—"];
            var signup = r.signup_link || r.signup_url;
            return '<tr><td>' + esc(r.domain) + "</td>" +
              '<td>' + esc(r.program || "—") + "</td>" +
              '<td><span class="badge ' + m[0] + '">' + m[1] + "</span></td>" +
              '<td>' + esc(r.commission || "—") + "</td>" +
              '<td>' + money(r.avg_price) + "</td>" +
              '<td>' + money(r.value_per_sale) + "</td>" +
              '<td>' + (signup ? '<a href="' + esc(signup) + '" target="_blank" rel="noopener">הרשמה ↗</a>' : "—") + "</td>" +
              '<td class="reg-actions" data-domain="' + esc(r.domain) + '">' +
                '<button class="btn small reg-activate" type="button">הפעל</button></td></tr>';
          }).join("");
          body.innerHTML = addRow + '<div class="table-wrap"><table><thead><tr>' +
            "<th>דומיין</th><th>תוכנית</th><th>סטטוס</th><th>עמלה</th><th>מחיר ממוצע</th><th>ערך/מכירה</th><th>הרשמה</th><th>פעולות</th>" +
            "</tr></thead><tbody>" + rows + "</tbody></table></div>";

          body.querySelectorAll(".reg-activate").forEach(function (btn) {
            btn.addEventListener("click", function () {
              var td = btn.closest(".reg-actions");
              var domain = td.dataset.domain;
              if (td.querySelector(".activate-input")) return;
              var wrap = h('<span class="activate-input" style="display:inline-flex;gap:6px;margin-inline-start:6px">' +
                '<input type="text" placeholder="לינק מעקב" style="width:160px"><button class="btn small" type="button">שלח</button></span>');
              td.appendChild(wrap);
              wrap.querySelector("button").addEventListener("click", function () {
                var link = wrap.querySelector("input").value.trim();
                if (!link) return;
                api("/registry/activate", { method: "POST", body: { domain: domain, link: link } })
                  .then(function () { toast("הופעל: " + domain, "ok"); renderTab(); })
                  .catch(function (err) { toast(err.message, "err"); });
              });
            });
          });
        }
        var addBtn = document.getElementById("reg-add-btn");
        addBtn.addEventListener("click", function () {
          var input = document.getElementById("reg-add-domain");
          var domain = input.value.trim();
          if (!domain) return;
          addBtn.disabled = true;
          addBtn.innerHTML = '<span class="spinner"></span>בודק... (עד 20 שנ׳)';
          api("/registry/add", { method: "POST", body: { domain: domain } })
            .then(function () { toast("נוסף: " + domain, "ok"); renderTab(); })
            .catch(function (err) { toast(err.message, "err"); })
            .finally(function () { addBtn.disabled = false; addBtn.textContent = "הוסף מותג"; });
        });
      });
    }

    function loadAccounts(body) {
      safeFetch(api("/hub")).then(function (res) {
        if (!res.ok) { body.innerHTML = unavailableCard("חשבונות"); return; }
        var accounts = (res.data && res.data.accounts) || [];
        if (!accounts.length) { body.innerHTML = emptyState("אין חשבונות רשומים"); return; }
        body.innerHTML = '<div class="cards-grid">' + accounts.map(function (a) {
          return '<div class="account-card">' +
            '<strong>' + esc(a.service || "—") + "</strong>" +
            '<span class="kpi-sub">' + esc(a.purpose || "") + "</span>" +
            (a.login ? '<span class="kpi-sub">' + esc(a.login) + "</span>" : "") +
            (a.login_url ? '<a href="' + esc(a.login_url) + '" target="_blank" rel="noopener" class="btn small secondary" style="margin-top:6px;text-align:center">פתח התחברות ↗</a>' : "") +
            "</div>";
        }).join("") + "</div>";
      });
    }

    function loadKeys(body) {
      safeFetch(api("/hub")).then(function (res) {
        if (!res.ok) { body.innerHTML = unavailableCard("מפתחות"); return; }
        var keys = (res.data && res.data.keys) || [];
        if (!keys.length) { body.innerHTML = emptyState("אין מפתחות רשומים"); return; }
        body.innerHTML = '<div class="cards-grid">' + keys.map(function (k) {
          return '<div class="key-card" data-key="' + esc(k.name) + '">' +
            "<strong>" + esc(k.name) + "</strong>" +
            '<span class="kpi-sub key-masked">' + esc(k.masked || "••••••") + "</span>" +
            '<span class="kpi-sub">' + (k.set ? "מוגדר" : "לא מוגדר") + " · עודכן " + relTime(k.updated) + "</span>" +
            '<div class="row" style="margin-top:6px">' +
              '<button class="btn small secondary key-copy" type="button">העתק</button>' +
              '<button class="btn small secondary key-show" type="button">הצג</button>' +
            "</div></div>";
        }).join("") + "</div>";

        body.querySelectorAll(".key-copy").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var name = btn.closest(".key-card").dataset.key;
            api("/keys/reveal", { method: "POST", body: { name: name } })
              .then(function (data) {
                var value = data.value || "";
                if (navigator.clipboard && navigator.clipboard.writeText) {
                  navigator.clipboard.writeText(value).then(function () { toast("הועתק ללוח", "ok"); },
                    function () { toast("העתקה נכשלה", "err"); });
                } else {
                  toast("העתקה אוטומטית לא נתמכת בדפדפן זה", "err");
                }
              })
              .catch(function (err) { toast(err.message, "err"); });
          });
        });
        body.querySelectorAll(".key-show").forEach(function (btn) {
          btn.addEventListener("click", function () {
            var cardEl = btn.closest(".key-card");
            var name = cardEl.dataset.key;
            var maskedEl = cardEl.querySelector(".key-masked");
            var originalText = maskedEl.textContent;
            api("/keys/reveal", { method: "POST", body: { name: name } })
              .then(function (data) {
                maskedEl.textContent = data.value || "";
                btn.disabled = true;
                setTimeout(function () {
                  maskedEl.textContent = originalText;
                  btn.disabled = false;
                }, 10000);
              })
              .catch(function (err) { toast(err.message, "err"); });
          });
        });
      });
    }

    function loadLinks(body) {
      safeFetch(api("/hub")).then(function (res) {
        if (!res.ok) { body.innerHTML = unavailableCard("קישורים"); return; }
        var links = (res.data && res.data.links) || [];
        if (!links.length) { body.innerHTML = emptyState("אין קישורים"); return; }
        body.innerHTML = '<div class="cards-grid">' + links.map(function (l) {
          return '<div class="link-card"><a href="' + esc(l.url) + '" target="_blank" rel="noopener">' +
            esc(l.label || l.url) + " ↗</a></div>";
        }).join("") + "</div>";
      });
    }
  }


  // ================= SCREEN 6: TUNING =================

  function renderTuning() {
    content.innerHTML =
      '<h1 class="page-title">כיוונון</h1>' +
      '<div id="tune-body">' + skeletonBlock(6) + "</div>" +
      '<div class="section"><h2 class="section-title">הרצות</h2>' +
      '<div class="row">' +
        '<button class="btn secondary" data-run="scout_dry" type="button">Scout (יבש)</button>' +
        '<button class="btn secondary" data-run="scout" type="button">Scout (אמיתי)</button>' +
        '<button class="btn secondary" data-run="metrics" type="button">איסוף מטריקות</button>' +
        '<button class="btn secondary" data-run="tiktok_retry" type="button">TikTok Retry</button>' +
      "</div>" +
      '<div class="kpi-sub" style="margin-top:6px">Heel Hunter רץ דרך /heel-hunter ב-Claude.</div>' +
      '<pre class="output" id="run-output" style="display:none;margin-top:10px"></pre>' +
      "</div>" +
      '<div class="section"><h2 class="section-title">שכפול נישה</h2><div class="card">' +
        '<div class="row">' +
          '<div><label>מקור</label><input type="text" id="clone-from" readonly></div>' +
          '<div><label>יעד (מזהה)</label><input type="text" id="clone-to" placeholder="new-niche-id"></div>' +
          '<div><label>שם</label><input type="text" id="clone-name" placeholder="שם תצוגה"></div>' +
        "</div>" +
        '<button class="btn" id="clone-btn" type="button" style="margin-top:12px">שכפל</button>' +
      "</div></div>";

    document.querySelectorAll("[data-run]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var action = btn.dataset.run;
        if (action === "scout" && !confirm("להריץ scout אמיתי? זה יבצע פעולות אמיתיות.")) return;
        btn.disabled = true;
        var out = document.getElementById("run-output");
        out.style.display = "block";
        out.textContent = "מריץ...";
        api("/run/" + action, { method: "POST", body: {} })
          .then(function (data) {
            out.textContent = data.output_tail || JSON.stringify(data, null, 2);
            toast("ההרצה הסתיימה", "ok");
          })
          .catch(function (err) { out.textContent = "שגיאה: " + err.message; toast(err.message, "err"); })
          .finally(function () { btn.disabled = false; });
      });
    });

    var niche = null;

    safeFetch(api("/niche")).then(function (res) {
      var body = document.getElementById("tune-body");
      if (!res.ok) { body.innerHTML = unavailableCard("הגדרות נישה"); return; }
      niche = res.data || {};
      document.getElementById("clone-from").value = (niche.identity && niche.identity.id) || "";
      body.innerHTML = renderNicheSections(niche);
      wireNicheSections(niche);
    });

    document.getElementById("clone-btn").addEventListener("click", function () {
      var from = document.getElementById("clone-from").value;
      var to = document.getElementById("clone-to").value.trim();
      var name = document.getElementById("clone-name").value.trim();
      if (!to || !name) { toast("נא למלא יעד ושם", "err"); return; }
      this.disabled = true;
      var self = this;
      api("/niche/clone", { method: "POST", body: { from: from, to: to, name: name } })
        .then(function () { toast("הנישה שוכפלה", "ok"); })
        .catch(function (err) { toast(err.message, "err"); })
        .finally(function () { self.disabled = false; });
    });
  }

  var WEEKDAYS = ["ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "שבת", "א׳"]; // Mon=0..Sun=6 python weekday

  function renderNicheSections(niche) {
    var html = "";
    Object.keys(niche).forEach(function (key) {
      if (key === "identity") return;
      var val = niche[key];
      html += '<div class="card section" data-section="' + esc(key) + '"><h3>' + esc(key) + "</h3>";
      html += '<div class="section-fields">' + renderFieldsForSection(key, val) + "</div>";
      html += '<button class="btn small save-section" type="button" data-section-save="' + esc(key) + '" style="margin-top:10px">שמור</button>';
      html += "</div>";
    });
    return html || emptyState("אין הגדרות נישה");
  }

  // Leaf-type-aware form: every leaf gets data-path="a.b"; collect walks the ORIGINAL
  // structure and parses each leaf back to its original type (never saves a list as text).
  function leafName(path) { var p = String(path).split("."); return p[p.length - 1]; }

  function renderFieldsForSection(path, val) {
    var name = leafName(path);
    var attr = ' data-path="' + esc(path) + '"';
    if (name === "skip_weekdays") {
      var arr = Array.isArray(val) ? val : [];
      return '<div class="weekday-row"' + attr + ' data-kind="weekdays">' + WEEKDAYS.map(function (label, idx) {
        return '<label class="weekday-chip"><input type="checkbox" data-wd="' + idx + '" ' +
          (arr.indexOf(idx) !== -1 ? "checked" : "") + "> " + label + "</label>";
      }).join("") + "</div>";
    }
    if (typeof val === "number") return '<input type="number" step="any"' + attr + ' value="' + esc(val) + '">';
    if (typeof val === "boolean") return '<label><input type="checkbox"' + attr + " " + (val ? "checked" : "") + "> מופעל</label>";
    if (Array.isArray(val)) {
      if (name === "slots") return '<input type="text"' + attr + ' value="' + esc(val.join(", ")) + '" placeholder="14:00, 18:00">';
      if (val.length && Array.isArray(val[0])) {
        return '<textarea' + attr + ' data-kind="pairs" placeholder="term | label">' +
          esc(val.map(function (x) { return x.join(" | "); }).join("\n")) + "</textarea>";
      }
      return '<textarea' + attr + ' data-kind="lines">' + esc(val.join("\n")) + "</textarea>";
    }
    if (val && typeof val === "object") {
      return Object.keys(val).map(function (k2) {
        return '<label class="field-label">' + esc(k2) + "</label>" + renderFieldsForSection(path + "." + k2, val[k2]);
      }).join("");
    }
    return '<input type="text"' + attr + ' value="' + esc(val == null ? "" : val) + '">';
  }

  function wireNicheSections(niche) {
    document.querySelectorAll(".save-section").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = btn.dataset.sectionSave;
        var sectionEl = btn.closest(".card");
        var original = niche[key];
        var updated = collectSectionValue(sectionEl, original, key);
        var payload = {};
        payload[key] = updated;
        btn.disabled = true;
        api("/niche", { method: "PUT", body: payload })
          .then(function () { toast("נשמר: " + key, "ok"); })
          .catch(function (err) { toast(err.message, "err"); })
          .finally(function () { btn.disabled = false; });
      });
    });
  }

  function collectSectionValue(sectionEl, original, key) {
    function walk(path, orig) {
      var el = sectionEl.querySelector('[data-path="' + CSS.escape(path) + '"]');
      if (orig && typeof orig === "object" && !Array.isArray(orig)) {
        var out = {};
        Object.keys(orig).forEach(function (k2) { out[k2] = walk(path + "." + k2, orig[k2]); });
        return out;
      }
      if (!el) return orig;
      if (el.dataset.kind === "weekdays") {
        var w = [];
        el.querySelectorAll("[data-wd]").forEach(function (cb) { if (cb.checked) w.push(Number(cb.dataset.wd)); });
        return w;
      }
      if (typeof orig === "number") { var n = Number(el.value); return isNaN(n) ? orig : n; }
      if (typeof orig === "boolean") return el.checked;
      if (Array.isArray(orig)) {
        if (leafName(path) === "slots") return el.value.split(",").map(function (x) { return x.trim(); }).filter(Boolean);
        var lines = el.value.split("\n").map(function (x) { return x.trim(); }).filter(Boolean);
        if (el.dataset.kind === "pairs") return lines.map(function (l) { return l.split("|").map(function (x) { return x.trim(); }); });
        return lines;
      }
      return el.value;
    }
    return walk(key, original);
  }

})();

// ---------- nav attention badges + "updated X ago" (polls /api/events/summary every 15s) ----------
(function () {
  var lastOk = null;
  function setBadge(route, n, title) {
    var a = document.querySelector('a[data-route="' + route + '"]');
    if (!a) return;
    var b = a.querySelector(".nav-badge");
    if (!n) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement("span"); b.className = "nav-badge"; a.appendChild(b); }
    b.textContent = n; b.title = title || "";
  }
  function stamp() {
    var el = document.getElementById("live-stamp");
    if (!el) {
      var hdr = document.querySelector("header") || document.body;
      el = document.createElement("span"); el.id = "live-stamp"; el.className = "live-stamp";
      hdr.appendChild(el);
    }
    if (!lastOk) { el.textContent = ""; return; }
    var s = Math.round((Date.now() - lastOk) / 1000);
    el.textContent = "עודכן לפני " + (s < 60 ? s + " ש׳" : Math.round(s / 60) + " ד׳");
  }
  function poll() {
    if (document.visibilityState === "hidden") return;
    fetch("/api/events/summary").then(function (r) { return r.json(); }).then(function (d) {
      setBadge("overview", d.needs_you, "דברים שדורשים אותך");
      setBadge("schedule", d.failed_posts, "פוסטים שנכשלו");
      setBadge("automations", d.running_jobs, "תהליכים רצים");
      if (window.CC_checkEngagement) window.CC_checkEngagement(d.engagement);
      lastOk = Date.now(); stamp();
    }).catch(function () {});
  }
  poll(); setInterval(poll, 15000); setInterval(stamp, 5000);
})();


// ---------- shutdown: stop the local server and close the tab ----------
(function () {
  var btn = document.getElementById("cc-shutdown");
  if (!btn) return;
  btn.addEventListener("click", function () {
    var running = document.getElementById("jobs-spinner");
    var warn = running && running.style.display !== "none" ? " ⚠️ יש תהליך שרץ עכשיו — הוא ייעצר." : "";
    if (!confirm("לסגור את מרכז השליטה ולכבות את השרת במחשב?" + warn)) return;
    var token = (document.querySelector('meta[name="control-token"]') || {}).content || "";
    fetch("/api/shutdown", { method: "POST", headers: { "X-Token": token } })
      .catch(function () {})
      .finally(function () {
        document.body.innerHTML = '<div style="display:grid;place-items:center;height:100vh;font-family:inherit;color:#a5a3ad;text-align:center">' +
          '<div><div style="font-size:40px">👠</div><h2 style="color:#f2f1ee">מרכז השליטה נסגר</h2>' +
          '<p>השרת כבוי. להפעלה מחדש: start_control.bat</p></div></div>';
        setTimeout(function () { window.close(); }, 800);
      });
  });
})();


// ---------- live engagement per channel: icon toast + sound ----------
(function () {
  var KEY = "cc_engagement_seen_v2";
  var ICON = {
    tiktok: '<svg viewBox="0 0 24 24" width="18" height="18" aria-label="TikTok"><path fill="#25F4EE" d="M9.4 9.6v-.9a6.6 6.6 0 0 0-.9-.1 6.8 6.8 0 0 0-3.8 12.4 6.8 6.8 0 0 1 4.7-11.4z"/><path fill="#25F4EE" d="M9.6 19.8a3.1 3.1 0 0 0 3.1-3V2.2h2.7a5.2 5.2 0 0 1-.1-1H11.6v14.6a3.1 3.1 0 1 1-2.1-2.9V9.6a6.8 6.8 0 0 0-4.7 11.4 6.8 6.8 0 0 0 4.8-1.2z"/><path fill="#FE2C55" d="M20.3 7.2V6.3a5.2 5.2 0 0 1-2.8-.8 5.2 5.2 0 0 0 2.8 1.7zM17.5 5.5a5.2 5.2 0 0 1-1.3-3.4h-1a5.2 5.2 0 0 0 2.3 3.4z"/><path fill="#fff" d="M8.5 13a3.1 3.1 0 0 0-1.4 5.8 3.1 3.1 0 0 1 3.6-5.1V9.9a6.6 6.6 0 0 0-.9-.1h-.4v3.3a3.1 3.1 0 0 0-.9 0zM20.3 7.2a5.2 5.2 0 0 1-2.8-1.7 5.2 5.2 0 0 1-2.3-3.4h-2.5v14.6a3.1 3.1 0 0 1-5.6 2.1 3.1 3.1 0 0 1 1.4-5.8 3.1 3.1 0 0 1 .9.1V9.8a6.8 6.8 0 0 0-4.8 11.5 6.8 6.8 0 0 0 11.6-4.8V9.1a8.8 8.8 0 0 0 5.1 1.6V7.2z"/></svg>',
    instagram: '<svg viewBox="0 0 24 24" width="18" height="18" aria-label="Instagram"><defs><radialGradient id="igg" cx="30%" cy="107%" r="150%"><stop offset="0" stop-color="#fdf497"/><stop offset=".05" stop-color="#fdf497"/><stop offset=".45" stop-color="#fd5949"/><stop offset=".6" stop-color="#d6249f"/><stop offset=".9" stop-color="#285AEB"/></radialGradient></defs><rect x="2" y="2" width="20" height="20" rx="6" fill="url(#igg)"/><rect x="6.2" y="6.2" width="11.6" height="11.6" rx="5.8" fill="none" stroke="#fff" stroke-width="1.8"/><circle cx="17.3" cy="6.7" r="1.2" fill="#fff"/></svg>',
    pinterest: '<svg viewBox="0 0 24 24" width="18" height="18" aria-label="Pinterest"><circle cx="12" cy="12" r="11" fill="#E60023"/><path fill="#fff" d="M12.3 5.2c-3.9 0-5.9 2.8-5.9 5.1 0 1.4.5 2.7 1.7 3.1.2.1.4 0 .4-.2l.2-.7c.1-.2 0-.3-.1-.5-.3-.4-.5-.9-.5-1.6 0-2.1 1.6-3.9 4.1-3.9 2.2 0 3.5 1.4 3.5 3.2 0 2.4-1.1 4.5-2.7 4.5-.9 0-1.5-.7-1.3-1.6.2-1.1.7-2.2.7-3 0-.7-.4-1.3-1.2-1.3-.9 0-1.7 1-1.7 2.3 0 .8.3 1.4.3 1.4l-1.1 4.6c-.3 1.4 0 3.1 0 3.3 0 .1.1.1.2 0 .1-.1 1.2-1.5 1.6-2.9l.6-2.4c.3.6 1.2 1.1 2.2 1.1 2.9 0 4.8-2.6 4.8-6.1 0-2.7-2.3-5.2-5.7-5.2z"/></svg>'
  };
  var NAME = { tiktok: "TikTok", instagram: "Instagram", pinterest: "Pinterest" };
  window.CC_ICON = ICON;
  var ctx = null;
  function beep(freqs) {
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      var t0 = ctx.currentTime;
      freqs.forEach(function (f, i) {
        var o = ctx.createOscillator(), g = ctx.createGain();
        o.type = "sine"; o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t0 + i * 0.12);
        g.gain.exponentialRampToValueAtTime(0.25, t0 + i * 0.12 + 0.02);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.12 + 0.25);
        o.connect(g); g.connect(ctx.destination);
        o.start(t0 + i * 0.12); o.stop(t0 + i * 0.12 + 0.3);
      });
    } catch (e) {}
  }
  document.addEventListener("click", function () {
    try { ctx = ctx || new (window.AudioContext || window.webkitAudioContext)(); ctx.resume(); } catch (e) {}
  }, { once: true });

  function iconToast(plat, text) {
    var stack = document.getElementById("eng-toasts");
    if (!stack) { stack = document.createElement("div"); stack.id = "eng-toasts"; document.body.appendChild(stack); }
    var el = document.createElement("div");
    el.className = "eng-toast eng-" + plat;
    el.innerHTML = '<span class="eng-ico">' + (ICON[plat] || "") + "</span><span><b>" + NAME[plat] + "</b> · " + text + "</span>";
    stack.appendChild(el);
    setTimeout(function () { el.classList.add("out"); setTimeout(function () { el.remove(); }, 400); }, 9000);
  }

  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) { return null; } }
  function save(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) {} }
  function n(v) { return Number(v || 0); }

  window.CC_checkEngagement = function (eng) {
    if (!eng || !eng.channels) return;
    var prev = load(), cur = eng.channels, any = false;
    if (prev) {
      Object.keys(cur).forEach(function (plat) {
        var c = cur[plat] || {}, p = prev[plat] || {};
        var df = n(c.followers) - n(p.followers);
        if (df > 0) { iconToast(plat, "👤 +" + df + " עוקבים חדשים (סה״כ " + c.followers + ")"); beep([660, 880, 1175]); any = true; }
        if (plat === "pinterest") {
          var ds = n(c.saves) - n(p.saves), doc = n(c.outbound) - n(p.outbound);
          if (ds > 0) { iconToast(plat, "📌 +" + ds + " שמירות"); beep([880, 1320]); any = true; }
          if (doc > 0) { iconToast(plat, "🔗 +" + doc + " קליקים לאתר"); beep([988, 1480]); any = true; }
        } else {
          var dl = n(c.likes) - n(p.likes), dc = n(c.comments) - n(p.comments), dsh = n(c.shares) - n(p.shares);
          if (dl > 0) { iconToast(plat, "❤️ +" + dl + " לייקים"); beep([880, 1320]); any = true; }
          if (dc > 0) { iconToast(plat, "💬 +" + dc + " תגובות"); beep([520, 780]); any = true; }
          if (dsh > 0) { iconToast(plat, "↗ +" + dsh + " שיתופים"); beep([740, 990]); any = true; }
        }
      });
    }
    save(cur);
    var el = document.getElementById("live-engage");
    if (!el) {
      var hdr = document.querySelector("header") || document.body;
      el = document.createElement("span"); el.id = "live-engage"; el.className = "live-engage";
      hdr.appendChild(el);
    }
    el.innerHTML = ["tiktok", "instagram", "pinterest"].map(function (plat) {
      var c = cur[plat] || {};
      var extra = plat === "pinterest" ? " · 🔗 " + n(c.outbound) : " · ❤️ " + n(c.likes);
      return '<span class="le-item" title="' + NAME[plat] + '">' + ICON[plat] + " " + (c.followers ?? "—") + extra + "</span>";
    }).join("");
    return any;
  };
  window.CC_testSound = function () { beep([880, 1320]); };

  // on open: pull FRESH numbers immediately so anything that happened while the dashboard
  // was closed shows up right away (diff vs. the last totals saved in this browser); then hourly.
  function pullFresh() {
    fetch("/api/events/summary?fresh=1").then(function (r) { return r.json(); })
      .then(function (d) { window.CC_checkEngagement(d.engagement); }).catch(function () {});
  }
  pullFresh();
  setInterval(pullFresh, 60 * 60 * 1000);
})();
