(function () {
  const api = window.RC_FPS_API || {};
  const els = {
    search: document.getElementById("rcDealerSearch"),
    searchBtn: document.getElementById("rcDealerSearchBtn"),
    addBtn: document.getElementById("rcDealerAddBtn"),
    refreshBtn: document.getElementById("rcDealerRefreshBtn"),
    gridBody: document.getElementById("rcDealerGridBody"),
    count: document.getElementById("rcDealerCount"),
    empty: document.getElementById("rcDealerEmpty"),
    hint: document.getElementById("rcDealerHint"),
    selected: document.getElementById("rcSelectedDealer"),
    selectedName: document.getElementById("rcSelectedName"),
    selectedMeta: document.getElementById("rcSelectedMeta"),
    fpsBlock: document.getElementById("rcFpsBlock"),
    fpsSearch: document.getElementById("rcFpsSearch"),
    fpsSearchBtn: document.getElementById("rcFpsSearchBtn"),
    fpsHint: document.getElementById("rcFpsHint"),
    uploadBlock: document.getElementById("rcUploadBlock"),
    uploadForm: document.getElementById("rcUploadForm"),
    csvFile: document.getElementById("rcCsvFile"),
    generateBtn: document.getElementById("rcGenerateBtn"),
    pdfBtn: document.getElementById("rcPdfBtn"),
    printBtn: document.getElementById("rcPrintBtn"),
    error: document.getElementById("rcError"),
    success: document.getElementById("rcSuccess"),
    warning: document.getElementById("rcWarning"),
    report: document.getElementById("rcReport"),
    reportSub: document.getElementById("rcReportSub"),
    summary: document.getElementById("rcSummary"),
    reportBody: document.getElementById("rcReportBody"),
    reportFooter: document.getElementById("rcReportFooter"),
    modalEl: document.getElementById("rcDealerModal"),
    modalTitle: document.getElementById("rcDealerModalTitle"),
    form: document.getElementById("rcDealerForm"),
    formError: document.getElementById("rcDealerFormError"),
    dealerId: document.getElementById("rcDealerId"),
    dealerName: document.getElementById("rcDealerName"),
    existingFps: document.getElementById("rcDealerExistingFps"),
    fps: document.getElementById("rcDealerFps"),
    district: document.getElementById("rcDealerDistrict"),
    tehsil: document.getElementById("rcDealerTehsil"),
    mobile: document.getElementById("rcDealerMobile"),
    address: document.getElementById("rcDealerAddress"),
    active: document.getElementById("rcDealerActive"),
    importModeModal: document.getElementById("rcImportModeModal"),
    importUpdateBtn: document.getElementById("rcImportUpdateBtn"),
    importOverwriteBtn: document.getElementById("rcImportOverwriteBtn"),
  };

  const isReadOnly = !!api.readOnly;

  if (!els.search || !api.search) {
    if (!(isReadOnly && api.scopedDealer && api.latest)) return;
  }

  const modal = els.modalEl && window.bootstrap
    ? window.bootstrap.Modal.getOrCreateInstance(els.modalEl)
    : null;
  const importModeModal = els.importModeModal && window.bootstrap
    ? window.bootstrap.Modal.getOrCreateInstance(els.importModeModal)
    : null;
  let importModeResolver = null;

  let selectedDealer = null;
  let gridRows = [];
  let hasImportedData = false;
  let lastQuery = "";
  let searchTimer = null;

  function csrfToken() {
    return els.form?.querySelector('[name="csrf_token"]')?.value ||
      els.uploadForm?.querySelector('[name="csrf_token"]')?.value ||
      api.csrf ||
      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
      "";
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showAlert(el, message) {
    if (!el) return;
    if (!message) {
      el.classList.add("d-none");
      el.textContent = "";
      return;
    }
    el.textContent = message;
    el.classList.remove("d-none");
  }

  function setError(message) { showAlert(els.error, message); }
  function setSuccess(message) { showAlert(els.success, message); }
  function setWarning(message) { showAlert(els.warning, message); }

  function normalizeId(value) {
    return String(value == null ? "" : value).trim().toUpperCase();
  }

  function dealerFpsKeys(row) {
    const keys = [];
    const fps = normalizeId(row && row.fps_id);
    const existing = normalizeId(row && row.existing_fps_id);
    if (fps) keys.push(fps);
    if (existing && existing !== fps) keys.push(existing);
    return keys;
  }

  function splitCsvLine(line) {
    const out = [];
    let cur = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i += 1) {
      const ch = line[i];
      if (inQuotes) {
        if (ch === '"' && line[i + 1] === '"') {
          cur += '"';
          i += 1;
        } else if (ch === '"') {
          inQuotes = false;
        } else {
          cur += ch;
        }
      } else if (ch === '"') {
        inQuotes = true;
      } else if (ch === ",") {
        out.push(cur);
        cur = "";
      } else {
        cur += ch;
      }
    }
    out.push(cur);
    return out;
  }

  function csvFpsIdsFromText(text) {
    const lines = String(text || "").replace(/^\uFEFF/, "").split(/\r\n|\n|\r/);
    let fpsIndex = -1;
    let existingIndex = -1;
    const fpsIds = [];
    const existingIds = [];
    const seenFps = {};
    const seenExisting = {};
    lines.forEach(function (line) {
      if (!line || !line.trim()) return;
      const cells = splitCsvLine(line).map(function (cell) { return cell.trim(); });
      if (fpsIndex < 0) {
        const lowered = cells.map(function (cell) { return cell.toLowerCase(); });
        fpsIndex = lowered.indexOf("fps id");
        existingIndex = lowered.indexOf("existing fps id");
        return;
      }
      if (fpsIndex >= 0) {
        const fps = normalizeId(cells[fpsIndex]);
        if (fps && !seenFps[fps]) {
          seenFps[fps] = true;
          fpsIds.push(fps);
        }
      }
      if (existingIndex >= 0) {
        const existing = normalizeId(cells[existingIndex]);
        if (existing && !seenExisting[existing]) {
          seenExisting[existing] = true;
          existingIds.push(existing);
        }
      }
    });
    return fpsIds.length ? fpsIds : existingIds;
  }

  function readFileText(file) {
    return new Promise(function (resolve, reject) {
      const reader = new FileReader();
      reader.onload = function () { resolve(String(reader.result || "")); };
      reader.onerror = function () { reject(new Error("Unable to read the CSV file.")); };
      reader.readAsText(file);
    });
  }

  function askImportMode() {
    if (!importModeModal) {
      const choice = window.prompt("Existing import found. Type UPDATE or OVERWRITE.", "UPDATE");
      if (!choice) return Promise.resolve(null);
      const value = String(choice).trim().toLowerCase();
      if (value === "update" || value === "overwrite") return Promise.resolve(value);
      return Promise.resolve(null);
    }
    return new Promise(function (resolve) {
      importModeResolver = resolve;
      importModeModal.show();
    });
  }

  function finishImportMode(choice) {
    const done = importModeResolver;
    importModeResolver = null;
    if (importModeModal) importModeModal.hide();
    if (typeof done === "function") done(choice);
  }

  function changeRowClass(status) {
    const key = String(status || "").toLowerCase();
    if (key === "added") return "rc-row-added";
    if (key === "deleted") return "rc-row-deleted";
    if (key === "updated") return "rc-row-updated";
    return "";
  }

  function changeLabel(status) {
    const key = String(status || "").toLowerCase();
    if (key === "added") return "Added";
    if (key === "deleted") return "Deleted";
    if (key === "updated") return "Updated";
    return "";
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

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
  }

  function dealerDisplayName(row) {
    const name = String(row.dealer_name || "").trim();
    const shop = String(row.shop_name || "").trim();
    if (shop && name && shop.toLowerCase() !== name.toLowerCase()) {
      return name + " — " + shop;
    }
    return name || shop;
  }

  function dealerMeta(row) {
    const parts = [];
    if (row.shop_name && row.shop_name !== row.dealer_name) parts.push("Shop: " + row.shop_name);
    if (row.fps_id) parts.push("FPS ID: " + row.fps_id);
    if (row.existing_fps_id) parts.push("Existing FPS: " + row.existing_fps_id);
    if (row.tehsil_name) parts.push("Tehsil: " + row.tehsil_name);
    if (row.district_name) parts.push("District: " + row.district_name);
    if (row.mobile_number) parts.push(row.mobile_number);
    return parts.join(" · ");
  }

  function setSelected(row) {
    selectedDealer = row || null;
    const has = !!selectedDealer;
    if (els.selected) els.selected.classList.toggle("d-none", !has || isReadOnly);
    if (els.fpsBlock) els.fpsBlock.classList.toggle("d-none", !has || isReadOnly);
    if (els.uploadBlock) els.uploadBlock.classList.toggle("d-none", !has);
    highlightSelected();
    if (!has) {
      hasImportedData = false;
      if (els.fpsSearch) els.fpsSearch.value = "";
      if (els.fpsHint) els.fpsHint.textContent = "";
      if (els.printBtn) els.printBtn.disabled = true;
      if (els.pdfBtn) els.pdfBtn.disabled = true;
      return;
    }
    if (els.selectedName) els.selectedName.textContent = dealerDisplayName(selectedDealer);
    if (els.selectedMeta) els.selectedMeta.textContent = dealerMeta(selectedDealer);
    if (els.fpsSearch) els.fpsSearch.value = selectedDealer.fps_id || selectedDealer.existing_fps_id || "";
    if (els.fpsHint) {
      els.fpsHint.textContent = selectedDealer.fps_id
        ? "FPS ID loaded from master. Search to confirm or pick another shop."
        : "Enter FPS ID from the CSV / master, then generate the report.";
    }
  }

  function highlightSelected() {
    if (!els.gridBody) return;
    const selectedId = selectedDealer ? String(selectedDealer.dealer_id) : "";
    Array.from(els.gridBody.querySelectorAll("tr[data-dealer-id]")).forEach(function (tr) {
      tr.classList.toggle("table-active", selectedId && tr.dataset.dealerId === selectedId);
    });
  }

  function renderResults(rows, query) {
    gridRows = Array.isArray(rows) ? rows : [];
    if (!els.gridBody) return;
    els.gridBody.innerHTML = "";
    const found = gridRows.length > 0;
    if (els.empty) {
      els.empty.classList.toggle("d-none", found || !query);
    }
    if (els.count) {
      els.count.textContent = gridRows.length + " record" + (gridRows.length === 1 ? "" : "s");
    }
    if (!found) {
      const tr = document.createElement("tr");
      tr.innerHTML = '<td colspan="8" class="text-muted py-3">No FPS shop or dealer found. Use Add to create one.</td>';
      els.gridBody.appendChild(tr);
      if (els.hint) {
        els.hint.textContent = query
          ? "No FPS shop or dealer matches this search. Use Add to create this ration dealer."
          : "FPS shops load here. Click a row to select it. Edit and Delete are in Actions.";
      }
      return;
    }
    if (els.hint) {
      els.hint.textContent = "Click a row to select it for CSV import. Edit and Delete stay in the Actions column.";
    }
    gridRows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.dealerId = String(row.dealer_id || "");
      const status = row.active_status !== false
        ? '<span class="badge text-bg-success">Active</span>'
        : '<span class="badge text-bg-secondary">Inactive</span>';
      tr.innerHTML =
        "<td>" +
          "<div class=\"rc-dealer-row-name\">" + escapeHtml(dealerDisplayName(row)) + "</div>" +
          (row.shop_name && row.shop_name !== row.dealer_name
            ? "<div class=\"rc-dealer-row-meta\">" + escapeHtml(row.shop_name) + "</div>"
            : "") +
        "</td>" +
        "<td>" + escapeHtml(row.fps_id || "") + "</td>" +
        "<td>" + escapeHtml(row.existing_fps_id || "") + "</td>" +
        "<td>" + escapeHtml(row.district_name || "") + "</td>" +
        "<td>" + escapeHtml(row.tehsil_name || "") + "</td>" +
        "<td>" + escapeHtml(row.mobile_number || "") + "</td>" +
        "<td>" + status + "</td>" +
        '<td class="text-end text-nowrap">' +
          '<button type="button" class="btn btn-sm btn-primary me-1 rc-select-btn">Select</button>' +
          (isReadOnly
            ? ""
            : '<button type="button" class="btn btn-sm btn-outline-primary me-1 rc-edit-btn" title="Edit">' +
              '<i class="bi bi-pencil"></i></button>' +
              '<button type="button" class="btn btn-sm btn-outline-danger rc-delete-btn" title="Delete">' +
              '<i class="bi bi-trash"></i></button>') +
        "</td>";
      tr.addEventListener("click", function (ev) {
        if (ev.target.closest("button")) return;
        selectDealer(row);
      });
      tr.querySelector(".rc-select-btn").addEventListener("click", function (ev) {
        ev.stopPropagation();
        selectDealer(row);
      });
      const editBtn = tr.querySelector(".rc-edit-btn");
      if (editBtn) {
        editBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          openEdit(row);
        });
      }
      const deleteBtn = tr.querySelector(".rc-delete-btn");
      if (deleteBtn) {
        deleteBtn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          deleteDealer(row).catch(function (err) { setError(err.message); });
        });
      }
      els.gridBody.appendChild(tr);
    });
    highlightSelected();
  }

  async function searchDealers(term) {
    const query = String(term == null ? els.search.value : term).trim();
    lastQuery = query;
    const url = new URL(api.search, window.location.origin);
    if (query) url.searchParams.set("q", query);
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    renderResults(data.rows || [], query);
    return data.rows || [];
  }

  function selectDealer(row) {
    setSelected(row);
    setError("");
    if (!isReadOnly) {
      setSuccess("Dealer selected: " + dealerDisplayName(row));
    }
    loadLatest(row.dealer_id);
  }

  function resetForm() {
    els.form.reset();
    els.dealerId.value = "";
    if (els.active) els.active.checked = true;
    showAlert(els.formError, "");
  }

  function fillForm(row) {
    els.dealerId.value = row.dealer_id || "";
    els.dealerName.value = row.dealer_name || "";
    els.existingFps.value = row.existing_fps_id || "";
    els.fps.value = row.fps_id || "";
    els.district.value = row.district_name || "";
    els.tehsil.value = row.tehsil_name || "";
    els.mobile.value = row.mobile_number || "";
    els.address.value = row.address || "";
    els.active.checked = row.active_status !== false;
  }

  function openCreate() {
    if (isReadOnly) return;
    resetForm();
    const typed = (els.search.value || "").trim();
    if (typed && !/fps/i.test(typed) && !/^\d+$/.test(typed)) {
      els.dealerName.value = typed;
    }
    if (/^fps/i.test(typed) || /^\d{8,}$/.test(typed)) {
      if (/^fps/i.test(typed)) els.fps.value = typed;
      else els.existingFps.value = typed;
    }
    if (els.modalTitle) els.modalTitle.textContent = "Add Ration Dealer";
    if (modal) modal.show();
    setTimeout(function () { els.dealerName?.focus(); }, 200);
  }

  function openEdit(row) {
    if (isReadOnly) return;
    const target = row || selectedDealer;
    if (!target) return;
    resetForm();
    fillForm(target);
    if (els.modalTitle) els.modalTitle.textContent = "Edit Ration Dealer";
    if (modal) modal.show();
  }

  async function saveDealer(ev) {
    ev.preventDefault();
    showAlert(els.formError, "");
    const id = parseInt(els.dealerId.value || "0", 10);
    const body = new FormData(els.form);
    if (els.active && els.active.checked) body.set("ActiveStatus", "1");
    else body.set("ActiveStatus", "0");
    body.set("csrf_token", csrfToken());
    const url = id ? apiUrl(api.update, id) : api.create;
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
        body: body,
      });
      const data = await parseJsonResponse(res);
      if (modal) modal.hide();
      await searchDealers(lastQuery);
      selectDealer(data.record);
      setSuccess(data.message || "Ration dealer saved.");
    } catch (err) {
      showAlert(els.formError, err.message || "Unable to save dealer.");
    }
  }

  async function deleteDealer(row) {
    if (isReadOnly) return;
    if (!row || !row.dealer_id || !api.delete) return;
    let creds = null;
    const message = "Delete this FPS / ration dealer? Imported ration-card rows for this shop will also be removed.";
    if (!window.JTCSDeleteConfirm?.ask) {
      const ok = window.JTCSDialog?.confirm
        ? await window.JTCSDialog.confirm(message)
        : window.confirm(message);
      if (!ok) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: message });
      if (!creds) return;
    }
    setError("");
    const res = await fetch(apiUrl(api.delete, row.dealer_id), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": csrfToken() },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password, csrf_token: csrfToken() }) }
        : {}),
    });
    const data = await parseJsonResponse(res);
    if (selectedDealer && String(selectedDealer.dealer_id) === String(row.dealer_id)) {
      setSelected(null);
      if (els.report) els.report.classList.add("d-none");
    }
    await searchDealers(lastQuery);
    setSuccess(data.message || "Ration dealer deleted.");
  }

  async function searchFps() {
    if (isReadOnly) return;
    const fps = (els.fpsSearch.value || "").trim();
    if (!fps) {
      setError("Enter an FPS ID to search.");
      return;
    }
    setError("");
    const url = new URL(api.byFps, window.location.origin);
    url.searchParams.set("fps", fps);
    try {
      const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
      const data = await parseJsonResponse(res);
      if (!data.found || !data.record) {
        if (els.fpsHint) {
          els.fpsHint.textContent = "FPS ID not in master. It will be used as a filter on the uploaded CSV.";
        }
        setWarning("FPS ID not found in dealer master. Generate will filter the CSV by this FPS ID.");
        return;
      }
      selectDealer(data.record);
      if (els.fpsSearch) els.fpsSearch.value = data.record.fps_id || fps;
      setSuccess("FPS matched dealer: " + data.record.dealer_name);
      setWarning("");
    } catch (err) {
      setError(err.message || "Unable to search FPS ID.");
    }
  }

  function schemeClass(scheme) {
    const key = String(scheme || "").toLowerCase();
    if (key === "aay") return "rc-scheme-aay";
    if (key === "phh") return "rc-scheme-phh";
    if (key === "sfy") return "rc-scheme-sfy";
    if (key === "ner") return "rc-scheme-ner";
    return "";
  }

  function hindiClass(scheme) {
    const key = String(scheme || "").toUpperCase();
    if (key === "AAY") return "rc-hindi-aay";
    if (key === "SFY") return "rc-hindi-sfy";
    if (key === "PHH") return "rc-hindi-phh";
    if (key === "NER") return "rc-hindi-ner";
    return "rc-hindi";
  }

  function stripHindiBrackets(name) {
    return String(name || "")
      .replace(/\s*\([^)]*[\u0900-\u097F][^)]*\)\s*/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function toProperCase(name) {
    return String(name || "")
      .trim()
      .split(/\s+/)
      .map(function (word) {
        return word.split("-").map(function (part) {
          if (!part) return part;
          const sep = part.indexOf("'") >= 0 ? "'" : (part.indexOf("’") >= 0 ? "’" : "");
          if (sep) {
            return part.split(sep).map(function (bit) {
              return bit ? bit.charAt(0).toUpperCase() + bit.slice(1).toLowerCase() : bit;
            }).join(sep);
          }
          return part.charAt(0).toUpperCase() + part.slice(1).toLowerCase();
        }).join("-");
      })
      .filter(Boolean)
      .join(" ");
  }

  function renderFullName(member) {
    const hindi = String(member.full_name_hi || "").trim();
    const rawEnglish = String(member.full_name_en || "").trim() ||
      stripHindiBrackets(member.full_name_display || member.full_name || "");
    const english = /[\u0900-\u097F]/.test(rawEnglish) ? rawEnglish : toProperCase(rawEnglish);
    if (english && hindi) {
      return escapeHtml(english) +
        ' <span class="rc-hindi ' + hindiClass(member.scheme_name) + '">(' + escapeHtml(hindi) + ")</span>";
    }
    return escapeHtml(english || hindi);
  }

  function enableExport(enabled) {
    if (els.printBtn) els.printBtn.disabled = !enabled;
    if (els.pdfBtn) els.pdfBtn.disabled = !enabled;
  }

  function renderReport(data) {
    if (!els.report) return;
    const dealer = data.dealer || selectedDealer || {};
    const totals = data.totals || {};
    const gridRows = data.grid_rows || [];
    els.report.classList.remove("d-none");
    if (els.reportSub) {
      const bits = [
        dealer.dealer_name ? "Dealer: " + dealer.dealer_name : "",
        dealer.fps_id ? "FPS ID: " + dealer.fps_id : "",
        dealer.existing_fps_id ? "Existing FPS: " + dealer.existing_fps_id : "",
        (data.districts && data.districts[0]) ? "District: " + data.districts[0] : "",
        data.generated_at ? "Generated: " + data.generated_at : "",
      ].filter(Boolean);
      els.reportSub.textContent = bits.join("  |  ");
    }
    if (els.summary) {
      const chips = [
        ["Cards", totals.card_count],
        ["Members", totals.member_count],
        ["Male", totals.male_count],
        ["Female", totals.female_count],
      ];
      if (totals.added_count || totals.updated_count || totals.deleted_count) {
        chips.push(["Added", totals.added_count || 0]);
        chips.push(["Updated", totals.updated_count || 0]);
        chips.push(["Deleted", totals.deleted_count || 0]);
      }
      if (data.import_mode) chips.push(["Mode", String(data.import_mode)]);
      (data.scheme_summary || []).forEach(function (item) {
        chips.push([item.scheme_name, item.card_count + " cards / " + item.member_count + " members"]);
      });
      els.summary.innerHTML = chips.map(function (item) {
        const extra = item[0] === "Added" ? " rc-chip-added" :
          item[0] === "Deleted" ? " rc-chip-deleted" :
          item[0] === "Updated" ? " rc-chip-updated" : "";
        return '<div class="rc-summary-chip' + extra + '"><strong>' + escapeHtml(item[0]) + ":</strong> " +
          escapeHtml(item[1]) + "</div>";
      }).join("");
    }
    if (els.reportBody) {
      const body = gridRows.map(function (member, index) {
        const status = String(member.change_status || "").toLowerCase();
        const groupRow = member.group_first
          ? '<tr class="rc-grid-group ' + schemeClass(member.group_scheme || member.scheme_name) + '">' +
              '<td colspan="5">' +
                "<strong>Scheme Name:</strong> " + escapeHtml(member.scheme_name) +
                " &nbsp;|&nbsp; <strong>RC Number:</strong> " + escapeHtml(member.rc_number) +
                " &nbsp;|&nbsp; <strong>Members:</strong> " + escapeHtml(member.group_member_count) +
                " &nbsp;|&nbsp; <strong>Male:</strong> " + escapeHtml(member.group_male_count) +
                " &nbsp;|&nbsp; <strong>Female:</strong> " + escapeHtml(member.group_female_count) +
                " &nbsp;|&nbsp; <strong>Age&lt;10:</strong> " + escapeHtml(member.group_age_lt_10) +
                " &nbsp;|&nbsp; <strong>Age&gt;10:</strong> " + escapeHtml(member.group_age_gt_10) +
              "</td>" +
            "</tr>"
          : "";
        const nameBits = renderFullName(member);
        const detail = member.change_detail
          ? '<div class="rc-change-detail">' + escapeHtml(member.change_detail) + "</div>"
          : "";
        const rowClass = [member.is_hof ? "rc-hof-row" : "", changeRowClass(status)].filter(Boolean).join(" ");
        return groupRow + "<tr class=\"" + rowClass + "\">" +
          "<td>" + (index + 1) + "</td>" +
          "<td class=\"" + (member.is_hof ? "rc-hof" : "") + "\">" + nameBits + detail + "</td>" +
          "<td>" + escapeHtml(member.scheme_name) + "</td>" +
          "<td>" + escapeHtml(member.rc_number) + "</td>" +
          "<td class=\"rc-change-cell\">" + escapeHtml(changeLabel(status)) + "</td>" +
        "</tr>";
      }).join("");
      els.reportBody.innerHTML =
        '<table class="table table-sm table-hover align-middle mb-0 rc-import-grid" id="rcImportGrid">' +
          "<colgroup>" +
            '<col class="rc-col-sr">' +
            '<col class="rc-col-name">' +
            '<col class="rc-col-scheme">' +
            '<col class="rc-col-rc">' +
            '<col class="rc-col-change">' +
          "</colgroup>" +
          "<thead><tr>" +
            "<th>#</th><th>Full Name</th><th>Scheme Name</th><th>RC Number</th><th>Change</th>" +
          "</tr></thead>" +
          "<tbody>" + (body || '<tr><td colspan="5" class="text-muted">No rows imported.</td></tr>') + "</tbody>" +
        "</table>";
    }
    if (els.reportFooter) {
      els.reportFooter.textContent =
        "Source: " + (data.file_name || "CSV") +
        "  |  Sort: Scheme Name + RC Number" +
        "  |  Group: Scheme Name + RC Number" +
        (data.batch_id ? "  |  Batch #" + data.batch_id : "");
    }
    enableExport(gridRows.length > 0);
    hasImportedData = gridRows.length > 0;
    els.report.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function loadLatest(dealerId) {
    if (!dealerId || !api.latest) return;
    try {
      const url = new URL(api.latest, window.location.origin);
      url.searchParams.set("dealer_id", String(dealerId));
      const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
      const data = await parseJsonResponse(res);
      if (data.found) renderReport(data);
    } catch (_err) {
      /* latest report is optional */
    }
  }

  async function generateReport(ev) {
    if (ev) ev.preventDefault();
    if (isReadOnly) return;
    setError("");
    setSuccess("");
    setWarning("");
    if (!selectedDealer) {
      setError("Select a ration dealer first.");
      return;
    }
    const dealerKeys = dealerFpsKeys(selectedDealer);
    if (!dealerKeys.length) {
      setError("Selected FPS / ration dealer has no FPS ID. Save FPS ID first.");
      return;
    }
    if (!els.csvFile || !els.csvFile.files || !els.csvFile.files[0]) {
      setError("Browse and select the ration-card CSV file.");
      return;
    }
    const csvFile = els.csvFile.files[0];
    try {
      const csvText = await readFileText(csvFile);
      const csvIds = csvFpsIdsFromText(csvText);
      if (!csvIds.length) {
        setError("CSV file has no FPS ID. Import cancelled.");
        return;
      }
      if (csvIds.length > 1) {
        setError("CSV file has multiple FPS IDs (" + csvIds.join(", ") + "). Import one FPS shop at a time.");
        return;
      }
      if (dealerKeys.indexOf(csvIds[0]) < 0) {
        setError(
          "CSV FPS ID (" + csvIds[0] + ") does not match selected dealer FPS ID (" +
          (selectedDealer.fps_id || selectedDealer.existing_fps_id) + "). Import cancelled."
        );
        return;
      }
      const typed = normalizeId(els.fpsSearch && els.fpsSearch.value);
      if (typed && dealerKeys.indexOf(typed) < 0 && typed !== csvIds[0]) {
        setError("FPS ID entered on screen does not match selected dealer / CSV FPS ID. Import cancelled.");
        return;
      }
    } catch (err) {
      setError(err.message || "Unable to read the CSV file.");
      return;
    }
    let importMode = "";
    if (hasImportedData) {
      importMode = await askImportMode();
      if (!importMode) return;
    }
    const body = new FormData();
    body.append("csrf_token", csrfToken());
    body.append("dealer_id", String(selectedDealer.dealer_id));
    body.append("fps_id", (els.fpsSearch && els.fpsSearch.value) || selectedDealer.fps_id || "");
    body.append("import_mode", importMode);
    body.append("csv_file", csvFile);
    const original = els.generateBtn ? els.generateBtn.innerHTML : "";
      if (els.generateBtn) {
        els.generateBtn.disabled = true;
        els.generateBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Importing…';
      }
    try {
      const res = await fetch(api.generate, {
        method: "POST",
        headers: { Accept: "application/json", "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
        body: body,
      });
      const data = await parseJsonResponse(res);
      if (data.dealer) setSelected(data.dealer);
      renderReport(data);
      const totals = data.totals || {};
      const parts = [];
      if (data.import_mode === "update") parts.push("Updated existing import.");
      if (data.import_mode === "overwrite") parts.push("Rebuilt current report from CSV. Previous import stays saved.");
      parts.push("Grid: " + (totals.card_count || 0) + " cards, " + (totals.member_count || 0) + " members.");
      if (totals.added_count) parts.push("Added " + totals.added_count + " (green).");
      if (totals.updated_count) parts.push("Updated " + totals.updated_count + ".");
      if (totals.deleted_count) parts.push("Deleted " + totals.deleted_count + " (red, still on report).");
      const masterSync = data.master_sync || {};
      if (masterSync.added || masterSync.updated) {
        parts.push(
          "Ration Card Master: " + (masterSync.added || 0) + " added, " +
          (masterSync.updated || 0) + " overwritten (Existing RC Number cleared, Members replaced)."
        );
      }
      parts.push("Use A4 portrait PDF for the report.");
      setSuccess(parts.join(" "));
      if (data.warnings && data.warnings.length) setWarning(data.warnings.join(" "));
    } catch (err) {
      setError(err.message || "Unable to import CSV.");
    } finally {
      if (els.generateBtn) {
        els.generateBtn.disabled = false;
        els.generateBtn.innerHTML = original;
      }
    }
  }

  async function downloadPdf() {
    if (!selectedDealer) {
      setError("Select a ration dealer first.");
      return;
    }
    const layout = window.innerWidth <= 768 ? "mobile" : "desktop";
    setError("");
    const url = new URL(api.pdf, window.location.origin);
    url.searchParams.set("dealer_id", String(selectedDealer.dealer_id));
    url.searchParams.set("layout", layout);
    const original = els.pdfBtn ? els.pdfBtn.innerHTML : "";
    if (els.pdfBtn) {
      els.pdfBtn.disabled = true;
      els.pdfBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> PDF…';
    }
    try {
      const res = await fetch(url.toString(), { headers: { "X-CSRFToken": csrfToken() } });
      const contentType = res.headers.get("content-type") || "";
      if (contentType.includes("application/json")) {
        const data = await res.json();
        throw new Error(data.error || "Unable to create PDF.");
      }
      if (!res.ok) throw new Error("Unable to create PDF.");
      const blob = await res.blob();
      const link = document.createElement("a");
      const disposition = res.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^"]+)"?/i);
      link.href = URL.createObjectURL(blob);
      link.download = match ? match[1] : "RationCard_FPS.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
      setSuccess((layout === "mobile" ? "Mobile " : "Desktop ") + "A4 portrait PDF downloaded.");
    } catch (err) {
      setError(err.message || "Unable to create PDF.");
    } finally {
      if (els.pdfBtn) {
        els.pdfBtn.disabled = false;
        els.pdfBtn.innerHTML = original;
      }
    }
  }

  els.searchBtn?.addEventListener("click", function () {
    searchDealers().catch(function (err) { setError(err.message); });
  });
  els.search?.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") {
      ev.preventDefault();
      searchDealers().catch(function (err) { setError(err.message); });
    }
  });
  els.search?.addEventListener("input", function () {
    const value = els.search.value.trim();
    clearTimeout(searchTimer);
    searchTimer = setTimeout(function () {
      searchDealers(value.length < 2 ? "" : value).catch(function (err) { setError(err.message); });
    }, 280);
  });
  els.addBtn?.addEventListener("click", openCreate);
  els.refreshBtn?.addEventListener("click", function () {
    searchDealers(els.search.value.trim()).catch(function (err) { setError(err.message); });
  });
  els.fpsSearchBtn?.addEventListener("click", function () {
    searchFps().catch(function (err) { setError(err.message); });
  });
  els.fpsSearch?.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter") {
      ev.preventDefault();
      searchFps().catch(function (err) { setError(err.message); });
    }
  });
  els.form?.addEventListener("submit", saveDealer);
  els.uploadForm?.addEventListener("submit", generateReport);
  els.pdfBtn?.addEventListener("click", function () {
    downloadPdf().catch(function (err) { setError(err.message); });
  });
  els.printBtn?.addEventListener("click", function () { window.print(); });
  els.importUpdateBtn?.addEventListener("click", function () { finishImportMode("update"); });
  els.importOverwriteBtn?.addEventListener("click", function () { finishImportMode("overwrite"); });
  els.importModeModal?.addEventListener("hidden.bs.modal", function () {
    if (typeof importModeResolver === "function") finishImportMode(null);
  });
  if (isReadOnly && api.scopedDealer) {
    selectDealer(api.scopedDealer);
  } else {
    searchDealers("").catch(function (err) { setError(err.message); });
  }
})();
