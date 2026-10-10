(function () {
  const els = {
    newBtn: document.getElementById("obcNewEntryBtn"),
    refreshBtn: document.getElementById("obcRefreshGridBtn"),
    gridBody: document.getElementById("obcDataGridBody"),
    empty: document.getElementById("obcGridEmpty"),
    count: document.getElementById("obcGridCount"),
    modalEl: document.getElementById("obcEntryModal"),
    modalDialog: document.getElementById("obcEntryModalDialog"),
    modalTitle: document.getElementById("obcEntryModalTitle"),
    maximizeBtn: document.getElementById("obcMaximizeBtn"),
    maximizeIcon: document.getElementById("obcMaximizeIcon"),
    form: document.getElementById("obcEntryForm"),
    entryId: document.getElementById("obcEntryId"),
    workDate: document.getElementById("obcWorkDate"),
    voucherNo: document.getElementById("obcVoucherNo"),
    amount: document.getElementById("obcAmount"),
    creditAccount: document.getElementById("obcCreditAccount"),
    creditSearch: document.getElementById("obcCreditSearch"),
    creditSuggest: document.getElementById("obcCreditSuggest"),
    debitAccount: document.getElementById("obcDebitAccount"),
    debitSearch: document.getElementById("obcDebitSearch"),
    debitSuggest: document.getElementById("obcDebitSuggest"),
    purpose: document.getElementById("obcPurpose"),
    remarks: document.getElementById("obcRemarks"),
    saveBtn: document.getElementById("obcSaveBtn"),
    customerSearch: document.getElementById("obcCustomerSearch"),
    customerId: document.getElementById("obcCustomerId"),
    customerSuggest: document.getElementById("obcCustomerSuggest"),
    invoiceMode: document.getElementById("obcInvoiceMode"),
    invoicePickerBtn: document.getElementById("obcInvoicePickerBtn"),
    invoicePickerMenu: document.getElementById("obcInvoicePickerMenu"),
    invoicePickerLabel: document.getElementById("obcInvoicePickerLabel"),
    invoiceModeValue: document.getElementById("obcInvoiceModeValue"),
    invoiceListWrap: document.getElementById("obcInvoiceListWrap"),
    invoiceList: document.getElementById("obcInvoiceList"),
    allocationPreview: document.getElementById("obcAllocationPreview"),
    invoiceHint: document.getElementById("obcInvoiceHint"),
    categoryWrap: document.getElementById("obcCategoryWrap"),
    subWorkWrap: document.getElementById("obcSubWorkWrap"),
    categoryName: document.getElementById("obcCategoryName"),
    subWorkName: document.getElementById("obcSubWorkName"),
    workId: document.getElementById("obcWorkId"),
    workTypeId: document.getElementById("obcWorkTypeId"),
  };

  if (!els.gridBody || !window.OBC_API) return;

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let allRows = [];
  let gridSortKey = "work_date";
  let gridSortDir = "desc";
  const gridFilters = {};
  let modalMaximized = false;
  let invoiceRows = [];
  let customerLedgerKey = "";
  let reservedAdvances = [];
  let customerFromCredit = false;

  function setModalMaximized(next) {
    modalMaximized = !!next;
    if (els.modalEl) {
      els.modalEl.classList.toggle("obc-modal-maximized", modalMaximized);
    }
    if (els.maximizeBtn) {
      els.maximizeBtn.title = modalMaximized ? "Restore" : "Maximize";
      els.maximizeBtn.setAttribute(
        "aria-label",
        modalMaximized ? "Restore" : "Maximize"
      );
    }
    if (els.maximizeIcon) {
      els.maximizeIcon.className = modalMaximized
        ? "bi bi-fullscreen-exit"
        : "bi bi-arrows-fullscreen";
    }
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
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
  }

  function isOtherPurpose() {
    return String(els.purpose?.value || "").trim().toLowerCase() === "other";
  }

  function syncOtherRemarksUi() {
    const other = isOtherPurpose();
    const label = document.querySelector('label[for="obcRemarks"]');
    if (label) label.classList.toggle("obc-required", other);
    if (els.remarks) {
      els.remarks.classList.toggle("obc-remarks-required", other);
      els.remarks.placeholder = other ? "Minimum 10 characters" : "";
    }
    const hint = document.getElementById("obcRemarksHint");
    if (hint) hint.classList.toggle("d-none", !other);
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
        "<td>" + escapeHtml((window.formatDisplaySmart || window.formatDisplayDate || String)(row.work_date)) + "</td>" +
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

  function buildAccountOptionsHtml(groups, rows, placeholder) {
    const parts = ['<option value="">' + escapeHtml(placeholder) + "</option>"];
    const groupList = Array.isArray(groups) && groups.length
      ? groups
      : [
          {
            label: "Accounts",
            accounts: rows || [],
          },
        ];
    groupList.forEach(function (group) {
      const accounts = group.accounts || [];
      if (!accounts.length) return;
      parts.push(
        '<optgroup label="' +
          escapeHtml(group.label || group.group_name || "Group") +
          '">'
      );
      accounts.forEach(function (acc) {
        const value = acc.ledger_key || (acc.account_id != null ? "bank-" + acc.account_id : "");
        if (!value) return;
        const customerAttr = acc.customer_id
          ? ' data-customer-id="' +
            escapeHtml(acc.customer_id) +
            '" data-customer-name="' +
            escapeHtml(acc.customer_name || "") +
            '"'
          : "";
        parts.push(
          '<option value="' +
            escapeHtml(value) +
            '"' +
            customerAttr +
            ">" +
            escapeHtml(acc.label) +
            "</option>"
        );
      });
      parts.push("</optgroup>");
    });
    return parts.join("");
  }

  function pickLedgerSelection(sel) {
    if (sel == null || sel === "") return { key: "", id: null };
    if (typeof sel === "object") {
      return {
        key: sel.ledger_key ? String(sel.ledger_key) : "",
        id: sel.account_id != null && sel.account_id !== "" ? sel.account_id : null,
      };
    }
    return { key: String(sel), id: null };
  }

  function resolveSelectValue(selectEl, selection) {
    if (!selectEl || !selection) return;
    const key = selection.key || "";
    if (key) {
      selectEl.value = key;
      if (selectEl.value === key) return;
    }
    if (selection.id != null && selection.id !== "") {
      const bankKey = "bank-" + String(selection.id);
      selectEl.value = bankKey;
    }
  }

  function setLedgerSelection(selectEl, searchEl, selection) {
    if (!selectEl) return;
    const key = (selection && (selection.ledger_key || selection.key)) || "";
    const label = (selection && (selection.label || selection.title)) || "";
    selectEl.innerHTML = '<option value="">Select account...</option>';
    if (!key) {
      if (searchEl) {
        searchEl.value = "";
        searchEl.setAttribute("data-selected-title", "");
      }
      return;
    }
    const opt = document.createElement("option");
    opt.value = key;
    opt.textContent = label || key;
    opt.selected = true;
    if (selection.customer_id) {
      opt.setAttribute("data-customer-id", String(selection.customer_id));
      opt.setAttribute("data-customer-name", selection.customer_name || "");
    }
    selectEl.appendChild(opt);
    if (searchEl) {
      const title = selection.title || label || "";
      searchEl.value = title;
      searchEl.setAttribute("data-selected-title", title);
    }
  }

  function renderAccountSuggestions(menu, rows, onPick) {
    if (!menu) return;
    menu.innerHTML = "";
    (rows || []).forEach(function (row) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "obc-account-item";
      const title = document.createElement("div");
      title.className = "obc-account-title";
      title.textContent = row.title || row.label || "";
      btn.appendChild(title);
      (row.lines || []).forEach(function (line) {
        const div = document.createElement("div");
        div.className = "obc-account-line";
        div.textContent = line;
        btn.appendChild(div);
      });
      btn.addEventListener("click", function () {
        onPick(row);
        menu.classList.add("d-none");
      });
      menu.appendChild(btn);
    });
    menu.classList.toggle("d-none", !(rows || []).length);
  }

  function bindAccountSearch(input, menu, selectEl, isCredit) {
    if (!input || !selectEl || !window.OBC_API.accountSearch) return;
    let timer = null;
    let token = 0;
    selectEl.addEventListener("invalid", function (event) {
      event.preventDefault();
      input.setCustomValidity("Select an account from the search results.");
      input.reportValidity();
    });
    input.addEventListener("input", function () {
      input.setCustomValidity("");
      const typed = input.value.trim();
      const selectedTitle = (input.getAttribute("data-selected-title") || "").trim();
      if (selectEl.value && typed !== selectedTitle) {
        selectEl.value = "";
        if (isCredit) selectEl.dispatchEvent(new Event("change"));
      }
      clearTimeout(timer);
      token += 1;
      const requestToken = token;
      if (!typed) {
        if (menu) {
          menu.classList.add("d-none");
          menu.innerHTML = "";
        }
        return;
      }
      timer = setTimeout(function () {
        const url = new URL(window.OBC_API.accountSearch, window.location.origin);
        url.searchParams.set("q", typed);
        url.searchParams.set("limit", "30");
        if (isCredit) url.searchParams.set("side", "credit");
        fetch(url.toString(), { headers: { Accept: "application/json" }, credentials: "same-origin" })
          .then(function (res) { return res.json(); })
          .then(function (data) {
            if (requestToken !== token) return;
            renderAccountSuggestions(menu, data.rows || [], function (row) {
              setLedgerSelection(selectEl, input, row);
              input.setCustomValidity("");
              if (isCredit) selectEl.dispatchEvent(new Event("change"));
            });
          })
          .catch(function () { /* search stays optional until a result is chosen */ });
      }, 300);
    });
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
    syncOtherRemarksUi();
  }

  let invoiceReceiptLaunch = null;

  function invoicePageWindowEl() {
    try {
      if (!window.frameElement || window.top === window) return null;
      const host = window.frameElement.closest(".jtcs-page-win");
      if (!host) return null;
      const frames = host.getElementsByTagName("iframe");
      for (let i = 0; i < frames.length; i += 1) {
        if (frames[i] === window.frameElement) return host;
      }
    } catch (_err) {
      /* not inside a page window */
    }
    return null;
  }

  function receiptReturnHost() {
    return {
      hideReceiptModal: function () {
        if (modal) modal.hide();
      },
      disarmRelaunch: function (plan) {
        const api = window.JtcsInvoiceReceiptReturn;
        if (!api) return;
        try {
          const record = api.pendingRecord(plan, Date.now());
          if (record) sessionStorage.setItem(api.PENDING_KEY, JSON.stringify(record));
        } catch (_err) {
          /* session storage is only a reload backup */
        }
        try {
          history.replaceState(null, "", window.location.pathname + "?" + api.disarmSearch());
        } catch (_err2) {
          /* keep the receipt query if history cannot change */
        }
      },
      hasInvoicePageWindow: function () {
        return !!invoicePageWindowEl();
      },
      finishInvoiceWindow: function (returnTo) {
        const el = invoicePageWindowEl();
        const top = window.top;
        if (top && typeof top.jtcsFinishInvoiceReceiptReturn === "function") {
          top.jtcsFinishInvoiceReceiptReturn({ windowEl: el, returnPath: returnTo });
          return;
        }
        if (top && el && typeof top.jtcsClosePageWindow === "function") {
          top.jtcsClosePageWindow(el, true);
        }
      },
      isEmbeddedInvoice: function () {
        try {
          return !!(window.frameElement && window.parent && window.parent !== window && !invoicePageWindowEl());
        } catch (_err) {
          return false;
        }
      },
      notifyOriginClose: function (plan) {
        try {
          window.parent.postMessage(
            {
              type: "jtcs-invoice-receipt-closed",
              receipt_origin: plan.origin,
              return_to: plan.returnTo,
            },
            window.location.origin
          );
        } catch (_err) {
          /* opener cannot be reached */
        }
      },
      navigateToOrigin: function (returnTo) {
        if (returnTo) window.location.assign(returnTo);
      },
    };
  }

  function returnAfterListedReceipt(launch) {
    const api = window.JtcsInvoiceReceiptReturn;
    if (!api || !launch) return false;
    const plan = api.planSaveSuccess(launch);
    if (!plan.listed) return false;
    invoiceReceiptLaunch = null;
    api.performListedReturn(launch, receiptReturnHost());
    return true;
  }

  async function openNew() {
    invoiceReceiptLaunch = null;
    els.form.reset();
    if (els.entryId) els.entryId.value = "";
    if (els.workDate) els.workDate.value = window.OBC_API.defaultDate || "";
    if (els.voucherNo) els.voucherNo.readOnly = false;
    if (els.modalTitle) {
      els.modalTitle.textContent = "New Bank/Cash Transaction/Electronic Transfer";
    }
    setModalMaximized(false);
    clearInvoiceLink();
    setLedgerSelection(els.creditAccount, els.creditSearch, null);
    setLedgerSelection(els.debitAccount, els.debitSearch, null);
    if (els.creditSuggest) els.creditSuggest.classList.add("d-none");
    if (els.debitSuggest) els.debitSuggest.classList.add("d-none");
    await fillPurposes();
    await refreshVoucher();
    if (modal) modal.show();
  }

  async function openEdit(entryId) {
    invoiceReceiptLaunch = null;
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
    if (els.modalTitle) {
      els.modalTitle.textContent = "Edit Bank/Cash Transaction/Electronic Transfer";
    }
    setModalMaximized(false);
    setLedgerSelection(els.creditAccount, els.creditSearch, {
      ledger_key: row.credit_ledger_key,
      label: row.credit_account,
      title: row.credit_account,
      customer_id: row.credit_customer_id,
      customer_name: row.credit_customer_name,
    });
    setLedgerSelection(els.debitAccount, els.debitSearch, {
      ledger_key: row.debit_ledger_key,
      label: row.debit_account,
      title: row.debit_account,
    });
    await fillPurposes(row.purpose);
    await restoreInvoiceLink(row);
    if (modal) modal.show();
  }

  function formatIsoDate(iso) {
    const match = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (!match) return "";
    return match[3] + "/" + match[2] + "/" + match[1];
  }

  function moneyLabel(value) {
    return "₹" + formatMoney(value);
  }

  function clearCategoryFields() {
    if (els.workId) els.workId.value = "";
    if (els.workTypeId) els.workTypeId.value = "";
    if (els.categoryName) els.categoryName.value = "";
    if (els.subWorkName) els.subWorkName.value = "";
    if (els.categoryWrap) els.categoryWrap.classList.add("d-none");
    if (els.subWorkWrap) els.subWorkWrap.classList.add("d-none");
  }

  function syncCategoryFromInvoices() {
    const mode = syncInvoiceModeField();
    if (mode === "none") {
      clearCategoryFields();
      return;
    }
    let source = null;
    if (mode === "all") {
      source = oldestFirst(invoiceRows)[0] || null;
    } else {
      const ids = checkedInvoiceIds();
      const selected = oldestFirst(
        invoiceRows.filter(function (inv) {
          return ids.indexOf(String(inv.invoice_id)) >= 0;
        })
      );
      source = selected[0] || null;
    }
    if (!source) {
      clearCategoryFields();
      return;
    }
    if (els.workId) els.workId.value = source.work_id ? String(source.work_id) : "";
    if (els.workTypeId) els.workTypeId.value = source.work_type_id ? String(source.work_type_id) : "";
    if (els.categoryName) els.categoryName.value = source.category_name || "";
    if (els.subWorkName) els.subWorkName.value = source.sub_work_name || "";
    const show = !!(source.work_id || source.work_type_id || source.category_name || source.sub_work_name);
    if (els.categoryWrap) els.categoryWrap.classList.toggle("d-none", !show);
    if (els.subWorkWrap) els.subWorkWrap.classList.toggle("d-none", !show);
  }

  function clearInvoiceLink() {
    invoiceRows = [];
    customerLedgerKey = "";
    reservedAdvances = [];
    customerFromCredit = false;
    if (els.customerSearch) els.customerSearch.value = "";
    if (els.customerId) els.customerId.value = "";
    if (els.customerSuggest) {
      els.customerSuggest.classList.add("d-none");
      els.customerSuggest.innerHTML = "";
    }
    clearCategoryFields();
    renderInvoiceChoices("none", []);
  }

  function checkedInvoiceIds() {
    if (!els.invoiceList) return [];
    return Array.from(els.invoiceList.querySelectorAll('input[name="InvoiceIDs"]:checked')).map(function (box) {
      return String(box.value);
    });
  }

  function syncInvoiceModeField() {
    const choice = els.invoiceMode ? els.invoiceMode.value : "none";
    let mode = "none";
    if (choice === "all") mode = "all";
    else if (choice && choice !== "none") mode = "selected";
    else if (checkedInvoiceIds().length) mode = "selected";
    if (els.invoiceModeValue) els.invoiceModeValue.value = mode;
    return mode;
  }

  function creditParty() {
    const option = els.creditAccount && els.creditAccount.selectedOptions
      ? els.creditAccount.selectedOptions[0]
      : null;
    if (!option) return null;
    const id = option.getAttribute("data-customer-id");
    if (!id) return null;
    return {
      id: String(id),
      name: option.getAttribute("data-customer-name") || option.textContent || "",
    };
  }

  function applyCreditParty(party) {
    customerFromCredit = true;
    if (els.customerId) els.customerId.value = party.id;
    if (els.customerSearch) els.customerSearch.value = party.name || "";
    if (els.customerSuggest) els.customerSuggest.classList.add("d-none");
    return loadCustomerInvoices(party.id);
  }

  function oldestFirst(list) {
    return list.slice().sort(function (a, b) {
      const da = String(a.invoice_date || "");
      const db = String(b.invoice_date || "");
      if (da < db) return -1;
      if (da > db) return 1;
      return Number(a.invoice_id || 0) - Number(b.invoice_id || 0);
    });
  }

  function invoiceChoiceHtml(inv) {
    const contact = String(inv.contact_person || "").trim();
    const dateText = formatIsoDate(inv.invoice_date) || "—";
    return (
      '<span class="obc-inv-line1">' +
      escapeHtml(inv.invoice_no || "Invoice") +
      " — " +
      moneyLabel(inv.invoice_amount) +
      " — Outstanding " +
      moneyLabel(inv.outstanding_amount) +
      "</span>" +
      '<span class="obc-inv-line2">' +
      escapeHtml(dateText) +
      " | Contact: " +
      escapeHtml(contact || "—") +
      "</span>"
    );
  }

  function paintInvoicePicker() {
    if (!els.invoicePickerMenu || !els.invoicePickerLabel || !els.invoiceMode) return;
    const value = String(els.invoiceMode.value || "none");
    const items = [
      { value: "none", html: '<span class="obc-inv-line1">No Invoice</span>' },
      { value: "all", html: '<span class="obc-inv-line1">All Invoices</span>' },
    ];
    invoiceRows.forEach(function (inv) {
      items.push({ value: String(inv.invoice_id), html: invoiceChoiceHtml(inv) });
    });
    els.invoicePickerMenu.innerHTML = items
      .map(function (item) {
        const active = value === String(item.value) ? " is-active" : "";
        return (
          '<button type="button" class="obc-invoice-picker-item' +
          active +
          '" data-value="' +
          escapeHtml(item.value) +
          '">' +
          item.html +
          "</button>"
        );
      })
      .join("");
    const current = invoiceRows.find(function (inv) {
      return String(inv.invoice_id) === value;
    });
    if (value === "all") {
      els.invoicePickerLabel.innerHTML = '<span class="obc-inv-line1">All Invoices</span>';
    } else if (value === "selected") {
      els.invoicePickerLabel.innerHTML =
        '<span class="obc-inv-line1">Selected invoices (' + checkedInvoiceIds().length + ")</span>";
    } else if (current) {
      els.invoicePickerLabel.innerHTML = invoiceChoiceHtml(current);
    } else {
      els.invoicePickerLabel.innerHTML = '<span class="obc-inv-line1">No Invoice</span>';
    }
  }

  function renderInvoiceChoices(mode, selectedIds) {
    const selected = new Set((selectedIds || []).map(String));
    if (els.invoiceMode) {
      const current = els.invoiceMode.value;
      const multi =
        mode === "selected" && selected.size > 1
          ? '<option value="selected">Selected invoices (' + selected.size + ")</option>"
          : "";
      els.invoiceMode.innerHTML =
        '<option value="none">No Invoice</option>' +
        '<option value="all">All Invoices</option>' +
        multi +
        invoiceRows
          .map(function (inv) {
            return (
              '<option value="' +
              escapeHtml(inv.invoice_id) +
              '">' +
              escapeHtml(inv.invoice_no || "Invoice") +
              "</option>"
            );
          })
          .join("");
      if (mode === "all") els.invoiceMode.value = "all";
      else if (mode === "selected" && selected.size === 1) els.invoiceMode.value = Array.from(selected)[0];
      else if (mode === "selected" && selected.size > 1) els.invoiceMode.value = "selected";
      else els.invoiceMode.value = "none";
      if (!els.invoiceMode.value) els.invoiceMode.value = current === "all" ? "all" : "none";
    }
    if (els.invoiceList) {
      els.invoiceList.innerHTML = invoiceRows.length
        ? '<table class="obc-invoice-table"><thead><tr>' +
          "<th></th><th>Invoice No.</th><th>Invoice Date</th><th>Invoice Amount</th>" +
          "<th>Contact Person</th><th>Received</th><th>Outstanding</th>" +
          "</tr></thead><tbody>" +
          invoiceRows
            .map(function (inv) {
              const checked = mode === "all" || selected.has(String(inv.invoice_id));
              const dateText = formatIsoDate(inv.invoice_date);
              const contact = String(inv.contact_person || "").trim();
              return (
                "<tr>" +
                '<td><input type="checkbox" name="InvoiceIDs" value="' +
                escapeHtml(inv.invoice_id) +
                '"' +
                (checked ? " checked" : "") +
                "></td>" +
                '<td data-invoice-id="' +
                escapeHtml(inv.invoice_id) +
                '">' +
                escapeHtml(inv.invoice_no || "Invoice") +
                ' <strong class="obc-alloc-amt"></strong></td>' +
                "<td>" + escapeHtml(dateText || "—") + "</td>" +
                "<td>" + moneyLabel(inv.invoice_amount) + "</td>" +
                "<td>" + escapeHtml(contact || "—") + "</td>" +
                "<td>" + moneyLabel(inv.received_amount) + "</td>" +
                "<td>" + moneyLabel(inv.outstanding_amount) + "</td>" +
                "</tr>"
              );
            })
            .join("") +
          "</tbody></table>"
        : "";
    }
    if (els.invoiceListWrap) {
      els.invoiceListWrap.classList.toggle("d-none", !invoiceRows.length || mode === "none");
    }
    syncInvoiceModeField();
    paintAllocation();
  }

  function paintAllocation() {
    const mode = syncInvoiceModeField();
    paintInvoicePicker();
    syncCategoryFromInvoices();
    if (els.invoiceHint) {
      if (mode === "none") {
        els.invoiceHint.textContent =
          "No Invoice keeps this as a normal transfer. Invoice balances are not changed.";
      } else if (mode === "all") {
        els.invoiceHint.textContent =
          "All Invoices adjusts the oldest outstanding invoices first, up to the payment amount. Anything above that stays as customer advance.";
      } else {
        els.invoiceHint.textContent =
          "Only the ticked invoices are adjusted, oldest outstanding first. Anything above that stays as customer advance.";
      }
    }
    if (!els.allocationPreview) return;
    if (mode === "none") {
      els.allocationPreview.innerHTML = "";
      if (els.invoiceListWrap) els.invoiceListWrap.classList.add("d-none");
      return;
    }
    if (els.invoiceListWrap) els.invoiceListWrap.classList.remove("d-none");
    const chosen = oldestFirst(
      mode === "all"
        ? invoiceRows
        : invoiceRows.filter(function (inv) {
            return checkedInvoiceIds().indexOf(String(inv.invoice_id)) >= 0;
          })
    );
    const allocatedById = {};
    let outstanding = 0;
    chosen.forEach(function (inv) {
      outstanding += Number(inv.outstanding_amount || 0);
    });
    let payment = Number(els.amount && els.amount.value ? els.amount.value : 0);
    if (!Number.isFinite(payment) || payment < 0) payment = 0;
    let remaining = payment;
    chosen.forEach(function (inv) {
      const room = Number(inv.outstanding_amount || 0);
      const take = Math.min(remaining, room);
      allocatedById[String(inv.invoice_id)] = take > 0.0001 ? take : 0;
      remaining -= take;
    });
    if (els.invoiceList) {
      els.invoiceList.querySelectorAll("[data-invoice-id]").forEach(function (node) {
        const take = allocatedById[node.getAttribute("data-invoice-id")] || 0;
        const label = node.querySelector(".obc-alloc-amt");
        if (label) label.textContent = take > 0.0001 ? " Allocated " + moneyLabel(take) : "";
      });
    }
    const allocated = payment - remaining;
    const spare = remaining > 0.009 ? remaining : 0;
    let advanceKept = 0;
    if (mode !== "all") {
      const chosenIds = {};
      chosen.forEach(function (inv) {
        chosenIds[String(inv.invoice_id)] = true;
      });
      reservedAdvances.forEach(function (item) {
        if (chosenIds[String(item.invoice_id)]) return;
        advanceKept += Number(item.allocated_amount || 0);
      });
      if (advanceKept > spare) advanceKept = spare;
    }
    const unallocated = spare - (advanceKept > 0.009 ? advanceKept : 0);
    let html =
      "<div>Payment Amount: <strong>" + moneyLabel(payment) + "</strong></div>" +
      "<div>Total Invoice Outstanding: <strong>" + moneyLabel(outstanding) + "</strong></div>" +
      "<div>Total Allocated: <strong>" + moneyLabel(allocated) + "</strong></div>";
    if (advanceKept > 0.009) {
      html +=
        "<div>Already applied to later invoices: <strong>" +
        moneyLabel(advanceKept) +
        "</strong></div>";
    }
    html +=
      "<div>Remaining Unallocated: <strong>" +
      moneyLabel(unallocated > 0.009 ? unallocated : 0) +
      "</strong></div>";
    els.allocationPreview.innerHTML = html;
  }

  async function loadCustomerInvoices(customerId, restore) {
    invoiceRows = [];
    customerLedgerKey = "";
    if (!customerId) {
      reservedAdvances = [];
      renderInvoiceChoices("none", []);
      return;
    }
    const url = new URL(window.OBC_API.customerInvoices, window.location.origin);
    url.searchParams.set("customer_id", String(customerId));
    if (els.entryId && els.entryId.value) url.searchParams.set("entry_id", els.entryId.value);
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" }, credentials: "same-origin" });
    const data = await parseJsonResponse(res);
    invoiceRows = data.invoices || [];
    customerLedgerKey = data.customer_ledger_key || "";
    reservedAdvances = restore && restore.advances ? restore.advances : [];
    const mode = restore && restore.mode ? restore.mode : "none";
    const ids = restore && restore.ids ? restore.ids : [];
    renderInvoiceChoices(mode, ids);
  }

  async function restoreInvoiceLink(row) {
    clearInvoiceLink();
    const party = creditParty();
    const savedId = row && row.customer_id ? String(row.customer_id) : "";
    const customerId = party ? party.id : savedId;
    if (!customerId) return;
    customerFromCredit = !!party;
    if (els.customerId) els.customerId.value = customerId;
    if (els.customerSearch) {
      els.customerSearch.value = party
        ? (party.name || "")
        : (row.customer_name || ("Customer #" + customerId));
    }
    const sameCustomer = !party || party.id === savedId;
    const ids = sameCustomer
      ? (row.allocations || []).map(function (item) { return item.invoice_id; })
      : [];
    if (sameCustomer && !ids.length && row.invoice_id) ids.push(row.invoice_id);
    await loadCustomerInvoices(customerId, {
      mode: sameCustomer ? (row.invoice_mode || (ids.length ? "selected" : "none")) : "none",
      ids: ids,
      advances: sameCustomer ? (row.advance_allocations || []) : [],
    });
  }

  async function saveEntry() {
    if (!els.form.checkValidity()) {
      els.form.reportValidity();
      return;
    }
    if (isOtherPurpose() && String(els.remarks?.value || "").trim().length < 10) {
      alert("If you select Other, the Remarks field is required.");
      els.remarks?.focus();
      return;
    }
    const linkMode = syncInvoiceModeField();
    if (linkMode !== "none" && !String(els.customerId?.value || "").trim()) {
      alert("Select a customer before linking invoices.");
      return;
    }
    if (linkMode === "selected" && !checkedInvoiceIds().length) {
      alert("Select at least one invoice.");
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
      if (returnAfterListedReceipt(invoiceReceiptLaunch)) return;
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
      if (!(await JTCSDialog.confirm("Delete this double-entry transaction?"))) return;
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

  let customerTimer = null;
  els.creditAccount?.addEventListener("change", function () {
    const party = creditParty();
    if (party) {
      applyCreditParty(party).catch(function (err) {
        alert(err.message || "Unable to load this customer's invoices.");
      });
      return;
    }
    if (!customerFromCredit) return;
    customerFromCredit = false;
    if (els.customerId) els.customerId.value = "";
    if (els.customerSearch) els.customerSearch.value = "";
    invoiceRows = [];
    customerLedgerKey = "";
    reservedAdvances = [];
    renderInvoiceChoices("none", []);
  });
  els.customerSearch?.addEventListener("input", function () {
    const party = creditParty();
    if (party) {
      customerFromCredit = true;
      if (els.customerId) els.customerId.value = party.id;
      if (els.customerSearch) els.customerSearch.value = party.name || "";
      if (els.customerSuggest) els.customerSuggest.classList.add("d-none");
      return;
    }
    customerFromCredit = false;
    if (els.customerId) els.customerId.value = "";
    invoiceRows = [];
    customerLedgerKey = "";
    reservedAdvances = [];
    renderInvoiceChoices("none", []);
    clearTimeout(customerTimer);
    const q = els.customerSearch.value.trim();
    customerTimer = setTimeout(function () {
      if (q.length < 2) {
        if (els.customerSuggest) els.customerSuggest.classList.add("d-none");
        return;
      }
      const url = new URL(window.OBC_API.customers, window.location.origin);
      url.searchParams.set("q", q);
      fetch(url.toString(), { headers: { Accept: "application/json" }, credentials: "same-origin" })
        .then(function (res) { return res.json(); })
        .then(function (data) {
          if (!els.customerSuggest) return;
          els.customerSuggest.innerHTML = "";
          (data.rows || []).forEach(function (row) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "list-group-item list-group-item-action py-1";
            btn.textContent = row.customer_name + (row.mobile ? " · " + row.mobile : "");
            btn.addEventListener("click", function () {
              if (els.customerId) els.customerId.value = String(row.customer_id);
              if (els.customerSearch) els.customerSearch.value = row.customer_name || "";
              els.customerSuggest.classList.add("d-none");
              loadCustomerInvoices(row.customer_id).catch(function (err) {
                alert(err.message || "Unable to load invoices.");
              });
            });
            els.customerSuggest.appendChild(btn);
          });
          els.customerSuggest.classList.toggle("d-none", !(data.rows || []).length);
        })
        .catch(function () { /* search stays optional */ });
    }, 250);
  });
  els.invoicePickerBtn?.addEventListener("click", function () {
    if (!els.invoicePickerMenu) return;
    const open = els.invoicePickerMenu.classList.toggle("d-none") === false;
    els.invoicePickerBtn.setAttribute("aria-expanded", open ? "true" : "false");
  });
  els.invoicePickerMenu?.addEventListener("click", function (event) {
    const item = event.target.closest("[data-value]");
    if (!item || !els.invoiceMode) return;
    els.invoiceMode.value = item.getAttribute("data-value") || "none";
    els.invoicePickerMenu.classList.add("d-none");
    if (els.invoicePickerBtn) els.invoicePickerBtn.setAttribute("aria-expanded", "false");
    els.invoiceMode.dispatchEvent(new Event("change"));
  });
  document.addEventListener("click", function (event) {
    if (els.invoicePickerMenu && !els.invoicePickerMenu.classList.contains("d-none")) {
      if (!event.target.closest("#obcInvoicePicker")) {
        els.invoicePickerMenu.classList.add("d-none");
        if (els.invoicePickerBtn) els.invoicePickerBtn.setAttribute("aria-expanded", "false");
      }
    }
    if (els.creditSuggest && !event.target.closest("#obcCreditSearchWrap")) {
      els.creditSuggest.classList.add("d-none");
    }
    if (els.debitSuggest && !event.target.closest("#obcDebitSearchWrap")) {
      els.debitSuggest.classList.add("d-none");
    }
  });
  bindAccountSearch(els.creditSearch, els.creditSuggest, els.creditAccount, true);
  bindAccountSearch(els.debitSearch, els.debitSuggest, els.debitAccount, false);
  els.invoiceMode?.addEventListener("change", function () {
    const value = els.invoiceMode.value;
    const boxes = els.invoiceList
      ? els.invoiceList.querySelectorAll('input[name="InvoiceIDs"]')
      : [];
    if (value === "none") {
      boxes.forEach(function (box) { box.checked = false; });
    } else if (value === "all") {
      boxes.forEach(function (box) { box.checked = true; });
    } else if (value !== "selected") {
      boxes.forEach(function (box) { box.checked = String(box.value) === String(value); });
    }
    paintAllocation();
  });
  els.invoiceList?.addEventListener("change", function (ev) {
    if (!ev.target.matches || !ev.target.matches('input[name="InvoiceIDs"]')) return;
    const ids = checkedInvoiceIds();
    if (!ids.length) {
      els.invoiceMode.value = "none";
    } else if (ids.length === invoiceRows.length && invoiceRows.length) {
      els.invoiceMode.value = "all";
    } else if (ids.length === 1) {
      els.invoiceMode.value = ids[0];
    } else if (els.invoiceMode.querySelector('option[value="selected"]') == null) {
      const option = document.createElement("option");
      option.value = "selected";
      option.textContent = "Selected invoices (" + ids.length + ")";
      els.invoiceMode.insertBefore(option, els.invoiceMode.options[2] || null);
      els.invoiceMode.value = "selected";
    } else {
      els.invoiceMode.querySelector('option[value="selected"]').textContent =
        "Selected invoices (" + ids.length + ")";
      els.invoiceMode.value = "selected";
    }
    paintAllocation();
  });
  els.amount?.addEventListener("input", paintAllocation);

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
  if (els.maximizeBtn) {
    els.maximizeBtn.addEventListener("click", function () {
      setModalMaximized(!modalMaximized);
    });
  }
  if (els.modalEl) {
    els.modalEl.addEventListener("hidden.bs.modal", function () {
      setModalMaximized(false);
    });
  }
  if (els.workDate) {
    els.workDate.addEventListener("change", function () {
      refreshVoucher().catch(function () {});
    });
  }
  if (els.purpose) {
    els.purpose.addEventListener("change", syncOtherRemarksUi);
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

  function receiptLaunchParams() {
    if (window.JtcsInvoiceReceiptReturn) {
      return window.JtcsInvoiceReceiptReturn.receiptLaunchFromSearch(window.location.search || "");
    }
    const params = new URLSearchParams(window.location.search || "");
    if (params.get("receipt") !== "1") return null;
    const customerId = (params.get("customer_id") || "").trim();
    if (!customerId) return null;
    return {
      customerId: customerId,
      customerName: (params.get("customer_name") || "").replace(/\s+/g, " ").trim(),
      invoiceId: (params.get("invoice_id") || "").trim(),
      amount: (params.get("amount") || "").trim(),
      origin: "",
      returnTo: "",
    };
  }

  async function resolveCreditCustomer(launch) {
    const term = launch.customerName || launch.customerId;
    if (window.OBC_API.accountSearch && term) {
      const url = new URL(window.OBC_API.accountSearch, window.location.origin);
      url.searchParams.set("q", term);
      url.searchParams.set("side", "credit");
      url.searchParams.set("limit", "30");
      const res = await fetch(url.toString(), {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      const data = await res.json();
      const match = (data.rows || []).find(function (row) {
        return String(row.customer_id || "") === String(launch.customerId);
      });
      if (match) return match;
    }
    const name = launch.customerName || ("Customer #" + launch.customerId);
    return {
      ledger_key: "customer-" + launch.customerId,
      title: name,
      label: name,
      customer_id: launch.customerId,
      customer_name: launch.customerName || name,
    };
  }

  async function openReceiptFromInvoice(launch) {
    await openNew();
    if (launch && launch.origin) invoiceReceiptLaunch = launch;
    const row = await resolveCreditCustomer(launch);
    setLedgerSelection(els.creditAccount, els.creditSearch, row);
    const partyName = row.customer_name || launch.customerName || row.title || "";
    await applyCreditParty({
      id: String(row.customer_id || launch.customerId),
      name: partyName,
    });
    const current = (invoiceRows || []).find(function (inv) {
      return String(inv.invoice_id) === String(launch.invoiceId);
    });
    const prefill = current && current.outstanding != null && current.outstanding !== ""
      ? current.outstanding
      : launch.amount;
    if (els.amount && prefill !== "" && prefill != null) els.amount.value = prefill;
    if (
      launch.invoiceId &&
      els.invoiceMode &&
      els.invoiceMode.querySelector('option[value="' + launch.invoiceId + '"]')
    ) {
      els.invoiceMode.value = launch.invoiceId;
      els.invoiceMode.dispatchEvent(new Event("change"));
    }
    try {
      const host = window.frameElement && window.frameElement.closest(".jtcs-page-win");
      const title = host && host.querySelector(".jtcs-page-win-title");
      if (title) title.textContent = "Money In-Out Receipt";
    } catch (_err) {
      /* standalone page has no page-window title */
    }
  }

  loadGrid()
    .then(function () {
      const api = window.JtcsInvoiceReceiptReturn;
      if (api) {
        let stored = "";
        try {
          stored = sessionStorage.getItem(api.PENDING_KEY) || "";
          sessionStorage.removeItem(api.PENDING_KEY);
        } catch (_err) {
          stored = "";
        }
        const search = window.location.search || "";
        const pending = api.readPendingReturn(stored, search, Date.now());
        if (pending) {
          api.performListedReturn(pending, receiptReturnHost());
          return;
        }
        if (api.shouldOpenReceiptOnLoad(search)) {
          const launched = receiptLaunchParams();
          if (launched) return openReceiptFromInvoice(launched);
          return;
        }
        if (new URLSearchParams(search).get("receipt_return") === "1") return;
      }
      const launch = receiptLaunchParams();
      if (launch) return openReceiptFromInvoice(launch);
      var autoId = parseInt(window.OBC_AUTO_LOAD_ENTRY_ID, 10);
      if (!Number.isNaN(autoId) && autoId > 0) {
        return openEdit(autoId);
      }
    })
    .catch(function () {});
})();
