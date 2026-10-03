(function () {
  "use strict";

  const api = window.CHART_ACCOUNT_API;
  if (!api) return;

  const els = {
    addBtn: document.getElementById("camAddBtn"),
    addNewBtn: document.getElementById("camAddNewBtn"),
    refreshBtn: document.getElementById("camRefreshBtn"),
    search: document.getElementById("camSearch"),
    count: document.getElementById("camCount"),
    body: document.getElementById("camGridBody"),
    empty: document.getElementById("camEmpty"),
    status: document.getElementById("camStatus"),
    modalEl: document.getElementById("camModal"),
    modalTitle: document.getElementById("camModalTitle"),
    form: document.getElementById("camForm"),
    id: document.getElementById("camId"),
    customerId: document.getElementById("camCustomerId"),
    workId: document.getElementById("camWorkId"),
    source: document.getElementById("camSource"),
    name: document.getElementById("camName"),
    nameHint: document.getElementById("camNameHint"),
    group: document.getElementById("camGroup"),
    openingBalance: document.getElementById("camOpeningBalance"),
    openingBalanceDate: document.getElementById("camOpeningBalanceDate"),
    obDr: document.getElementById("camObDr"),
    obCr: document.getElementById("camObCr"),
    isActive: document.getElementById("camIsActive"),
    activeWrap: document.getElementById("camActiveWrap"),
    entryHint: document.getElementById("camEntryHint"),
    entryName: document.getElementById("camEntryName"),
    entryClear: document.getElementById("camEntryClear"),
    entryBlocked: document.getElementById("camEntryBlocked"),
    entryLinks: document.getElementById("camEntryLinks"),
    entryRows: document.getElementById("camEntryRows"),
    entryNone: document.getElementById("camEntryNone"),
  };

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let searchTimer = null;
  const MAX_GROUPS = 5;

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(id));
  }

  function normalizeGroupIds(value) {
    if (Array.isArray(value)) {
      return value
        .map(function (v) {
          return String(v);
        })
        .filter(Boolean);
    }
    if (value == null || value === "") return [];
    return [String(value)];
  }

  function selectedGroupIds() {
    if (!els.group) return [];
    return Array.prototype.slice
      .call(els.group.selectedOptions || [])
      .map(function (opt) {
        return opt.value;
      })
      .filter(Boolean);
  }

  function enforceMaxGroups() {
    if (!els.group) return;
    const selected = Array.prototype.slice.call(els.group.selectedOptions || []);
    if (selected.length <= MAX_GROUPS) return;
    selected.slice(MAX_GROUPS).forEach(function (opt) {
      opt.selected = false;
    });
    alert("Maximum " + MAX_GROUPS + " groups allowed (Sale / Purchase / Income / Expense / Contra).");
  }

  function defaultDrCrFromUnderType(underType) {
    return String(underType || "").trim().toLowerCase() === "liabilities" ? "Cr" : "Dr";
  }

  function setOpeningDrCr(value) {
    const v = value === "Cr" ? "Cr" : "Dr";
    if (els.obDr) els.obDr.checked = v === "Dr";
    if (els.obCr) els.obCr.checked = v === "Cr";
  }

  function applyDefaultDrCrFromGroups() {
    const opt = els.group?.selectedOptions && els.group.selectedOptions[0];
    const under = (opt && opt.dataset.underType) || "";
    setOpeningDrCr(defaultDrCrFromUnderType(under));
  }

  function selectedOpeningDrCr() {
    if (els.obCr?.checked) return "Cr";
    return "Dr";
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

  function setLinkedMode(source) {
    const linked = source === "customer" || source === "work";
    if (els.source) els.source.value = source || "manual";
    if (els.name) {
      els.name.readOnly = !!linked;
      els.name.classList.toggle("bg-light", !!linked);
    }
    if (els.nameHint) {
      if (!linked) {
        els.nameHint.classList.add("d-none");
      } else {
        els.nameHint.textContent =
          source === "work"
            ? "From Income/Expense Master — only Group can be changed."
            : "From Customer Master — only Group can be changed.";
        els.nameHint.classList.remove("d-none");
      }
    }
    if (els.activeWrap) els.activeWrap.classList.toggle("d-none", !!linked);
  }

  function sourceBadge(row) {
    if (row.source === "customer") {
      return '<span class="badge text-bg-primary">Customer</span>';
    }
    if (row.source === "work") {
      const kind = row.ledger_kind ? " · " + escapeHtml(row.ledger_kind) : "";
      return '<span class="badge text-bg-success">Income/Expense' + kind + "</span>";
    }
    return '<span class="badge text-bg-secondary">Manual</span>';
  }

  function loadGroups(selectedIds) {
    const keepSet = {};
    normalizeGroupIds(selectedIds).forEach(function (id) {
      keepSet[id] = true;
    });
    return fetch(api.groups, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load groups.");
          return data.rows || [];
        });
      })
      .then(function (rows) {
        if (!els.group) return;
        els.group.innerHTML = "";
        rows.forEach(function (row) {
          const opt = document.createElement("option");
          opt.value = String(row.group_id);
          opt.textContent = row.label || row.group_name;
          opt.dataset.underType = row.under_type || "";
          if (keepSet[String(row.group_id)]) opt.selected = true;
          els.group.appendChild(opt);
        });
        applyDefaultDrCrFromGroups();
      });
  }

  function editAttrs(row) {
    if (row.source === "customer") {
      return 'data-source="customer" data-customer-id="' + escapeHtml(row.customer_id) + '"';
    }
    if (row.source === "work") {
      return 'data-source="work" data-work-id="' + escapeHtml(row.work_id) + '"';
    }
    return 'data-source="manual" data-id="' + escapeHtml(row.account_id) + '"';
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
          : row.under_type
            ? '<span class="badge text-bg-info">Assets</span>'
            : "—";
      const hasGroups =
        (Array.isArray(row.group_ids) && row.group_ids.length > 0) || !!row.group_id || !!row.group_name;
      const groupCell = hasGroups
        ? escapeHtml(row.group_name || "")
        : '<span class="text-muted">— Select group —</span>';
      const attrs = editAttrs(row);
      const blocked = !!row.has_entries;
      const deleteBtn =
        '<button type="button" class="btn btn-outline-danger btn-sm cam-delete" ' +
        attrs +
        (blocked ? ' disabled title="Entries exist. Shown on the right."' : ' title="Permanent delete"') +
        '><i class="bi bi-trash"></i> Delete</button>';
      let idHint = "";
      if (row.source === "customer" && row.customer_id) {
        idHint = ' <span class="text-muted small">#' + escapeHtml(row.customer_id) + "</span>";
      } else if (row.source === "work" && row.work_id) {
        idHint = ' <span class="text-muted small">#' + escapeHtml(row.work_id) + "</span>";
      }
      const tr = document.createElement("tr");
      tr.dataset.source = row.source || "manual";
      tr.dataset.accountId = row.account_id != null ? String(row.account_id) : "";
      tr.dataset.customerId = row.customer_id != null ? String(row.customer_id) : "";
      tr.dataset.workId = row.work_id != null ? String(row.work_id) : "";
      tr.dataset.name = row.account_name || "";
      tr.dataset.hasEntries = blocked ? "1" : "0";
      tr.innerHTML =
        "<td>" +
        sourceBadge(row) +
        "</td>" +
        "<td>" +
        escapeHtml(row.account_name) +
        idHint +
        "</td>" +
        "<td>" +
        groupCell +
        "</td>" +
        "<td>" +
        underBadge +
        "</td>" +
        "<td>" +
        (hasGroups
          ? '<span class="badge text-bg-success">Assigned</span>'
          : '<span class="badge text-bg-secondary">Pending</span>') +
        "</td>" +
        '<td class="text-end text-nowrap">' +
        '<button type="button" class="btn btn-outline-primary btn-sm me-1 cam-edit" ' +
        attrs +
        '><i class="bi bi-pencil"></i> Edit</button>' +
        deleteBtn +
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
    if (els.customerId) els.customerId.value = "";
    if (els.workId) els.workId.value = "";
    if (els.name) els.name.value = "";
    if (els.openingBalance) els.openingBalance.value = "";
    if (els.openingBalanceDate) els.openingBalanceDate.value = "";
    setOpeningDrCr("Dr");
    if (els.isActive) els.isActive.checked = true;
    setLinkedMode("manual");
    if (els.modalTitle) els.modalTitle.textContent = "Add Manual Account";
    loadGroups("")
      .then(function () {
        modal?.show();
        els.name?.focus();
      })
      .catch(function (err) {
        alert(err.message || "Unable to load groups.");
      });
  }

  function fillForm(record) {
    const source = record.source || "manual";
    setLinkedMode(source);
    if (els.id) els.id.value = record.account_id != null ? String(record.account_id) : "";
    if (els.customerId) {
      els.customerId.value = record.customer_id != null ? String(record.customer_id) : "";
    }
    if (els.workId) {
      els.workId.value = record.work_id != null ? String(record.work_id) : "";
    }
    if (els.name) els.name.value = record.account_name || "";
    if (els.openingBalance) els.openingBalance.value = record.opening_balance || "";
    if (els.openingBalanceDate) {
      els.openingBalanceDate.value = record.opening_balance_date || "";
    }
    if (els.isActive) els.isActive.checked = !!record.is_active;
    if (els.modalTitle) {
      els.modalTitle.textContent = source === "manual" ? "Edit Account" : "Assign Group";
    }
    const selected =
      Array.isArray(record.group_ids) && record.group_ids.length
        ? record.group_ids
        : record.group_id != null
          ? [record.group_id]
          : [];
    return loadGroups(selected).then(function () {
      if (record.opening_balance_dr_cr) {
        setOpeningDrCr(record.opening_balance_dr_cr);
      } else {
        applyDefaultDrCrFromGroups();
      }
      modal?.show();
      if (source === "manual") els.name?.focus();
      else els.group?.focus();
    });
  }

  function openEditCustomer(customerId) {
    fetch(apiUrl(api.customer, customerId), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data.record;
        });
      })
      .then(fillForm)
      .catch(function (err) {
        alert(err.message || "Unable to load.");
      });
  }

  function openEditWork(workId) {
    fetch(apiUrl(api.work, workId), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data.record;
        });
      })
      .then(fillForm)
      .catch(function (err) {
        alert(err.message || "Unable to load.");
      });
  }

  function openEditManual(id) {
    fetch(apiUrl(api.record, id), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data.record;
        });
      })
      .then(fillForm)
      .catch(function (err) {
        alert(err.message || "Unable to load.");
      });
  }

  function save(event) {
    event.preventDefault();
    const source = (els.source?.value || "manual").trim();
    const customerId = (els.customerId?.value || "").trim();
    const workId = (els.workId?.value || "").trim();
    const accountId = (els.id?.value || "").trim();
    const groupIds = selectedGroupIds();
    const payload = {
      account_name: (els.name?.value || "").trim(),
      group_ids: groupIds,
      group_id: groupIds[0] || "",
      is_active: els.isActive?.checked ? "1" : "0",
      opening_balance: (els.openingBalance?.value || "").trim(),
      opening_balance_date: (els.openingBalanceDate?.value || "").trim(),
      opening_balance_dr_cr: selectedOpeningDrCr(),
    };

    if (!groupIds.length) {
      alert("Select at least one group.");
      return;
    }
    if (groupIds.length > MAX_GROUPS) {
      alert("Maximum " + MAX_GROUPS + " groups allowed.");
      return;
    }

    let url;
    if (source === "customer") {
      if (!customerId) {
        alert("Customer is missing.");
        return;
      }
      url = apiUrl(api.assignCustomer, customerId);
    } else if (source === "work") {
      if (!workId) {
        alert("Work type is missing.");
        return;
      }
      url = apiUrl(api.assignWork, workId);
    } else {
      if (!payload.account_name) {
        alert("Account Name is required.");
        return;
      }
      url = accountId ? apiUrl(api.update, accountId) : api.create;
    }

    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": window.CHART_ACCOUNT_CSRF || "",
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

  function formatInr(value) {
    const num = Number(value);
    if (!Number.isFinite(num)) return "";
    return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function formatEntryDate(value) {
    const text = String(value || "").slice(0, 10);
    const parts = text.split("-");
    if (parts.length !== 3) return text || "—";
    return parts[2] + "/" + parts[1] + "/" + parts[0];
  }

  function hideEntryPanel() {
    els.entryHint?.classList.remove("d-none");
    els.entryName?.classList.add("d-none");
    els.entryClear?.classList.add("d-none");
    els.entryBlocked?.classList.add("d-none");
    if (els.entryLinks) els.entryLinks.innerHTML = "";
    if (els.entryRows) els.entryRows.innerHTML = "";
  }

  function showEntryPanel(name, usage) {
    if (els.entryHint) els.entryHint.classList.add("d-none");
    if (els.entryName) {
      els.entryName.textContent = name || "";
      els.entryName.classList.remove("d-none");
    }
    const blocked = !usage || usage.can_delete === false;
    els.entryClear?.classList.toggle("d-none", blocked);
    els.entryBlocked?.classList.toggle("d-none", !blocked);
    if (!blocked) return;
    const links = (usage && usage.links) || [];
    const txns = (usage && usage.transactions) || [];
    if (els.entryLinks) {
      els.entryLinks.innerHTML = links
        .map(function (link) {
          return (
            '<span class="cam-entry-chip">' +
            escapeHtml(link.label || link.table || "Entry") +
            " (" +
            escapeHtml(link.count) +
            ")</span>"
          );
        })
        .join("");
    }
    if (els.entryRows) {
      els.entryRows.innerHTML = txns
        .map(function (row) {
          const work = escapeHtml(row.work || row.source || "Entry");
          const ref = row.reference
            ? '<span class="d-block text-muted">' + escapeHtml(row.reference) + "</span>"
            : "";
          const source = row.source
            ? '<span class="d-block text-muted">' + escapeHtml(row.source) + "</span>"
            : "";
          const amount =
            row.amount == null || row.amount === "" ? "—" : escapeHtml(formatInr(row.amount));
          return (
            "<tr><td class=\"text-nowrap\">" +
            escapeHtml(formatEntryDate(row.txn_date)) +
            "</td><td>" +
            work +
            ref +
            source +
            '</td><td class="text-end text-nowrap">' +
            amount +
            "</td></tr>"
          );
        })
        .join("");
    }
    els.entryNone?.classList.toggle("d-none", txns.length > 0);
  }

  function usageUrl(rowEl) {
    const params = new URLSearchParams();
    params.set("source", rowEl.dataset.source || "manual");
    if (rowEl.dataset.accountId) params.set("account_id", rowEl.dataset.accountId);
    if (rowEl.dataset.customerId) params.set("customer_id", rowEl.dataset.customerId);
    if (rowEl.dataset.workId) params.set("work_id", rowEl.dataset.workId);
    return api.usage + "?" + params.toString();
  }

  function loadUsage(rowEl) {
    document.querySelectorAll("#camGridBody tr.cam-row-selected").forEach(function (tr) {
      tr.classList.remove("cam-row-selected");
    });
    rowEl.classList.add("cam-row-selected");
    return fetch(usageUrl(rowEl), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load entries.");
          return data.usage || { can_delete: true, links: [], transactions: [] };
        });
      })
      .then(function (usage) {
        const blocked = usage.can_delete === false;
        rowEl.dataset.hasEntries = blocked ? "1" : "0";
        const btn = rowEl.querySelector(".cam-delete");
        if (btn) {
          btn.disabled = blocked;
          btn.title = blocked ? "Entries exist. Shown on the right." : "Permanent delete";
        }
        showEntryPanel(rowEl.dataset.name || "", usage);
        return usage;
      });
  }

  async function remove(btn) {
    const rowEl = btn.closest("tr");
    let usage = null;
    try {
      usage = rowEl ? await loadUsage(rowEl) : null;
    } catch (err) {
      alert(err.message || "Unable to check entries.");
      return;
    }
    if (usage && usage.can_delete === false) {
      btn.disabled = true;
      return;
    }
    const source = btn.getAttribute("data-source") || "manual";
    const message =
      source === "customer"
        ? "Permanently delete this customer account? The customer master record will also be removed. This cannot be recovered."
        : source === "work"
          ? "Permanently delete this income/expense account? The work master record will also be removed. This cannot be recovered."
          : "Permanently delete this account? This cannot be recovered.";
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm(message))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: message });
      if (!creds) return;
    }

    let url;
    if (source === "customer") {
      url = apiUrl(api.clearCustomer, btn.getAttribute("data-customer-id"));
    } else if (source === "work") {
      url = apiUrl(api.clearWork, btn.getAttribute("data-work-id"));
    } else {
      url = apiUrl(api.delete, btn.getAttribute("data-id"));
    }

    fetch(url, {
      method: "POST",
      headers: Object.assign(
        {
          Accept: "application/json",
          "X-CSRFToken": window.CHART_ACCOUNT_CSRF || "",
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
        showStatus(data.message || "Permanently deleted.", "info");
        hideEntryPanel();
        return loadRows();
      })
      .catch(function (err) {
        alert(err.message || "Delete failed.");
      });
  }

  els.group?.addEventListener("change", function () {
    enforceMaxGroups();
    applyDefaultDrCrFromGroups();
  });
  els.addBtn?.addEventListener("click", openAdd);
  els.addNewBtn?.addEventListener("click", openAdd);
  els.refreshBtn?.addEventListener("click", loadRows);
  els.form?.addEventListener("submit", save);
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadRows, 250);
  });
  els.body?.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".cam-edit");
    if (editBtn) {
      const source = editBtn.getAttribute("data-source");
      if (source === "customer") openEditCustomer(editBtn.getAttribute("data-customer-id"));
      else if (source === "work") openEditWork(editBtn.getAttribute("data-work-id"));
      else openEditManual(editBtn.getAttribute("data-id"));
      return;
    }
    const delBtn = event.target.closest(".cam-delete");
    if (delBtn) {
      if (delBtn.disabled) {
        const rowEl = delBtn.closest("tr");
        if (rowEl) {
          loadUsage(rowEl).catch(function (err) {
            alert(err.message || "Unable to load entries.");
          });
        }
        return;
      }
      remove(delBtn);
      return;
    }
    const rowEl = event.target.closest("tr");
    if (rowEl) {
      loadUsage(rowEl).catch(function (err) {
        alert(err.message || "Unable to load entries.");
      });
    }
  });

  renderRows(window.CHART_ACCOUNT_INITIAL_ROWS || []);
})();
