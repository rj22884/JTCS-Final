(function () {
  "use strict";

  const api = window.ACCOUNT_TYPE_API;
  if (!api) return;

  const els = {
    addBtn: document.getElementById("atmAddBtn"),
    addNewBtn: document.getElementById("atmAddNewBtn"),
    refreshBtn: document.getElementById("atmRefreshBtn"),
    search: document.getElementById("atmSearch"),
    count: document.getElementById("atmCount"),
    body: document.getElementById("atmGridBody"),
    empty: document.getElementById("atmEmpty"),
    status: document.getElementById("atmStatus"),
    modalEl: document.getElementById("atmModal"),
    modalTitle: document.getElementById("atmModalTitle"),
    form: document.getElementById("atmForm"),
    id: document.getElementById("atmId"),
    code: document.getElementById("atmCode"),
    name: document.getElementById("atmName"),
    description: document.getElementById("atmDescription"),
    orderNo: document.getElementById("atmOrderNo"),
    isActive: document.getElementById("atmIsActive"),
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
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" +
        escapeHtml(row.account_type_id) +
        "</td>" +
        "<td><code>" +
        escapeHtml(row.account_type_code) +
        "</code></td>" +
        "<td>" +
        escapeHtml(row.account_type_name) +
        "</td>" +
        "<td>" +
        escapeHtml(row.description || "—") +
        "</td>" +
        '<td class="text-end">' +
        escapeHtml(row.order_no) +
        "</td>" +
        "<td>" +
        (row.is_active
          ? '<span class="badge text-bg-success">Active</span>'
          : '<span class="badge text-bg-secondary">Inactive</span>') +
        "</td>" +
        '<td class="text-end text-nowrap">' +
        '<button type="button" class="btn btn-outline-primary btn-sm me-1 atm-edit" data-id="' +
        row.account_type_id +
        '"><i class="bi bi-pencil"></i> Edit</button>' +
        '<button type="button" class="btn btn-outline-danger btn-sm atm-delete" data-id="' +
        row.account_type_id +
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
    if (els.code) els.code.value = "";
    if (els.name) els.name.value = "";
    if (els.description) els.description.value = "";
    if (els.orderNo) els.orderNo.value = "100";
    if (els.isActive) els.isActive.checked = true;
    if (els.modalTitle) els.modalTitle.textContent = "Add Account Type";
    modal?.show();
    els.code?.focus();
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
        if (els.id) els.id.value = String(record.account_type_id || "");
        if (els.code) els.code.value = record.account_type_code || "";
        if (els.name) els.name.value = record.account_type_name || "";
        if (els.description) els.description.value = record.description || "";
        if (els.orderNo) els.orderNo.value = String(record.order_no != null ? record.order_no : 100);
        if (els.isActive) els.isActive.checked = !!record.is_active;
        if (els.modalTitle) els.modalTitle.textContent = "Edit Account Type";
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
      account_type_code: (els.code?.value || "").trim(),
      account_type_name: (els.name?.value || "").trim(),
      description: (els.description?.value || "").trim(),
      order_no: els.orderNo?.value || 100,
      is_active: els.isActive?.checked ? "1" : "0",
    };
    if (!payload.account_type_code || !payload.account_type_name) {
      alert("Account Type Code and Name are required.");
      return;
    }
    const url = id ? apiUrl(api.update, id) : api.create;
    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": window.ACCOUNT_TYPE_CSRF || "",
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
      if (!(await JTCSDialog.confirm("Delete this account type?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this account type?" });
      if (!creds) return;
    }
    fetch(apiUrl(api.delete, id), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": window.ACCOUNT_TYPE_CSRF || "", "X-Requested-With": "XMLHttpRequest" },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
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
    const editBtn = event.target.closest(".atm-edit");
    if (editBtn) {
      openEdit(editBtn.getAttribute("data-id"));
      return;
    }
    const delBtn = event.target.closest(".atm-delete");
    if (delBtn) remove(delBtn.getAttribute("data-id"));
  });

  renderRows(window.ACCOUNT_TYPE_INITIAL_ROWS || []);
})();
