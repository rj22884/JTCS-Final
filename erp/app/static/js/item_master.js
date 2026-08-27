(function () {
  "use strict";

  const api = window.ITEM_MASTER_API;
  if (!api) return;

  const els = {
    addBtn: document.getElementById("itmAddBtn"),
    addNewBtn: document.getElementById("itmAddNewBtn"),
    refreshBtn: document.getElementById("itmRefreshBtn"),
    search: document.getElementById("itmSearch"),
    count: document.getElementById("itmCount"),
    body: document.getElementById("itmGridBody"),
    empty: document.getElementById("itmEmpty"),
    status: document.getElementById("itmStatus"),
    modalEl: document.getElementById("itmModal"),
    modalTitle: document.getElementById("itmModalTitle"),
    form: document.getElementById("itmForm"),
    id: document.getElementById("itmId"),
    code: document.getElementById("itmCode"),
    name: document.getElementById("itmName"),
    hsn: document.getElementById("itmHsn"),
    hsnSuggest: document.getElementById("itmHsnSuggest"),
    hsnType: document.getElementById("itmHsnType"),
    unit: document.getElementById("itmUnit"),
    chartGroup: document.getElementById("itmChartGroup"),
    rate: document.getElementById("itmRate"),
    gstApplicable: document.getElementById("itmGstApplicable"),
    gst: document.getElementById("itmGst"),
    openingQty: document.getElementById("itmOpeningQty"),
    openingRate: document.getElementById("itmOpeningRate"),
    openingBalance: document.getElementById("itmOpeningBalance"),
    openingDate: document.getElementById("itmOpeningDate"),
    orderNo: document.getElementById("itmOrderNo"),
    description: document.getElementById("itmDescription"),
    isActive: document.getElementById("itmIsActive"),
  };

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let searchTimer = null;
  let hsnTimer = null;
  let hsnSeq = 0;

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

  async function parseJsonResponse(res) {
    const data = await res.json().catch(function () {
      return {};
    });
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || "Request failed.");
    }
    return data;
  }

  function syncGstRateEnabled() {
    const on = !!(els.gstApplicable && els.gstApplicable.checked);
    if (!els.gst) return;
    els.gst.disabled = !on;
    if (!on) {
      els.gst.value = "0";
    } else if (!String(els.gst.value || "").trim() || Number(els.gst.value) === 0) {
      els.gst.value = "18";
    }
  }

  function syncOpeningBalance() {
    const qty = parseFloat(els.openingQty?.value || "0") || 0;
    const rate = parseFloat(els.openingRate?.value || "0") || 0;
    const bal = Math.max(0, qty * rate);
    if (els.openingBalance) els.openingBalance.value = bal.toFixed(2);
  }

  function hideHsnSuggest() {
    if (!els.hsnSuggest) return;
    els.hsnSuggest.classList.add("d-none");
    els.hsnSuggest.innerHTML = "";
  }

  function pickHsn(row) {
    if (!row) return;
    if (els.hsn) els.hsn.value = row.code || "";
    if (els.hsnType && row.hsn_sac_type) els.hsnType.value = row.hsn_sac_type;
    hideHsnSuggest();
  }

  function searchHsn(query) {
    const q = String(query || "").trim();
    if (q.length < 2 || !api.hsnSearch) {
      hideHsnSuggest();
      return;
    }
    const seq = ++hsnSeq;
    const url = new URL(api.hsnSearch, window.location.origin);
    url.searchParams.set("q", q);
    if (els.hsnType?.value) url.searchParams.set("type", els.hsnType.value);
    fetch(url.toString(), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (seq !== hsnSeq || !els.hsnSuggest) return;
        const rows = data.ok ? data.rows || [] : [];
        if (!rows.length) {
          els.hsnSuggest.innerHTML =
            '<div class="list-group-item text-muted small">No HSN/SAC matches</div>';
          els.hsnSuggest.classList.remove("d-none");
          return;
        }
        els.hsnSuggest.innerHTML = rows
          .map(function (row) {
            return (
              '<button type="button" class="list-group-item list-group-item-action py-1 small itm-hsn-pick" ' +
              'data-code="' +
              escapeHtml(row.code) +
              '" data-type="' +
              escapeHtml(row.hsn_sac_type || "") +
              '">' +
              "<strong>" +
              escapeHtml(row.code) +
              "</strong>" +
              (row.description
                ? '<div class="text-muted">' + escapeHtml(row.description) + "</div>"
                : "") +
              "</button>"
            );
          })
          .join("");
        els.hsnSuggest.classList.remove("d-none");
      })
      .catch(function () {
        if (seq !== hsnSeq) return;
        hideHsnSuggest();
      });
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
      const gstLabel = row.gst_applicable === false ? "0 (N/A)" : row.gst_rate_percent;
      tr.innerHTML =
        "<td>" +
        escapeHtml(row.item_id) +
        "</td>" +
        "<td><code>" +
        escapeHtml(row.item_code) +
        "</code></td>" +
        "<td>" +
        escapeHtml(row.item_name) +
        "</td>" +
        "<td>" +
        escapeHtml(row.hsn_sac || "—") +
        "</td>" +
        "<td>" +
        escapeHtml(row.hsn_sac_type || "SAC") +
        "</td>" +
        "<td>" +
        escapeHtml(row.unit || "NOS") +
        "</td>" +
        '<td class="text-end">' +
        escapeHtml(row.default_rate) +
        "</td>" +
        '<td class="text-end">' +
        escapeHtml(gstLabel) +
        "</td>" +
        "<td>" +
        (row.is_active
          ? '<span class="badge text-bg-success">Active</span>'
          : '<span class="badge text-bg-secondary">Inactive</span>') +
        "</td>" +
        '<td class="text-end text-nowrap">' +
        '<button type="button" class="btn btn-outline-primary btn-sm me-1 itm-edit" data-id="' +
        row.item_id +
        '"><i class="bi bi-pencil"></i></button>' +
        '<button type="button" class="btn btn-outline-danger btn-sm itm-delete" data-id="' +
        row.item_id +
        '"><i class="bi bi-trash"></i></button>' +
        "</td>";
      els.body.appendChild(tr);
    });
  }

  function clearForm() {
    els.form?.reset();
    if (els.id) els.id.value = "";
    if (els.unit) els.unit.value = "NOS";
    if (els.chartGroup) els.chartGroup.value = "";
    if (els.gst) els.gst.value = "18";
    if (els.rate) els.rate.value = "0";
    if (els.orderNo) els.orderNo.value = "100";
    if (els.hsnType) els.hsnType.value = "SAC";
    if (els.gstApplicable) els.gstApplicable.checked = true;
    if (els.openingQty) els.openingQty.value = "0";
    if (els.openingRate) els.openingRate.value = "0";
    if (els.openingBalance) els.openingBalance.value = "0.00";
    if (els.openingDate) els.openingDate.value = "";
    if (els.isActive) els.isActive.checked = true;
    hideHsnSuggest();
    syncGstRateEnabled();
    syncOpeningBalance();
  }

  function openAdd() {
    clearForm();
    if (els.modalTitle) els.modalTitle.textContent = "Add Item";
    modal?.show();
  }

  async function openEdit(id) {
    const res = await fetch(apiUrl(api.record, id), { credentials: "same-origin" });
    const data = await parseJsonResponse(res);
    const row = data.record;
    clearForm();
    if (els.id) els.id.value = String(row.item_id || "");
    if (els.code) els.code.value = row.item_code || "";
    if (els.name) els.name.value = row.item_name || "";
    if (els.hsn) els.hsn.value = row.hsn_sac || "";
    if (els.hsnType) els.hsnType.value = row.hsn_sac_type || "SAC";
    if (els.unit) els.unit.value = row.unit || "NOS";
    if (els.chartGroup) {
      els.chartGroup.value =
        row.chart_group_id != null && row.chart_group_id !== ""
          ? String(row.chart_group_id)
          : "";
    }
    if (els.rate) els.rate.value = row.default_rate || "0";
    if (els.gstApplicable) els.gstApplicable.checked = row.gst_applicable !== false;
    if (els.gst) els.gst.value = row.gst_rate_percent || "0";
    if (els.openingQty) els.openingQty.value = row.opening_qty || "0";
    if (els.openingRate) els.openingRate.value = row.opening_rate || "0";
    if (els.openingDate) els.openingDate.value = (row.opening_balance_date || "").slice(0, 10);
    if (els.orderNo) els.orderNo.value = String(row.order_no != null ? row.order_no : 100);
    if (els.description) els.description.value = row.description || "";
    if (els.isActive) els.isActive.checked = !!row.is_active;
    syncGstRateEnabled();
    syncOpeningBalance();
    if (els.modalTitle) els.modalTitle.textContent = "Edit Item";
    modal?.show();
  }

  async function loadRows() {
    const q = (els.search?.value || "").trim();
    const url = new URL(api.list, window.location.origin);
    if (q) url.searchParams.set("search", q);
    const res = await fetch(url.toString(), { credentials: "same-origin" });
    const data = await parseJsonResponse(res);
    renderRows(data.rows || []);
  }

  async function deleteItem(id) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this item?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this item?" });
      if (!creds) return;
    }
    const res = await fetch(apiUrl(api.delete, id), {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": window.ITEM_MASTER_CSRF || "",
      },
      body: JSON.stringify(creds ? window.JTCSDeleteConfirm.withCreds({}, creds) : {}),
    });
    const data = await parseJsonResponse(res);
    showStatus(data.message || "Deleted.", "success");
    await loadRows();
  }

  els.addBtn?.addEventListener("click", openAdd);
  els.addNewBtn?.addEventListener("click", openAdd);
  els.refreshBtn?.addEventListener("click", function () {
    loadRows().catch(function (err) {
      showStatus(err.message || String(err), "danger");
    });
  });
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      loadRows().catch(function (err) {
        showStatus(err.message || String(err), "danger");
      });
    }, 300);
  });

  els.gstApplicable?.addEventListener("change", syncGstRateEnabled);
  els.openingQty?.addEventListener("input", syncOpeningBalance);
  els.openingRate?.addEventListener("input", syncOpeningBalance);

  els.hsn?.addEventListener("input", function () {
    clearTimeout(hsnTimer);
    hsnTimer = setTimeout(function () {
      searchHsn(els.hsn.value);
    }, 280);
  });
  els.hsn?.addEventListener("focus", function () {
    if ((els.hsn.value || "").trim().length >= 2) searchHsn(els.hsn.value);
  });
  els.hsnSuggest?.addEventListener("click", function (ev) {
    const btn = ev.target.closest(".itm-hsn-pick");
    if (!btn) return;
    pickHsn({
      code: btn.getAttribute("data-code"),
      hsn_sac_type: btn.getAttribute("data-type"),
    });
  });
  document.addEventListener("click", function (ev) {
    if (!ev.target.closest("#itmHsn") && !ev.target.closest("#itmHsnSuggest")) {
      hideHsnSuggest();
    }
  });

  els.body?.addEventListener("click", function (ev) {
    const editBtn = ev.target.closest(".itm-edit");
    const delBtn = ev.target.closest(".itm-delete");
    if (editBtn) {
      openEdit(editBtn.getAttribute("data-id")).catch(function (err) {
        showStatus(err.message || String(err), "danger");
      });
    }
    if (delBtn) {
      deleteItem(delBtn.getAttribute("data-id")).catch(function (err) {
        if (window.JTCSDialog?.alert) JTCSDialog.alert(err.message || String(err), "error");
        showStatus(err.message || String(err), "danger");
      });
    }
  });

  els.form?.addEventListener("submit", function (ev) {
    ev.preventDefault();
    const id = (els.id?.value || "").trim();
    const hsn = (els.hsn?.value || "").trim();
    if (!hsn) {
      showStatus("HSN / SAC is required.", "danger");
      els.hsn?.focus();
      return;
    }
    const chartGroupId = (els.chartGroup?.value || "").trim();
    if (!chartGroupId) {
      showStatus("Select Chart of Account group.", "danger");
      els.chartGroup?.focus();
      return;
    }
    syncOpeningBalance();
    const payload = {
      item_code: els.code?.value || "",
      item_name: els.name?.value || "",
      hsn_sac: hsn,
      hsn_sac_type: els.hsnType?.value || "SAC",
      unit: els.unit?.value || "NOS",
      chart_group_id: chartGroupId,
      default_rate: els.rate?.value || "0",
      gst_applicable: els.gstApplicable?.checked ? "1" : "0",
      gst_rate_percent: els.gstApplicable?.checked ? els.gst?.value || "18" : "0",
      opening_qty: els.openingQty?.value || "0",
      opening_rate: els.openingRate?.value || "0",
      opening_balance: els.openingBalance?.value || "0",
      opening_balance_date: els.openingDate?.value || "",
      order_no: els.orderNo?.value || "100",
      description: els.description?.value || "",
      is_active: els.isActive?.checked ? "1" : "0",
    };
    const url = id ? apiUrl(api.update, id) : api.create;
    fetch(url, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": window.ITEM_MASTER_CSRF || "",
      },
      body: JSON.stringify(payload),
    })
      .then(parseJsonResponse)
      .then(function (data) {
        modal?.hide();
        showStatus(data.message || "Saved.", "success");
        return loadRows();
      })
      .catch(function (err) {
        showStatus(err.message || String(err), "danger");
      });
  });

  syncGstRateEnabled();
  syncOpeningBalance();
  renderRows(window.ITEM_MASTER_INITIAL_ROWS || []);
})();
