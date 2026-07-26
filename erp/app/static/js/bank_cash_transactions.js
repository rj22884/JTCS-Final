(function () {
  const els = {
    newBtn: document.getElementById("obcNewEntryBtn"),
    refreshBtn: document.getElementById("obcRefreshGridBtn"),
    gridBody: document.getElementById("obcDataGridBody"),
    empty: document.getElementById("obcGridEmpty"),
    count: document.getElementById("obcGridCount"),
    modalEl: document.getElementById("obcEntryModal"),
    modalTitle: document.getElementById("obcEntryModalTitle"),
    form: document.getElementById("obcEntryForm"),
    entryId: document.getElementById("obcEntryId"),
    workDate: document.getElementById("obcWorkDate"),
    voucherNo: document.getElementById("obcVoucherNo"),
    amount: document.getElementById("obcAmount"),
    creditAccount: document.getElementById("obcCreditAccount"),
    debitAccount: document.getElementById("obcDebitAccount"),
    purpose: document.getElementById("obcPurpose"),
    remarks: document.getElementById("obcRemarks"),
    saveBtn: document.getElementById("obcSaveBtn"),
  };

  if (!els.gridBody || !window.OBC_API) return;

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let allRows = [];
  let gridSortKey = "work_date";
  let gridSortDir = "desc";
  const gridFilters = {};

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
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
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

  function readGridFiltersFromDom() {
    document.querySelectorAll("#obcDataGrid .obc-col-filter").forEach(function (input) {
      const key = input.dataset.filterKey;
      if (!key) return;
      gridFilters[key] = (input.value || "").trim().toLowerCase();
    });
  }

  function hasActiveGridFilters() {
    return Object.keys(gridFilters).some(function (key) {
      return !!gridFilters[key];
    });
  }

  function rowFilterValue(row, key) {
    if (key === "amount") return formatMoney(row.amount);
    return String(row[key] == null ? "" : row[key]);
  }

  function rowMatchesFilters(row) {
    if (!hasActiveGridFilters()) return true;
    return Object.keys(gridFilters).every(function (key) {
      const needle = gridFilters[key];
      if (!needle) return true;
      return rowFilterValue(row, key).toLowerCase().indexOf(needle) !== -1;
    });
  }

  function sortValue(row, key) {
    if (key === "amount") return Number(row.amount || 0);
    if (key === "work_date") return String(row.work_date || "");
    return String(row[key] == null ? "" : row[key]).toLowerCase();
  }

  function compareSortValues(a, b, dir) {
    const emptyA = a === "" || a == null;
    const emptyB = b === "" || b == null;
    if (emptyA && emptyB) return 0;
    if (emptyA) return 1;
    if (emptyB) return -1;
    if (typeof a === "number" && typeof b === "number") {
      return dir === "asc" ? a - b : b - a;
    }
    const sa = String(a);
    const sb = String(b);
    if (sa < sb) return dir === "asc" ? -1 : 1;
    if (sa > sb) return dir === "asc" ? 1 : -1;
    return 0;
  }

  function prepareRows(rows) {
    let prepared = (rows || []).filter(rowMatchesFilters);
    if (gridSortKey) {
      prepared = prepared.slice().sort(function (a, b) {
        return compareSortValues(sortValue(a, gridSortKey), sortValue(b, gridSortKey), gridSortDir);
      });
    }
    return prepared;
  }

  function updateGridSortHeaders() {
    document.querySelectorAll("#obcDataGrid thead th.obc-sortable").forEach(function (th) {
      const key = th.dataset.sortKey;
      const icon = th.querySelector(".obc-sort-icon");
      const active = key === gridSortKey;
      th.classList.toggle("obc-sorted", active);
      th.setAttribute(
        "aria-sort",
        active ? (gridSortDir === "asc" ? "ascending" : "descending") : "none"
      );
      if (icon) {
        icon.textContent = active ? (gridSortDir === "asc" ? " ▲" : " ▼") : "";
      }
    });
  }

  function renderRows(rows) {
    const visible = prepareRows(rows);
    els.gridBody.innerHTML = "";
    if (!visible.length) {
      if (els.empty) {
        els.empty.textContent = allRows.length
          ? "No records match the current filters."
          : "No bank/cash transfer records yet.";
        els.empty.classList.remove("d-none");
      }
      if (els.count) {
        els.count.textContent = allRows.length
          ? "0 of " + allRows.length + " records"
          : "0 records";
      }
      updateGridSortHeaders();
      return;
    }
    if (els.empty) els.empty.classList.add("d-none");
    if (els.count) {
      els.count.textContent =
        visible.length === allRows.length
          ? visible.length + " record" + (visible.length === 1 ? "" : "s")
          : visible.length + " of " + allRows.length + " records";
    }

    visible.forEach(function (row) {
      const money = formatMoney(row.amount);
      const creditCell =
        escapeHtml(row.credit_account) +
        ' <span class="obc-amt-credit">(-' +
        escapeHtml(money) +
        ")</span>";
      const debitCell =
        escapeHtml(row.debit_account) +
        ' <span class="obc-amt-debit">(₹ +' +
        escapeHtml(money) +
        ")</span>";
      const tr = document.createElement("tr");
      tr.innerHTML =
        "<td>" + escapeHtml(row.voucher_no) + "</td>" +
        "<td>" + escapeHtml(row.work_date) + "</td>" +
        "<td>" + escapeHtml(row.purpose) + "</td>" +
        "<td>" + creditCell + "</td>" +
        "<td>" + debitCell + "</td>" +
        '<td class="text-end">₹ ' + escapeHtml(money) + "</td>" +
        "<td>" + escapeHtml(row.remarks) + "</td>" +
        "<td>" + escapeHtml(row.entered_by || "") + "</td>" +
        '<td class="text-end text-nowrap">' +
          '<button type="button" class="btn btn-sm btn-outline-primary me-1 obc-edit-btn" data-id="' +
          row.entry_id +
          '" title="Edit"><i class="bi bi-pencil"></i></button>' +
          '<button type="button" class="btn btn-sm btn-outline-danger obc-delete-btn" data-id="' +
          row.entry_id +
          '" title="Delete"><i class="bi bi-trash"></i></button>' +
        "</td>";
      els.gridBody.appendChild(tr);
    });
    updateGridSortHeaders();
  }

  function refreshGridView() {
    readGridFiltersFromDom();
    renderRows(allRows);
  }

  function onGridSortHeader(sortKey) {
    if (!sortKey) return;
    if (gridSortKey === sortKey) {
      gridSortDir = gridSortDir === "asc" ? "desc" : "asc";
    } else {
      gridSortKey = sortKey;
      gridSortDir = "asc";
    }
    refreshGridView();
  }

  async function loadGrid() {
    const res = await fetch(window.OBC_API.grid, { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    allRows = data.rows || [];
    refreshGridView();
  }

  async function fillAccounts(selectedCredit, selectedDebit) {
    const res = await fetch(window.OBC_API.accounts, { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    const options = ['<option value="">Select account...</option>']
      .concat(
        (data.rows || []).map(function (acc) {
          return (
            '<option value="' +
            acc.account_id +
            '">' +
            escapeHtml(acc.label) +
            "</option>"
          );
        })
      )
      .join("");
    if (els.creditAccount) {
      els.creditAccount.innerHTML = options;
      if (selectedCredit) els.creditAccount.value = String(selectedCredit);
    }
    if (els.debitAccount) {
      els.debitAccount.innerHTML = options.replace(
        "Select account...",
        "Select account (Bank / Cash / RD)..."
      );
      if (selectedDebit) els.debitAccount.value = String(selectedDebit);
    }
  }

  async function refreshVoucher() {
    if (els.entryId && els.entryId.value) return;
    const workDate = els.workDate ? els.workDate.value : "";
    const url = new URL(window.OBC_API.nextVoucher, window.location.origin);
    if (workDate) url.searchParams.set("work_date", workDate);
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    if (els.voucherNo) els.voucherNo.value = data.voucher_no || "";
  }

  async function fillPurposes(selectedPurpose) {
    const purposes = window.OBC_API.purposes || [];
    if (!els.purpose) return;
    els.purpose.innerHTML =
      '<option value="">Select purpose...</option>' +
      purposes
        .map(function (item) {
          return (
            '<option value="' +
            escapeHtml(item.purpose_name) +
            '">' +
            escapeHtml(item.purpose_name) +
            "</option>"
          );
        })
        .join("");
    if (selectedPurpose) els.purpose.value = selectedPurpose;
  }

  async function openNew() {
    els.form.reset();
    if (els.entryId) els.entryId.value = "";
    if (els.workDate) els.workDate.value = window.OBC_API.defaultDate || "";
    if (els.voucherNo) els.voucherNo.readOnly = false;
    if (els.modalTitle) els.modalTitle.textContent = "New Bank/Cash Transaction";
    await fillAccounts();
    await fillPurposes();
    await refreshVoucher();
    if (modal) modal.show();
  }

  async function openEdit(entryId) {
    const res = await fetch(apiUrl(window.OBC_API.entry, entryId), {
      headers: { Accept: "application/json" },
    });
    const data = await parseJsonResponse(res);
    const row = data.record;
    els.form.reset();
    if (els.entryId) els.entryId.value = String(row.entry_id);
    if (els.workDate) els.workDate.value = row.work_date || "";
    if (els.voucherNo) {
      els.voucherNo.value = row.voucher_no || "";
      els.voucherNo.readOnly = true;
    }
    if (els.amount) els.amount.value = row.amount || "";
    if (els.remarks) els.remarks.value = row.remarks || "";
    if (els.modalTitle) els.modalTitle.textContent = "Edit Bank/Cash Transaction";
    await fillAccounts(row.credit_account_id, row.debit_account_id);
    await fillPurposes(row.purpose);
    if (modal) modal.show();
  }

  async function saveEntry() {
    if (!els.form.checkValidity()) {
      els.form.reportValidity();
      return;
    }
    if (els.creditAccount.value && els.creditAccount.value === els.debitAccount.value) {
      alert("Credit and Debit accounts must be different.");
      return;
    }
    const body = new FormData(els.form);
    els.saveBtn.disabled = true;
    try {
      const res = await fetch(window.OBC_API.save, {
        method: "POST",
        headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
        body: body,
      });
      const data = await parseJsonResponse(res);
      alert(data.message || "Saved.");
      if (modal) modal.hide();
      await loadGrid();
    } catch (err) {
      alert(err.message || "Save failed.");
    } finally {
      els.saveBtn.disabled = false;
    }
  }

  async function deleteEntry(entryId) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!window.confirm("Delete this double-entry transaction?")) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this double-entry transaction?" });
      if (!creds) return;
    }
    const res = await fetch(apiUrl(window.OBC_API.delete, entryId), {
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
    await loadGrid();
  }

  if (els.newBtn) {
    els.newBtn.addEventListener("click", function () {
      openNew().catch(function (err) {
        alert(err.message || "Unable to open form.");
      });
    });
  }
  if (els.refreshBtn) {
    els.refreshBtn.addEventListener("click", function () {
      loadGrid().catch(function (err) {
        alert(err.message || "Unable to refresh.");
      });
    });
  }
  if (els.saveBtn) {
    els.saveBtn.addEventListener("click", function () {
      saveEntry();
    });
  }
  if (els.workDate) {
    els.workDate.addEventListener("change", function () {
      refreshVoucher().catch(function () {});
    });
  }

  const gridTable = document.getElementById("obcDataGrid");
  if (gridTable) {
    gridTable.addEventListener("click", function (ev) {
      const th = ev.target.closest("th.obc-sortable");
      if (th && gridTable.contains(th)) {
        onGridSortHeader(th.dataset.sortKey);
      }
    });
    gridTable.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      const th = ev.target.closest("th.obc-sortable");
      if (!th || !gridTable.contains(th)) return;
      ev.preventDefault();
      onGridSortHeader(th.dataset.sortKey);
    });
    gridTable.addEventListener("input", function (ev) {
      if (ev.target.classList.contains("obc-col-filter")) {
        refreshGridView();
      }
    });
  }

  els.gridBody.addEventListener("click", function (ev) {
    const editBtn = ev.target.closest(".obc-edit-btn");
    const deleteBtn = ev.target.closest(".obc-delete-btn");
    if (editBtn) {
      openEdit(editBtn.dataset.id).catch(function (err) {
        alert(err.message || "Unable to load entry.");
      });
      return;
    }
    if (deleteBtn) {
      deleteEntry(deleteBtn.dataset.id).catch(function (err) {
        alert(err.message || "Unable to delete.");
      });
    }
  });

  loadGrid()
    .then(function () {
      var autoId = parseInt(window.OBC_AUTO_LOAD_ENTRY_ID, 10);
      if (!Number.isNaN(autoId) && autoId > 0) {
        return openEdit(autoId);
      }
    })
    .catch(function () {});
})();
