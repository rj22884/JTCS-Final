(function () {
  const form = document.getElementById("rcfEntryForm");
  if (!form) return;

  const els = {
    newBtn: document.getElementById("rcfNewEntryBtn"),
    refreshBtn: document.getElementById("rcfRefreshGridBtn"),
    modalEl: document.getElementById("rcfEntryModal"),
    modalTitle: document.getElementById("rcfEntryModalTitle"),
    entryId: document.getElementById("rcfEntryID"),
    workDate: document.getElementById("rcfWorkDate"),
    billNo: document.getElementById("rcfBillNo"),
    amount: document.getElementById("rcfAmount"),
    fpsRowId: document.getElementById("rcfFpsRowID"),
    state: document.getElementById("rcfState"),
    district: document.getElementById("rcfDistrict"),
    dso: document.getElementById("rcfDso"),
    aro: document.getElementById("rcfAro"),
    fpsSearch: document.getElementById("rcfFpsSearch"),
    fpsResults: document.getElementById("rcfFpsResults"),
    fpsSelected: document.getElementById("rcfFpsSelected"),
    dealerName: document.getElementById("rcfDealerName"),
    fpsCode: document.getElementById("rcfFpsCode"),
    workDone: document.getElementById("rcfWorkDone"),
    tallyBill: document.getElementById("rcfTallyBillGenerated"),
    paymentReceived: document.getElementById("rcfPaymentReceived"),
    autoBillBtn: document.getElementById("rcfAutoBillBtn"),
    tallyBillWrap: document.getElementById("rcfTallyBillWrap"),
    tallyBillNo: document.getElementById("rcfTallyBillNo"),
    tallyBillDate: document.getElementById("rcfTallyBillDate"),
    tallyBillAmount: document.getElementById("rcfTallyBillAmount"),
    paymentSection: document.getElementById("rcfPaymentSection"),
    paymentLockedHint: document.getElementById("rcfPaymentLockedHint"),
    paymentFieldset: document.getElementById("rcfPaymentFieldset"),
    paymentLines: document.getElementById("rcfPaymentLines"),
    paymentSummary: document.getElementById("rcfPaymentSummary"),
    addPaymentBtn: document.getElementById("rcfAddPaymentBtn"),
    remarks: document.getElementById("rcfRemarks"),
    saveBtn: document.getElementById("rcfSaveBtn"),
    gridBody: document.getElementById("rcfDataGridBody"),
    gridEmpty: document.getElementById("rcfGridEmpty"),
    gridSearch: document.getElementById("rcfGridSearch"),
    gridDateFrom: document.getElementById("rcfGridDateFrom"),
    gridDateTo: document.getElementById("rcfGridDateTo"),
    gridCount: document.getElementById("rcfGridCount"),
    applyFilterBtn: document.getElementById("rcfApplyFilterBtn"),
    clearFilterBtn: document.getElementById("rcfClearFilterBtn"),
  };

  const entryModal =
    els.modalEl && window.bootstrap
      ? window.bootstrap.Modal.getOrCreateInstance(els.modalEl)
      : null;

  let allGridRows = [];
  let billNoTouched = false;
  let fpsSearchTimer = null;

  function csrfToken() {
    return form.querySelector('[name="csrf_token"]')?.value || window.RCF_CSRF || "";
  }

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(\/|$)/, "/" + id + "$1");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatAmount(value) {
    const n = Number(value || 0);
    return Number.isFinite(n) ? n.toFixed(2) : "0.00";
  }

  function formatDisplayDate(raw) {
    if (!raw) return "";
    const s = String(raw).slice(0, 10);
    const parts = s.split("-");
    if (parts.length === 3) return parts[2] + "/" + parts[1] + "/" + parts[0];
    return s;
  }

  function isEditMode() {
    return !!(els.entryId && els.entryId.value);
  }

  function isWorkDoneChecked() {
    return !!(els.workDone && els.workDone.checked);
  }

  function isTallyChecked() {
    return !!(els.tallyBill && els.tallyBill.checked);
  }

  function isPaymentReceivedChecked() {
    return !!(els.paymentReceived && els.paymentReceived.checked);
  }

  function syncWorkflow() {
    const workDone = isWorkDoneChecked();
    if (els.tallyBill) {
      els.tallyBill.disabled = !workDone;
      if (!workDone) els.tallyBill.checked = false;
    }
    const tally = isTallyChecked();
    if (els.paymentReceived) {
      els.paymentReceived.disabled = !tally;
      if (!tally) els.paymentReceived.checked = false;
    }
    els.tallyBillWrap?.classList.toggle("d-none", !tally);
    if (tally && els.tallyBillNo && !(els.tallyBillNo.value || "").trim() && els.billNo) {
      els.tallyBillNo.value = (els.billNo.value || "").trim();
    }
    const paymentOn = isPaymentReceivedChecked();
    if (els.paymentFieldset) els.paymentFieldset.disabled = !paymentOn;
    els.paymentSection?.classList.toggle("rcf-payment-section-locked", !paymentOn);
    els.paymentSection?.classList.toggle("oie-payment-section-locked", !paymentOn);
    els.paymentLockedHint?.classList.toggle("d-none", paymentOn);
    if (paymentOn) {
      ensurePaymentLines();
      const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
      if (lines.length === 1 && getPaymentTotal() <= 0) {
        const amtInput = lines[0].querySelector(".oie-payment-amount");
        const amt = parseFloat(els.amount?.value || "0");
        if (amtInput && amt > 0) amtInput.value = amt.toFixed(2);
      }
      updatePaymentSummary();
    }
  }

  function paymentModeValue(item) {
    return String(item.bank_account_id || item.payment_mode_id || "");
  }

  function paymentModeLabel(item) {
    return item.display_account_number || item.bank_name || paymentModeValue(item);
  }

  function defaultBankAccountId() {
    const accounts = window.RCF_BANK_ACCOUNTS || [];
    const preferred = accounts.find(function (item) {
      return item && item.is_default;
    });
    if (preferred) return paymentModeValue(preferred);
    const byNumber = accounts.find(function (item) {
      const number = String(item.account_number || item.display_account_number || "").replace(/\D/g, "");
      return number === "58250200000396" || number.endsWith("0396");
    });
    return byNumber ? paymentModeValue(byNumber) : "";
  }

  function autoSelectPaymentBank(select, preferredValue) {
    const want = preferredValue || defaultBankAccountId();
    if (
      want &&
      Array.from(select.options).some(function (opt) {
        return opt.value === String(want);
      })
    ) {
      select.value = String(want);
      return;
    }
    const firstOption = Array.from(select.options).find(function (opt) {
      return opt.value;
    });
    if (firstOption) select.value = firstOption.value;
  }

  function buildPaymentBankSelect(selectedValue) {
    const select = document.createElement("select");
    select.className = "form-select oie-payment-bank rcf-payment-bank";
    select.required = true;
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = "-- Select --";
    select.appendChild(empty);
    (window.RCF_BANK_ACCOUNTS || []).forEach(function (item) {
      const opt = document.createElement("option");
      opt.value = paymentModeValue(item);
      opt.textContent = paymentModeLabel(item);
      select.appendChild(opt);
    });
    autoSelectPaymentBank(select, selectedValue);
    return select;
  }

  function getPaymentTotal() {
    let total = 0;
    els.paymentLines?.querySelectorAll(".oie-payment-amount, .rcf-payment-amount").forEach(function (input) {
      const val = parseFloat(input.value || "0");
      if (!Number.isNaN(val)) total += val;
    });
    return total;
  }

  function updatePaymentSummary() {
    if (!els.paymentSummary) return;
    const total = getPaymentTotal();
    const entryAmount = parseFloat(els.amount?.value || "0") || 0;
    if (!total && !entryAmount) {
      els.paymentSummary.textContent = "";
      return;
    }
    let text = "Received: " + total.toFixed(2);
    if (entryAmount > 0) text += " / Amount: " + entryAmount.toFixed(2);
    els.paymentSummary.textContent = text;
    const matched = entryAmount > 0 && Math.abs(total - entryAmount) < 0.005;
    els.paymentSummary.className =
      "small ms-auto " + (matched || !entryAmount ? "text-success" : "text-danger");
  }

  function defaultPaymentDate() {
    return els.workDate?.value || window.RCF_DEFAULT_DATE || new Date().toISOString().slice(0, 10);
  }

  function addPaymentLine(options) {
    options = options || {};
    if (!els.paymentLines) return;
    const line = document.createElement("div");
    line.className = "oie-payment-line rcf-payment-line";

    const bankWrap = document.createElement("div");
    bankWrap.className = "oie-payment-bank-wrap";
    const bankLabel = document.createElement("label");
    bankLabel.className = "form-label";
    bankLabel.textContent = "Payment Mode *";
    const bankSelect = buildPaymentBankSelect(options.bank_account_id || options.bankAccountId);
    bankWrap.appendChild(bankLabel);
    bankWrap.appendChild(bankSelect);

    const dateWrap = document.createElement("div");
    dateWrap.className = "oie-payment-date-wrap";
    const dateLabel = document.createElement("label");
    dateLabel.className = "form-label";
    dateLabel.textContent = "Date *";
    const dateInput = document.createElement("input");
    dateInput.type = "date";
    dateInput.className = "form-control oie-payment-date rcf-payment-date";
    dateInput.required = true;
    dateInput.value = options.payment_date || defaultPaymentDate();
    dateWrap.appendChild(dateLabel);
    dateWrap.appendChild(dateInput);

    const amountWrap = document.createElement("div");
    amountWrap.className = "oie-payment-amount-wrap";
    const amountLabel = document.createElement("label");
    amountLabel.className = "form-label oie-payment-amount-label";
    amountLabel.textContent = "Received Amount";
    const amountInput = document.createElement("input");
    amountInput.type = "number";
    amountInput.step = "0.01";
    amountInput.min = "0";
    amountInput.className = "form-control oie-payment-amount rcf-payment-amount";
    amountInput.required = true;
    amountInput.value =
      options.amount != null && options.amount !== "" ? options.amount : "";
    amountInput.addEventListener("input", updatePaymentSummary);
    amountWrap.appendChild(amountLabel);
    amountWrap.appendChild(amountInput);

    const actionWrap = document.createElement("div");
    actionWrap.className = "oie-payment-action-wrap";
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "btn btn-outline-danger btn-sm oie-payment-remove rcf-payment-remove";
    removeBtn.innerHTML = '<i class="bi bi-trash"></i>';
    removeBtn.title = "Remove";
    removeBtn.addEventListener("click", function () {
      const lines = els.paymentLines.querySelectorAll(".oie-payment-line") || [];
      if (lines.length <= 1) {
        const select = line.querySelector("select");
        const amount = line.querySelector(".oie-payment-amount, .rcf-payment-amount");
        const date = line.querySelector(".oie-payment-date");
        if (select) select.value = "";
        if (amount) amount.value = "";
        if (date) date.value = "";
        updatePaymentSummary();
        return;
      }
      line.remove();
      updatePaymentRemoveButtons();
      updatePaymentSummary();
    });
    actionWrap.appendChild(removeBtn);

    line.appendChild(bankWrap);
    line.appendChild(dateWrap);
    line.appendChild(amountWrap);
    line.appendChild(actionWrap);
    els.paymentLines.appendChild(line);
    updatePaymentRemoveButtons();
    updatePaymentSummary();
  }

  function updatePaymentRemoveButtons() {
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    lines.forEach(function (line) {
      const btn = line.querySelector(".oie-payment-remove, .rcf-payment-remove");
      if (btn) btn.disabled = false;
    });
  }

  function ensurePaymentLines() {
    if (!els.paymentLines) return;
    if (!els.paymentLines.querySelector(".oie-payment-line")) {
      addPaymentLine({});
    }
  }

  function resetPaymentLines(lines) {
    if (!els.paymentLines) return;
    els.paymentLines.innerHTML = "";
    const rows = lines && lines.length ? lines : [{}];
    rows.forEach(function (row) {
      addPaymentLine(row);
    });
  }

  function syncPaymentLinesToForm() {
    form.querySelectorAll(".rcf-payment-sync").forEach(function (el) {
      el.remove();
    });
    if (!isPaymentReceivedChecked()) return;
    if (els.paymentFieldset) els.paymentFieldset.disabled = false;
    els.paymentLines?.querySelectorAll(".oie-payment-line").forEach(function (line) {
      const bank = line.querySelector(".oie-payment-bank, .rcf-payment-bank");
      const dateInput = line.querySelector(".oie-payment-date, .rcf-payment-date");
      const amount = line.querySelector(".oie-payment-amount, .rcf-payment-amount");
      if (!bank || !amount) return;
      const wrap = document.createElement("div");
      wrap.className = "rcf-payment-sync d-none";
      ["PaymentBankAccountID[]", "PaymentDate[]", "PaymentAmount[]"].forEach(function (name, idx) {
        const hidden = document.createElement("input");
        hidden.type = "hidden";
        hidden.name = name;
        hidden.value =
          idx === 0 ? bank.value || "" : idx === 1 ? dateInput?.value || "" : amount.value || "";
        wrap.appendChild(hidden);
      });
      form.appendChild(wrap);
    });
  }

  function validatePaymentLines() {
    if (!isPaymentReceivedChecked()) return null;
    const lines = els.paymentLines?.querySelectorAll(".oie-payment-line") || [];
    if (!lines.length) return "At least one payment mode is required.";
    for (let i = 0; i < lines.length; i++) {
      const bank = lines[i].querySelector(".oie-payment-bank, .rcf-payment-bank");
      const amount = parseFloat(
        lines[i].querySelector(".oie-payment-amount, .rcf-payment-amount")?.value || "0"
      );
      const dateVal = lines[i].querySelector(".oie-payment-date, .rcf-payment-date")?.value || "";
      if (!bank?.value) return "Each payment mode must be selected.";
      if (!dateVal) return "Each payment line must have a date.";
      if (!(amount > 0)) return "Each payment amount must be greater than zero.";
    }
    if (getPaymentTotal() <= 0) {
      return "Total payment amount must be greater than zero.";
    }
    return null;
  }

  function fillSelect(select, rows, placeholder) {
    if (!select) return;
    select.innerHTML = "";
    const empty = document.createElement("option");
    empty.value = "";
    empty.textContent = placeholder || "-- Select --";
    select.appendChild(empty);
    (rows || []).forEach(function (row) {
      const opt = document.createElement("option");
      opt.value = String(row.id || row.value || "");
      opt.textContent = row.label || row.name || opt.value;
      select.appendChild(opt);
    });
  }

  function cascadeUrl(level, parentId) {
    const url = new URL(window.RCF_CASCADE_URL, window.location.origin);
    url.searchParams.set("level", level);
    if (parentId) url.searchParams.set("parent_id", parentId);
    return url.toString();
  }

  function loadCascade(level, parentId, select, placeholder) {
    select.disabled = true;
    fillSelect(select, [], placeholder);
    return fetch(cascadeUrl(level, parentId), { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        fillSelect(select, data.ok ? data.rows || [] : [], placeholder);
        select.disabled = !(data.ok && (data.rows || []).length);
      })
      .catch(function () {
        fillSelect(select, [], placeholder);
        select.disabled = true;
      });
  }

  function resetFpsSelection() {
    if (els.fpsRowId) els.fpsRowId.value = "";
    if (els.dealerName) els.dealerName.value = "";
    if (els.fpsCode) els.fpsCode.value = "";
    if (els.fpsSearch) els.fpsSearch.value = "";
    els.fpsSelected?.classList.add("d-none");
    els.fpsResults?.classList.add("d-none");
  }

  function applyFpsSelection(row) {
    if (!row) return;
    if (els.fpsRowId) els.fpsRowId.value = row.fps_row_id || "";
    const name = row.dealer_name || row.shop_name || "";
    const code = row.fps_id || row.existing_fps_id || "";
    if (els.dealerName) els.dealerName.value = name;
    if (els.fpsCode) els.fpsCode.value = code;
    if (els.fpsSearch) els.fpsSearch.value = name;
    if (els.fpsSelected) {
      els.fpsSelected.textContent =
        "Selected: " +
        name +
        (code ? " · FPS " + code : "") +
        (row.district_name ? " · " + row.district_name : "");
      els.fpsSelected.classList.remove("d-none");
    }
    els.fpsResults?.classList.add("d-none");
  }

  function searchFps(query) {
    const aroId = els.aro?.value || "";
    if (!aroId || !window.RCF_FPS_SEARCH_URL) return;
    const url = new URL(window.RCF_FPS_SEARCH_URL, window.location.origin);
    url.searchParams.set("q", query || "");
    url.searchParams.set("state_id", els.state?.value || "");
    url.searchParams.set("district_id", els.district?.value || "");
    url.searchParams.set("dso_id", els.dso?.value || "");
    url.searchParams.set("aro_id", aroId);
    return fetch(url.toString(), { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!els.fpsResults) return;
        els.fpsResults.innerHTML = "";
        const rows = data.ok ? data.rows || data.dealers || [] : [];
        if (!rows.length) {
          els.fpsResults.classList.add("d-none");
          return;
        }
        rows.slice(0, 30).forEach(function (row) {
          const btn = document.createElement("button");
          btn.type = "button";
          btn.className = "list-group-item list-group-item-action py-1 small";
          const name = row.dealer_name || row.shop_name || "";
          const code = row.fps_id || "";
          btn.textContent = name + (code ? " · " + code : "");
          btn.addEventListener("click", function () {
            applyFpsSelection(row);
          });
          els.fpsResults.appendChild(btn);
        });
        els.fpsResults.classList.remove("d-none");
      })
      .catch(function () {
        els.fpsResults?.classList.add("d-none");
      });
  }

  function initCascade() {
    loadCascade("state", null, els.state, "-- State --").then(function () {
      if (els.state && !els.state.disabled) els.state.disabled = false;
    });
  }

  function refreshBillNoIfNeeded() {
    if (isEditMode() || billNoTouched) return Promise.resolve();
    if (!els.workDate?.value || !window.RCF_NEXT_BILL_URL) return Promise.resolve();
    const url =
      window.RCF_NEXT_BILL_URL +
      "?work_date=" +
      encodeURIComponent(els.workDate.value);
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data.ok && data.bill_no && els.billNo) els.billNo.value = data.bill_no;
      })
      .catch(function () {});
  }

  function setEditMode(entryId) {
    if (els.entryId) els.entryId.value = entryId || "";
    if (els.modalTitle) els.modalTitle.textContent = entryId ? "Edit Entry" : "New Entry";
  }

  function resetForm() {
    setEditMode("");
    billNoTouched = false;
    form.reset();
    if (els.workDate) els.workDate.value = window.RCF_DEFAULT_DATE || "";
    if (els.tallyBillDate) els.tallyBillDate.value = window.RCF_DEFAULT_DATE || "";
    resetFpsSelection();
    if (els.district) {
      fillSelect(els.district, [], "-- District --");
      els.district.disabled = true;
    }
    if (els.dso) {
      fillSelect(els.dso, [], "-- DSO --");
      els.dso.disabled = true;
    }
    if (els.aro) {
      fillSelect(els.aro, [], "-- ARO --");
      els.aro.disabled = true;
    }
    if (els.fpsSearch) els.fpsSearch.disabled = true;
    initCascade();
    resetPaymentLines([{}]);
    if (els.workDone) els.workDone.checked = false;
    if (els.tallyBill) els.tallyBill.checked = false;
    if (els.paymentReceived) els.paymentReceived.checked = false;
    syncWorkflow();
    refreshBillNoIfNeeded();
  }

  function openNewEntry() {
    resetForm();
    entryModal?.show();
  }

  function parseJsonResponse(res) {
    const contentType = res.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      return res.text().then(function () {
        throw new Error("Unexpected server response. Refresh and try again.");
      });
    }
    return res.json().then(function (data) {
      if (!res.ok || !data.ok) throw new Error(data.error || "Request failed.");
      return data;
    });
  }

  function validateForm() {
    if (!els.workDate?.value) return "Work date is required.";
    if (!(parseFloat(els.amount?.value || "0") > 0)) return "Amount must be greater than zero.";
    if (!(els.fpsRowId?.value || "").trim()) return "Select a PDS FPS shop.";
    if (isTallyChecked() && !isWorkDoneChecked()) {
      return "Work Done must be checked before Tally Bill Generated.";
    }
    if (isPaymentReceivedChecked() && !isTallyChecked()) {
      return "Tally Bill Generated must be checked before Payment Received.";
    }
    if (isTallyChecked()) {
      if (!(els.tallyBillNo?.value || "").trim()) {
        return "Tally bill number is required when Tally Bill Generated is checked.";
      }
    }
    return validatePaymentLines();
  }

  function saveEntry() {
    const error = validateForm();
    if (error) {
      alert(error);
      return Promise.resolve();
    }
    els.paymentLines?.querySelectorAll(".oie-payment-date, .rcf-payment-date").forEach(function (input) {
      if (!input.value) input.value = defaultPaymentDate();
    });
    syncPaymentLinesToForm();
    if (els.saveBtn) els.saveBtn.disabled = true;
    return fetch(window.RCF_SAVE_URL || "/public-report/ration-card/followup/save", {
      method: "POST",
      body: new FormData(form),
      headers: {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrfToken(),
      },
    })
      .then(function (res) {
        return parseJsonResponse(res);
      })
      .then(function () {
        entryModal?.hide();
        return loadGrid();
      })
      .catch(function (err) {
        alert(err.message || "Unable to save entry.");
      })
      .finally(function () {
        if (els.saveBtn) els.saveBtn.disabled = false;
      });
  }

  function ensureBillNoThenSave() {
    if (isEditMode() || (els.billNo && els.billNo.value.trim())) {
      return saveEntry();
    }
    return refreshBillNoIfNeeded().then(function () {
      if (!els.billNo?.value?.trim()) {
        alert("Bill number could not be generated. Check work date.");
        return;
      }
      return saveEntry();
    });
  }

  function statusBadges(row) {
    const parts = [];
    if (row.work_done) {
      parts.push('<span class="badge text-bg-success">Work Done</span>');
    }
    if (row.tally_bill_generated) {
      parts.push('<span class="badge text-bg-primary">Tally Bill</span>');
    } else if (row.work_done) {
      parts.push('<span class="badge text-bg-warning text-dark">Bill Pending</span>');
    }
    if (row.payment_received) {
      parts.push('<span class="badge text-bg-info">Paid</span>');
    }
    return parts.join(" ") || '<span class="text-muted">—</span>';
  }

  function filteredRows() {
    const q = (els.gridSearch?.value || "").trim().toLowerCase();
    const from = els.gridDateFrom?.value || "";
    const to = els.gridDateTo?.value || "";
    return allGridRows.filter(function (row) {
      if (from && (row.work_date || "") < from) return false;
      if (to && (row.work_date || "") > to) return false;
      if (!q) return true;
      const hay = [
        row.bill_no,
        row.display_name,
        row.dealer_name,
        row.fps_name,
        row.fps_code,
        row.district_name,
        row.remarks,
      ]
        .join(" ")
        .toLowerCase();
      return hay.indexOf(q) >= 0;
    });
  }

  function renderGrid() {
    const rows = filteredRows();
    if (els.gridCount) els.gridCount.textContent = rows.length + " record(s)";
    if (!els.gridBody) return;
    if (!rows.length) {
      els.gridBody.innerHTML = "";
      els.gridEmpty?.classList.remove("d-none");
      return;
    }
    els.gridEmpty?.classList.add("d-none");
    els.gridBody.innerHTML = rows
      .map(function (row) {
        return (
          "<tr>" +
          "<td>" +
          escapeHtml(row.bill_no) +
          "</td>" +
          "<td>" +
          escapeHtml(formatDisplayDate(row.work_date)) +
          "</td>" +
          "<td>" +
          escapeHtml(row.display_name || row.dealer_name || row.fps_name || "") +
          "</td>" +
          "<td>" +
          escapeHtml(row.fps_code || "") +
          "</td>" +
          '<td class="text-end">' +
          escapeHtml(formatAmount(row.amount)) +
          "</td>" +
          '<td class="rcf-status-badges">' +
          statusBadges(row) +
          "</td>" +
          "<td>" +
          escapeHtml(row.remarks || "") +
          "</td>" +
          '<td class="text-end text-nowrap">' +
          '<button type="button" class="btn btn-outline-secondary btn-sm rcf-grid-edit-btn" data-id="' +
          row.entry_id +
          '" title="Edit"><i class="bi bi-pencil"></i></button> ' +
          '<button type="button" class="btn btn-outline-danger btn-sm rcf-grid-delete-btn" data-id="' +
          row.entry_id +
          '" title="Delete"><i class="bi bi-trash"></i></button>' +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function loadGrid() {
    if (!window.RCF_GRID_URL) return Promise.resolve();
    return fetch(window.RCF_GRID_URL, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return parseJsonResponse(res);
      })
      .then(function (data) {
        allGridRows = data.rows || [];
        renderGrid();
      })
      .catch(function (err) {
        console.error(err);
      });
  }

  function loadEntry(entryId) {
    const url = apiUrl(window.RCF_RECORD_URL, entryId);
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data.ok || !data.record) {
          alert(data.error || "Could not load record.");
          return;
        }
        const record = data.record;
        resetForm();
        setEditMode(record.entry_id);
        billNoTouched = true;
        if (els.billNo) els.billNo.value = record.bill_no || "";
        if (els.workDate) els.workDate.value = record.work_date || "";
        if (els.amount) els.amount.value = record.amount || "";
        if (els.fpsRowId) els.fpsRowId.value = record.fps_row_id || "";
        if (els.dealerName) els.dealerName.value = record.dealer_name || record.fps_name || "";
        if (els.fpsCode) els.fpsCode.value = record.fps_code || "";
        if (els.fpsSearch) {
          els.fpsSearch.value = record.dealer_name || record.fps_name || "";
          els.fpsSearch.disabled = false;
        }
        if (els.fpsSelected) {
          els.fpsSelected.textContent =
            "Selected: " +
            (record.dealer_name || record.fps_name || "") +
            (record.fps_code ? " · FPS " + record.fps_code : "");
          els.fpsSelected.classList.remove("d-none");
        }
        if (els.workDone) els.workDone.checked = !!record.work_done;
        if (els.tallyBill) els.tallyBill.checked = !!record.tally_bill_generated;
        if (els.paymentReceived) {
          els.paymentReceived.checked = !!(
            record.payment_received ||
            (record.payments && record.payments.length)
          );
        }
        if (els.tallyBillNo) els.tallyBillNo.value = record.tally_bill_no || "";
        if (els.tallyBillDate) {
          els.tallyBillDate.value = (record.tally_bill_date || record.work_date || "").slice(0, 10);
        }
        if (els.tallyBillAmount) {
          els.tallyBillAmount.value = record.tally_bill_amount || record.amount || "";
        }
        if (els.remarks) els.remarks.value = record.remarks || "";
        resetPaymentLines(record.payments && record.payments.length ? record.payments : [{}]);
        syncWorkflow();
        entryModal?.show();
      });
  }

  function deleteEntry(entryId) {
    const run = function (creds) {
      const headers = {
        Accept: "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-CSRFToken": csrfToken(),
      };
      const body = new FormData();
      body.append("csrf_token", csrfToken());
      if (creds) {
        Object.keys(creds).forEach(function (key) {
          body.append(key, creds[key]);
        });
      }
      return fetch(apiUrl(window.RCF_DELETE_URL, entryId), {
        method: "POST",
        headers: headers,
        body: body,
      })
        .then(function (res) {
          return parseJsonResponse(res);
        })
        .then(function () {
          return loadGrid();
        })
        .catch(function (err) {
          alert(err.message || "Delete failed.");
        });
    };
    if (window.JTCSDeleteConfirm?.ask) {
      return window.JTCSDeleteConfirm.ask({ message: "Delete this followup entry?" }).then(
        function (creds) {
          if (!creds) return;
          return run(creds);
        }
      );
    }
    if (!window.confirm("Delete this followup entry?")) return Promise.resolve();
    return run(null);
  }

  els.state?.addEventListener("change", function () {
    resetFpsSelection();
    fillSelect(els.dso, [], "-- DSO --");
    els.dso.disabled = true;
    fillSelect(els.aro, [], "-- ARO --");
    els.aro.disabled = true;
    if (els.fpsSearch) els.fpsSearch.disabled = true;
    if (!els.state.value) {
      fillSelect(els.district, [], "-- District --");
      els.district.disabled = true;
      return;
    }
    loadCascade("district", els.state.value, els.district, "-- District --");
  });

  els.district?.addEventListener("change", function () {
    resetFpsSelection();
    fillSelect(els.aro, [], "-- ARO --");
    els.aro.disabled = true;
    if (els.fpsSearch) els.fpsSearch.disabled = true;
    if (!els.district.value) {
      fillSelect(els.dso, [], "-- DSO --");
      els.dso.disabled = true;
      return;
    }
    loadCascade("dso", els.district.value, els.dso, "-- DSO --");
  });

  els.dso?.addEventListener("change", function () {
    resetFpsSelection();
    if (els.fpsSearch) els.fpsSearch.disabled = true;
    if (!els.dso.value) {
      fillSelect(els.aro, [], "-- ARO --");
      els.aro.disabled = true;
      return;
    }
    loadCascade("aro", els.dso.value, els.aro, "-- ARO --");
  });

  els.aro?.addEventListener("change", function () {
    resetFpsSelection();
    if (els.fpsSearch) {
      els.fpsSearch.disabled = !els.aro.value;
      if (els.aro.value) els.fpsSearch.focus();
    }
  });

  els.fpsSearch?.addEventListener("input", function () {
    clearTimeout(fpsSearchTimer);
    const q = (els.fpsSearch.value || "").trim();
    if (q.length < 2) {
      els.fpsResults?.classList.add("d-none");
      return;
    }
    fpsSearchTimer = setTimeout(function () {
      searchFps(q);
    }, 250);
  });

  document.addEventListener("click", function (ev) {
    if (!ev.target.closest("#rcfFpsSearch") && !ev.target.closest("#rcfFpsResults")) {
      els.fpsResults?.classList.add("d-none");
    }
  });

  function ensureFpsCustomerOnWorkDone() {
    const name = (els.dealerName?.value || "").trim();
    const code = (els.fpsCode?.value || "").trim();
    if (!name || !code) {
      alert("Pehle PDS FPS select karein (Name + FPS Code).");
      if (els.workDone) els.workDone.checked = false;
      syncWorkflow();
      return Promise.resolve(null);
    }
    const body = new FormData();
    body.append("csrf_token", csrfToken());
    body.append("fps_name", name);
    body.append("fps_code", code);
    return fetch(window.RCF_ENSURE_CUSTOMER_URL || "/public-report/ration-card/followup/ensure-customer", {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: body,
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) {
            throw new Error(data.error || "Customer create failed.");
          }
          return data;
        });
      })
      .then(function (data) {
        if (data.created && data.customer_name) {
          // Soft notice — avoid blocking workflow
          if (els.fpsSelected) {
            const base = els.fpsSelected.textContent || "";
            if (base.indexOf("Customer:") < 0) {
              els.fpsSelected.textContent =
                base + " · Customer: " + data.customer_name;
            }
          }
        }
        return data;
      })
      .catch(function (err) {
        alert(err.message || "Customer create failed.");
        if (els.workDone) els.workDone.checked = false;
        syncWorkflow();
        return null;
      });
  }

  els.workDone?.addEventListener("change", function () {
    if (isWorkDoneChecked()) {
      ensureFpsCustomerOnWorkDone().finally(syncWorkflow);
    } else {
      syncWorkflow();
    }
  });
  els.tallyBill?.addEventListener("change", syncWorkflow);
  els.paymentReceived?.addEventListener("change", syncWorkflow);
  els.amount?.addEventListener("input", updatePaymentSummary);
  els.addPaymentBtn?.addEventListener("click", function () {
    addPaymentLine({});
  });
  // Automated bill generation removed — Sales Invoice module is separate.
  els.billNo?.addEventListener("input", function () {
    billNoTouched = true;
  });
  els.workDate?.addEventListener("change", function () {
    if (!isEditMode()) {
      billNoTouched = false;
      refreshBillNoIfNeeded();
    }
  });

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    ensureBillNoThenSave();
  });

  els.newBtn?.addEventListener("click", openNewEntry);
  els.refreshBtn?.addEventListener("click", loadGrid);
  els.applyFilterBtn?.addEventListener("click", renderGrid);
  els.clearFilterBtn?.addEventListener("click", function () {
    if (els.gridSearch) els.gridSearch.value = "";
    if (els.gridDateFrom) els.gridDateFrom.value = "";
    if (els.gridDateTo) els.gridDateTo.value = "";
    renderGrid();
  });
  els.gridSearch?.addEventListener("input", renderGrid);

  els.gridBody?.addEventListener("click", function (ev) {
    const editBtn = ev.target.closest(".rcf-grid-edit-btn");
    const delBtn = ev.target.closest(".rcf-grid-delete-btn");
    if (editBtn) loadEntry(editBtn.getAttribute("data-id"));
    if (delBtn) deleteEntry(delBtn.getAttribute("data-id"));
  });

  initCascade();
  loadGrid().then(function () {
    if (window.RCF_AUTO_LOAD_ENTRY_ID) {
      loadEntry(window.RCF_AUTO_LOAD_ENTRY_ID);
    }
  });
})();
