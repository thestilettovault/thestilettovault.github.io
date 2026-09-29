/* Products screen — stage-based catalog view (pool/pending/approved/producing/produced/scheduled/published/rejected) */
(function () {
  "use strict";
  var CC = window.CC;
  var h = CC.h, esc = CC.esc, api = CC.api, safeFetch = CC.safeFetch, toast = CC.toast;
  var card = CC.card, unavailableCard = CC.unavailableCard, emptyState = CC.emptyState, skeletonBlock = CC.skeletonBlock;

  var CHIPS = [
    { key: "all", label: "הכל", stages: null },
    { key: "pool", label: "מאגר", stages: ["pool"] },
    { key: "pending", label: "ממתין", stages: ["pending"] },
    { key: "approved", label: "מאושר", stages: ["approved"] },
    { key: "producing", label: "בהפקה", stages: ["producing", "produced", "scheduled"] },
    { key: "published", label: "פורסם", stages: ["published"] },
    { key: "rejected", label: "נדחה", stages: ["rejected"] }
  ];

  var state = { chip: "all", search: "", sort: "newest", selected: {} };

  function renderProducts() {
    var content = CC.content();
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
        '<select id="p-sort" style="flex:0 0 160px">' +
          '<option value="newest">חדש קודם</option>' +
          '<option value="price">מחיר</option>' +
          '<option value="clicks">קליקים</option>' +
        "</select>" +
      "</div>" +
      '<div class="chips" id="p-chips"></div>' +
      '<div class="row" id="p-bulk" style="display:none;margin-bottom:10px">' +
        '<span class="kpi-sub" id="p-bulk-count" style="flex:0 0 auto"></span>' +
        '<button class="btn small" id="p-bulk-approve" type="button" style="flex:0 0 auto">אשר נבחרים</button>' +
        '<button class="btn small danger" id="p-bulk-reject" type="button" style="flex:0 0 auto">דחה נבחרים</button>' +
      "</div>" +
      '<div id="p-grid">' + skeletonBlock(6) + "</div>";

    var chipsEl = document.getElementById("p-chips");
    var allProducts = [];

    CHIPS.forEach(function (c) {
      var chip = h('<button type="button" class="chip' + (c.key === state.chip ? " active" : "") +
        '" data-chip="' + c.key + '">' + esc(c.label) + ' <span class="chip-count"></span></button>');
      chip.addEventListener("click", function () {
        state.chip = c.key;
        state.selected = {};
        chipsEl.querySelectorAll(".chip").forEach(function (x) { x.classList.remove("active"); });
        chip.classList.add("active");
        renderGrid(allProducts);
      });
      chipsEl.appendChild(chip);
    });

    document.getElementById("p-search").addEventListener("input", function (e) {
      state.search = e.target.value.toLowerCase();
      renderGrid(allProducts);
    });
    document.getElementById("p-sort").addEventListener("change", function (e) {
      state.sort = e.target.value;
      renderGrid(allProducts);
    });

    document.getElementById("add-url-btn").addEventListener("click", function () {
      var input = document.getElementById("add-url");
      var url = input.value.trim();
      if (!url) return;
      var btn = document.getElementById("add-url-btn");
      btn.disabled = true;
      btn.innerHTML = '<span class="spinner"></span>מוסיף...';
      api("/products/add", { method: "POST", body: { url: url } })
        .then(function () { toast("המוצר נוסף", "ok"); input.value = ""; load(); })
        .catch(function (err) { toast(err.message, "err"); })
        .finally(function () { btn.disabled = false; btn.textContent = "הוסף"; });
    });

    document.getElementById("p-bulk-approve").addEventListener("click", function () { bulkAct("approve"); });
    document.getElementById("p-bulk-reject").addEventListener("click", function () { bulkAct("reject"); });

    load();

    function load() {
      safeFetch(api("/products")).then(function (res) {
        if (!res.ok) {
          document.getElementById("p-grid").innerHTML = unavailableCard("מוצרים");
          toast(res.error, "err");
          return;
        }
        allProducts = Array.isArray(res.data) ? res.data : [];
        updateChipCounts(allProducts);
        renderGrid(allProducts);
      });
    }

    function updateChipCounts(items) {
      chipsEl.querySelectorAll(".chip").forEach(function (chipEl) {
        var key = chipEl.dataset.chip;
        var def = CHIPS.filter(function (c) { return c.key === key; })[0];
        var n = def.stages ? items.filter(function (p) { return def.stages.indexOf(p.stage) !== -1; }).length : items.length;
        chipEl.querySelector(".chip-count").textContent = "(" + n + ")";
      });
    }

    function filtered(items) {
      var def = CHIPS.filter(function (c) { return c.key === state.chip; })[0];
      var out = items.filter(function (p) {
        if (def.stages && def.stages.indexOf(p.stage) === -1) return false;
        if (state.search) {
          var hay = ((p.title || "") + " " + (p.domain || "")).toLowerCase();
          if (hay.indexOf(state.search) === -1) return false;
        }
        return true;
      });
      if (state.sort === "price") {
        out.sort(function (a, b) { return (Number(priceOf(b)) || 0) - (Number(priceOf(a)) || 0); });
      } else if (state.sort === "clicks") {
        out.sort(function (a, b) { return (b.clicks || 0) - (a.clicks || 0); });
      } else {
        out.sort(function (a, b) { return String(b.date || "").localeCompare(String(a.date || "")); });
      }
      return out;
    }

    function priceOf(p) {
      if (p.price !== null && p.price !== undefined) return p.price;
      if (p.deal && p.deal.sale) return p.deal.sale;
      return null;
    }

    function renderGrid(items) {
      var list = filtered(items);
      var bulkBar = document.getElementById("p-bulk");
      var showBulk = state.chip === "pool" || state.chip === "pending";
      bulkBar.style.display = showBulk ? "flex" : "none";

      var target = document.getElementById("p-grid");
      if (!list.length) {
        target.innerHTML = emptyState("אין מוצרים תואמים");
        updateBulkCount();
        return;
      }
      target.innerHTML = '<div class="cards-grid" id="p-cards"></div>';
      var wrap = document.getElementById("p-cards");
      list.forEach(function (p) {
        wrap.appendChild(productCard(p, showBulk));
      });
      updateBulkCount();
    }

    function updateBulkCount() {
      var n = Object.keys(state.selected).filter(function (k) { return state.selected[k]; }).length;
      document.getElementById("p-bulk-count").textContent = n ? n + " נבחרו" : "";
    }

    function productCard(p, showCheckbox) {
      var price = priceOf(p);
      var dealHtml = "";
      if (p.deal && p.deal.discount) {
        dealHtml = '<span class="badge warn">' + esc(p.deal.discount) + " הנחה</span>";
      }
      var el = h('<div class="card p-card" style="display:flex;flex-direction:column;gap:8px">' +
        (showCheckbox ? '<label style="align-self:flex-start"><input type="checkbox" class="p-select"> בחר</label>' : "") +
        (p.image_url ? '<img class="thumb" loading="lazy" style="width:100%;height:150px" src="' + esc(p.image_url) + '" alt="">'
          : '<div class="thumb" style="width:100%;height:150px"></div>') +
        '<div style="font-size:13px;font-weight:600;line-height:1.3">' + esc(p.title || "—") + "</div>" +
        '<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">' +
          CC.statusBadgeHtml(p.stage) + dealHtml +
          (price ? '<span class="kpi-sub">' + CC.money(price) + "</span>" : "") +
        "</div>" +
        '<div class="kpi-sub">' + esc(p.domain || "—") + " · " + (p.clicks || 0) + " קליקים · " + (p.sales || 0) + " מכירות</div>" +
        '<div class="row p-actions" style="margin-top:auto"></div>' +
      "</div>");

      if (showCheckbox) {
        var cb = el.querySelector(".p-select");
        cb.checked = !!state.selected[p.key];
        cb.addEventListener("change", function () {
          state.selected[p.key] = cb.checked;
          updateBulkCount();
        });
      }

      var actions = el.querySelector(".p-actions");
      if (p.stage === "pool" || p.stage === "pending") {
        var approveBtn = h('<button class="btn small" type="button">אשר ✅</button>');
        var rejectBtn = h('<button class="btn small danger" type="button">דחה ❌</button>');
        approveBtn.addEventListener("click", function () { actOnProduct(p, "approve", approveBtn); });
        rejectBtn.addEventListener("click", function () { actOnProduct(p, "reject", rejectBtn); });
        actions.appendChild(approveBtn);
        actions.appendChild(rejectBtn);
      } else if (p.stage === "rejected") {
        var undoBtn = h('<button class="btn small secondary" type="button">החזר</button>');
        undoBtn.addEventListener("click", function () { undoReject(p, undoBtn); });
        actions.appendChild(undoBtn);
      } else {
        var link = p.aff_link || p.url;
        if (link) {
          var openBtn = h('<a class="btn small secondary" target="_blank" rel="noopener" href="' + esc(link) + '">פתח מוצר ↗</a>');
          actions.appendChild(openBtn);
        }
      }
      return el;
    }

    function actOnProduct(p, action, btn) {
      btn.disabled = true;
      var body = action === "approve"
        ? { url: p.url, title: p.title, image_url: p.image_url, domain: p.domain, commission: p.commission, pending_id: p.pending_id || "" }
        : { url: p.url, title: p.title, pending_id: p.pending_id || "" };
      // optimistic: move it out of the current chip immediately
      p.stage = action === "approve" ? "approved" : "rejected";
      renderGrid(allProducts);
      api("/products/" + action, { method: "POST", body: body })
        .then(function () {
          toast(action === "approve" ? "המוצר אושר" : "המוצר נדחה", "ok");
          load();
        })
        .catch(function (err) { toast(err.message, "err"); load(); });
    }

    function undoReject(p, btn) {
      btn.disabled = true;
      api("/products/undo_reject", { method: "POST", body: { url: p.url } })
        .then(function () { toast("המוצר הוחזר", "ok"); load(); })
        .catch(function (err) { toast(err.message, "err"); btn.disabled = false; });
    }

    function bulkAct(action) {
      var keys = Object.keys(state.selected).filter(function (k) { return state.selected[k]; });
      if (!keys.length) { toast("לא נבחרו מוצרים", "err"); return; }
      var items = allProducts.filter(function (p) { return keys.indexOf(p.key) !== -1; });
      Promise.all(items.map(function (p) {
        var body = action === "approve"
          ? { url: p.url, title: p.title, image_url: p.image_url, domain: p.domain, commission: p.commission, pending_id: p.pending_id || "" }
          : { url: p.url, title: p.title, pending_id: p.pending_id || "" };
        return api("/products/" + action, { method: "POST", body: body }).catch(function () { return null; });
      })).then(function () {
        toast(action === "approve" ? "המוצרים אושרו" : "המוצרים נדחו", "ok");
        state.selected = {};
        load();
      });
    }
  }

  CC.registerRoute("products", renderProducts);
})();
