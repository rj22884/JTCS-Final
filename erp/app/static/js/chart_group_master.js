(function () {
  "use strict";

  const api = window.CHART_GROUP_API;
  if (!api) return;

  const els = {
    addBtn: document.getElementById("cgmAddBtn"),
    addNewBtn: document.getElementById("cgmAddNewBtn"),
    refreshBtn: document.getElementById("cgmRefreshBtn"),
    search: document.getElementById("cgmSearch"),
    count: document.getElementById("cgmCount"),
    body: document.getElementById("cgmGridBody"),
    empty: document.getElementById("cgmEmpty"),
    status: document.getElementById("cgmStatus"),
    modalEl: document.getElementById("cgmModal"),
    modalTitle: document.getElementById("cgmModalTitle"),
    form: document.getElementById("cgmForm"),
    id: document.getElementById("cgmId"),
    name: document.getElementById("cgmName"),
    parent: document.getElementById("cgmParent"),
    isActive: document.getElementById("cgmIsActive"),
  };

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let searchTimer = null;
  let allGroups = Array.isArray(window.CHART_GROUP_INITIAL_ROWS)
    ? window.CHART_GROUP_INITIAL_ROWS.slice()
    : [];

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(id));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fillParentOptions(excludeId, selectedValue) {
    if (!els.parent) return;
    const current = selectedValue != null ? String(selectedValue) : "Assets";
    const skip = excludeId != null && excludeId !== "" ? String(excludeId) : "";
    let html =
      '<option value="Assets">Assets (Primary)</option>' +
      '<option value="Liabilities">Liabilities (Primary)</option>';
    const groups = (allGroups || []).slice().sort(function (a, b) {
      return String(a.group_name || "").localeCompare(String(b.group_name || ""));
    });
    groups.forEach(function (g) {
      if (!g || String(g.group_id) === skip) return;
      if (g.is_active === false) return;
      const label = (g.group_name || "") + " (" + (g.under_label || g.parent_group_name || g.under_type || "") + ")";
      html +=
        '<option value="' +
        escapeHtml(String(g.group_id)) +
        '">' +
        escapeHtml(label) +
        "</option>";
    });
    els.parent.innerHTML = html;
    if (current && Array.prototype.some.call(els.parent.options, function (opt) { return opt.value === current; })) {
      els.parent.value = current;
    } else {
      els.parent.value = "Assets";
    }
  }

  function selectedParentPayload() {
    const v = (els.parent && els.parent.value) || "Assets";
    if (v === "Assets" || v === "Liabilities") {
      return { under_type: v, parent_group_id: null };
    }
    const gid = parseInt(v, 10);
    return { parent_group_id: gid || null };
  }

  function parentSelectValue(record) {
    if (record && record.parent_group_id) return String(record.parent_group_id);
    return record && record.under_type === "Liabilities" ? "Liabilities" : "Assets";
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

  function renderRows(rows) {
    if (!els.body) return;
    els.body.innerHTML = "";
    if (!rows.length) {
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }
    rows.forEach(function (row) {
      const underLabel = row.under_label || row.parent_group_name || row.under_type || "";
      const underBadge =
        row.parent_group_id
          ? '<span class="badge text-bg-primary">' + escapeHtml(underLabel) + "</span>"
          : row.under_type === "Liabilities"
          ? '<span class="badge text-bg-warning">Liabilities</span>'
          : '<span class="badge text-bg-info">Assets</span>';
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" +
        escapeHtml(row.group_id) +
        "</td>" +
        "<td>" +
        escapeHtml(row.group_name) +
        "</td>" +
        "<td>" +
        underBadge +
        "</td>" +
        "<td>" +
        (row.is_active
          ? '<span class="badge text-bg-success">Active</span>'
          : '<span class="badge text-bg-secondary">Inactive</span>') +
        "</td>" +
        '<td class="text-end text-nowrap">' +
        '<button type="button" class="btn btn-outline-primary btn-sm me-1 cgm-edit" data-id="' +
        row.group_id +
        '"><i class="bi bi-pencil"></i> Edit</button>' +
        '<button type="button" class="btn btn-outline-danger btn-sm cgm-delete" data-id="' +
        row.group_id +
        '"><i class="bi bi-trash"></i> Delete</button>' +
        "</td>";
      els.body.appendChild(tr);
    });
  }

  function filteredRows() {
    const q = (els.search?.value || "").trim().toLowerCase();
    if (!q) return allGroups;
    return allGroups.filter(function (row) {
      const blob = [
        row.group_name,
        row.under_label,
        row.parent_group_name,
        row.under_type,
      ]
        .join(" ")
        .toLowerCase();
      return blob.indexOf(q) >= 0;
    });
  }

  function loadRows() {
    return fetch(api.list, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data;
        });
      })
      .then(function (data) {
        allGroups = data.rows || [];
        renderRows(filteredRows());
      })
      .catch(function (err) {
        showStatus(err.message || "Load failed.", "danger");
      });
  }

  function openAdd() {
    if (els.id) els.id.value = "";
    if (els.name) els.name.value = "";
    fillParentOptions("", "Assets");
    if (els.isActive) els.isActive.checked = true;
    if (els.modalTitle) els.modalTitle.textContent = "Add Group";
    modal?.show();
    els.name?.focus();
  }

  function openEdit(id) {
    fetch(apiUrl(api.record, id), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data.record;
        });
      })
      .then(function (record) {
        if (els.id) els.id.value = String(record.group_id || "");
        if (els.name) els.name.value = record.group_name || "";
        fillParentOptions(record.group_id, parentSelectValue(record));
        if (els.isActive) els.isActive.checked = !!record.is_active;
        if (els.modalTitle) els.modalTitle.textContent = "Edit Group";
        modal?.show();
      })
      .catch(function (err) {
        alert(err.message || "Unable to load.");
      });
  }

  function save(event) {
    event.preventDefault();
    const id = (els.id?.value || "").trim();
    const payload = Object.assign(
      {
        group_name: (els.name?.value || "").trim(),
        is_active: els.isActive?.checked ? "1" : "0",
      },
      selectedParentPayload()
    );
    if (!payload.group_name) {
      alert("Group Name is required.");
      return;
    }
    const url = id ? apiUrl(api.update, id) : api.create;
    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": window.CHART_GROUP_CSRF || "",
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Save failed.");
          return data;
        });
      })
      .then(function (data) {
        modal?.hide();
        showStatus(data.message || "Saved.", "success");
        return loadRows();
      })
      .catch(function (err) {
        alert(err.message || "Save failed.");
      });
  }

  async function remove(id) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this group?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this group?" });
      if (!creds) return;
    }
    fetch(apiUrl(api.delete, id), {
      method: "POST",
      headers: Object.assign(
        {
          Accept: "application/json",
          "X-CSRFToken": window.CHART_GROUP_CSRF || "",
          "X-Requested-With": "XMLHttpRequest",
        },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) } : {}),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Delete failed.");
          return data;
        });
      })
      .then(function (data) {
        showStatus(data.message || "Deleted.", "info");
        return loadRows();
      })
      .catch(function (err) {
        alert(err.message || "Delete failed.");
      });
  }

  els.addBtn?.addEventListener("click", openAdd);
  els.addNewBtn?.addEventListener("click", openAdd);
  els.refreshBtn?.addEventListener("click", loadRows);
  els.form?.addEventListener("submit", save);
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      renderRows(filteredRows());
    }, 250);
  });
  els.body?.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".cgm-edit");
    if (editBtn) {
      openEdit(editBtn.getAttribute("data-id"));
      return;
    }
    const delBtn = event.target.closest(".cgm-delete");
    if (delBtn) remove(delBtn.getAttribute("data-id"));
  });

  renderRows(filteredRows());
})();
