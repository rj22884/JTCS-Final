(function () {
  const cfg = window.PDS_MASTER;
  if (!cfg) return;

  const els = {
    addBtn: document.getElementById("pdsAddBtn"),
    addNewBtn: document.getElementById("pdsAddNewBtn"),
    editBtn: document.getElementById("pdsEditBtn"),
    deleteBtn: document.getElementById("pdsDeleteBtn"),
    refreshBtn: document.getElementById("pdsRefreshBtn"),
    search: document.getElementById("pdsSearch"),
    parentFilter: document.getElementById("pdsParentFilter"),
    count: document.getElementById("pdsCount"),
    gridHead: document.getElementById("pdsGridHead"),
    gridBody: document.getElementById("pdsGridBody"),
    empty: document.getElementById("pdsEmpty"),
    modalEl: document.getElementById("pdsModal"),
    modalTitle: document.getElementById("pdsModalTitle"),
    form: document.getElementById("pdsForm"),
    rowId: document.getElementById("pdsRowId"),
    parentFields: document.getElementById("pdsParentFields"),
    fieldGrid: document.getElementById("pdsFieldGrid"),
    activeStatus: document.getElementById("pdsActiveStatus"),
  };

  if (!els.gridBody) return;

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let rows = [];
  let selectedId = null;
  let searchTimer = null;

  const readOnly = !!cfg.readOnly;

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=\/|$)/, "/" + String(id));
  }

  function optionsUrl(slug) {
    return String(cfg.optionsBase || "").replace("/state/options", "/" + slug + "/options");
  }

  function csrfToken() {
    return (
      els.form?.querySelector('[name="csrf_token"]')?.value ||
      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
      ""
    );
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function parseJsonResponse(res) {
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("Server returned an unexpected response. Refresh and try again.");
    }
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || ("Request failed (HTTP " + res.status + ")."));
    }
    return data;
  }

  function columnHeaders() {
    const headers = [];
    (cfg.parents || []).forEach(function (parent) {
      headers.push({ key: parent.slug === (cfg.parents[0] && cfg.parents[0].slug) ? "parent_label" : parent.slug + "_label", label: parent.label });
    });
    (cfg.fields || []).forEach(function (field) {
      headers.push({ key: field.key, label: field.label });
    });
    headers.push({ key: "source", label: "Source" });
    headers.push({ key: "active_status", label: "Status" });
    return headers;
  }

  function renderHead() {
    if (!els.gridHead) return;
    const headers = columnHeaders();
    els.gridHead.innerHTML =
      headers.map(function (col) { return "<th>" + escapeHtml(col.label) + "</th>"; }).join("") +
      (readOnly ? "" : '<th class="text-end">Actions</th>');
  }

  function setSelected(rowId) {
    selectedId = rowId ? parseInt(rowId, 10) : null;
    const hasSelection = !!selectedId;
    if (!readOnly) {
      if (els.editBtn) els.editBtn.disabled = !hasSelection;
      if (els.deleteBtn) els.deleteBtn.disabled = !hasSelection;
    }
    Array.from(els.gridBody.querySelectorAll("tr")).forEach(function (row) {
      row.classList.toggle("table-active", parseInt(row.dataset.rowId, 10) === selectedId);
    });
  }

  function renderRows(data) {
    rows = data || [];
    els.gridBody.innerHTML = "";
    if (!rows.length) {
      if (els.empty) els.empty.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      setSelected(null);
      return;
    }
    if (els.empty) els.empty.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }
    const headers = columnHeaders();
    rows.forEach(function (row) {
      const id = row[cfg.pkKey];
      const tr = document.createElement("tr");
      tr.dataset.rowId = String(id);
      tr.innerHTML = headers.map(function (col) {
        if (col.key === "active_status") {
          return "<td>" + (row.active_status
            ? '<span class="badge text-bg-success">Active</span>'
            : '<span class="badge text-bg-secondary">Inactive</span>') + "</td>";
        }
        return "<td>" + escapeHtml(row[col.key] || "") + "</td>";
      }).join("") +
        (readOnly
          ? ""
          : '<td class="text-end">' +
              '<button type="button" class="btn btn-sm btn-outline-primary me-1 pds-edit-btn" data-id="' + id + '"><i class="bi bi-pencil"></i></button>' +
              '<button type="button" class="btn btn-sm btn-outline-danger pds-delete-btn" data-id="' + id + '"><i class="bi bi-trash"></i></button>' +
            "</td>");
      tr.addEventListener("click", function (ev) {
        if (ev.target.closest("button")) return;
        setSelected(id);
        if (readOnly) {
          openEdit(id).catch(function (err) {
            alert(err.message || "Unable to load record.");
          });
        }
      });
      els.gridBody.appendChild(tr);
    });
    setSelected(selectedId);
  }

  async function loadRows() {
    const url = new URL(cfg.list, window.location.origin);
    const search = els.search ? els.search.value.trim() : "";
    if (search) url.searchParams.set("search", search);
    if (els.parentFilter && els.parentFilter.value) {
      url.searchParams.set("parent_id", els.parentFilter.value);
    }
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    renderRows(data.rows || []);
  }

  async function fetchOptions(slug, parentId) {
    const url = new URL(optionsUrl(slug), window.location.origin);
    if (parentId) url.searchParams.set("parent_id", String(parentId));
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    return data.rows || [];
  }

  function fillSelect(select, options, selected, placeholder) {
    if (!select) return;
    const current = selected == null ? "" : String(selected);
    select.innerHTML = '<option value="">' + escapeHtml(placeholder || "Select") + "</option>";
    options.forEach(function (opt) {
      const option = document.createElement("option");
      option.value = String(opt.id);
      option.textContent = opt.label;
      if (String(opt.id) === current) option.selected = true;
      select.appendChild(option);
    });
  }

  async function loadFilterOptions() {
    if (!els.parentFilter || !(cfg.parents || []).length) return;
    const parent = cfg.parents[0];
    const options = await fetchOptions(parent.slug);
    const selected = els.parentFilter.value;
    fillSelect(els.parentFilter, options, selected, "All");
  }

  function parentSelectId(parent) {
    return "pdsParent_" + parent.slug;
  }

  function buildFormFields() {
    if (els.parentFields) {
      els.parentFields.innerHTML = (cfg.parents || []).map(function (parent) {
        return (
          '<div class="col-md-6">' +
            '<label class="form-label" for="' + parentSelectId(parent) + '">' +
              escapeHtml(parent.label) + (parent.required ? " *" : "") +
            "</label>" +
            '<select class="form-select" id="' + parentSelectId(parent) + '" name="' + escapeHtml(parent.column) + '"' +
              (parent.required ? " required" : "") + "></select>" +
          "</div>"
        );
      }).join("");
    }
    if (els.fieldGrid) {
      els.fieldGrid.innerHTML = (cfg.fields || []).map(function (field) {
        const col = field.kind === "textarea" ? "col-12" : "col-md-6";
        const required = field.required ? " required" : "";
        const max = field.maxlength ? ' maxlength="' + field.maxlength + '"' : "";
        if (field.kind === "textarea") {
          return (
            '<div class="' + col + '">' +
              '<label class="form-label" for="pdsField_' + field.key + '">' + escapeHtml(field.label) + (field.required ? " *" : "") + "</label>" +
              '<textarea class="form-control" id="pdsField_' + field.key + '" name="' + escapeHtml(field.column) + '" rows="2"' + max + required + "></textarea>" +
            "</div>"
          );
        }
        const type = field.kind === "number" ? "number" : "text";
        return (
          '<div class="' + col + '">' +
            '<label class="form-label" for="pdsField_' + field.key + '">' + escapeHtml(field.label) + (field.required ? " *" : "") + "</label>" +
            '<input type="' + type + '" class="form-control" id="pdsField_' + field.key + '" name="' + escapeHtml(field.column) + '"' + max + required + ">" +
          "</div>"
        );
      }).join("");
    }
  }

  function parentValue(parent) {
    const select = document.getElementById(parentSelectId(parent));
    return select && select.value ? select.value : "";
  }

  async function reloadParentSelect(index, selected) {
    const parents = cfg.parents || [];
    const parent = parents[index];
    if (!parent) return;
    let filterId = "";
    if (index > 0) {
      filterId = parentValue(parents[index - 1]);
    }
    const options = await fetchOptions(parent.slug, filterId || null);
    fillSelect(
      document.getElementById(parentSelectId(parent)),
      options,
      selected,
      (parent.required ? "Select " : "Optional ") + parent.label
    );
  }

  async function reloadParentsFrom(index, selectedMap) {
    const parents = cfg.parents || [];
    for (let i = index; i < parents.length; i += 1) {
      const selected = selectedMap ? selectedMap[parents[i].key] || selectedMap[parents[i].column] : "";
      await reloadParentSelect(i, selected);
    }
  }

  function bindParentCascade() {
    (cfg.parents || []).forEach(function (parent, index) {
      const select = document.getElementById(parentSelectId(parent));
      if (!select) return;
      select.addEventListener("change", function () {
        reloadParentsFrom(index + 1, {}).catch(function (err) {
          alert(err.message || "Unable to load linked offices.");
        });
      });
    });
  }

  function applyCodeLock(isEdit) {
    (cfg.fields || []).forEach(function (field) {
      const input = document.getElementById("pdsField_" + field.key);
      if (!input) return;
      const lock = !!(field.locked && isEdit);
      input.readOnly = lock;
      input.classList.toggle("bg-light", lock);
      if (lock) {
        input.setAttribute("title", "Code cannot be changed after save");
      } else {
        input.removeAttribute("title");
      }
    });
  }

  function resetForm() {
    els.form.reset();
    els.rowId.value = "";
    if (els.activeStatus) els.activeStatus.checked = true;
    (cfg.fields || []).forEach(function (field) {
      const input = document.getElementById("pdsField_" + field.key);
      if (input) input.value = "";
    });
    applyCodeLock(false);
  }

  async function openCreate() {
    resetForm();
    const selectedMap = {};
    if (els.parentFilter && els.parentFilter.value && (cfg.parents || []).length) {
      selectedMap[cfg.parents[0].key] = els.parentFilter.value;
    }
    await reloadParentsFrom(0, selectedMap);
    if (els.modalTitle) els.modalTitle.textContent = "Add " + cfg.title.replace(" Master", "");
    applyCodeLock(false);
    if (modal) modal.show();
  }

  async function openEdit(rowId) {
    const res = await fetch(apiUrl(cfg.record, rowId), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    const row = data.record || {};
    resetForm();
    els.rowId.value = row[cfg.pkKey] || "";
    (cfg.fields || []).forEach(function (field) {
      const input = document.getElementById("pdsField_" + field.key);
      if (input) input.value = row[field.key] == null ? "" : row[field.key];
    });
    if (els.activeStatus) els.activeStatus.checked = !!row.active_status;
    if (readOnly) {
      (cfg.parents || []).forEach(function (parent, index) {
        const select = document.getElementById(parentSelectId(parent));
        if (!select) return;
        const label = index === 0
          ? (row.parent_label || "")
          : (row[parent.slug + "_label"] || "");
        const value = row[parent.key] || row[parent.column] || "";
        select.innerHTML = '<option value="' + escapeHtml(String(value)) + '">' +
          escapeHtml(String(label || value || "—")) + "</option>";
      });
    } else {
      await reloadParentsFrom(0, row);
    }
    if (els.modalTitle) els.modalTitle.textContent = (readOnly ? "View " : "Edit ") + cfg.title.replace(" Master", "");
    Array.from(els.form.querySelectorAll("input, select, textarea")).forEach(function (field) {
      if (field.name === "csrf_token" || field.id === "pdsRowId") return;
      field.disabled = readOnly;
    });
    if (!readOnly) applyCodeLock(true);
    if (modal) modal.show();
  }

  async function deleteRecord(rowId) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this " + cfg.title + " record?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this " + cfg.title + " record?" });
      if (!creds) return;
    }
    const res = await fetch(apiUrl(cfg.delete, rowId), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": csrfToken() },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password, csrf_token: csrfToken() }) }
        : {}),
    });
    const data = await parseJsonResponse(res);
    alert(data.message || "Deleted.");
    selectedId = null;
    await loadRows();
  }

  els.form.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    if (readOnly) return;
    const id = els.rowId.value ? parseInt(els.rowId.value, 10) : null;
    const url = id ? apiUrl(cfg.update, id) : cfg.create;
    const body = new FormData(els.form);
    if (!els.activeStatus.checked) body.set("ActiveStatus", "0");
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
        body: body,
      });
      const data = await parseJsonResponse(res);
      alert(data.message || "Saved.");
      if (modal) modal.hide();
      await loadRows();
    } catch (err) {
      alert(err.message || "Save failed.");
    }
  });

  els.gridBody.addEventListener("click", function (ev) {
    const editBtn = ev.target.closest(".pds-edit-btn");
    const deleteBtn = ev.target.closest(".pds-delete-btn");
    if (editBtn) {
      openEdit(editBtn.dataset.id).catch(function (err) {
        alert(err.message || "Unable to load record.");
      });
    } else if (deleteBtn) {
      deleteRecord(deleteBtn.dataset.id).catch(function (err) {
        alert(err.message || "Unable to delete.");
      });
    }
  });

  if (els.addBtn) els.addBtn.addEventListener("click", function () {
    if (readOnly) return;
    openCreate().catch(function (err) { alert(err.message || "Unable to open form."); });
  });
  if (els.addNewBtn) els.addNewBtn.addEventListener("click", function () {
    if (readOnly) return;
    openCreate().catch(function (err) { alert(err.message || "Unable to open form."); });
  });
  if (els.editBtn) {
    els.editBtn.addEventListener("click", function () {
      if (selectedId) openEdit(selectedId).catch(function (err) { alert(err.message || "Unable to load record."); });
    });
  }
  if (els.deleteBtn) {
    els.deleteBtn.addEventListener("click", function () {
      if (selectedId) deleteRecord(selectedId).catch(function (err) { alert(err.message || "Unable to delete."); });
    });
  }
  if (els.refreshBtn) els.refreshBtn.addEventListener("click", function () {
    loadRows().catch(function (err) { alert(err.message || "Refresh failed."); });
  });
  if (els.search) {
    els.search.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        loadRows().catch(function (err) { alert(err.message || "Search failed."); });
      }, 250);
    });
  }
  if (els.parentFilter) {
    els.parentFilter.addEventListener("change", function () {
      loadRows().catch(function (err) { alert(err.message || "Filter failed."); });
    });
  }

  renderHead();
  buildFormFields();
  bindParentCascade();
  if (!readOnly) {
    loadFilterOptions().catch(function () { /* optional */ });
  }
  if (Array.isArray(window.PDS_MASTER_INITIAL_ROWS) && window.PDS_MASTER_INITIAL_ROWS.length) {
    renderRows(window.PDS_MASTER_INITIAL_ROWS);
  } else {
    loadRows().catch(function (err) { alert(err.message || "Unable to load records."); });
  }
})();
