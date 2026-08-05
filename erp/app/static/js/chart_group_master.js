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
    underAssets: document.getElementById("cgmUnderAssets"),
    underLiabilities: document.getElementById("cgmUnderLiabilities"),
    isActive: document.getElementById("cgmIsActive"),
  };

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let searchTimer = null;

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

  function selectedUnder() {
    if (els.underLiabilities && els.underLiabilities.checked) return "Liabilities";
    return "Assets";
  }

  function setUnder(value) {
    const isLiab = String(value || "") === "Liabilities";
    if (els.underAssets) els.underAssets.checked = !isLiab;
    if (els.underLiabilities) els.underLiabilities.checked = isLiab;
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
      const underBadge =
        row.under_type === "Liabilities"
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

  function loadRows() {
    const params = new URLSearchParams();
    const q = (els.search?.value || "").trim();
    if (q) params.set("search", q);
    return fetch(api.list + "?" + params.toString(), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data;
        });
      })
      .then(function (data) {
        renderRows(data.rows || []);
      })
      .catch(function (err) {
        showStatus(err.message || "Load failed.", "danger");
      });
  }

  function openAdd() {
    if (els.id) els.id.value = "";
    if (els.name) els.name.value = "";
    setUnder("Assets");
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
        setUnder(record.under_type || "Assets");
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
    const payload = {
      group_name: (els.name?.value || "").trim(),
      under_type: selectedUnder(),
      is_active: els.isActive?.checked ? "1" : "0",
    };
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
      if (!window.confirm("Delete this group?")) return;
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
    searchTimer = setTimeout(loadRows, 250);
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

  renderRows(window.CHART_GROUP_INITIAL_ROWS || []);
})();
