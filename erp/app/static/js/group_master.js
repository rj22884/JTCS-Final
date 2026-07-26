(function () {
  "use strict";

  const els = {
    addBtn: document.getElementById("gmAddBtn"),
    addNewBtn: document.getElementById("gmAddNewBtn"),
    addNewEmptyBtn: document.getElementById("gmAddNewEmptyBtn"),
    editBtn: document.getElementById("gmEditBtn"),
    editTopBtn: document.getElementById("gmEditTopBtn"),
    activeBtn: document.getElementById("gmActiveBtn"),
    activeTopBtn: document.getElementById("gmActiveTopBtn"),
    deleteBtn: document.getElementById("gmDeleteBtn"),
    deleteTopBtn: document.getElementById("gmDeleteTopBtn"),
    refreshBtn: document.getElementById("gmRefreshBtn"),
    search: document.getElementById("gmSearch"),
    count: document.getElementById("gmCount"),
    gridBody: document.getElementById("gmGridBody"),
    empty: document.getElementById("gmEmpty"),
    status: document.getElementById("gmStatus"),
    modalEl: document.getElementById("gmModal"),
    modalTitle: document.getElementById("gmModalTitle"),
    form: document.getElementById("gmForm"),
    groupId: document.getElementById("gmGroupId"),
    groupCode: document.getElementById("gmGroupCode"),
    groupName: document.getElementById("gmGroupName"),
    displayOrder: document.getElementById("gmDisplayOrder"),
    codeWrap: document.getElementById("gmCodeWrap"),
    statusWrap: document.getElementById("gmStatusWrap"),
    activeStatus: document.getElementById("gmActiveStatus"),
    tabChecks: document.querySelectorAll(".gm-tab-check"),
    saveBtn: document.getElementById("gmSaveBtn"),
  };

  if (!els.gridBody || !window.GM_API) return;

  const modal = els.modalEl ? new bootstrap.Modal(els.modalEl) : null;
  let rows = window.GM_INITIAL_ROWS || [];
  let selectedId = null;
  let formMode = "add";

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(id));
  }

  function csrfToken() {
    return window.GM_CSRF || "";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showStatus(message, type) {
    if (!els.status) return;
    if (!message) {
      els.status.classList.add("d-none");
      els.status.textContent = "";
      return;
    }
    els.status.textContent = message;
    els.status.className = "alert py-2 small mb-3 alert-" + (type || "success");
    els.status.classList.remove("d-none");
  }

  function isActive(row) {
    return row.active_status !== false && row.active_status !== 0 && row.active_status !== "0";
  }

  function setSelected(groupId) {
    selectedId = groupId || null;
    const row = rows.find(function (r) { return r.group_id === selectedId; });
    const has = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !has;
    if (els.editTopBtn) els.editTopBtn.disabled = !has;
    if (els.activeBtn) els.activeBtn.disabled = !has || !row || isActive(row);
    if (els.activeTopBtn) els.activeTopBtn.disabled = !has || !row || isActive(row);
    if (els.deleteBtn) els.deleteBtn.disabled = !has || (row && !isActive(row));
    if (els.deleteTopBtn) els.deleteTopBtn.disabled = !has || (row && !isActive(row));
    els.gridBody.querySelectorAll("tr").forEach(function (tr) {
      tr.classList.toggle("table-active", tr.dataset.id === String(selectedId));
    });
  }

  function formatTabs(row) {
    const tabs = row.tab_codes || [];
    if (!tabs.length) return "—";
    return tabs.map(function (t) { return "<code>" + escapeHtml(t) + "</code>"; }).join(", ");
  }

  function renderGrid(data) {
    rows = data || [];
    if (!rows.length) {
      els.gridBody.innerHTML = "";
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      setSelected(null);
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }
    els.gridBody.innerHTML = rows.map(function (row) {
      const active = isActive(row);
      return (
        "<tr data-id=\"" + row.group_id + "\">" +
        "<td>" + row.group_id + "</td>" +
        "<td><strong>" + escapeHtml(row.group_code) + "</strong></td>" +
        "<td>" + escapeHtml(row.group_name) + "</td>" +
        "<td class=\"gm-tabs-cell\">" + formatTabs(row) + "</td>" +
        "<td>" + row.display_order + "</td>" +
        "<td>" + (active ? '<span class="badge bg-success">Active</span>' : '<span class="badge bg-secondary">Inactive</span>') + "</td>" +
        "</tr>"
      );
    }).join("");
    setSelected(selectedId);
  }

  function loadGrid() {
    const params = new URLSearchParams();
    const search = (els.search?.value || "").trim();
    if (search) params.set("search", search);
    const url = window.GM_API.list + (params.toString() ? "?" + params.toString() : "");
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to load groups.");
        renderGrid(data.rows);
      })
      .catch(function (err) {
        showStatus(err.message, "danger");
      });
  }

  function setTabChecks(selected) {
    const set = new Set(selected || []);
    els.tabChecks.forEach(function (cb) {
      cb.checked = set.has(cb.value);
    });
  }

  function getSelectedTabs() {
    const tabs = [];
    els.tabChecks.forEach(function (cb) {
      if (cb.checked) tabs.push(cb.value);
    });
    return tabs;
  }

  function openModal(mode, record) {
    formMode = mode;
    if (els.modalTitle) {
      els.modalTitle.textContent = mode === "add" ? "Add New Customer Group" : "Edit Customer Group";
    }
    if (els.groupId) els.groupId.value = record ? String(record.group_id) : "";
    if (els.groupCode) els.groupCode.value = record ? record.group_code : "";
    if (els.groupName) els.groupName.value = record ? record.group_name : "";
    if (els.displayOrder) els.displayOrder.value = record ? record.display_order : 1;
    if (els.codeWrap) els.codeWrap.classList.toggle("d-none", mode === "edit");
    if (els.statusWrap) els.statusWrap.classList.toggle("d-none", mode !== "edit");
    if (els.activeStatus) {
      els.activeStatus.value = record && !isActive(record) ? "0" : "1";
    }
    setTabChecks(record ? record.tab_codes : ["basic", "contact", "address"]);
    modal?.show();
  }

  function saveGroup() {
    const code = (els.groupCode?.value || "").trim().toUpperCase();
    const name = (els.groupName?.value || "").trim();
    const tabs = getSelectedTabs();
    if (!name) {
      showStatus("Group name is required.", "warning");
      return;
    }
    if (formMode === "add" && !code) {
      showStatus("Group code is required.", "warning");
      return;
    }
    if (!tabs.length) {
      showStatus("Select at least one tab.", "warning");
      return;
    }
    const payload = {
      group_name: name,
      tab_codes: tabs,
      display_order: parseInt(els.displayOrder?.value || "1", 10) || 1,
    };
    let url = window.GM_API.create;
    if (formMode === "edit" && els.groupId?.value) {
      url = apiUrl(window.GM_API.update, els.groupId.value);
      payload.active_status = els.activeStatus?.value === "1" ? 1 : 0;
    } else {
      payload.group_code = code;
    }
    els.saveBtn.disabled = true;
    fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Save failed.");
        showStatus(data.message || "Saved successfully.", "success");
        modal?.hide();
        loadGrid();
      })
      .catch(function (err) {
        showStatus(err.message, "danger");
      })
      .finally(function () {
        els.saveBtn.disabled = false;
      });
  }

  async function deleteGroup(groupId) {
    const id = groupId || selectedId;
    const row = rows.find(function (r) { return r.group_id === id; });
    const label = row ? row.group_name : "this group";
    if (!id) return;
    const message =
      'Mark "' + label + '" as Inactive?\n\nIt will be hidden from Customer Master dropdown.';
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!confirm(message)) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: message });
      if (!creds) return;
    }
    fetch(apiUrl(window.GM_API.delete, id), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": csrfToken() },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Delete failed.");
        showStatus(data.message, "success");
        setSelected(null);
        loadGrid();
      })
      .catch(function (err) {
        showStatus(err.message, "danger");
      });
  }

  function activateGroup(groupId) {
    const id = groupId || selectedId;
    const row = rows.find(function (r) { return r.group_id === id; });
    const label = row ? row.group_name : "this group";
    if (!id || !confirm('Activate "' + label + '"?')) return;
    fetch(apiUrl(window.GM_API.activate, id), {
      method: "POST",
      headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Activate failed.");
        showStatus(data.message, "success");
        loadGrid();
      })
      .catch(function (err) {
        showStatus(err.message, "danger");
      });
  }

  function loadRecord(id) {
    return fetch(apiUrl(window.GM_API.get, id), { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Group not found.");
        openModal("edit", data.record);
      })
      .catch(function (err) {
        showStatus(err.message, "danger");
      });
  }

  function openAddModal() {
    openModal("add");
  }

  els.addBtn?.addEventListener("click", openAddModal);
  els.addNewBtn?.addEventListener("click", openAddModal);
  els.addNewEmptyBtn?.addEventListener("click", openAddModal);
  els.editBtn?.addEventListener("click", function () {
    if (selectedId) loadRecord(selectedId);
  });
  els.editTopBtn?.addEventListener("click", function () {
    if (selectedId) loadRecord(selectedId);
  });
  els.activeBtn?.addEventListener("click", function () { activateGroup(selectedId); });
  els.activeTopBtn?.addEventListener("click", function () { activateGroup(selectedId); });
  els.deleteBtn?.addEventListener("click", function () { deleteGroup(selectedId); });
  els.deleteTopBtn?.addEventListener("click", function () { deleteGroup(selectedId); });
  els.refreshBtn?.addEventListener("click", loadGrid);
  els.saveBtn?.addEventListener("click", saveGroup);
  els.search?.addEventListener("input", function () {
    clearTimeout(window._gmSearchTimer);
    window._gmSearchTimer = setTimeout(loadGrid, 300);
  });

  els.gridBody.addEventListener("click", function (event) {
    const tr = event.target.closest("tr[data-id]");
    if (tr) {
      setSelected(parseInt(tr.dataset.id, 10));
    }
  });

  renderGrid(rows);
})();
