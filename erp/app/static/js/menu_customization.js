(function () {
  "use strict";

  const root = document.getElementById("menuCustomizationPage");
  if (!root) return;

  const urls = {
    list: root.dataset.listUrl,
    move: root.dataset.moveUrl,
    add: root.dataset.addUrl,
    edit: root.dataset.editUrl,
    remove: root.dataset.removeUrl,
  };

  const ICON_CHOICES = [
    "bi-circle", "bi-folder", "bi-folder2-open", "bi-grid", "bi-list-ul",
    "bi-house", "bi-speedometer2", "bi-gear", "bi-sliders", "bi-tools",
    "bi-people", "bi-person", "bi-person-badge", "bi-person-vcard", "bi-building",
    "bi-bank", "bi-cash", "bi-cash-coin", "bi-wallet2", "bi-credit-card",
    "bi-receipt", "bi-receipt-cutoff", "bi-calculator", "bi-graph-up", "bi-bar-chart",
    "bi-pie-chart", "bi-clipboard", "bi-clipboard-data", "bi-journal-text", "bi-book",
    "bi-file-earmark", "bi-file-earmark-text", "bi-file-earmark-spreadsheet", "bi-files",
    "bi-box", "bi-box-seam", "bi-boxes", "bi-cart", "bi-bag", "bi-shop",
    "bi-truck", "bi-briefcase", "bi-kanban", "bi-table", "bi-card-list",
    "bi-tags", "bi-tag", "bi-bookmark", "bi-star", "bi-heart",
    "bi-bell", "bi-envelope", "bi-chat", "bi-telephone", "bi-printer",
    "bi-upc-scan", "bi-qr-code", "bi-key", "bi-shield-lock", "bi-lock",
    "bi-cloud", "bi-cloud-upload", "bi-cloud-download", "bi-hdd", "bi-database",
    "bi-server", "bi-hdd-network", "bi-wifi", "bi-globe", "bi-link-45deg",
    "bi-calendar", "bi-calendar-check", "bi-clock", "bi-alarm", "bi-hourglass",
    "bi-check2-circle", "bi-x-circle", "bi-exclamation-triangle", "bi-info-circle",
    "bi-question-circle", "bi-plus-circle", "bi-dash-circle", "bi-arrow-repeat",
    "bi-arrow-left-right", "bi-arrows-move", "bi-pencil", "bi-trash", "bi-eye",
    "bi-search", "bi-funnel", "bi-sort-down", "bi-ui-checks", "bi-ui-checks-grid",
    "bi-window", "bi-layout-text-window", "bi-collection", "bi-layers", "bi-stack",
    "bi-puzzle", "bi-lightning", "bi-magic", "bi-palette", "bi-brush",
    "bi-image", "bi-camera", "bi-paperclip", "bi-pin-map", "bi-geo-alt",
    "bi-compass", "bi-flag", "bi-award", "bi-trophy", "bi-gem",
  ];

  const els = {
    body: document.getElementById("mcustBody"),
    count: document.getElementById("mcustCount"),
    status: document.getElementById("mcustStatus"),
    levelTitle: document.getElementById("mcustLevelTitle"),
    breadcrumb: document.getElementById("mcustBreadcrumb"),
    btnBack: document.getElementById("mcustBtnBack"),
    btnOpen: document.getElementById("mcustBtnOpen"),
    btnUp: document.getElementById("mcustBtnUp"),
    btnDown: document.getElementById("mcustBtnDown"),
    btnAdd: document.getElementById("mcustBtnAdd"),
    btnEdit: document.getElementById("mcustBtnEdit"),
    btnRemove: document.getElementById("mcustBtnRemove"),
    btnRefresh: document.getElementById("mcustBtnRefresh"),
    addTitle: document.getElementById("mcustAddTitle"),
    addHint: document.getElementById("mcustAddHint"),
    addName: document.getElementById("mcustAddName"),
    addUrl: document.getElementById("mcustAddUrl"),
    addIcon: document.getElementById("mcustAddIcon"),
    addError: document.getElementById("mcustAddError"),
    addSave: document.getElementById("mcustAddSave"),
    urlHint: document.getElementById("mcustUrlHint"),
    iconPreview: document.getElementById("mcustIconPreview"),
    btnBrowseIcon: document.getElementById("mcustBtnBrowseIcon"),
    iconGrid: document.getElementById("mcustIconGrid"),
    iconSearch: document.getElementById("mcustIconSearch"),
  };

  let parentId = null;
  let parentUrl = "";
  let breadcrumb = [];
  let items = [];
  let selectedId = null;
  let addModal = null;
  let iconModal = null;
  let urlManualEdit = false;
  let formMode = "add"; // add | edit
  let editingId = null;

  function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta && meta.content) return meta.content;
    const input = document.querySelector('input[name="csrf_token"]');
    return input ? input.value : "";
  }

  function setStatus(msg, isError) {
    if (!els.status) return;
    els.status.textContent = msg || "";
    els.status.classList.toggle("text-danger", !!isError);
    els.status.classList.toggle("text-success", !!msg && !isError);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function slugFromMenuName(name) {
    let s = String(name || "").trim().toLowerCase();
    s = s.replace(/[/\\]+/g, " ");
    s = s.replace(/&/g, " and ");
    s = s.replace(/[^a-z0-9\s_-]/g, " ");
    s = s.replace(/[\s-]+/g, "_");
    s = s.replace(/_+/g, "_").replace(/^_|_$/g, "");
    // Match existing Masters URLs: "Bank Master" → bank, "Item Master" → item
    s = s.replace(/_master$/g, "");
    s = s.replace(/^master_/g, "");
    return s;
  }

  function buildAutoUrl(menuName) {
    const slug = slugFromMenuName(menuName);
    if (!slug) return "";
    if (parentId == null) {
      // Top-level: leave blank so it can be a dropdown parent, unless user wants a link
      return "";
    }
    const base = (parentUrl || "").replace(/\/+$/, "");
    if (!base) {
      const parentName =
        (breadcrumb.length && breadcrumb[breadcrumb.length - 1].name) || "";
      const parentSlug = slugFromMenuName(parentName);
      return parentSlug ? "/" + parentSlug + "/" + slug : "/" + slug;
    }
    return base + "/" + slug;
  }

  function syncAutoUrl() {
    if (urlManualEdit) return;
    if (parentId == null) {
      // Main level: optional URL — keep empty unless user typed a name and wants a leaf
      els.addUrl.value = "";
      if (els.urlHint) {
        els.urlHint.textContent =
          "Main menu: leave URL blank for a dropdown parent.";
      }
      return;
    }
    const auto = buildAutoUrl(els.addName.value);
    els.addUrl.value = auto;
    if (els.urlHint) {
      const base = (parentUrl || "/…").replace(/\/+$/, "");
      els.urlHint.textContent =
        "Auto: " + base + "/ + menu name (spaces → _, trailing “Master” removed).";
    }
  }

  function normalizeIconClass(raw) {
    let s = String(raw || "").trim();
    if (!s) return "bi-circle";
    s = s.replace(/\s+/g, "-");
    if (!s.startsWith("bi-")) {
      if (s.startsWith("bi")) s = "bi-" + s.slice(2).replace(/^-+/, "");
      else s = "bi-" + s.replace(/^-+/, "");
    }
    s = s.replace(/-+/g, "-");
    return s;
  }

  function updateIconPreview() {
    if (!els.iconPreview) return;
    const cls = normalizeIconClass(els.addIcon.value);
    els.iconPreview.innerHTML = '<i class="bi ' + escapeHtml(cls) + '"></i>';
  }

  function selectedRow() {
    return (
      items.find(function (row) {
        return row.menu_id === selectedId;
      }) || null
    );
  }

  function updateButtons() {
    const idx = items.findIndex(function (row) {
      return row.menu_id === selectedId;
    });
    const row = idx >= 0 ? items[idx] : null;
    els.btnBack.disabled = parentId == null;
    els.btnOpen.disabled = !row || !row.has_children;
    els.btnUp.disabled = idx <= 0;
    els.btnDown.disabled = idx < 0 || idx >= items.length - 1;
    if (els.btnEdit) els.btnEdit.disabled = !row;
    els.btnRemove.disabled = !row || !!row.protected;
  }

  function renderBreadcrumb() {
    if (parentId == null) {
      els.levelTitle.textContent = "Main menus";
      els.breadcrumb.innerHTML = "";
      els.addHint.textContent = "Adding under: Main menus";
      els.addTitle.textContent = "Add main menu";
      return;
    }
    const parentName =
      (breadcrumb.length && breadcrumb[breadcrumb.length - 1].name) || "Submenus";
    els.levelTitle.textContent = "Submenus of " + parentName;
    els.addHint.textContent = "Adding under: " + parentName;
    els.addTitle.textContent = "Add submenu";

    const parts = ['<a href="#" data-parent="null">Main menus</a>'];
    breadcrumb.forEach(function (crumb) {
      parts.push(
        '<a href="#" data-parent="' +
          crumb.menu_id +
          '">' +
          escapeHtml(crumb.name) +
          "</a>"
      );
    });
    els.breadcrumb.innerHTML = parts.join(
      ' <span class="text-muted">/</span> '
    );
  }

  function render() {
    renderBreadcrumb();
    els.count.textContent =
      items.length + " item" + (items.length === 1 ? "" : "s");
    if (!items.length) {
      els.body.innerHTML =
        '<tr><td colspan="5" class="text-muted text-center py-4">No menus at this level.</td></tr>';
      updateButtons();
      return;
    }
    els.body.innerHTML = items
      .map(function (row) {
        const selected = row.menu_id === selectedId ? " mcust-selected" : "";
        const locked = row.protected ? " mcust-protected" : "";
        const badge = row.protected
          ? ' <span class="badge text-bg-secondary">Protected</span>'
          : "";
        const sub = row.has_children
          ? '<span class="badge text-bg-light border">' +
            row.child_count +
            "</span>"
          : '<span class="text-muted">—</span>';
        return (
          '<tr class="' +
          selected +
          locked +
          '" data-id="' +
          row.menu_id +
          '" data-has-children="' +
          (row.has_children ? "1" : "0") +
          '">' +
          '<td class="text-center"><i class="bi ' +
          escapeHtml(row.icon || "bi-circle") +
          ' mcust-icon"></i></td>' +
          "<td><strong>" +
          escapeHtml(row.name) +
          "</strong>" +
          badge +
          (row.has_children
            ? ' <i class="bi bi-chevron-right text-muted small" title="Has submenus"></i>'
            : "") +
          "</td>" +
          '<td class="small text-muted">' +
          escapeHtml(row.url || "(dropdown parent)") +
          "</td>" +
          '<td class="text-center">' +
          sub +
          "</td>" +
          '<td class="text-end">' +
          escapeHtml(row.display_order) +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
    updateButtons();
  }

  async function api(url, options) {
    const opts = options || {};
    const headers = Object.assign(
      { Accept: "application/json" },
      opts.headers || {}
    );
    if (opts.method && opts.method !== "GET") {
      headers["Content-Type"] = "application/json";
      const token = csrfToken();
      if (token) headers["X-CSRFToken"] = token;
    }
    const res = await fetch(url, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin",
    });
    const data = await res.json().catch(function () {
      return { ok: false, error: "Invalid server response." };
    });
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Request failed.");
    }
    return data;
  }

  function listUrlFor(pid) {
    if (pid == null) return urls.list;
    return (
      urls.list +
      (urls.list.indexOf("?") >= 0 ? "&" : "?") +
      "parent_id=" +
      encodeURIComponent(pid)
    );
  }

  async function loadList(pid) {
    if (typeof pid !== "undefined") parentId = pid;
    setStatus("Loading…");
    try {
      const data = await api(listUrlFor(parentId));
      items = data.items || [];
      breadcrumb = data.breadcrumb || [];
      parentId = data.parent_id == null ? null : data.parent_id;
      parentUrl = data.parent_url || "";
      if (
        selectedId != null &&
        !items.some(function (row) {
          return row.menu_id === selectedId;
        })
      ) {
        selectedId = null;
      }
      render();
      setStatus("Ready. Double-click a menu with submenus to open it.");
    } catch (err) {
      els.body.innerHTML =
        '<tr><td colspan="5" class="text-danger text-center py-4">' +
        escapeHtml(err.message || "Load failed") +
        "</td></tr>";
      setStatus(err.message || "Load failed", true);
    }
  }

  function openSelected() {
    const row = selectedRow();
    if (!row || !row.has_children) return;
    selectedId = null;
    loadList(row.menu_id);
  }

  function goBack() {
    if (parentId == null) return;
    if (breadcrumb.length <= 1) {
      selectedId = parentId;
      loadList(null);
      return;
    }
    const parentCrumb = breadcrumb[breadcrumb.length - 2];
    selectedId = parentId;
    loadList(parentCrumb.menu_id);
  }

  async function move(direction) {
    if (selectedId == null) return;
    try {
      const data = await api(urls.move, {
        method: "POST",
        body: {
          menu_id: selectedId,
          direction: direction,
          parent_id: parentId,
        },
      });
      items = data.items || [];
      breadcrumb = data.breadcrumb || [];
      parentUrl = data.parent_url || parentUrl;
      render();
      setStatus("Order updated. Refresh the page to see menu change.");
    } catch (err) {
      setStatus(err.message || "Move failed", true);
    }
  }

  async function removeSelected() {
    const row = selectedRow();
    if (!row || row.protected) return;
    const label = parentId == null ? "main menu ribbon" : "submenu list";
    if (!window.confirm('Remove "' + row.name + '" from the ' + label + "?")) {
      return;
    }
    try {
      const data = await api(urls.remove, {
        method: "POST",
        body: { menu_id: selectedId, parent_id: parentId },
      });
      items = data.items || [];
      breadcrumb = data.breadcrumb || [];
      parentUrl = data.parent_url || parentUrl;
      selectedId = null;
      render();
      setStatus("Removed. Refresh the page to update menus.");
    } catch (err) {
      setStatus(err.message || "Remove failed", true);
    }
  }

  function openFormModal(mode) {
    formMode = mode === "edit" ? "edit" : "add";
    els.addError.classList.add("d-none");
    renderBreadcrumb();

    if (formMode === "edit") {
      const row = selectedRow();
      if (!row) return;
      editingId = row.menu_id;
      urlManualEdit = true; // keep existing URL unless user changes name and wants auto
      els.addTitle.textContent =
        parentId == null ? "Edit main menu" : "Edit submenu";
      els.addHint.textContent =
        "Editing: " +
        row.name +
        (parentId == null
          ? ""
          : " (under " +
            ((breadcrumb.length && breadcrumb[breadcrumb.length - 1].name) ||
              "parent") +
            ")");
      els.addName.value = row.name || "";
      els.addUrl.value = row.url || "";
      els.addIcon.value = normalizeIconClass(row.icon || "bi-circle");
      els.addSave.textContent = "Save changes";
      els.addSave.classList.remove("btn-success");
      els.addSave.classList.add("btn-warning");
    } else {
      editingId = null;
      urlManualEdit = false;
      els.addTitle.textContent =
        parentId == null ? "Add main menu" : "Add submenu";
      els.addName.value = "";
      els.addUrl.value = "";
      els.addIcon.value = "bi-circle";
      els.addSave.textContent = "Add menu";
      els.addSave.classList.remove("btn-warning");
      els.addSave.classList.add("btn-success");
      syncAutoUrl();
    }
    updateIconPreview();

    if (window.bootstrap && window.bootstrap.Modal) {
      addModal = window.bootstrap.Modal.getOrCreateInstance(
        document.getElementById("mcustAddModal")
      );
      addModal.show();
      setTimeout(function () {
        els.addName.focus();
      }, 200);
    }
  }

  async function saveForm() {
    els.addError.classList.add("d-none");
    const name = (els.addName.value || "").trim();
    if (!name) {
      els.addError.textContent = "Menu name is required.";
      els.addError.classList.remove("d-none");
      return;
    }
    if (formMode === "add" && !urlManualEdit) syncAutoUrl();
    const icon = normalizeIconClass(els.addIcon.value);
    const body = {
      name: name,
      url: (els.addUrl.value || "").trim(),
      icon: icon,
      parent_id: parentId,
    };
    try {
      let data;
      if (formMode === "edit") {
        body.menu_id = editingId;
        data = await api(urls.edit, { method: "POST", body: body });
        setStatus("Menu updated. Refresh the page to see ribbon change.");
      } else {
        data = await api(urls.add, { method: "POST", body: body });
        setStatus("Menu added. Refresh the page to see it.");
      }
      items = data.items || [];
      breadcrumb = data.breadcrumb || [];
      parentUrl = data.parent_url || parentUrl;
      selectedId = data.menu_id || selectedId;
      render();
      if (addModal) addModal.hide();
      els.addName.value = "";
      els.addUrl.value = "";
      els.addIcon.value = "";
      urlManualEdit = false;
      formMode = "add";
      editingId = null;
      updateIconPreview();
    } catch (err) {
      els.addError.textContent =
        err.message || (formMode === "edit" ? "Update failed" : "Add failed");
      els.addError.classList.remove("d-none");
    }
  }

  function renderIconGrid(filter) {
    if (!els.iconGrid) return;
    const q = String(filter || "")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "-");
    const list = ICON_CHOICES.filter(function (name) {
      if (!q) return true;
      return name.indexOf(q) >= 0 || name.replace(/^bi-/, "").indexOf(q) >= 0;
    });
    if (!list.length) {
      els.iconGrid.innerHTML =
        '<div class="text-muted small p-2">No icons match.</div>';
      return;
    }
    els.iconGrid.innerHTML = list
      .map(function (name) {
        return (
          '<button type="button" class="mcust-icon-pick" data-icon="' +
          escapeHtml(name) +
          '" title="' +
          escapeHtml(name) +
          '">' +
          '<i class="bi ' +
          escapeHtml(name) +
          '"></i>' +
          "<span>" +
          escapeHtml(name.replace(/^bi-/, "")) +
          "</span>" +
          "</button>"
        );
      })
      .join("");
  }

  function openIconBrowser() {
    renderIconGrid("");
    if (els.iconSearch) els.iconSearch.value = "";
    if (window.bootstrap && window.bootstrap.Modal) {
      iconModal = window.bootstrap.Modal.getOrCreateInstance(
        document.getElementById("mcustIconModal")
      );
      iconModal.show();
      setTimeout(function () {
        if (els.iconSearch) els.iconSearch.focus();
      }, 200);
    }
  }

  els.body.addEventListener("click", function (ev) {
    const tr = ev.target.closest("tr[data-id]");
    if (!tr) return;
    selectedId = parseInt(tr.getAttribute("data-id"), 10);
    render();
  });

  els.body.addEventListener("dblclick", function (ev) {
    const tr = ev.target.closest("tr[data-id]");
    if (!tr) return;
    selectedId = parseInt(tr.getAttribute("data-id"), 10);
    render();
    openSelected();
  });

  els.breadcrumb.addEventListener("click", function (ev) {
    const a = ev.target.closest("a[data-parent]");
    if (!a) return;
    ev.preventDefault();
    const raw = a.getAttribute("data-parent");
    selectedId = null;
    if (raw === "null") loadList(null);
    else loadList(parseInt(raw, 10));
  });

  els.btnBack.addEventListener("click", goBack);
  els.btnOpen.addEventListener("click", openSelected);
  els.btnUp.addEventListener("click", function () {
    move("up");
  });
  els.btnDown.addEventListener("click", function () {
    move("down");
  });
  els.btnRemove.addEventListener("click", removeSelected);
  els.btnRefresh.addEventListener("click", function () {
    loadList(parentId);
  });

  els.btnAdd.addEventListener("click", function () {
    openFormModal("add");
  });
  if (els.btnEdit) {
    els.btnEdit.addEventListener("click", function () {
      openFormModal("edit");
    });
  }
  els.addSave.addEventListener("click", saveForm);

  // If user changes name while editing, offer auto-URL again when they clear URL
  els.addName.addEventListener("change", function () {
    if (formMode === "edit" && !(els.addUrl.value || "").trim()) {
      urlManualEdit = false;
      syncAutoUrl();
    }
  });

  els.addName.addEventListener("input", function () {
    syncAutoUrl();
  });
  els.addUrl.addEventListener("input", function () {
    urlManualEdit = true;
  });
  els.addIcon.addEventListener("input", function () {
    updateIconPreview();
  });
  if (els.btnBrowseIcon) {
    els.btnBrowseIcon.addEventListener("click", openIconBrowser);
  }
  if (els.iconSearch) {
    els.iconSearch.addEventListener("input", function () {
      renderIconGrid(els.iconSearch.value);
    });
  }
  if (els.iconGrid) {
    els.iconGrid.addEventListener("click", function (ev) {
      const btn = ev.target.closest(".mcust-icon-pick");
      if (!btn) return;
      els.addIcon.value = btn.getAttribute("data-icon") || "bi-circle";
      updateIconPreview();
      if (iconModal) iconModal.hide();
    });
  }

  loadList(null);
})();
