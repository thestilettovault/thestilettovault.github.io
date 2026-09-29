/* Schedule screen — Sunday-first month calendar of Zernio posts, + list view fallback */
(function () {
  "use strict";
  var CC = window.CC;
  var h = CC.h, esc = CC.esc, api = CC.api, safeFetch = CC.safeFetch, toast = CC.toast;
  var emptyState = CC.emptyState, skeletonBlock = CC.skeletonBlock, unavailableCard = CC.unavailableCard;

  var HE_DAYS = ["א׳", "ב׳", "ג׳", "ד׳", "ה׳", "ו׳", "ש׳"]; // Sunday-first, matches Date.getDay()
  var PLATFORM_ICON = { tiktok: "🎵 TT", instagram: "📷 IG" };

  var state = { cursor: new Date(), view: "day", allPosts: [], cacheAge: null, eng: {} };

  function engLine(id) {
    var e = state.eng[id];
    if (!e) return "";
    return '<span class="sc-eng">👁 ' + e.views + " · ❤️ " + e.likes + " · 💬 " + e.comments + " · ↗ " + e.shares + "</span>";
  }

  function jerusalemYMD(iso) {
    if (!iso) return null;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    var parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Jerusalem", year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(d);
    var y, m, day;
    parts.forEach(function (p) {
      if (p.type === "year") y = p.value;
      if (p.type === "month") m = p.value;
      if (p.type === "day") day = p.value;
    });
    return y + "-" + m + "-" + day;
  }

  function jerusalemHour(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return null;
    return Number(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Jerusalem", hour: "2-digit", hour12: false }).format(d)) % 24;
  }

  function ymd(date) {
    return date.getFullYear() + "-" + String(date.getMonth() + 1).padStart(2, "0") + "-" + String(date.getDate()).padStart(2, "0");
  }

  function renderSchedule() {
    var content = CC.content();
    content.innerHTML =
      '<h1 class="page-title">לוח פרסום</h1>' +
      '<div class="row" style="margin-bottom:10px;align-items:center">' +
        '<button class="btn small secondary" id="sc-prev" type="button">‹ הקודם</button>' +
        '<button class="btn small secondary" id="sc-today" type="button">היום</button>' +
        '<button class="btn small secondary" id="sc-next" type="button">הבא ›</button>' +
        '<h2 class="section-title" id="sc-title" style="margin:0;flex:1;text-align:center"></h2>' +
        '<div class="sc-seg" role="tablist">' +
          '<button type="button" class="btn small secondary" data-view="day">יום</button>' +
          '<button type="button" class="btn small secondary" data-view="calendar">חודש</button>' +
          '<button type="button" class="btn small secondary" data-view="list">רשימה</button>' +
        "</div>" +
        '<button class="btn small" id="sc-refresh" type="button">רענן</button>' +
      "</div>" +
      '<div class="kpi-sub" id="sc-cache-age" style="margin-bottom:10px"></div>' +
      '<div class="section" id="sc-summary"></div>' +
      '<div id="sc-body">' + skeletonBlock(6) + "</div>" +
      '<div id="sc-modal-root"></div>';

    document.getElementById("sc-prev").addEventListener("click", function () {
      var c = state.cursor;
      state.cursor = state.view === "day" ? new Date(c.getFullYear(), c.getMonth(), c.getDate() - 1)
                                          : new Date(c.getFullYear(), c.getMonth() - 1, 1);
      renderBody();
    });
    document.getElementById("sc-next").addEventListener("click", function () {
      var c = state.cursor;
      state.cursor = state.view === "day" ? new Date(c.getFullYear(), c.getMonth(), c.getDate() + 1)
                                          : new Date(c.getFullYear(), c.getMonth() + 1, 1);
      renderBody();
    });
    document.getElementById("sc-today").addEventListener("click", function () {
      state.cursor = new Date();
      state.view = "day";
      renderBody();
    });
    document.querySelectorAll(".sc-seg [data-view]").forEach(function (btn) {
      btn.addEventListener("click", function () { state.view = btn.dataset.view; renderBody(); });
    });
    document.getElementById("sc-refresh").addEventListener("click", function () { load(true); });

    load(false);

    function load(fresh) {
      document.getElementById("sc-body").innerHTML = skeletonBlock(6);
      safeFetch(api("/posts" + (fresh ? "?fresh=1" : ""))).then(function (res) {
        if (!res.ok) {
          document.getElementById("sc-body").innerHTML = unavailableCard("פוסטים");
          toast(res.error, "err");
          return;
        }
        state.allPosts = Array.isArray(res.data) ? res.data : [];
        safeFetch(api("/engagement?posts=1")).then(function (e) {
          if (e.ok && e.data && e.data.per_post) { state.eng = e.data.per_post; renderBody(); }
        });
        safeFetch(api("/posts/meta")).then(function (m) {
          state.cacheAge = (m.ok && m.data) ? m.data.cached_seconds_ago : null;
          renderCacheAge();
        });
        renderBody();
      });
    }

    function renderCacheAge() {
      var el = document.getElementById("sc-cache-age");
      if (state.cacheAge === null || state.cacheAge === undefined) { el.textContent = ""; return; }
      var mins = Math.floor(state.cacheAge / 60);
      el.textContent = mins < 1 ? "עודכן לפני רגע" : "עודכן לפני " + mins + " דק'";
    }

    function renderBody() {
      document.querySelectorAll(".sc-seg [data-view]").forEach(function (b) {
        b.classList.toggle("active", b.dataset.view === state.view);
      });
      document.getElementById("sc-title").textContent = state.view === "day"
        ? state.cursor.toLocaleDateString("he-IL", { weekday: "long", day: "numeric", month: "long", year: "numeric" })
        : state.cursor.toLocaleDateString("he-IL", { month: "long", year: "numeric" });
      if (state.view === "list") renderListView();
      else if (state.view === "day") renderDayView();
      else renderCalendarView();
    }

    function renderDayView() {
      var dstr = ymd(state.cursor);
      var dayPosts = state.allPosts.filter(function (p) { return jerusalemYMD(p.scheduledFor) === dstr; })
        .sort(function (a, b) { return String(a.scheduledFor).localeCompare(String(b.scheduledFor)); });
      var byHour = {};
      dayPosts.forEach(function (p) { var hr = jerusalemHour(p.scheduledFor); (byHour[hr] = byHour[hr] || []).push(p); });
      var counts = { scheduled: 0, published: 0, failed: 0 };
      dayPosts.forEach(function (p) { if (counts[p.status] !== undefined) counts[p.status]++; });
      var isSat = state.cursor.getDay() === 6;
      document.getElementById("sc-summary").innerHTML =
        '<div class="row" style="gap:16px">' +
          '<span class="kpi-sub">פוסטים ביום: <b>' + dayPosts.length + "</b></span>" +
          '<span class="kpi-sub">מתוזמנים: <b style="color:var(--warn)">' + counts.scheduled + "</b></span>" +
          '<span class="kpi-sub">פורסמו: <b style="color:var(--ok)">' + counts.published + "</b></span>" +
          '<span class="kpi-sub">נכשלו: <b style="color:var(--err)">' + counts.failed + "</b></span>" +
          (isSat ? '<span class="badge neutral">שבת — לא מפרסמים</span>' : "") +
        "</div>";
      var now = new Date(), isToday = ymd(now) === dstr, nowHr = jerusalemHour(now.toISOString());
      var statusMap = { scheduled: "warn", published: "ok", failed: "err" };
      var rows = "";
      for (var hr = 0; hr < 24; hr++) {
        var list = byHour[hr] || [];
        var items = list.map(function (p) {
          var plat = (p.platforms || [])[0] || "";
          return '<button type="button" class="sc-dpost card" data-post-id="' + esc(p.id) + '">' +
            (p.thumb ? '<img referrerpolicy="no-referrer" src="' + esc(p.thumb) + '" alt="">' : '<div class="sc-dthumb"></div>') +
            '<div class="sc-dtext"><div><span class="badge ' + (statusMap[p.status] || "neutral") + '">' + esc(p.status || "—") + "</span> " +
              "<b>" + esc(PLATFORM_ICON[plat] || plat) + "</b> · " + CC.fmtTimeHe(p.scheduledFor) + " " + engLine(p.id) + "</div>" +
              '<div class="sc-dcontent">' + esc((p.content || "").slice(0, 110)) + "</div></div></button>";
        }).join("");
        rows += '<div class="sc-hour' + (isToday && hr === nowHr ? " sc-hour-now" : "") + (list.length ? "" : " sc-hour-empty") +
          '" data-hour="' + hr + '">' +
          '<div class="sc-hour-label">' + String(hr).padStart(2, "0") + ":00</div>" +
          '<div class="sc-hour-body">' + items + "</div></div>";
      }
      document.getElementById("sc-body").innerHTML =
        (dayPosts.length ? "" : '<div class="card" style="margin-bottom:10px">' +
          (isSat ? "שבת — לא מפרסמים." : "יום פנוי — אין פוסטים מתוזמנים.") + "</div>") +
        '<div class="sc-dayview">' + rows + "</div>";
      document.querySelectorAll(".sc-dpost").forEach(function (el) {
        el.addEventListener("click", function () {
          var post = state.allPosts.filter(function (p) { return String(p.id) === String(el.dataset.postId); })[0];
          if (post) openPostModal(post, load);
        });
      });
      var target = document.querySelector(".sc-hour-now") ||
        (dayPosts.length ? document.querySelector('.sc-hour[data-hour="' + jerusalemHour(dayPosts[0].scheduledFor) + '"]') : null);
      if (target) setTimeout(function () { target.scrollIntoView({ behavior: "smooth", block: "center" }); }, 60);
    }

    function renderListView() {
      var showHist = window.__showHistory === true;
      var posts = state.allPosts.filter(function (p) { return showHist || p.status !== "published"; })
        .sort(function (a, b) { return String(a.scheduledFor).localeCompare(String(b.scheduledFor)); });
      if (showHist) posts.reverse();
      var groups = {};
      posts.forEach(function (p) {
        var day = CC.fmtDateHe(p.scheduledFor);
        (groups[day] = groups[day] || []).push(p);
      });
      var html = '<p><button class="btn secondary small" id="toggle-history">' +
        (showHist ? "הסתר פוסטים שפורסמו" : "הצג גם פוסטים שפורסמו") + "</button></p>";
      if (!posts.length) {
        html += emptyState("אין פוסטים מתוזמנים");
      } else {
        Object.keys(groups).forEach(function (day) {
          html += '<div class="section"><h2 class="section-title">' + esc(day) + "</h2>" +
            '<div class="grid" style="grid-template-columns:1fr">' +
            groups[day].map(postCardHtml).join("") + "</div></div>";
        });
      }
      document.getElementById("sc-summary").innerHTML = "";
      document.getElementById("sc-body").innerHTML = html;
      var th = document.getElementById("toggle-history");
      if (th) th.addEventListener("click", function () { window.__showHistory = !showHist; renderListView(); });
      document.getElementById("sc-body").querySelectorAll("[data-move-id]").forEach(function (btn) {
        btn.addEventListener("click", function () { openMoveInline(btn.dataset.moveId, btn); });
      });
      document.getElementById("sc-body").querySelectorAll("[data-cancel-id]").forEach(function (btn) {
        btn.addEventListener("click", function () { cancelPost(btn.dataset.cancelId, btn, renderListView); });
      });
    }

    function postCardHtml(p) {
      var statusMap = { scheduled: "warn", published: "ok", failed: "err" };
      var badgeCls = statusMap[p.status] || "neutral";
      var platforms = (p.platforms || []).map(function (pl) { return '<span class="badge neutral">' + esc(pl) + "</span>"; }).join(" ");
      return '<div class="card">' +
        '<div style="display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap">' +
          '<div><span class="badge ' + badgeCls + '">' + esc(p.status || "—") + "</span> " + platforms +
          ' <span class="kpi-sub">' + CC.fmtTimeHe(p.scheduledFor) + "</span></div>" +
          (p.url ? '<a href="' + esc(p.url) + '" target="_blank" rel="noopener" class="kpi-sub">צפה בפוסט ↗</a>' : "") +
        "</div>" +
        '<div style="margin:8px 0;font-size:13px">' + esc((p.content || "").slice(0, 180)) + "</div>" +
        '<div class="row" style="align-items:center">' +
          '<button class="btn small secondary" data-move-id="' + esc(p.id) + '" type="button">הזז</button>' +
          '<button class="btn small danger" data-cancel-id="' + esc(p.id) + '" type="button">בטל</button>' +
        "</div></div>";
    }

    function openMoveInline(id, btn) {
      var existing = btn.parentElement.querySelector(".move-input");
      if (existing) { existing.remove(); return; }
      var wrap = h('<span class="move-input" style="display:inline-flex;gap:6px;align-items:center;margin-inline-start:8px">' +
        '<input type="datetime-local" style="width:auto"><button class="btn small" type="button">אישור</button></span>');
      btn.parentElement.appendChild(wrap);
      wrap.querySelector("button").addEventListener("click", function () {
        var val = wrap.querySelector("input").value;
        if (!val) return;
        movePost(id, new Date(val).toISOString(), function () { renderListView(); });
      });
    }

    function movePost(id, iso, done) {
      api("/posts/move", { method: "POST", body: { id: id, scheduledFor: iso } })
        .then(function () { toast("הפוסט הוזז", "ok"); load(true); if (done) done(); })
        .catch(function (err) { toast(err.message, "err"); });
    }

    function cancelPost(id, btn, done) {
      if (!confirm("לבטל את הפוסט?")) return;
      btn.disabled = true;
      api("/posts/cancel", { method: "POST", body: { id: id } })
        .then(function () { toast("הפוסט בוטל", "ok"); load(true); if (done) done(); })
        .catch(function (err) { toast(err.message, "err"); btn.disabled = false; });
    }

    function renderCalendarView() {
      var year = state.cursor.getFullYear(), month = state.cursor.getMonth();
      var firstOfMonth = new Date(year, month, 1);
      var startOffset = firstOfMonth.getDay(); // 0=Sunday
      var daysInMonth = new Date(year, month + 1, 0).getDate();
      var gridStart = new Date(year, month, 1 - startOffset);

      var byDay = {};
      state.allPosts.forEach(function (p) {
        var day = jerusalemYMD(p.scheduledFor);
        if (!day) return;
        (byDay[day] = byDay[day] || []).push(p);
      });

      var todayStr = ymd(new Date());
      var cells = "";
      var totalCells = Math.ceil((startOffset + daysInMonth) / 7) * 7;
      var emptyNonSaturdayDays = 0;
      var counts = { scheduled: 0, published: 0, failed: 0 };

      for (var i = 0; i < totalCells; i++) {
        var d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i);
        var inMonth = d.getMonth() === month;
        var dstr = ymd(d);
        var dayPosts = byDay[dstr] || [];
        var isToday = dstr === todayStr;
        var isSaturday = d.getDay() === 6;
        if (inMonth) {
          dayPosts.forEach(function (p) { if (counts[p.status] !== undefined) counts[p.status]++; });
          if (!dayPosts.length && !isSaturday) emptyNonSaturdayDays++;
        }
        var chipsHtml = dayPosts.slice(0, 4).map(function (p) {
          var statusMap = { scheduled: "warn", published: "ok", failed: "err" };
          var cls = statusMap[p.status] || "neutral";
          var plat = (p.platforms || [])[0] || "";
          var icon = PLATFORM_ICON[plat] || plat;
          return '<button type="button" class="badge ' + cls + ' sc-chip" data-post-id="' + esc(p.id) +
            '" style="display:flex;align-items:center;gap:4px;width:100%;margin-bottom:3px;text-align:right;border:none">' +
            (p.thumb ? '<img referrerpolicy="no-referrer" src="' + esc(p.thumb) + '" style="width:16px;height:16px;object-fit:cover;border-radius:3px" alt="">' : "") +
            "<span>" + esc(icon) + " " + CC.fmtTimeHe(p.scheduledFor) + "</span></button>";
        }).join("");
        var extra = dayPosts.length > 4 ? '<div class="kpi-sub">+' + (dayPosts.length - 4) + " נוספים</div>" : "";
        cells += '<div class="sc-day' + (inMonth ? "" : " sc-day-out") + (isToday ? " sc-day-today" : "") +
          (isSaturday ? " sc-day-sat" : "") + '" data-date="' + dstr + '">' +
          '<div class="sc-day-num">' + d.getDate() + "</div>" +
          '<div class="sc-day-chips">' + chipsHtml + extra + "</div>" +
          "</div>";
      }

      document.getElementById("sc-summary").innerHTML =
        '<div class="row" style="gap:16px">' +
          '<span class="kpi-sub">מתוזמנים: <b style="color:var(--warn)">' + counts.scheduled + "</b></span>" +
          '<span class="kpi-sub">פורסמו: <b style="color:var(--ok)">' + counts.published + "</b></span>" +
          '<span class="kpi-sub">נכשלו: <b style="color:var(--err)">' + counts.failed + "</b></span>" +
          '<span class="kpi-sub">ימים ריקים (לא שבת): <b>' + emptyNonSaturdayDays + "</b></span>" +
        "</div>";

      var html = '<div class="sc-cal">' +
        '<div class="sc-week-header">' + HE_DAYS.map(function (l) { return '<div class="sc-day-label">' + l + "</div>"; }).join("") + "</div>" +
        '<div class="sc-grid">' + cells + "</div></div>";
      document.getElementById("sc-body").innerHTML = html;

      document.querySelectorAll(".sc-day").forEach(function (cell) {
        cell.addEventListener("click", function (e) {
          if (e.target.closest(".sc-chip")) return;
          var parts = cell.dataset.date.split("-");
          state.cursor = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
          state.view = "day";
          renderBody();
        });
      });
      document.querySelectorAll(".sc-chip").forEach(function (chip) {
        chip.addEventListener("click", function () {
          var id = chip.dataset.postId;
          var post = state.allPosts.filter(function (p) { return String(p.id) === String(id); })[0];
          if (post) openPostModal(post, load);
        });
      });
    }
  }

  function openPostModal(p, reload) {
    var root = document.getElementById("sc-modal-root");
    var statusMap = { scheduled: "warn", published: "ok", failed: "err" };
    var badgeCls = statusMap[p.status] || "neutral";
    var platforms = (p.platforms || []).map(function (pl) { return '<span class="badge neutral">' + esc(pl) + "</span>"; }).join(" ");
    var modal = h('<div class="sc-modal-backdrop">' +
      '<div class="sc-modal card">' +
        '<div style="display:flex;justify-content:space-between;align-items:center">' +
          '<h3 style="margin:0">פרטי פוסט</h3><button type="button" class="btn small secondary" id="sc-modal-close">סגור ✕</button>' +
        "</div>" +
        (p.thumb ? '<img referrerpolicy="no-referrer" src="' + esc(p.thumb) + '" style="width:100%;max-height:240px;object-fit:cover;border-radius:8px;margin:10px 0">' : "") +
        '<div style="margin:8px 0"><span class="badge ' + badgeCls + '">' + esc(p.status || "—") + "</span> " + platforms + "</div>" +
        '<div class="kpi-sub">מתוזמן ל: ' + CC.fmtDateHe(p.scheduledFor) + " " + CC.fmtTimeHe(p.scheduledFor) + "</div>" +
        (state.eng[p.id] ? '<div style="margin-top:6px">' + engLine(p.id) + "</div>" : "") +
        '<div style="margin:10px 0;font-size:13px;white-space:pre-wrap">' + esc(p.content || "") + "</div>" +
        (p.url ? '<a href="' + esc(p.url) + '" target="_blank" rel="noopener" class="btn small secondary">פתח פוסט ↗</a>' : "") +
        '<div class="row" style="margin-top:14px">' +
          '<input type="datetime-local" id="sc-modal-date" style="flex:1">' +
          '<button class="btn small" id="sc-modal-move" type="button">הזז</button>' +
          '<button class="btn small danger" id="sc-modal-cancel" type="button">בטל</button>' +
        "</div>" +
      "</div></div>");
    root.innerHTML = "";
    root.appendChild(modal);

    modal.querySelector("#sc-modal-close").addEventListener("click", function () { root.innerHTML = ""; });
    modal.addEventListener("click", function (e) { if (e.target === modal) root.innerHTML = ""; });
    modal.querySelector("#sc-modal-move").addEventListener("click", function () {
      var val = modal.querySelector("#sc-modal-date").value;
      if (!val) { toast("בחר תאריך ושעה", "err"); return; }
      api("/posts/move", { method: "POST", body: { id: p.id, scheduledFor: new Date(val).toISOString() } })
        .then(function () { toast("הפוסט הוזז", "ok"); root.innerHTML = ""; reload(true); })
        .catch(function (err) { toast(err.message, "err"); });
    });
    modal.querySelector("#sc-modal-cancel").addEventListener("click", function () {
      if (!confirm("לבטל את הפוסט?")) return;
      api("/posts/cancel", { method: "POST", body: { id: p.id } })
        .then(function () { toast("הפוסט בוטל", "ok"); root.innerHTML = ""; reload(true); })
        .catch(function (err) { toast(err.message, "err"); });
    });
  }

  CC.registerRoute("schedule", renderSchedule);
})();
