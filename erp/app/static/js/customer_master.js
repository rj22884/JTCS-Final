(function () {
  "use strict";

  const els = {
    addBtn: document.getElementById("cmAddBtn"),
    editBtn: document.getElementById("cmEditBtn"),
    restoreBtn: document.getElementById("cmRestoreBtn"),
    restoreFormBtn: document.getElementById("cmRestoreFormBtn"),
    deleteBtn: document.getElementById("cmDeleteBtn"),
    resetPortalBtn: document.getElementById("cmResetPortalBtn"),
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
    chartGroupBar: document.getElementById("cmChartGroupBar"),
    chartGroups: document.getElementById("cm_chart_groups"),
    groupComboWarn: document.getElementById("cmGroupComboWarn"),
    ieWorkBar: document.getElementById("cmIeWorkBar"),
    ieWorks: document.getElementById("cm_ie_works"),
    tabNav: document.getElementById("cmTabNav"),
    formPanels: document.getElementById("cmFormPanels"),
    formError: document.getElementById("cmFormError"),
    saveBtn: document.getElementById("cmSaveBtn"),
    mobileDupPanel: document.getElementById("cmMobileDupPanel"),
    mobileDupList: document.getElementById("cmMobileDupList"),
    usagePanel: document.getElementById("cmUsagePanel"),
    usageLinks: document.getElementById("cmUsageLinks"),
    usageRows: document.getElementById("cmUsageRows"),
    usageEmpty: document.getElementById("cmUsageEmpty"),
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
    aadhaarUnlockBtn: document.getElementById("cmAadhaarUnlockBtn"),
    aadhaarApplyBtn: document.getElementById("cmAadhaarApplyBtn"),
    aadhaarOpenPortalBtn: document.getElementById("cmAadhaarOpenPortalBtn"),
    aadhaarCopyBtn: document.getElementById("cmAadhaarCopyBtn"),
    aadhaarReadyHint: document.getElementById("cmAadhaarReadyHint"),
    aadhaarStepPassword: document.getElementById("cmAadhaarStepPassword"),
    aadhaarZipPassword: document.getElementById("cmAadhaarZipPassword"),
    aadhaarWaitBox: document.getElementById("cmAadhaarWaitBox"),
    aadhaarPreviewWrap: document.getElementById("cmAadhaarPreviewWrap"),
    aadhaarPhotoPreview: document.getElementById("cmAadhaarPhotoPreview"),
    aadhaarSyncName: document.getElementById("cmAadhaarSyncName"),
    aadhaarSyncDob: document.getElementById("cmAadhaarSyncDob"),
    aadhaarSyncGender: document.getElementById("cmAadhaarSyncGender"),
    aadhaarSyncAddress: document.getElementById("cmAadhaarSyncAddress"),
    photoPreview: document.getElementById("cm_photo_preview"),
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
  let aadhaarJobId = "";
  let aadhaarPollTimer = null;
  let aadhaarParsedData = null;
  let aadhaarPhotoUrl = "";
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

  function formatUsageDate(value) {
    const raw = String(value || "").slice(0, 10);
    const parts = raw.split("-");
    if (parts.length === 3) return parts[2] + "/" + parts[1] + "/" + parts[0];
    return raw || "—";
  }

  function formatUsageAmount(value) {
    if (value == null || value === "") return "—";
    const num = Number(value);
    if (!Number.isFinite(num)) return "—";
    return num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function hideUsagePanel() {
    if (els.usagePanel) els.usagePanel.classList.add("d-none");
    if (els.usageLinks) els.usageLinks.innerHTML = "";
    if (els.usageRows) els.usageRows.innerHTML = "";
    if (els.usageEmpty) els.usageEmpty.classList.add("d-none");
    applyStatusLock(false);
  }

  function applyStatusLock(locked) {
    const statusField = document.getElementById("cm_customer_status");
    if (!statusField) return;
    Array.prototype.forEach.call(statusField.options, function (opt) {
      if (String(opt.value).toLowerCase() === "inactive") {
        opt.disabled = !!locked && String(statusField.value).toLowerCase() !== "inactive";
      }
    });
  }

  function showUsagePanel(usage) {
    if (!els.usagePanel) return;
    if (!usage || usage.can_delete !== false) {
      hideUsagePanel();
      return;
    }
    const links = usage.links || [];
    const txns = usage.transactions || [];
    if (els.usageLinks) {
      els.usageLinks.innerHTML = links.map(function (link) {
        return (
          '<span class="cm-usage-chip">' +
          escapeHtml(link.label || link.table || "Record") +
          " (" + escapeHtml(link.count) + ")</span>"
        );
      }).join("");
    }
    if (els.usageRows) {
      els.usageRows.innerHTML = txns.map(function (row) {
        const work = escapeHtml(row.work || row.source || "—");
        const ref = row.reference ? '<span class="cm-usage-ref">' + escapeHtml(row.reference) + "</span>" : "";
        return (
          "<tr>" +
          "<td>" + escapeHtml(formatUsageDate(row.txn_date)) + "</td>" +
          '<td class="cm-usage-work">' + work + ref + "</td>" +
          '<td class="text-end">' + escapeHtml(formatUsageAmount(row.amount)) + "</td>" +
          "</tr>"
        );
      }).join("");
    }
    if (els.usageEmpty) {
      els.usageEmpty.classList.toggle("d-none", txns.length > 0);
    }
    const wrap = els.usagePanel.querySelector(".cm-usage-table-wrap");
    if (wrap) wrap.classList.toggle("d-none", txns.length === 0);
    applyStatusLock(true);
    els.usagePanel.classList.remove("d-none");
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
    if (els.restoreBtn) els.restoreBtn.disabled = !has || !row || row.customer_status !== "Inactive";
    if (els.deleteBtn) {
      els.deleteBtn.disabled = !has || (row && (row.customer_status === "Inactive" || row.has_links));
    }
    if (els.resetPortalBtn) {
      els.resetPortalBtn.disabled = !has || (row && row.customer_status === "Inactive");
    }
    els.gridBody.querySelectorAll("tr").forEach(function (tr) {
      tr.classList.toggle("table-active", tr.dataset.id === String(selectedId));
    });
  }

  async function resetPortalPassword(customerId) {
    if (!customerId || !window.CM_API.resetPortalPassword) return;
    if (!(await JTCSDialog.confirm("Clear Customer Portal password? Customer must verify PAN/Aadhaar and create a new password on next login."))) return;
    const url = apiUrl(window.CM_API.resetPortalPassword, customerId);
    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: "{}",
      credentials: "same-origin",
    })
      .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
      .then(function (result) {
        if (!result.ok || !result.data || !result.data.ok) {
          const msg = (result.data && result.data.error) || "Unable to reset portal password.";
          if (window.JTCSDialog) JTCSDialog.alert(msg, "error");
          else showStatus(msg, "danger");
          return;
        }
        const msg = result.data.message || "Default password reset successfully.";
        if (window.JTCSDialog) JTCSDialog.alert(msg, "success");
        else showStatus(msg, "success");
      })
      .catch(function () {
        const msg = "Unable to reset portal password.";
        if (window.JTCSDialog) JTCSDialog.alert(msg, "error");
        else showStatus(msg, "danger");
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
      const linked = !!row.has_links;
      let extraBtn = "";
      if (inactive) {
        extraBtn = '<button type="button" class="btn btn-outline-success btn-sm cm-row-restore" data-id="' + row.customer_id + '" title="Restore Active"><i class="bi bi-arrow-counterclockwise"></i></button>';
      } else if (!linked) {
        extraBtn = '<button type="button" class="btn btn-outline-danger btn-sm cm-row-delete" data-id="' + row.customer_id + '" title="Delete"><i class="bi bi-trash"></i></button>';
      }
      const badge = inactive
        ? '<span class="badge bg-secondary">Inactive</span>'
        : '<span class="badge bg-success">' + escapeHtml(row.customer_status || "Active") + "</span>";
      const logged = !!row.logged;
      const loggedLight = logged
        ? '<span class="cm-logged-light is-on" title="Portal login active (password set)" aria-label="Logged"></span>'
        : '<span class="cm-logged-light is-off" title="Not yet logged in / password not set" aria-label="Not logged"></span>';
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
        '<td class="text-center">' + loggedLight + "</td>" +
        '<td class="text-end cm-actions">' +
        '<button type="button" class="btn btn-outline-primary btn-sm cm-row-edit" data-id="' + row.customer_id + '" title="Edit"><i class="bi bi-pencil"></i></button> ' +
        extraBtn +
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
    const url = portals.aadhaarPortal || "https://myaadhaar.uidai.gov.in/offline-ekyc";
    window.open(url, "cmAadhaarPortal", "noopener,noreferrer,width=1100,height=800");
  }

  function stopAadhaarPoll() {
    if (aadhaarPollTimer) {
      clearInterval(aadhaarPollTimer);
      aadhaarPollTimer = null;
    }
  }

  function showAadhaarError(message) {
    if (!els.aadhaarSyncError) return;
    if (!message) {
      els.aadhaarSyncError.classList.add("d-none");
      els.aadhaarSyncError.textContent = "";
      return;
    }
    els.aadhaarSyncError.textContent = message;
    els.aadhaarSyncError.classList.remove("d-none");
  }

  function setCustomerPhotoPreview(url) {
    const src = url || "";
    if (els.aadhaarPhotoPreview) {
      if (src) {
        els.aadhaarPhotoPreview.src = src;
        els.aadhaarPreviewWrap?.classList.remove("d-none");
      } else {
        els.aadhaarPhotoPreview.removeAttribute("src");
        els.aadhaarPreviewWrap?.classList.add("d-none");
      }
    }
    if (els.photoPreview) {
      if (src) {
        els.photoPreview.src = src;
        els.photoPreview.classList.remove("d-none");
      } else {
        els.photoPreview.removeAttribute("src");
        els.photoPreview.classList.add("d-none");
      }
    }
  }

  function applyAadhaarMappedFields(data) {
    if (!data || typeof data !== "object") return 0;
    let count = 0;
    Object.keys(data).forEach(function (key) {
      const value = data[key];
      if (value == null || String(value).trim() === "") return;
      const field = document.getElementById("cm_" + key);
      if (!field) return;
      if (field.tagName === "SELECT" && key === "country" && window.JtcsPincodeAutofill) {
        window.JtcsPincodeAutofill.ensureSelectValue(field, value);
      } else {
        field.value = value;
      }
      count += 1;
    });
    if (data.pincode && typeof refreshPincodeIntegration === "function") {
      refreshPincodeIntegration();
    }
    return count;
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
    stopAadhaarPoll();
    aadhaarJobId = "";
    aadhaarParsedData = null;
    aadhaarPhotoUrl = "";
    showAadhaarError("");
    els.aadhaarStepAsk?.classList.remove("d-none");
    els.aadhaarStepPortal?.classList.add("d-none");
    els.aadhaarStepPassword?.classList.add("d-none");
    els.aadhaarContinueBtn?.classList.remove("d-none");
    els.aadhaarUnlockBtn?.classList.add("d-none");
    els.aadhaarApplyBtn?.classList.add("d-none");
    if (els.aadhaarZipPassword) els.aadhaarZipPassword.value = "";
    if (els.aadhaarSyncNumber) {
      els.aadhaarSyncNumber.value = getFieldValue("aadhaar_number") || "";
    }
    if (els.aadhaarReadyHint) els.aadhaarReadyHint.textContent = "";
    if (els.aadhaarWaitBox) {
      els.aadhaarWaitBox.innerHTML =
        "<strong>Waiting for ZIP download…</strong> On UIDAI: enter Aadhaar, CAPTCHA, OTP, Share Code, then click <em>Download</em>. Do not close this dialog.";
    }
    els.aadhaarPreviewWrap?.classList.add("d-none");
  }

  function openAadhaarSyncModal() {
    resetAadhaarModal();
    aadhaarSyncModal?.show();
  }

  function pollAadhaarJob(jobId) {
    const statusUrl = (window.CM_API && window.CM_API.aadhaarEkycStatus) || "";
    if (!statusUrl || !jobId) return;
    stopAadhaarPoll();
    let tries = 0;
    aadhaarPollTimer = setInterval(function () {
      tries += 1;
      fetch(statusUrl + "?job_id=" + encodeURIComponent(jobId), {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      })
        .then(function (res) {
          return res.json();
        })
        .then(function (payload) {
          if (!payload.ok || !payload.job) return;
          const job = payload.job;
          if (els.aadhaarReadyHint) els.aadhaarReadyHint.textContent = job.message || "";
          if (job.status === "need_password") {
            stopAadhaarPoll();
            els.aadhaarStepPassword?.classList.remove("d-none");
            els.aadhaarUnlockBtn?.classList.remove("d-none");
            if (els.aadhaarWaitBox) {
              els.aadhaarWaitBox.innerHTML =
                "<strong>ZIP detected:</strong> " +
                (job.zip_name || "Aadhaar ZIP") +
                ". Enter Share Code (ZIP password), then Unlock.";
            }
            setSyncStatus("Aadhaar ZIP detected. Enter Share Code.");
          } else if (job.status === "done") {
            stopAadhaarPoll();
            aadhaarParsedData = job.data || null;
            aadhaarPhotoUrl = job.photo_url || "";
            setCustomerPhotoPreview(aadhaarPhotoUrl);
            els.aadhaarUnlockBtn?.classList.add("d-none");
            els.aadhaarApplyBtn?.classList.remove("d-none");
            setSyncStatus(job.message || "Aadhaar XML ready. Apply to form.");
          } else if (job.status === "error") {
            stopAadhaarPoll();
            showAadhaarError(job.message || "Aadhaar import failed.");
            setSyncStatus(job.message || "Aadhaar import failed.", true);
          }
        })
        .catch(function () {
          if (tries >= 200) {
            stopAadhaarPoll();
            showAadhaarError("Timed out waiting for ZIP download.");
          }
        });
      if (tries >= 200) {
        stopAadhaarPoll();
        showAadhaarError("Timed out waiting for ZIP download.");
      }
    }, 1500);
  }

  function continueAadhaarToPortal() {
    const aadhaar = (els.aadhaarSyncNumber?.value || "").replace(/\D/g, "");
    if (aadhaar.length !== 12) {
      showAadhaarError("Valid 12-digit Aadhaar number is required.");
      return;
    }
    showAadhaarError("");
    aadhaarSyncValue = aadhaar;
    // Keep on form for review/save; not logged server-side by eKYC APIs.
    setFieldValue("aadhaar_number", aadhaar);

    const startUrl = (window.CM_API && window.CM_API.aadhaarEkycStart) || "";
    if (!startUrl) {
      showAadhaarError("Aadhaar eKYC API is not configured.");
      return;
    }
    els.aadhaarContinueBtn.disabled = true;
    fetch(startUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({}),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to start Aadhaar watch.");
          return data;
        });
      })
      .then(function (data) {
        aadhaarJobId = data.job_id || "";
        if (data.portal_url) portals.aadhaarPortal = data.portal_url;
        els.aadhaarStepAsk?.classList.add("d-none");
        els.aadhaarStepPortal?.classList.remove("d-none");
        els.aadhaarContinueBtn?.classList.add("d-none");
        if (els.aadhaarReadyHint) {
          els.aadhaarReadyHint.textContent = "Waiting for Offline Aadhaar ZIP in Downloads…";
        }
        copyText(aadhaar).catch(function () {});
        setSyncStatus("Offline eKYC portal opening. Complete CAPTCHA/OTP, then Download.");
        openAadhaarPortal();
        pollAadhaarJob(aadhaarJobId);
      })
      .catch(function (err) {
        showAadhaarError(err.message || "Unable to start Aadhaar import.");
      })
      .finally(function () {
        els.aadhaarContinueBtn.disabled = false;
      });
  }

  function unlockAadhaarZip() {
    const password = (els.aadhaarZipPassword?.value || "").trim();
    if (!password) {
      showAadhaarError("ZIP password (Share Code) is required.");
      return;
    }
    if (!aadhaarJobId) {
      showAadhaarError("Import session expired. Start again.");
      return;
    }
    showAadhaarError("");
    const unlockUrl = (window.CM_API && window.CM_API.aadhaarEkycUnlock) || "";
    if (!unlockUrl) return;
    els.aadhaarUnlockBtn.disabled = true;
    fetch(unlockUrl, {
      method: "POST",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
      },
      body: JSON.stringify({ job_id: aadhaarJobId, password: password }),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to unlock ZIP.");
          return data;
        });
      })
      .then(function (data) {
        aadhaarParsedData = data.data || null;
        aadhaarPhotoUrl = data.photo_url || "";
        setCustomerPhotoPreview(aadhaarPhotoUrl);
        els.aadhaarUnlockBtn?.classList.add("d-none");
        els.aadhaarApplyBtn?.classList.remove("d-none");
        if (els.aadhaarZipPassword) els.aadhaarZipPassword.value = "";
        setSyncStatus(data.message || "Aadhaar XML read successfully.");
      })
      .catch(function (err) {
        showAadhaarError(err.message || "Wrong password or invalid ZIP.");
        setSyncStatus(err.message || "Unable to unlock Aadhaar ZIP.", true);
      })
      .finally(function () {
        els.aadhaarUnlockBtn.disabled = false;
      });
  }

  function applyAadhaarSyncToForm() {
    // Never clear the whole form — only overwrite fields present in XML mapping.
    if (aadhaarSyncValue) setFieldValue("aadhaar_number", aadhaarSyncValue);
    const data = aadhaarParsedData || {};
    const n = applyAadhaarMappedFields(data);
    if (aadhaarPhotoUrl) setCustomerPhotoPreview(aadhaarPhotoUrl);
    setSyncStatus(
      n
        ? "Aadhaar Offline eKYC applied (" + n + " field(s)). Review, then Save Customer."
        : "No Aadhaar fields to apply."
    );
    aadhaarSyncModal?.hide();
    stopAadhaarPoll();
  }

  const chartGroupMeta = {};
  (window.CM_CHART_GROUPS || []).forEach(function (g) {
    if (g && g.group_id != null) chartGroupMeta[String(g.group_id)] = g;
  });
  const allCustomerGroups = (window.CM_CUSTOMER_GROUPS || []).map(function (g) {
    return { code: String((g && g.code) || "").trim(), label: (g && g.label) || "" };
  }).filter(function (g) { return g.code; });
  const groupChartFilter = window.CM_GROUP_CHART_FILTER || {};
  const customerGroupUsage = groupChartFilter.usage || {};
  const chartNatures = groupChartFilter.chart_natures || {};
  const INVALID_COMBO_MSG =
    "Selected Customer Group is not valid for the selected Chart of Account Group.";

  function selectedChartGroupIds() {
    if (!els.chartGroups) return [];
    const v = (els.chartGroups.value || "").trim();
    return v ? [v] : [];
  }

  function chartNatureForId(chartId) {
    if (chartId == null || chartId === "") return "";
    const fromMap = chartNatures[String(chartId)];
    if (fromMap) return String(fromMap).trim();
    const g = chartGroupMeta[String(chartId)] || {};
    return String(g.group_nature || "").trim();
  }

  function allowedCustomerGroupCodes(chartId, includeCode) {
    if (!chartId) return [];
    const selectedNature = chartNatureForId(chartId);
    const include = String(includeCode || "").trim().toUpperCase();
    const gid = parseInt(chartId, 10);
    const allowed = [];
    allCustomerGroups.forEach(function (g) {
      const code = g.code;
      const key = String(code).toUpperCase();
      if (include && key === include) {
        if (allowed.indexOf(code) < 0) allowed.push(code);
        return;
      }
      const used = customerGroupUsage[key] || customerGroupUsage[code] || [];
      const usedIds = (Array.isArray(used) ? used : []).map(function (id) {
        return parseInt(id, 10);
      }).filter(function (id) { return id > 0; });
      if (!usedIds.length) {
        allowed.push(code);
        return;
      }
      if (usedIds.indexOf(gid) >= 0) {
        allowed.push(code);
        return;
      }
      const usedNatures = {};
      usedIds.forEach(function (id) {
        const n = chartNatureForId(id);
        if (n) usedNatures[n] = true;
      });
      if (selectedNature && usedNatures[selectedNature]) {
        allowed.push(code);
      }
    });
    return allowed;
  }

  function isCustomerGroupValidForChart(code, chartId) {
    const group = String(code || "").trim().toUpperCase();
    if (!group || !chartId) return false;
    return allowedCustomerGroupCodes(chartId, null).some(function (c) {
      return String(c).toUpperCase() === group;
    });
  }

  function setGroupComboWarning(message) {
    if (!els.groupComboWarn) return;
    if (!message) {
      els.groupComboWarn.classList.add("d-none");
      els.groupComboWarn.textContent = "";
      return;
    }
    els.groupComboWarn.textContent = message;
    els.groupComboWarn.classList.remove("d-none");
  }

  function rebuildCustomerGroupOptions(preferredCode, opts) {
    if (!els.customerGroup) return;
    opts = opts || {};
    const chartId = selectedChartGroupIds()[0] || "";
    const preferred = String(preferredCode || "").trim();
    const keep = opts.keepInvalid ? preferred : "";
    const allowed = chartId ? allowedCustomerGroupCodes(chartId, keep) : [];
    const labels = {};
    allCustomerGroups.forEach(function (g) { labels[String(g.code).toUpperCase()] = g.label || g.code; });
    Array.prototype.slice.call(els.customerGroup.options || []).forEach(function (opt) {
      if (opt.value) labels[String(opt.value).toUpperCase()] = opt.textContent;
    });
    let html = '<option value="">-- Select Group --</option>';
    allowed.forEach(function (code) {
      html +=
        '<option value="' +
        escapeHtml(code) +
        '">' +
        escapeHtml(labels[String(code).toUpperCase()] || code) +
        "</option>";
    });
    els.customerGroup.innerHTML = html;
    els.customerGroup.disabled = !chartId;
    const prefKey = preferred.toUpperCase();
    const match = allowed.find(function (c) { return String(c).toUpperCase() === prefKey; });
    els.customerGroup.value = match || "";
    const current = (els.customerGroup.value || "").trim().toUpperCase();
    if (current && chartId && !isCustomerGroupValidForChart(current, chartId)) {
      setGroupComboWarning(INVALID_COMBO_MSG);
    } else {
      setGroupComboWarning("");
    }
  }

  function selectedIeWorkIds() {
    if (!els.ieWorks) return [];
    return Array.prototype.slice
      .call(els.ieWorks.selectedOptions || [])
      .map(function (opt) {
        return opt.value;
      })
      .filter(Boolean);
  }

  function setChartGroupSelection(ids) {
    if (!els.chartGroups) return;
    const list = Array.isArray(ids) ? ids : [];
    const first = list.length ? String(list[0]) : "";
    els.chartGroups.value = first;
    els.chartGroups.classList.remove("cm-field-error");
  }

  function defaultChartGroupIds() {
    if (window.CM_DEFAULT_CHART_GROUP_ID != null && window.CM_DEFAULT_CHART_GROUP_ID !== "") {
      return [String(window.CM_DEFAULT_CHART_GROUP_ID)];
    }
    const found = (window.CM_CHART_GROUPS || []).find(function (g) {
      return String((g && g.group_name) || "")
        .trim()
        .toLowerCase() === "individual client";
    });
    return found && found.group_id != null ? [String(found.group_id)] : [];
  }

  function applyDefaultChartGroupsIfEmpty() {
    if (!els.chartGroups) return;
    if (selectedChartGroupIds().length) return;
    setChartGroupSelection(defaultChartGroupIds());
  }

  function defaultDrCrFromUnderType(underType) {
    return String(underType || "").trim().toLowerCase() === "liabilities" ? "Cr" : "Dr";
  }

  function setOpeningDrCr(value) {
    const v = value === "Cr" ? "Cr" : "Dr";
    const dr = document.getElementById("cm_opening_balance_dr");
    const cr = document.getElementById("cm_opening_balance_cr");
    if (dr) dr.checked = v === "Dr";
    if (cr) cr.checked = v === "Cr";
  }

  function applyDefaultDrCrFromChartGroups() {
    const ids = selectedChartGroupIds();
    let under = "";
    if (ids.length) {
      const g = chartGroupMeta[String(ids[0])] || {};
      under = g.under_type || "";
    }
    setOpeningDrCr(defaultDrCrFromUnderType(under));
  }

  function setIeWorkSelection(ids) {
    if (!els.ieWorks) return;
    const keep = {};
    (Array.isArray(ids) ? ids : []).forEach(function (id) {
      keep[String(id)] = true;
    });
    Array.prototype.forEach.call(els.ieWorks.options || [], function (opt) {
      opt.selected = !!keep[String(opt.value)];
    });
    els.ieWorks.classList.remove("cm-field-error");
  }

  function textLooksIncomeExpense(text) {
    const t = String(text || "").toLowerCase();
    return (
      t.indexOf("income") >= 0 ||
      t.indexOf("expense") >= 0 ||
      t.indexOf("purchase") >= 0 ||
      t.indexOf("sale") >= 0 ||
      t.indexOf("salary") >= 0 ||
      t.indexOf("wages") >= 0 ||
      t.indexOf("contra") >= 0
    );
  }

  function needsIncomeExpenseWorks() {
    const custGroup = (els.customerGroup?.value || "").trim();
    if (textLooksIncomeExpense(custGroup)) return true;
    return selectedChartGroupIds().some(function (id) {
      const g = chartGroupMeta[String(id)] || {};
      return textLooksIncomeExpense(
        (g.label || "") + " " + (g.group_name || "") + " " + (g.under_type || "")
      );
    });
  }

  function syncChartGroupBar() {
    if (els.chartGroupBar) {
      els.chartGroupBar.classList.remove("d-none");
    }
    const chartId = selectedChartGroupIds()[0] || "";
    if (!chartId) {
      rebuildCustomerGroupOptions("");
      setIeWorkSelection([]);
    } else {
      rebuildCustomerGroupOptions(els.customerGroup?.value || "");
      applyDefaultDrCrFromChartGroups();
    }
    syncIeWorkBar();
  }

  function syncIeWorkBar() {
    const show = needsIncomeExpenseWorks();
    if (els.ieWorkBar) {
      els.ieWorkBar.classList.toggle("d-none", !show);
    }
    if (!show) {
      setIeWorkSelection([]);
      if (els.ieWorks) els.ieWorks.classList.remove("cm-field-error");
    }
  }

  function clearForm() {
    resetSyncState();
    if (typeof cmPincodeBinder !== "undefined" && cmPincodeBinder) {
      if (cmPincodeBinder.unlock) cmPincodeBinder.unlock();
      if (cmPincodeBinder.resetCache) cmPincodeBinder.resetCache();
    }
    els.form?.querySelectorAll("[data-cm-field]").forEach(function (field) {
      field.classList.remove("cm-integrated-locked");
      if (field.type === "radio") {
        field.checked = false;
        field.disabled = false;
      } else if (field.tagName === "SELECT") {
        field.selectedIndex = 0;
        field.disabled = false;
      } else {
        field.readOnly = false;
        field.value = "";
      }
      field.classList.remove("cm-field-error");
    });
    if (els.customerId) els.customerId.value = "";
    if (els.displayId) els.displayId.value = "";
    if (els.customerGroup) els.customerGroup.value = "";
    setChartGroupSelection([]);
    setIeWorkSelection([]);
    setOpeningDrCr("Dr");
    setGroupComboWarning("");
    applyDefaultChartGroupsIfEmpty();
    syncChartGroupBar();
    const statusField = document.getElementById("cm_customer_status");
    if (statusField) statusField.value = "Active";
    const countryField = document.getElementById("cm_country");
    if (countryField) {
      if (window.JtcsPincodeAutofill) {
        window.JtcsPincodeAutofill.ensureSelectValue(countryField, "India");
      } else {
        countryField.value = "India";
      }
    }
    if (els.restoreFormBtn) els.restoreFormBtn.classList.add("d-none");
    if (els.tabNav) els.tabNav.innerHTML = "";
    els.formPanels?.querySelectorAll(".cm-tab-panel").forEach(function (p) {
      p.classList.add("d-none");
    });
    if (els.formError) {
      els.formError.classList.add("d-none");
      els.formError.textContent = "";
    }
    hideMobileDupPanel();
    hideUsagePanel();
    syncMandatoryMarkers();
    syncFilingFrequencyVisibility();
  }

  function fillForm(record) {
    clearForm();
    if (!record) return;
    if (els.customerId) els.customerId.value = record.customer_id || "";
    if (els.displayId) els.displayId.value = record.customer_id || "Auto";
    const savedChartIds = record.chart_group_ids || record.group_ids || [];
    if (Array.isArray(savedChartIds) && savedChartIds.length) {
      setChartGroupSelection(savedChartIds);
    } else {
      applyDefaultChartGroupsIfEmpty();
    }
    const existingGroup = String(record.customer_group || "").trim().toUpperCase();
    rebuildCustomerGroupOptions(existingGroup, { keepInvalid: true });
    if (els.customerGroup) {
      buildTabs(els.customerGroup.value);
    }
    const chartId = selectedChartGroupIds()[0] || "";
    if (existingGroup && chartId && !isCustomerGroupValidForChart(existingGroup, chartId)) {
      setGroupComboWarning(INVALID_COMBO_MSG);
    }
    syncIeWorkBar();
    setIeWorkSelection(record.income_expense_work_ids || record.work_ids || []);
    els.form?.querySelectorAll("[data-cm-field]").forEach(function (field) {
      const key = field.dataset.cmField;
      if (!key || key === "customer_group") return;
      const val = record[key];
      if (val == null) return;
      if (field.type === "radio") {
        field.checked = String(field.value) === String(val);
        return;
      }
      if (field.type === "date") {
        field.value = String(val).slice(0, 10);
      } else if (field.tagName === "SELECT" && key === "country" && window.JtcsPincodeAutofill) {
        window.JtcsPincodeAutofill.ensureSelectValue(field, val || "India");
      } else {
        field.value = val;
      }
    });
    if (record.opening_balance_dr_cr) {
      setOpeningDrCr(record.opening_balance_dr_cr);
    } else {
      applyDefaultDrCrFromChartGroups();
    }
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
    refreshPincodeIntegration();
    if (els.restoreFormBtn) {
      const inactive = String(record.customer_status || "") === "Inactive";
      els.restoreFormBtn.classList.toggle("d-none", !inactive);
    }
    showUsagePanel(record.usage);
    if (record.photo_path) {
      const rel = String(record.photo_path).replace(/^\/?static\//, "");
      setCustomerPhotoPreview("/static/" + rel.replace(/^\//, ""));
    } else {
      setCustomerPhotoPreview("");
    }
  }

  function openNew() {
    clearForm();
    if (els.modalTitle) els.modalTitle.textContent = "New Customer";
    if (els.displayId) els.displayId.value = "Auto";
    syncMandatoryMarkers();
    if (cmPincodeBinder) cmPincodeBinder.resetCache();
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
        if (field.type === "radio") {
          if (field.checked) payload[field.dataset.cmField] = field.value;
          return;
        }
        payload[field.dataset.cmField] = field.value;
      });
    });
    if (els.customerGroup) payload.customer_group = els.customerGroup.value;
    if (els.customerId?.value) payload.customer_id = els.customerId.value;
    const chartIds = selectedChartGroupIds();
    payload.chart_group_ids = chartIds;
    payload.group_ids = chartIds;
    if (chartIds.length) payload.group_id = chartIds[0];
    const workIds = selectedIeWorkIds();
    payload.income_expense_work_ids = workIds;
    payload.work_ids = workIds;
    return payload;
  }

  function validateClient(payload) {
    const errors = [];
    const required = activeMandatoryFields();
    const chartIds = Array.isArray(payload.chart_group_ids) ? payload.chart_group_ids : [];
    if (!chartIds.length) {
      errors.push("Select Chart of Account Group.");
    }
    if (!payload.customer_group) errors.push("Select customer group.");
    if (payload.customer_group && chartIds.length) {
      if (!isCustomerGroupValidForChart(payload.customer_group, chartIds[0])) {
        errors.push(INVALID_COMBO_MSG);
      }
    }
    required.forEach(function (key) {
      if (!(payload[key] || "").trim()) {
        errors.push(key.replace(/_/g, " ") + " is required.");
      }
    });
    // Format checks only when optional fields are filled.
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
    const email = (payload.email_id || "").trim();
    if (email) {
      const at = email.indexOf("@");
      const domain = at >= 0 ? email.slice(at + 1) : "";
      if (at < 1 || !domain || domain.indexOf(".") < 1) {
        errors.push("Valid email ID is required.");
      }
    }
    els.form?.querySelectorAll("[data-cm-field]").forEach(function (f) {
      f.classList.remove("cm-field-error");
    });
    if (els.chartGroups) els.chartGroups.classList.remove("cm-field-error");
    if (els.ieWorks) els.ieWorks.classList.remove("cm-field-error");
    if (errors.length) {
      required.forEach(function (key) {
        if (!(payload[key] || "").trim()) {
          const field = document.getElementById("cm_" + key);
          if (field) field.classList.add("cm-field-error");
        }
      });
      if (!chartIds.length && els.chartGroups) {
        els.chartGroups.classList.add("cm-field-error");
      }
      if (!payload.customer_group && els.customerGroup) {
        els.customerGroup.classList.add("cm-field-error");
      }
      if (
        payload.customer_group &&
        chartIds.length &&
        !isCustomerGroupValidForChart(payload.customer_group, chartIds[0])
      ) {
        if (els.customerGroup) els.customerGroup.classList.add("cm-field-error");
        if (els.chartGroups) els.chartGroups.classList.add("cm-field-error");
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
        if (result.status === 409 && data.in_use) {
          showUsagePanel(data.usage);
          if (els.formError) {
            els.formError.textContent = data.error || "This customer is in use and cannot be inactivated.";
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
      if (!(await JTCSDialog.confirm(message))) return;
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
        if (data.in_use) {
          if (row) row.has_links = true;
          showStatus(data.error || "Customer is in use and cannot be deleted.", "warning");
          setSelected(customerId);
          loadRecord(customerId);
          return;
        }
        if (!data.ok) throw new Error(data.error || "Delete failed.");
        showStatus(data.message, "success");
        setSelected(null);
        loadGrid();
      })
      .catch(function (err) {
        showStatus(err.message, "danger");
      });
  }

  async function restoreCustomer(id) {
    const customerId = id || selectedId;
    if (!customerId || !window.CM_API.restore) return;
    const row = rows.find(function (r) { return r.customer_id === customerId; });
    const name = row ? row.customer_name : "this customer";
    if (!(await JTCSDialog.confirm('Restore "' + name + '" to Active?'))) return;
    fetch(apiUrl(window.CM_API.restore, customerId), {
      method: "POST",
      headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Restore failed.");
        showStatus(data.message, "success");
        const statusField = document.getElementById("cm_customer_status");
        if (statusField) statusField.value = "Active";
        if (els.restoreFormBtn) els.restoreFormBtn.classList.add("d-none");
        if (row) row.customer_status = "Active";
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
  els.restoreBtn?.addEventListener("click", function () { restoreCustomer(selectedId); });
  els.restoreFormBtn?.addEventListener("click", function () {
    const id = parseInt(els.customerId?.value || selectedId, 10);
    restoreCustomer(id);
  });
  els.resetPortalBtn?.addEventListener("click", function () {
    if (selectedId) resetPortalPassword(selectedId);
  });
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
    const chartId = selectedChartGroupIds()[0] || "";
    const group = (els.customerGroup.value || "").trim();
    if (group && chartId && !isCustomerGroupValidForChart(group, chartId)) {
      setGroupComboWarning(INVALID_COMBO_MSG);
    } else {
      setGroupComboWarning("");
    }
    syncMandatoryMarkers();
    syncIeWorkBar();
  });
  els.chartGroups?.addEventListener("change", function () {
    els.chartGroups.classList.remove("cm-field-error");
    const previousGroup = (els.customerGroup?.value || "").trim();
    rebuildCustomerGroupOptions(previousGroup);
    if (previousGroup && els.customerGroup && els.customerGroup.value !== previousGroup) {
      buildTabs(els.customerGroup.value);
    } else if (els.customerGroup) {
      buildTabs(els.customerGroup.value);
    }
    applyDefaultDrCrFromChartGroups();
    syncIeWorkBar();
  });
  els.ieWorks?.addEventListener("change", function () {
    els.ieWorks.classList.remove("cm-field-error");
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
    const restoreBtn = event.target.closest(".cm-row-restore");
    if (restoreBtn) {
      const id = parseInt(restoreBtn.dataset.id, 10);
      setSelected(id);
      restoreCustomer(id);
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
  els.aadhaarUnlockBtn?.addEventListener("click", unlockAadhaarZip);
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
  els.aadhaarSyncModalEl?.addEventListener("hidden.bs.modal", function () {
    stopAadhaarPoll();
  });

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

  // Address tab: pincode + country → state / district / city / GST code (locked)
  var cmPincodeBinder = null;
  function refreshPincodeIntegration() {
    if (!cmPincodeBinder) return;
    cmPincodeBinder.resetCache();
    const pin = getFieldValue("pincode").replace(/\D/g, "");
    const country = getFieldValue("country") || "India";
    if (pin.length === 6 && country.toLowerCase() === "india") {
      cmPincodeBinder.lookup();
    }
  }
  if (window.JtcsPincodeAutofill && window.CM_API && window.CM_API.pincodeLookup) {
    cmPincodeBinder = window.JtcsPincodeAutofill.bind({
      pincode: "cm_pincode",
      country: "cm_country",
      state: "cm_state",
      district: "cm_district",
      city: "cm_city",
      stateGstCode: "cm_state_gst_code",
      apiUrl: window.CM_API.pincodeLookup,
      lookupOnBind: false,
    });
  }

  renderGrid(rows);
})();
