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

  // ---------- routing ----------

  var ROUTES = {
    overview: renderOverview,
    products: renderProducts,
    schedule: renderSchedule,
    affiliates: renderAffiliates,
    research: renderResearch,
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

  document.getElementById("hamburger").addEventListener("click", function () {
    document.getElementById("sidebar").classList.toggle("open");
  });

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
        needs.forEach(function (item) {
          var li = h('<li class="needs-item">' +
            '<span class="txt">' + esc(item.text || item.kind || "") + "</span>" +
            '<button class="btn small" type="button">פתח</button></li>');
          li.querySelector("button").addEventListener("click", function () {
            location.hash = "#" + (item.action || "overview");
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

  // ================= SCREEN 2: PRODUCTS =================

  var productsState = { filter: "all", search: "" };

  function renderProducts() {
    content.innerHTML =
      '<h1 class="page-title">מוצרים</h1>' +
      '<div class="card section">' +
        '<div class="row">' +
          '<input type="url" id="add-url" placeholder="הוסף מוצר מ-URL...">' +
          '<button class="btn" id="add-url-btn" type="button" style="flex:0 0 auto">הוסף</button>' +
        "</div>" +
      "</div>" +
      '<div class="row" style="margin-bottom:10px">' +
        '<input type="search" id="p-search" placeholder="חיפוש מוצר..." style="flex:2">' +
      "</div>" +
      '<div class="chips" id="p-chips"></div>' +
      '<div id="p-table">' + skeletonBlock(5) + "</div>";

    var chipsEl = document.getElementById("p-chips");
    var filters = [
      ["all", "הכל"], ["pending", "ממתין"], ["approved", "אושר"],
      ["rejected", "נדחה"], ["published", "פורסם"]
    ];
    filters.forEach(function (f) {
      var chip = h('<button type="button" class="chip' + (f[0] === "all" ? " active" : "") + '">' + f[1] + "</button>");
      chip.addEventListener("click", function () {
        productsState.filter = f[0];
        chipsEl.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("active"); });
        chip.classList.add("active");
        renderProductsTable(allProducts);
      });
      chipsEl.appendChild(chip);
    });

    document.getElementById("p-search").addEventListener("input", function (e) {
      productsState.search = e.target.value.toLowerCase();
      renderProductsTable(allProducts);
    });

    document.getElementById("add-url-btn").addEventListener("click", function () {
      var input = document.getElementById("add-url");
      var url = input.value.trim();
      if (!url) return;
      var btn = document.getElementById("add-url-btn");
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>מוסיף...';
      api("/products/add", { method: "POST", body: { url: url } })
        .then(function () {
          toast("המוצר נוסף", "ok");
          input.value = "";
          loadProducts();
        })
        .catch(function (err) { toast(err.message, "err"); })
        .finally(function () {
          btn.disabled = false;
          btn.textContent = "הוסף";
        });
    });

    var allProducts = [];
    loadProducts();

    function loadProducts() {
      safeFetch(api("/products")).then(function (res) {
        if (!res.ok) {
          document.getElementById("p-table").innerHTML = unavailableCard("מוצרים");
          toast(res.error, "err");
          return;
        }
        allProducts = Array.isArray(res.data) ? res.data : (res.data.products || []);
        renderProductsTable(allProducts);
      });
    }

    function renderProductsTable(items) {
      var filtered = items.filter(function (p) {
        if (productsState.filter !== "all" && (p.status || "") !== productsState.filter) return false;
        if (productsState.search) {
          var hay = ((p.title || "") + " " + (p.domain || "")).toLowerCase();
          if (hay.indexOf(productsState.search) === -1) return false;
        }
        return true;
      });
      var target = document.getElementById("p-table");
      if (!filtered.length) {
        target.innerHTML = emptyState("אין מוצרים תואמים");
        return;
      }
      var rows = filtered.map(function (p) {
        var statusBadge = statusBadgeHtml(p.status);
        return '<tr>' +
          '<td>' + (p.image_url
            ? '<img class="thumb" loading="lazy" src="' + esc(p.image_url) + '" alt="">'
            : '<div class="thumb"></div>') + "</td>" +
          '<td>' + esc(p.title || "—") + "</td>" +
          '<td>' + money(p.price) + "</td>" +
          '<td>' + esc(p.domain || "—") + "</td>" +
          '<td>' + statusBadge + "</td>" +
          '<td>' + (p.clicks ?? 0) + "</td>" +
          '<td>' + (p.sales ?? 0) + "</td>" +
          '<td class="p-actions" data-idx="' + esc(p.url || "") + '">' +
            '<button class="btn small p-approve" type="button">אשר</button> ' +
            '<button class="btn small danger p-reject" type="button">דחה</button>' +
          "</td></tr>";
      }).join("");
      target.innerHTML = '<div class="table-wrap"><table><thead><tr>' +
        "<th></th><th>שם</th><th>מחיר</th><th>דומיין</th><th>סטטוס</th><th>קליקים</th><th>מכירות</th><th>פעולות</th>" +
        "</tr></thead><tbody>" + rows + "</tbody></table></div>";

      target.querySelectorAll(".p-approve").forEach(function (btn, i) {
        btn.addEventListener("click", function () { actOnProduct(filtered[i], "approve", btn); });
      });
      target.querySelectorAll(".p-reject").forEach(function (btn, i) {
        btn.addEventListener("click", function () { actOnProduct(filtered[i], "reject", btn); });
      });
    }

    function actOnProduct(p, action, btn) {
      btn.disabled = true;
      var body = action === "approve"
        ? { url: p.url, title: p.title, image_url: p.image_url, domain: p.domain, commission: p.commission }
        : { url: p.url, title: p.title };
      api("/products/" + action, { method: "POST", body: body })
        .then(function () {
          toast(action === "approve" ? "המוצר אושר" : "המוצר נדחה", "ok");
          loadProducts();
        })
        .catch(function (err) { toast(err.message, "err"); btn.disabled = false; });
    }
  }

  function statusBadgeHtml(status) {
    var map = {
      approved: ["ok", "אושר"], published: ["ok", "פורסם"],
      pending: ["warn", "ממתין"], rejected: ["err", "נדחה"],
      scheduled: ["warn", "מתוזמן"], failed: ["err", "נכשל"]
    };
    var m = map[status] || ["neutral", status || "—"];
    return '<span class="badge ' + m[0] + '">' + esc(m[1]) + "</span>";
  }

  // ================= SCREEN 3: SCHEDULE =================

  function renderSchedule() {
    content.innerHTML =
      '<h1 class="page-title">לוח פרסום</h1>' +
      '<div class="section"><button class="btn" id="retry-all" type="button">נסה שוב לכל הכושלים</button></div>' +
      '<div id="sched-list">' + skeletonBlock(6) + "</div>";

    document.getElementById("retry-all").addEventListener("click", function () {
      var btn = this;
      btn.disabled = true;
      api("/posts/retry", { method: "POST", body: {} })
        .then(function () { toast("ניסיון חוזר הופעל", "ok"); load(); })
        .catch(function (err) { toast(err.message, "err"); })
        .finally(function () { btn.disabled = false; });
    });

    load();

    function load() {
      safeFetch(api("/posts")).then(function (res) {
        var target = document.getElementById("sched-list");
        if (!res.ok) {
          target.innerHTML = unavailableCard("פוסטים");
          toast(res.error, "err");
          return;
        }
        var posts = Array.isArray(res.data) ? res.data : (res.data.posts || []);
        if (!posts.length) {
          target.innerHTML = emptyState("אין פוסטים מתוזמנים");
          return;
        }
        var groups = {};
        // upcoming first (soonest on top); published history hidden unless toggled
        var showHist = window.__showHistory === true;
        posts = posts.filter(function (p) { return showHist || p.status !== "published"; })
          .sort(function (a, b) { return String(a.scheduledFor).localeCompare(String(b.scheduledFor)); });
        if (showHist) posts.reverse();
        posts.forEach(function (p) {
          var day = fmtDateHe(p.scheduledFor);
          (groups[day] = groups[day] || []).push(p);
        });
        var html = "";
        Object.keys(groups).forEach(function (day) {
          html += '<div class="section"><h2 class="section-title">' + esc(day) + "</h2>" +
            '<div class="grid" style="grid-template-columns:1fr">' +
            groups[day].map(postCardHtml).join("") + "</div></div>";
        });
        if (!document.body.contains(target)) return;   // user navigated away mid-load
        html = '<p><button class="btn secondary small" id="toggle-history">' +
          (showHist ? "הסתר פוסטים שפורסמו" : "הצג גם פוסטים שפורסמו") + "</button></p>" + html;
        target.innerHTML = html;
        var th = document.getElementById("toggle-history");
        if (th) th.addEventListener("click", function () { window.__showHistory = !showHist; route(); });

        target.querySelectorAll("[data-move-id]").forEach(function (btn) {
          btn.addEventListener("click", function () { openMove(btn.dataset.moveId, btn); });
        });
        target.querySelectorAll("[data-cancel-id]").forEach(function (btn) {
          btn.addEventListener("click", function () { cancelPost(btn.dataset.cancelId, btn); });
        });
      });
    }

    function postCardHtml(p) {
      var statusMap = { scheduled: "warn", published: "ok", failed: "err" };
      var badgeCls = statusMap[p.status] || "neutral";
      var platforms = (p.platforms || []).map(function (pl) {
        return '<span class="badge neutral">' + esc(pl) + "</span>";
      }).join(" ");
      return '<div class="card">' +
        '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">' +
          '<div><span class="badge ' + badgeCls + '">' + esc(p.status || "—") + "</span> " + platforms +
          ' <span class="kpi-sub">' + fmtTimeHe(p.scheduledFor) + "</span></div>" +
          (p.url ? '<a href="' + esc(p.url) + '" target="_blank" rel="noopener" class="kpi-sub">צפה בפוסט ↗</a>' : "") +
        "</div>" +
        '<div style="margin:8px 0;font-size:13px">' + esc((p.content || "").slice(0, 180)) + "</div>" +
        '<div class="row" style="align-items:center">' +
          '<button class="btn small secondary" data-move-id="' + esc(p.id) + '" type="button">הזז</button>' +
          '<button class="btn small danger" data-cancel-id="' + esc(p.id) + '" type="button">בטל</button>' +
        "</div></div>";
    }

    function openMove(id, btn) {
      var existing = btn.parentElement.querySelector(".move-input");
      if (existing) { existing.remove(); return; }
      var wrap = h('<span class="move-input" style="display:inline-flex;gap:6px;align-items:center;margin-inline-start:8px">' +
        '<input type="datetime-local" style="width:auto"><button class="btn small" type="button">אישור</button></span>');
      btn.parentElement.appendChild(wrap);
      wrap.querySelector("button").addEventListener("click", function () {
        var val = wrap.querySelector("input").value;
        if (!val) return;
        var iso = new Date(val).toISOString();
        api("/posts/move", { method: "POST", body: { id: id, scheduledFor: iso } })
          .then(function () { toast("הפוסט הוזז", "ok"); load(); })
          .catch(function (err) { toast(err.message, "err"); });
      });
    }

    function cancelPost(id, btn) {
      if (!confirm("לבטל את הפוסט?")) return;
      btn.disabled = true;
      api("/posts/cancel", { method: "POST", body: { id: id } })
        .then(function () { toast("הפוסט בוטל", "ok"); load(); })
        .catch(function (err) { toast(err.message, "err"); btn.disabled = false; });
    }
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

  // ================= SCREEN 5: RESEARCH =================

  function renderResearch() {
    content.innerHTML =
      '<h1 class="page-title">מחקר ולמידה</h1>' +
      '<div class="section" id="res-summary">' + skeletonBlock(3) + "</div>" +
      '<div class="section"><h2 class="section-title">מה עבד (לפי מאפיין)</h2><div id="res-learning">' + skeletonBlock(4) + "</div></div>" +
      '<div class="section"><h2 class="section-title">טרנדים</h2><div id="res-trends">' + skeletonBlock(4) + "</div></div>";

    safeFetch(api("/learning")).then(function (res) {
      var summaryEl = document.getElementById("res-summary");
      var learnEl = document.getElementById("res-learning");
      if (!res.ok) {
        summaryEl.innerHTML = unavailableCard("סיכום שבועי");
        learnEl.innerHTML = unavailableCard("ביצועים לפי מאפיין");
        return;
      }
      var d = res.data || {};
      var summary = d.summary || [];
      summaryEl.innerHTML = summary.length
        ? card("סיכום שבועי", "<ul style='margin:0;padding-inline-start:20px;font-size:13px;line-height:1.8'>" +
            summary.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("") + "</ul>")
        : emptyState("אין עדיין נתוני סיכום");

      var rows = d.rows || [];
      if (!rows.length) {
        learnEl.innerHTML = emptyState("אין עדיין נתוני למידה");
      } else {
        var byAttr = {};
        rows.forEach(function (r) { (byAttr[r.attribute] = byAttr[r.attribute] || []).push(r); });
        var maxClicks = Math.max.apply(null, rows.map(function (r) { return r.clicks_per_shoe || 0; }).concat([1]));
        var html = "";
        var ATTR_HE = { price_band: "טווח מחיר", program: "תוכנית שותפים", discount_band: "אחוז הנחה", has_video: "וידאו", weekday: "יום בשבוע" };
        var VAL_HE = { "true": "עם וידאו", "false": "בלי וידאו", "none": "בלי הנחה", "unknown": "לא ידוע" };
        Object.keys(byAttr).forEach(function (attr) {
          html += '<div class="card" style="margin-bottom:12px"><h3>' + esc(ATTR_HE[attr] || attr) + "</h3>";
          byAttr[attr].forEach(function (r) {
            var pct = Math.round(((r.clicks_per_shoe || 0) / maxClicks) * 100);
            html += '<div style="margin-bottom:8px;font-size:13px">' +
              '<div style="display:flex;justify-content:space-between"><span>' + esc(VAL_HE[String(r.value).toLowerCase()] || r.value) + "</span>" +
              '<span class="kpi-sub">' + (r.shoes ?? 0) + " פריטים · " + (r.clicks ?? 0) + " קליקים · " + (r.sales ?? 0) + " מכירות</span></div>" +
              '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div></div>';
          });
          html += "</div>";
        });
        learnEl.innerHTML = html;
      }
    });

    safeFetch(api("/trends")).then(function (res) {
      var el = document.getElementById("res-trends");
      if (!res.ok) { el.innerHTML = unavailableCard("טרנדים"); return; }
      var items = Array.isArray(res.data) ? res.data : (res.data.trends || []);
      if (!items.length) { el.innerHTML = emptyState("אין נתוני טרנד"); return; }
      var rows = items.map(function (t) {
        return "<tr><td>" + esc(t.date || "—") + "</td><td>" + esc(t.name || "—") + "</td>" +
          "<td>" + (t.views ?? "—") + "</td><td>" + esc(t.domain || "—") + "</td>" +
          "<td>" + statusBadgeHtml(t.affiliate_status) + "</td>" +
          "<td>" + (t.url ? '<a href="' + esc(t.url) + '" target="_blank" rel="noopener">קישור ↗</a>' : "—") + "</td></tr>";
      }).join("");
      el.innerHTML = '<div class="table-wrap"><table><thead><tr>' +
        "<th>תאריך</th><th>שם</th><th>צפיות</th><th>דומיין</th><th>סטטוס שותפות</th><th>קישור</th>" +
        "</tr></thead><tbody>" + rows + "</tbody></table></div>";
    });
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

  // ---------- boot ----------

  loadHeader();
  route();
})();
