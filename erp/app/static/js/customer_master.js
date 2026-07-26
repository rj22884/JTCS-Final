(function () {
  "use strict";

  const els = {
    addBtn: document.getElementById("cmAddBtn"),
    editBtn: document.getElementById("cmEditBtn"),
    deleteBtn: document.getElementById("cmDeleteBtn"),
    newBtn: document.getElementById("cmNewBtn"),
    refreshBtn: document.getElementById("cmRefreshBtn"),
    search: document.getElementById("cmSearch"),
    filterGroup: document.getElementById("cmFilterGroup"),
    filterStatus: document.getElementById("cmFilterStatus"),
    count: document.getElementById("cmCount"),
    status: document.getElementById("cmStatus"),
    gridBody: document.getElementById("cmGridBody"),
    empty: document.getElementById("cmEmpty"),
    modalEl: document.getElementById("cmEntryModal"),
    modalTitle: document.getElementById("cmEntryModalTitle"),
    form: document.getElementById("cmEntryForm"),
    customerId: document.getElementById("cm_customer_id"),
    displayId: document.getElementById("cm_display_customer_id"),
    customerGroup: document.getElementById("cm_customer_group"),
    tabNav: document.getElementById("cmTabNav"),
    formPanels: document.getElementById("cmFormPanels"),
    formError: document.getElementById("cmFormError"),
    saveBtn: document.getElementById("cmSaveBtn"),
    mobileDupPanel: document.getElementById("cmMobileDupPanel"),
    mobileDupList: document.getElementById("cmMobileDupList"),
    duplicateModalEl: document.getElementById("cmDuplicateModal"),
    duplicateMessage: document.getElementById("cmDuplicateMessage"),
    duplicateDetails: document.getElementById("cmDuplicateDetails"),
    duplicateEditYes: document.getElementById("cmDuplicateEditYes"),
    duplicateEditNo: document.getElementById("cmDuplicateEditNo"),
    syncIncomeTaxBtn: document.getElementById("cmSyncIncomeTaxBtn"),
    syncAadhaarBtn: document.getElementById("cmSyncAadhaarBtn"),
    syncGstBtn: document.getElementById("cmSyncGstBtn"),
    itPortalLoginBtn: document.getElementById("cmItPortalLoginBtn"),
    syncStatus: document.getElementById("cmSyncStatus"),
    itSyncModalEl: document.getElementById("cmItSyncModal"),
    itUserId: document.getElementById("cmItUserId"),
    itPassword: document.getElementById("cmItPassword"),
    itSyncError: document.getElementById("cmItSyncError"),
    itSyncSaveBtn: document.getElementById("cmItSyncSaveBtn"),
    itHelperModalEl: document.getElementById("cmItPortalHelperModal"),
    itHelperUserId: document.getElementById("cmItHelperUserId"),
    itHelperPassword: document.getElementById("cmItHelperPassword"),
    itCopyUserBtn: document.getElementById("cmItCopyUserBtn"),
    itCopyPassBtn: document.getElementById("cmItCopyPassBtn"),
    itOpenPortalBtn: document.getElementById("cmItOpenPortalBtn"),
    aadhaarSyncModalEl: document.getElementById("cmAadhaarSyncModal"),
    aadhaarSyncNumber: document.getElementById("cmAadhaarSyncNumber"),
    aadhaarSyncError: document.getElementById("cmAadhaarSyncError"),
    aadhaarStepAsk: document.getElementById("cmAadhaarStepAsk"),
    aadhaarStepPortal: document.getElementById("cmAadhaarStepPortal"),
    aadhaarContinueBtn: document.getElementById("cmAadhaarContinueBtn"),
    aadhaarApplyBtn: document.getElementById("cmAadhaarApplyBtn"),
    aadhaarOpenPortalBtn: document.getElementById("cmAadhaarOpenPortalBtn"),
    aadhaarCopyBtn: document.getElementById("cmAadhaarCopyBtn"),
    aadhaarReadyHint: document.getElementById("cmAadhaarReadyHint"),
    aadhaarSyncName: document.getElementById("cmAadhaarSyncName"),
    aadhaarSyncDob: document.getElementById("cmAadhaarSyncDob"),
    aadhaarSyncGender: document.getElementById("cmAadhaarSyncGender"),
    aadhaarSyncAddress: document.getElementById("cmAadhaarSyncAddress"),
  };

  if (!els.gridBody || !window.CM_API) return;

  const modal = els.modalEl ? new bootstrap.Modal(els.modalEl) : null;
  const duplicateModal = els.duplicateModalEl ? new bootstrap.Modal(els.duplicateModalEl) : null;
  const itSyncModal = els.itSyncModalEl ? new bootstrap.Modal(els.itSyncModalEl) : null;
  const itHelperModal = els.itHelperModalEl ? new bootstrap.Modal(els.itHelperModalEl) : null;
  const aadhaarSyncModal = els.aadhaarSyncModalEl ? new bootstrap.Modal(els.aadhaarSyncModalEl) : null;
  const portals = window.CM_PORTALS || {};
  let itCredentials = { userId: "", password: "" };
  let aadhaarSyncValue = "";
  const groupTabs = window.CM_GROUP_TABS || {};
  const tabLabels = window.CM_TAB_LABELS || {};
  const mandatoryFields = new Set(window.CM_MANDATORY || []);
  const otherMandatoryFields = new Set(window.CM_OTHER_MANDATORY || ["customer_name"]);
  const otherCustomerType = String(window.CM_OTHER_TYPE || "Other");
  const placeholderPan = String(window.CM_PLACEHOLDER_PAN || "PANNOTAVBL");
  let rows = window.CM_INITIAL_ROWS || [];
  let selectedId = null;
  let activeTab = "basic";
  let pendingDuplicateCustomerId = null;
  let mobileDuplicatesVisible = false;

  function isOtherCustomerType() {
    const typeField = document.getElementById("cm_customer_type");
    return String(typeField?.value || "").trim().toLowerCase() === otherCustomerType.toLowerCase();
  }

  function activeMandatoryFields() {
    return isOtherCustomerType() ? otherMandatoryFields : mandatoryFields;
  }

  function syncMandatoryMarkers() {
    const required = activeMandatoryFields();
    const otherMode = isOtherCustomerType();
    els.form?.querySelectorAll("[data-master-required='1']").forEach(function (field) {
      const key = field.dataset.cmField || "";
      const wrap = field.closest(".cm-field-wrap");
      const label = wrap?.querySelector(".form-label");
      const must = required.has(key);
      if (label) label.classList.toggle("cm-required", must);
      field.classList.toggle("cm-other-optional", otherMode && !must);
    });
    const nameLabel = document.querySelector('label[for="cm_customer_name"]');
    if (nameLabel) nameLabel.classList.add("cm-required");
  }

  function syncFilingFrequencyVisibility() {
    const wraps = [
      document.getElementById("cmFilingFrequencyWrap"),
      document.getElementById("cmFilingFrequencyWrapTds"),
    ].filter(Boolean);
    if (!wraps.length) return;
    let hasGst = false;
    els.form?.querySelectorAll('[data-cm-field="gst_number"]').forEach(function (field) {
      if (String(field.value || "").trim()) hasGst = true;
    });
    wraps.forEach(function (wrap) {
      wrap.classList.toggle("d-none", !hasGst);
      if (!hasGst) {
        const freq = wrap.querySelector('[data-cm-field="filing_frequency"]');
        if (freq) freq.value = "";
      }
    });
  }

  function apiUrl(template, id) {
    return String(template || "").replace(/\/0(?=$|\/)/, "/" + String(id));
  }

  function csrfToken() {
    return window.CM_CSRF || "";
  }

  function escapeHtml(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function hideMobileDupPanel() {
    mobileDuplicatesVisible = false;
    if (els.mobileDupPanel) els.mobileDupPanel.classList.add("d-none");
    if (els.mobileDupList) els.mobileDupList.innerHTML = "";
  }

  function showMobileDupPanel(duplicates) {
    if (!els.mobileDupPanel || !els.mobileDupList) return;
    const list = duplicates || [];
    if (!list.length) {
      hideMobileDupPanel();
      return;
    }
    mobileDuplicatesVisible = true;
    els.mobileDupList.innerHTML = list.map(function (item) {
      return (
        "<li>" +
        '<div class="cm-dup-name">' + escapeHtml(item.customer_name || "—") + "</div>" +
        '<div class="cm-dup-pan">PAN: ' + escapeHtml(item.pan_number || "—") + "</div>" +
        "</li>"
      );
    }).join("");
    els.mobileDupPanel.classList.remove("d-none");
  }

  function duplicateDetailsHtml(dup) {
    if (!dup) return "";
    return (
      "<dl class=\"mb-0\">" +
      "<dt>Customer ID</dt><dd>" + escapeHtml(dup.customer_id) + "</dd>" +
      "<dt>Customer Name</dt><dd>" + escapeHtml(dup.customer_name || "—") + "</dd>" +
      "<dt>PAN</dt><dd>" + escapeHtml(dup.pan_number || "—") + "</dd>" +
      "<dt>Mobile</dt><dd>" + escapeHtml(dup.mobile_number || "—") + "</dd>" +
      "<dt>Group</dt><dd>" + escapeHtml(dup.customer_group || "—") + "</dd>" +
      "</dl>"
    );
  }

  function showDuplicateModal(type, duplicate, message) {
    pendingDuplicateCustomerId = duplicate ? duplicate.customer_id : null;
    const label = type === "aadhaar_number" ? "Aadhaar" : "PAN";
    if (els.duplicateMessage) {
      els.duplicateMessage.textContent = message || (label + " already exists in Customer Master.");
    }
    if (els.duplicateDetails) {
      els.duplicateDetails.innerHTML = duplicateDetailsHtml(duplicate);
    }
    duplicateModal?.show();
  }

  function getCustomerIdForCheck() {
    const raw = els.customerId?.value;
    if (!raw) return null;
    const id = parseInt(raw, 10);
    return Number.isFinite(id) && id > 0 ? id : null;
  }

  function checkDuplicatesRemote(fields) {
    if (!window.CM_API.checkDuplicates) return Promise.resolve(null);
    const params = new URLSearchParams();
    const customerId = getCustomerIdForCheck();
    if (customerId) params.set("customer_id", String(customerId));
    if (fields.pan != null) params.set("pan", fields.pan);
    if (fields.aadhaar != null) params.set("aadhaar", fields.aadhaar);
    if (fields.mobile != null) params.set("mobile", fields.mobile);
    const url = window.CM_API.checkDuplicates + "?" + params.toString();
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Duplicate check failed.");
        return data;
      });
  }

  function handleFieldDuplicateCheck(fieldName) {
    const field = document.getElementById("cm_" + fieldName);
    if (!field) return;
    const value = (field.value || "").trim();
    if (!value) return;
    const payload = {};
    if (fieldName === "pan_number") payload.pan = value;
    if (fieldName === "aadhaar_number") payload.aadhaar = value;
    if (fieldName === "mobile_number") payload.mobile = value;
    checkDuplicatesRemote(payload)
      .then(function (data) {
        if (!data) return;
        if (fieldName === "pan_number" && data.pan_duplicate) {
          showDuplicateModal("pan_number", data.pan_duplicate,
            "This PAN is already registered with another customer.");
          field.classList.add("cm-field-error");
          return;
        }
        if (fieldName === "aadhaar_number" && data.aadhaar_duplicate) {
          showDuplicateModal("aadhaar_number", data.aadhaar_duplicate,
            "This Aadhaar is already registered with another customer.");
          field.classList.add("cm-field-error");
          return;
        }
        if (fieldName === "mobile_number") {
          showMobileDupPanel(data.mobile_duplicates || []);
          if ((data.mobile_duplicates || []).length) {
            field.classList.add("cm-field-error");
          } else {
            field.classList.remove("cm-field-error");
          }
        }
      })
      .catch(function () { /* ignore background check errors */ });
  }

  function showStatus(message, type) {
    if (!els.status) return;
    if (!message) {
      els.status.classList.add("d-none");
      return;
    }
    els.status.textContent = message;
    els.status.className = "alert py-2 small mb-3 alert-" + (type || "success");
    els.status.classList.remove("d-none");
  }

  function setSelected(id) {
    selectedId = id || null;
    const row = rows.find(function (r) { return r.customer_id === selectedId; });
    const has = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !has;
    if (els.deleteBtn) els.deleteBtn.disabled = !has || (row && row.customer_status === "Inactive");
    els.gridBody.querySelectorAll("tr").forEach(function (tr) {
      tr.classList.toggle("table-active", tr.dataset.id === String(selectedId));
    });
  }

  function renderGrid(data) {
    rows = data || [];
    if (!rows.length) {
      els.gridBody.innerHTML = "";
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      setSelected(null);
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    els.gridBody.innerHTML = rows.map(function (row) {
      const inactive = row.customer_status === "Inactive";
      const delBtn = inactive
        ? '<button type="button" class="btn btn-outline-secondary btn-sm" disabled><i class="bi bi-trash"></i></button>'
        : '<button type="button" class="btn btn-outline-danger btn-sm cm-row-delete" data-id="' + row.customer_id + '"><i class="bi bi-trash"></i></button>';
      const badge = inactive
        ? '<span class="badge bg-secondary">Inactive</span>'
        : '<span class="badge bg-success">Active</span>';
      return (
        "<tr data-id=\"" + row.customer_id + "\">" +
        "<td>" + row.customer_id + "</td>" +
        "<td><strong>" + escapeHtml(row.customer_name) + "</strong></td>" +
        "<td>" + escapeHtml(row.customer_group || "—") + "</td>" +
        "<td>" + escapeHtml(row.mobile_number || "—") + "</td>" +
        "<td>" + escapeHtml(row.pan_number || "—") + "</td>" +
        "<td>" + escapeHtml(row.email_id || "—") + "</td>" +
        "<td>" + escapeHtml(row.city || "—") + "</td>" +
        "<td>" + badge + "</td>" +
        '<td class="text-end cm-actions">' +
        '<button type="button" class="btn btn-outline-primary btn-sm cm-row-edit" data-id="' + row.customer_id + '"><i class="bi bi-pencil"></i></button> ' +
        delBtn +
        "</td></tr>"
      );
    }).join("");
    setSelected(selectedId);
  }

  function loadGrid() {
    const params = new URLSearchParams();
    const search = (els.search?.value || "").trim();
    const grp = (els.filterGroup?.value || "").trim();
    const status = (els.filterStatus?.value || "").trim();
    if (search) params.set("search", search);
    if (grp) params.set("customer_group", grp);
    if (status) params.set("status", status);
    const url = window.CM_API.list + (params.toString() ? "?" + params.toString() : "");
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to load customers.");
        renderGrid(data.rows);
      })
      .catch(function (err) {
        showStatus(err.message, "danger");
      });
  }

  function buildTabs(groupCode) {
    const tabs = groupTabs[groupCode] || [];
    if (!els.tabNav) return;
    els.tabNav.innerHTML = tabs.map(function (tab, idx) {
      return (
        '<li class="nav-item" role="presentation">' +
        '<button type="button" class="nav-link' + (idx === 0 ? " active" : "") + '" data-tab="' + tab + '">' +
        escapeHtml(tabLabels[tab] || tab) +
        "</button></li>"
      );
    }).join("");
    activeTab = tabs[0] || "basic";
    showTabPanel(activeTab, tabs);
  }

  function showTabPanel(tabKey, visibleTabs) {
    const allowed = visibleTabs || groupTabs[els.customerGroup?.value] || [];
    els.formPanels?.querySelectorAll(".cm-tab-panel").forEach(function (panel) {
      const key = panel.dataset.tab;
      const show = allowed.includes(key) && key === tabKey;
      panel.classList.toggle("d-none", !show);
    });
    els.tabNav?.querySelectorAll(".nav-link").forEach(function (btn) {
      btn.classList.toggle("active", btn.dataset.tab === tabKey);
    });
    activeTab = tabKey;
  }

  function setFieldValue(fieldName, value) {
    const field = document.getElementById("cm_" + fieldName);
    if (!field || value == null || value === "") return;
    field.value = value;
  }

  function getFieldValue(fieldName) {
    const field = document.getElementById("cm_" + fieldName);
    return field ? String(field.value || "").trim() : "";
  }

  function setSyncStatus(message, isError) {
    if (!els.syncStatus) return;
    if (!message) {
      els.syncStatus.classList.add("d-none");
      els.syncStatus.textContent = "";
      els.syncStatus.classList.remove("text-danger", "text-success");
      return;
    }
    els.syncStatus.textContent = message;
    els.syncStatus.classList.remove("d-none", "text-muted", "text-danger", "text-success");
    els.syncStatus.classList.add(isError ? "text-danger" : "text-success");
  }

  function updateItPortalLoginVisibility() {
    if (!els.itPortalLoginBtn) return;
    const ready = !!(itCredentials.userId && itCredentials.password);
    els.itPortalLoginBtn.classList.toggle("d-none", !ready);
  }

  function resetSyncState() {
    itCredentials = { userId: "", password: "" };
    aadhaarSyncValue = "";
    updateItPortalLoginVisibility();
    setSyncStatus("");
  }

  function copyText(value) {
    const text = String(value || "");
    if (!text) return Promise.reject(new Error("Nothing to copy."));
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    return new Promise(function (resolve, reject) {
      const input = document.createElement("textarea");
      input.value = text;
      document.body.appendChild(input);
      input.select();
      try {
        document.execCommand("copy");
        resolve();
      } catch (err) {
        reject(err);
      } finally {
        input.remove();
      }
    });
  }

  function applyPortalDataToForm(data) {
    if (!data || typeof data !== "object") return 0;
    let count = 0;
    Object.keys(data).forEach(function (key) {
      const value = data[key];
      if (value == null || String(value).trim() === "") return;
      const field = document.getElementById("cm_" + key);
      if (!field) return;
      field.value = value;
      count += 1;
    });
    return count;
  }

  function pollIncomeTaxJob(jobId) {
    const statusUrl = (window.CM_API && window.CM_API.incomeTaxPortalStatus) || "";
    if (!statusUrl || !jobId) return;
    let tries = 0;
    const maxTries = 120; // ~4 minutes @ 2s
    const timer = setInterval(function () {
      tries += 1;
      fetch(statusUrl + "?job_id=" + encodeURIComponent(jobId), {
        headers: { Accept: "application/json" },
      })
        .then(function (res) {
          return res.json();
        })
        .then(function (payload) {
          if (!payload.ok || !payload.job) return;
          const job = payload.job;
          if (job.message) setSyncStatus(job.message, job.status === "error");
          if (job.status === "running") return;
          clearInterval(timer);
          if (job.status === "done") {
            const n = applyPortalDataToForm(job.data || {});
            setSyncStatus(
              (job.message || "Sync complete.") +
                (n ? " Applied " + n + " field(s) to form." : "")
            );
            itHelperModal?.hide();
          } else if (job.status === "error") {
            setSyncStatus(job.message || "Income Tax sync failed.", true);
          }
        })
        .catch(function () {
          if (tries >= maxTries) clearInterval(timer);
        });
      if (tries >= maxTries) {
        clearInterval(timer);
        setSyncStatus("Sync wait timed out — you can still fill form manually.", true);
      }
    }, 2000);
  }

  function openIncomeTaxPortal() {
    const url = portals.incomeTaxLogin || "https://eportal.incometax.gov.in/iec/foservices/#/login";
    const apiUrlLogin = (window.CM_API && window.CM_API.incomeTaxPortalLogin) || "";
    if (!apiUrlLogin) {
      window.open(url, "cmIncomeTaxPortal", "noopener,noreferrer,width=1100,height=800");
      return Promise.resolve();
    }
    if (els.itOpenPortalBtn) els.itOpenPortalBtn.disabled = true;
    setSyncStatus("Opening Income Tax portal, filling PAN/password, enabling Continue...");
    return fetch(apiUrlLogin, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({
        user_id: itCredentials.userId,
        password: itCredentials.password,
      }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) {
            throw new Error(data.error || "Unable to open portal with PAN fill.");
          }
          return data;
        });
      })
      .then(function (data) {
        setSyncStatus(data.message || "Portal opened.");
        if (data.job_id) pollIncomeTaxJob(data.job_id);
      })
      .catch(function (err) {
        copyText(itCredentials.userId).catch(function () {});
        window.open(url, "cmIncomeTaxPortal", "noopener,noreferrer,width=1100,height=800");
        setSyncStatus(
          (err && err.message ? err.message + " — " : "") +
            "Fallback: portal opened; PAN copied — paste in User ID box.",
          true
        );
      })
      .finally(function () {
        if (els.itOpenPortalBtn) els.itOpenPortalBtn.disabled = false;
      });
  }

  function openAadhaarPortal() {
    const url = portals.aadhaarPortal || "https://myaadhaar.uidai.gov.in/";
    window.open(url, "cmAadhaarPortal", "noopener,noreferrer,width=1100,height=800");
  }

  function openItCredentialsModal() {
    if (els.itSyncError) {
      els.itSyncError.classList.add("d-none");
      els.itSyncError.textContent = "";
    }
    if (els.itUserId) {
      els.itUserId.value = itCredentials.userId || getFieldValue("pan_number") || "";
    }
    if (els.itPassword) {
      els.itPassword.value = itCredentials.password || getFieldValue("income_tax_password") || "";
    }
    itSyncModal?.show();
  }

  function saveItCredentials() {
    const userId = (els.itUserId?.value || "").trim().toUpperCase();
    const password = els.itPassword?.value || "";
    if (!userId || userId.length < 5) {
      if (els.itSyncError) {
        els.itSyncError.textContent = "Valid Income Tax User ID (PAN) is required.";
        els.itSyncError.classList.remove("d-none");
      }
      return;
    }
    if (!password) {
      if (els.itSyncError) {
        els.itSyncError.textContent = "Income Tax password is required.";
        els.itSyncError.classList.remove("d-none");
      }
      return;
    }
    itCredentials = { userId: userId, password: password };
    if (/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(userId)) {
      setFieldValue("pan_number", userId);
    }
    setFieldValue("income_tax_password", password);
    updateItPortalLoginVisibility();
    setSyncStatus("Income Tax credentials saved. Portal login button ready (red icon).");
    itSyncModal?.hide();
    showItPortalHelper();
  }

  function showItPortalHelper() {
    if (els.itHelperUserId) els.itHelperUserId.textContent = itCredentials.userId || "—";
    if (els.itHelperPassword) els.itHelperPassword.textContent = itCredentials.password ? "••••••••" : "—";
    itHelperModal?.show();
  }

  function resetAadhaarModal() {
    if (els.aadhaarSyncError) {
      els.aadhaarSyncError.classList.add("d-none");
      els.aadhaarSyncError.textContent = "";
    }
    els.aadhaarStepAsk?.classList.remove("d-none");
    els.aadhaarStepPortal?.classList.add("d-none");
    els.aadhaarContinueBtn?.classList.remove("d-none");
    els.aadhaarApplyBtn?.classList.add("d-none");
    if (els.aadhaarSyncNumber) {
      els.aadhaarSyncNumber.value = aadhaarSyncValue || getFieldValue("aadhaar_number") || "";
    }
    if (els.aadhaarSyncName) els.aadhaarSyncName.value = "";
    if (els.aadhaarSyncDob) els.aadhaarSyncDob.value = "";
    if (els.aadhaarSyncGender) els.aadhaarSyncGender.value = "";
    if (els.aadhaarSyncAddress) els.aadhaarSyncAddress.value = "";
    if (els.aadhaarReadyHint) els.aadhaarReadyHint.textContent = "";
  }

  function openAadhaarSyncModal() {
    resetAadhaarModal();
    aadhaarSyncModal?.show();
  }

  function continueAadhaarToPortal() {
    const aadhaar = (els.aadhaarSyncNumber?.value || "").replace(/\D/g, "");
    if (aadhaar.length !== 12) {
      if (els.aadhaarSyncError) {
        els.aadhaarSyncError.textContent = "Valid 12-digit Aadhaar number is required.";
        els.aadhaarSyncError.classList.remove("d-none");
      }
      return;
    }
    aadhaarSyncValue = aadhaar;
    setFieldValue("aadhaar_number", aadhaar);
    els.aadhaarStepAsk?.classList.add("d-none");
    els.aadhaarStepPortal?.classList.remove("d-none");
    els.aadhaarContinueBtn?.classList.add("d-none");
    els.aadhaarApplyBtn?.classList.remove("d-none");
    if (els.aadhaarReadyHint) {
      els.aadhaarReadyHint.textContent = "Aadhaar " + aadhaar + " ready — complete captcha on portal.";
    }
    copyText(aadhaar)
      .then(function () {
        setSyncStatus("Aadhaar copied. Portal opening — complete captcha, then apply details.");
      })
      .catch(function () {
        setSyncStatus("Aadhaar saved on form. Open portal and enter number, then captcha.");
      });
    openAadhaarPortal();
  }

  function applyAadhaarSyncToForm() {
    if (aadhaarSyncValue) setFieldValue("aadhaar_number", aadhaarSyncValue);
    const name = (els.aadhaarSyncName?.value || "").trim();
    const dob = els.aadhaarSyncDob?.value || "";
    const gender = els.aadhaarSyncGender?.value || "";
    const address = (els.aadhaarSyncAddress?.value || "").trim();
    if (name) setFieldValue("customer_name", name);
    if (dob) setFieldValue("date_of_birth", dob);
    if (gender) setFieldValue("gender", gender);
    if (address) setFieldValue("address_line1", address);
    setSyncStatus("Aadhaar details applied to customer form.");
    aadhaarSyncModal?.hide();
  }

  function clearForm() {
    resetSyncState();
    els.form?.querySelectorAll("[data-cm-field]").forEach(function (field) {
      if (field.tagName === "SELECT") {
        field.selectedIndex = 0;
      } else {
        field.value = "";
      }
      field.classList.remove("cm-field-error");
    });
    if (els.customerId) els.customerId.value = "";
    if (els.displayId) els.displayId.value = "";
    if (els.customerGroup) els.customerGroup.value = "";
    const statusField = document.getElementById("cm_customer_status");
    if (statusField) statusField.value = "Active";
    if (els.tabNav) els.tabNav.innerHTML = "";
    els.formPanels?.querySelectorAll(".cm-tab-panel").forEach(function (p) {
      p.classList.add("d-none");
    });
    if (els.formError) {
      els.formError.classList.add("d-none");
      els.formError.textContent = "";
    }
    hideMobileDupPanel();
    syncMandatoryMarkers();
    syncFilingFrequencyVisibility();
  }

  function fillForm(record) {
    clearForm();
    if (!record) return;
    if (els.customerId) els.customerId.value = record.customer_id || "";
    if (els.displayId) els.displayId.value = record.customer_id || "Auto";
    if (els.customerGroup) {
      els.customerGroup.value = record.customer_group || "";
      buildTabs(els.customerGroup.value);
    }
    els.form?.querySelectorAll("[data-cm-field]").forEach(function (field) {
      const key = field.dataset.cmField;
      if (!key || key === "customer_group") return;
      const val = record[key];
      if (val == null) return;
      if (field.type === "date") {
        field.value = String(val).slice(0, 10);
      } else {
        field.value = val;
      }
    });
    if (record.pan_number && record.income_tax_password) {
      itCredentials = {
        userId: String(record.pan_number || "").toUpperCase(),
        password: String(record.income_tax_password || ""),
      };
      updateItPortalLoginVisibility();
    }
    if (els.modalTitle) {
      els.modalTitle.textContent = record.customer_id ? "Edit Customer" : "New Customer";
    }
    syncMandatoryMarkers();
    syncFilingFrequencyVisibility();
  }

  function openNew() {
    clearForm();
    if (els.modalTitle) els.modalTitle.textContent = "New Customer";
    if (els.displayId) els.displayId.value = "Auto";
    syncMandatoryMarkers();
    modal?.show();
  }

  function openEdit(record) {
    fillForm(record);
    if (els.modalTitle) els.modalTitle.textContent = "Edit Customer #" + record.customer_id;
    modal?.show();
  }

  function loadRecord(id) {
    return fetch(apiUrl(window.CM_API.get, id), { headers: { Accept: "application/json" } })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Customer not found.");
        openEdit(data.record);
      });
  }

  function collectPayload() {
    const payload = {};
    const group = (els.customerGroup?.value || "").trim();
    const allowedTabs = groupTabs[group] || [];
    els.form?.querySelectorAll(".cm-tab-panel").forEach(function (panel) {
      if (!allowedTabs.includes(panel.dataset.tab)) return;
      panel.querySelectorAll("[data-cm-field]").forEach(function (field) {
        payload[field.dataset.cmField] = field.value;
      });
    });
    if (els.customerGroup) payload.customer_group = els.customerGroup.value;
    if (els.customerId?.value) payload.customer_id = els.customerId.value;
    return payload;
  }

  function validateClient(payload) {
    const errors = [];
    const required = activeMandatoryFields();
    const otherMode = isOtherCustomerType();
    if (!payload.customer_group) errors.push("Select customer group.");
    if (otherMode && !(payload.customer_type || "").trim()) {
      errors.push("Customer type is required.");
    }
    required.forEach(function (key) {
      if (!(payload[key] || "").trim()) {
        errors.push(key.replace(/_/g, " ") + " is required.");
      }
    });
    if (otherMode) {
      const pan = (payload.pan_number || "").trim().toUpperCase();
      if (pan && pan.length !== 10) {
        errors.push("Valid 10-character PAN is required.");
      }
      const mobile = (payload.mobile_number || "").replace(/\D/g, "");
      if (mobile && mobile.length !== 10) {
        errors.push("Valid 10-digit mobile number is required.");
      }
      const aadhaar = (payload.aadhaar_number || "").replace(/\D/g, "");
      if (aadhaar && aadhaar.length !== 12) {
        errors.push("Valid 12-digit Aadhaar is required.");
      }
    }
    els.form?.querySelectorAll("[data-cm-field]").forEach(function (f) {
      f.classList.remove("cm-field-error");
    });
    if (errors.length) {
      required.forEach(function (key) {
        if (!(payload[key] || "").trim()) {
          const field = document.getElementById("cm_" + key);
          if (field) field.classList.add("cm-field-error");
        }
      });
      if (!payload.customer_group && els.customerGroup) {
        els.customerGroup.classList.add("cm-field-error");
      }
    }
    return errors;
  }

  function saveCustomer(allowDuplicateMobile) {
    const payload = collectPayload();
    if (isOtherCustomerType() && !(payload.pan_number || "").trim()) {
      payload.pan_number = placeholderPan;
      const panField = document.getElementById("cm_pan_number");
      if (panField && !panField.value.trim()) panField.value = placeholderPan;
    }
    const errors = validateClient(payload);
    if (errors.length) {
      if (els.formError) {
        els.formError.textContent = errors[0];
        els.formError.classList.remove("d-none");
      }
      return;
    }
    if (els.formError) els.formError.classList.add("d-none");
    if (allowDuplicateMobile || mobileDuplicatesVisible) {
      payload.allow_duplicate_mobile = true;
    }
    els.saveBtn.disabled = true;
    fetch(window.CM_API.save, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { status: res.status, data: data };
        });
      })
      .then(function (result) {
        const data = result.data;
        if (result.status === 409 && data.duplicate_type === "pan_number") {
          showDuplicateModal("pan_number", data.duplicate, data.error);
          return;
        }
        if (result.status === 409 && data.duplicate_type === "aadhaar_number") {
          showDuplicateModal("aadhaar_number", data.duplicate, data.error);
          return;
        }
        if (result.status === 409 && data.duplicate_type === "mobile_number") {
          showMobileDupPanel(data.mobile_duplicates || []);
          if (els.formError) {
            els.formError.textContent = data.error || "Duplicate mobile — you may save again to proceed.";
            els.formError.className = "alert alert-warning py-2 small mt-3";
            els.formError.classList.remove("d-none");
          }
          return;
        }
        if (!data.ok) throw new Error(data.error || "Save failed.");
        showStatus(data.message || "Customer saved.", "success");
        hideMobileDupPanel();
        modal?.hide();
        loadGrid();
      })
      .catch(function (err) {
        if (els.formError) {
          els.formError.className = "alert alert-danger py-2 small mt-3";
          els.formError.textContent = err.message || "Unable to save.";
          els.formError.classList.remove("d-none");
        }
      })
      .finally(function () {
        els.saveBtn.disabled = false;
      });
  }

  async function deleteCustomer(id) {
    const customerId = id || selectedId;
    if (!customerId) return;
    const row = rows.find(function (r) { return r.customer_id === customerId; });
    const name = row ? row.customer_name : "this customer";
    const message =
      'Delete "' + name + '"?\n\nSoft delete — customer will be marked Inactive.';
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!confirm(message)) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: message });
      if (!creds) return;
    }
    fetch(apiUrl(window.CM_API.delete, customerId), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": csrfToken() },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Delete failed.");
        showStatus(data.message, "success");
        setSelected(null);
        loadGrid();
      })
      .catch(function (err) {
        showStatus(err.message, "danger");
      });
  }

  els.addBtn?.addEventListener("click", openNew);
  els.newBtn?.addEventListener("click", openNew);
  els.editBtn?.addEventListener("click", function () {
    if (selectedId) loadRecord(selectedId);
  });
  els.deleteBtn?.addEventListener("click", function () { deleteCustomer(selectedId); });
  els.refreshBtn?.addEventListener("click", loadGrid);
  els.saveBtn?.addEventListener("click", function () { saveCustomer(false); });
  els.search?.addEventListener("input", function () {
    clearTimeout(window._cmSearchTimer);
    window._cmSearchTimer = setTimeout(loadGrid, 300);
  });
  els.filterGroup?.addEventListener("change", loadGrid);
  els.filterStatus?.addEventListener("change", loadGrid);

  els.customerGroup?.addEventListener("change", function () {
    els.customerGroup.classList.remove("cm-field-error");
    buildTabs(els.customerGroup.value);
    syncMandatoryMarkers();
  });

  els.form?.addEventListener("change", function (event) {
    const target = event.target;
    if (target && target.id === "cm_customer_type") {
      syncMandatoryMarkers();
    }
  });

  ["pan_number", "aadhaar_number", "mobile_number"].forEach(function (fieldName) {
    const field = document.getElementById("cm_" + fieldName);
    field?.addEventListener("blur", function () {
      handleFieldDuplicateCheck(fieldName);
    });
  });

  els.duplicateEditYes?.addEventListener("click", function () {
    duplicateModal?.hide();
    if (pendingDuplicateCustomerId) {
      loadRecord(pendingDuplicateCustomerId);
    }
    pendingDuplicateCustomerId = null;
  });

  els.duplicateEditNo?.addEventListener("click", function () {
    duplicateModal?.hide();
    pendingDuplicateCustomerId = null;
  });

  els.duplicateModalEl?.addEventListener("hidden.bs.modal", function () {
    pendingDuplicateCustomerId = null;
  });

  els.tabNav?.addEventListener("click", function (event) {
    const btn = event.target.closest(".nav-link[data-tab]");
    if (!btn) return;
    showTabPanel(btn.dataset.tab);
  });

  els.gridBody.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".cm-row-edit");
    if (editBtn) {
      const id = parseInt(editBtn.dataset.id, 10);
      setSelected(id);
      loadRecord(id);
      return;
    }
    const delBtn = event.target.closest(".cm-row-delete");
    if (delBtn) {
      const id = parseInt(delBtn.dataset.id, 10);
      setSelected(id);
      deleteCustomer(id);
      return;
    }
    const tr = event.target.closest("tr[data-id]");
    if (tr && !event.target.closest(".cm-actions")) {
      setSelected(parseInt(tr.dataset.id, 10));
    }
  });

  els.syncIncomeTaxBtn?.addEventListener("click", openItCredentialsModal);
  els.syncAadhaarBtn?.addEventListener("click", openAadhaarSyncModal);
  els.syncGstBtn?.addEventListener("click", function () {
    setSyncStatus("GST portal import baad me enable hoga.", true);
  });
  els.itPortalLoginBtn?.addEventListener("click", function () {
    if (!itCredentials.userId || !itCredentials.password) {
      openItCredentialsModal();
      return;
    }
    showItPortalHelper();
  });
  els.itSyncSaveBtn?.addEventListener("click", saveItCredentials);
  els.itOpenPortalBtn?.addEventListener("click", function () {
    openIncomeTaxPortal();
  });
  els.itCopyUserBtn?.addEventListener("click", function () {
    copyText(itCredentials.userId).then(function () {
      setSyncStatus("User ID copied.");
    });
  });
  els.itCopyPassBtn?.addEventListener("click", function () {
    copyText(itCredentials.password).then(function () {
      setSyncStatus("Password copied.");
    });
  });
  els.aadhaarContinueBtn?.addEventListener("click", continueAadhaarToPortal);
  els.aadhaarOpenPortalBtn?.addEventListener("click", function () {
    if (aadhaarSyncValue) {
      copyText(aadhaarSyncValue).catch(function () {});
    }
    openAadhaarPortal();
  });
  els.aadhaarCopyBtn?.addEventListener("click", function () {
    copyText(aadhaarSyncValue || (els.aadhaarSyncNumber?.value || "").replace(/\D/g, "")).then(
      function () {
        if (els.aadhaarReadyHint) els.aadhaarReadyHint.textContent = "Aadhaar number copied.";
      }
    );
  });
  els.aadhaarApplyBtn?.addEventListener("click", applyAadhaarSyncToForm);

  syncFilingFrequencyVisibility();
  els.form?.querySelectorAll('[data-cm-field="gst_number"]').forEach(function (field) {
    field.addEventListener("input", syncFilingFrequencyVisibility);
    field.addEventListener("change", syncFilingFrequencyVisibility);
  });
  els.form?.querySelectorAll('[data-cm-field="filing_frequency"]').forEach(function (field) {
    field.addEventListener("change", function () {
      const value = field.value;
      els.form?.querySelectorAll('[data-cm-field="filing_frequency"]').forEach(function (other) {
        if (other !== field) other.value = value;
      });
    });
  });

  renderGrid(rows);
})();
