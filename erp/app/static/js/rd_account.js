(function () {
  const els = {
    addBtn: document.getElementById("rdAccountAddBtn"),
    addNewBtn: document.getElementById("rdAccountAddNewBtn"),
    editBtn: document.getElementById("rdAccountEditBtn"),
    deleteBtn: document.getElementById("rdAccountDeleteBtn"),
    refreshBtn: document.getElementById("rdAccountRefreshBtn"),
    search: document.getElementById("rdAccountSearch"),
    count: document.getElementById("rdAccountCount"),
    gridBody: document.getElementById("rdAccountGridBody"),
    empty: document.getElementById("rdAccountEmpty"),
    modalEl: document.getElementById("rdAccountModal"),
    modalTitle: document.getElementById("rdAccountModalTitle"),
    form: document.getElementById("rdAccountForm"),
    rdAccountId: document.getElementById("rdAccountId"),
    rdName: document.getElementById("rdAccountName"),
    rdNumber: document.getElementById("rdAccountNumber"),
    bankName: document.getElementById("rdAccountBankName"),
    openingDate: document.getElementById("rdAccountOpeningDate"),
    maturityDate: document.getElementById("rdAccountMaturityDate"),
    interestRate: document.getElementById("rdAccountInterestRate"),
    installment: document.getElementById("rdAccountInstallment"),
    openingBalance: document.getElementById("rdAccountOpeningBalance"),
    remarks: document.getElementById("rdAccountRemarks"),
    activeStatus: document.getElementById("rdAccountActiveStatus"),
  };

  if (!els.gridBody || !window.RD_ACCOUNT_API) return;

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let rows = [];
  let selectedId = null;
  let searchTimer = null;

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
  }

  function csrfToken() {
    return els.form?.querySelector('[name="csrf_token"]')?.value || "";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatMoney(value) {
    const num = Number(value || 0);
    if (!Number.isFinite(num) || !value) return "";
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

  function setSelected(rdAccountId) {
    selectedId = rdAccountId ? parseInt(rdAccountId, 10) : null;
    const hasSelection = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !hasSelection;
    if (els.deleteBtn) els.deleteBtn.disabled = !hasSelection;
    Array.from(els.gridBody.querySelectorAll("tr")).forEach(function (row) {
      row.classList.toggle("table-active", parseInt(row.dataset.rdAccountId, 10) === selectedId);
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

    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.rdAccountId = String(row.rd_account_id);
      tr.innerHTML =
        "<td>" + escapeHtml(row.rd_account_id) + "</td>" +
        "<td>" + escapeHtml(row.rd_name) + "</td>" +
        "<td>" + escapeHtml(row.rd_number) + "</td>" +
        "<td>" + escapeHtml(row.bank_name) + "</td>" +
        "<td>" + escapeHtml(row.opening_date) + "</td>" +
        "<td>" + escapeHtml(row.maturity_date) + "</td>" +
        '<td class="text-end">' + escapeHtml(formatMoney(row.installment_amount)) + "</td>" +
        '<td class="text-end">' + escapeHtml(formatMoney(row.opening_balance)) + "</td>" +
        "<td>" + (row.active_status ? '<span class="badge text-bg-success">Active</span>' : '<span class="badge text-bg-secondary">Inactive</span>') + "</td>" +
        '<td class="text-end">' +
          '<button type="button" class="btn btn-sm btn-outline-primary me-1 rd-edit-btn" data-id="' + row.rd_account_id + '"><i class="bi bi-pencil"></i></button>' +
          '<button type="button" class="btn btn-sm btn-outline-danger rd-delete-btn" data-id="' + row.rd_account_id + '"><i class="bi bi-trash"></i></button>' +
        "</td>";
      tr.addEventListener("click", function (ev) {
        if (ev.target.closest("button")) return;
        setSelected(row.rd_account_id);
      });
      els.gridBody.appendChild(tr);
    });
    setSelected(selectedId);
  }

  async function loadRows(search) {
    const url = new URL(window.RD_ACCOUNT_API.list, window.location.origin);
    if (search) url.searchParams.set("search", search);
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    renderRows(data.rows || []);
  }

  function resetForm() {
    els.form.reset();
    els.rdAccountId.value = "";
    if (els.activeStatus) els.activeStatus.checked = true;
  }

  function openCreate() {
    resetForm();
    if (els.modalTitle) els.modalTitle.textContent = "Add RD Account";
    if (modal) modal.show();
  }

  async function openEdit(rdAccountId) {
    const res = await fetch(apiUrl(window.RD_ACCOUNT_API.record, rdAccountId), {
      headers: { Accept: "application/json" },
    });
    const data = await parseJsonResponse(res);
    const row = data.record;
    els.rdAccountId.value = row.rd_account_id;
    els.rdName.value = row.rd_name || "";
    els.rdNumber.value = row.rd_number || "";
    els.bankName.value = row.bank_name || "";
    els.openingDate.value = row.opening_date || "";
    els.maturityDate.value = row.maturity_date || "";
    els.interestRate.value = row.interest_rate || "";
    els.installment.value = row.installment_amount || "";
    els.openingBalance.value = row.opening_balance || "";
    els.remarks.value = row.remarks || "";
    els.activeStatus.checked = !!row.active_status;
    if (els.modalTitle) els.modalTitle.textContent = "Edit RD Account";
    if (modal) modal.show();
  }

  async function deleteRecord(rdAccountId) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!window.confirm("Delete this RD account?")) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this RD account?" });
      if (!creds) return;
    }
    const res = await fetch(apiUrl(window.RD_ACCOUNT_API.delete, rdAccountId), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": csrfToken() },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    });
    const data = await parseJsonResponse(res);
    alert(data.message || "Deleted.");
    selectedId = null;
    await loadRows(els.search ? els.search.value.trim() : "");
  }

  els.form.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    const id = els.rdAccountId.value ? parseInt(els.rdAccountId.value, 10) : null;
    const url = id
      ? apiUrl(window.RD_ACCOUNT_API.update, id)
      : window.RD_ACCOUNT_API.create;
    const body = new FormData(els.form);
    if (!els.activeStatus.checked) {
      body.set("ActiveStatus", "0");
    }
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
        body: body,
      });
      const data = await parseJsonResponse(res);
      alert(data.message || "Saved.");
      if (modal) modal.hide();
      await loadRows(els.search ? els.search.value.trim() : "");
    } catch (err) {
      alert(err.message || "Save failed.");
    }
  });

  els.gridBody.addEventListener("click", function (ev) {
    const editBtn = ev.target.closest(".rd-edit-btn");
    const deleteBtn = ev.target.closest(".rd-delete-btn");
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

  if (els.addBtn) els.addBtn.addEventListener("click", openCreate);
  if (els.addNewBtn) els.addNewBtn.addEventListener("click", openCreate);
  if (els.editBtn) {
    els.editBtn.addEventListener("click", function () {
      if (!selectedId) return;
      openEdit(selectedId).catch(function (err) {
        alert(err.message || "Unable to load record.");
      });
    });
  }
  if (els.deleteBtn) {
    els.deleteBtn.addEventListener("click", function () {
      if (!selectedId) return;
      deleteRecord(selectedId).catch(function (err) {
        alert(err.message || "Unable to delete.");
      });
    });
  }
  if (els.refreshBtn) {
    els.refreshBtn.addEventListener("click", function () {
      loadRows(els.search ? els.search.value.trim() : "").catch(function (err) {
        alert(err.message || "Unable to refresh.");
      });
    });
  }
  if (els.search) {
    els.search.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        loadRows(els.search.value.trim()).catch(function () {});
      }, 250);
    });
  }

  renderRows(window.RD_ACCOUNT_INITIAL_ROWS || []);
})();
