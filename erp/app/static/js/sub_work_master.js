(function () {
  "use strict";

  const api = window.SUB_WORK_API;
  if (!api) return;

  const els = {
    addBtn: document.getElementById("swAddBtn"),
    addNewBtn: document.getElementById("swAddNewBtn"),
    refreshBtn: document.getElementById("swRefreshBtn"),
    filterKind: document.getElementById("swFilterKind"),
    search: document.getElementById("swSearch"),
    count: document.getElementById("swCount"),
    body: document.getElementById("swGridBody"),
    empty: document.getElementById("swEmpty"),
    status: document.getElementById("swStatus"),
    modalEl: document.getElementById("swModal"),
    modalTitle: document.getElementById("swModalTitle"),
    form: document.getElementById("swForm"),
    id: document.getElementById("swId"),
    workId: document.getElementById("swWorkId"),
    underGroup: document.getElementById("swUnderGroup"),
    underGroupWrap: document.getElementById("swUnderGroupWrap"),
    subWorkType: document.getElementById("swSubWorkType"),
  };

  let searchTimer = null;
  let cachedRows = [];
  let saving = false;
  const workGroups = { Income: [], Expense: [], "Misc.": [] };

  function normalizeKind(kind) {
    const raw = String(kind == null ? "" : kind).trim();
    if (!raw) return "";
    const lower = raw.toLowerCase().replace(/\s+/g, "").replace(/\.+$/, "");
    if (lower === "misc") return "Misc.";
    if (lower === "income") return "Income";
    if (lower === "expense") return "Expense";
    return raw;
  }

  function ingestGroups(raw) {
    Object.keys(raw || {}).forEach(function (key) {
      const rows = raw[key] || [];
      rows.forEach(function (row) {
        const k = normalizeKind(row.ledger_kind || key);
        if (!workGroups[k]) workGroups[k] = [];
        workGroups[k].push(row);
      });
    });
  }
  ingestGroups(window.SUB_WORK_GROUPS);

  function worksForKind(kind) {
    const want = normalizeKind(kind);
    const direct = workGroups[want] || [];
    if (direct.length) return direct;
    const aliases = [want, "Misc.", "Misc", "misc", "MISC."];
    for (let i = 0; i < aliases.length; i += 1) {
      const rows = workGroups[aliases[i]];
      if (rows && rows.length && normalizeKind(aliases[i]) === want) return rows;
    }
    return [];
  }

  function getModal() {
    if (!els.modalEl) return null;
    if (!window.bootstrap || !bootstrap.Modal) return null;
    return bootstrap.Modal.getOrCreateInstance(els.modalEl);
  }

  function showModal() {
    const inst = getModal();
    if (inst) {
      inst.show();
      return;
    }
    if (!els.modalEl) return;
    els.modalEl.classList.add("show");
    els.modalEl.style.display = "block";
    els.modalEl.setAttribute("aria-hidden", "false");
    document.body.classList.add("modal-open");
  }

  function hideModal() {
    const inst = getModal();
    if (inst) {
      inst.hide();
      return;
    }
    if (!els.modalEl) return;
    els.modalEl.classList.remove("show");
    els.modalEl.style.display = "none";
    els.modalEl.setAttribute("aria-hidden", "true");
    document.body.classList.remove("modal-open");
  }

  function parseJsonResponse(res) {
    const contentType = res.headers.get("content-type") || "";
    return res.text().then(function (text) {
      let data = {};
      if (contentType.indexOf("application/json") >= 0 && text) {
        try {
          data = JSON.parse(text);
        } catch (err) {
          throw new Error("Server returned invalid JSON.");
        }
      } else if (text && text.trim().charAt(0) === "{") {
        try {
          data = JSON.parse(text);
        } catch (err) {
          data = {};
        }
      }
      if (!res.ok || data.ok === false) {
        throw new Error(data.error || data.message || "Request failed (HTTP " + res.status + ").");
      }
      return data;
    });
  }

  function csrfToken() {
    return (
      window.SUB_WORK_CSRF ||
      els.form?.querySelector('[name="csrf_token"]')?.value ||
      ""
    );
  }

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

  function selectedLedgerKind() {
    const checked = document.querySelector('input[name="swLedgerKind"]:checked');
    return normalizeKind((checked && checked.value) || "Misc.");
  }

  function isMiscKind(kind) {
    return normalizeKind(kind) === "Misc.";
  }

  function syncChartGroupVisibility() {
    const misc = isMiscKind(selectedLedgerKind());
    els.underGroupWrap?.classList.toggle("d-none", misc);
    if (misc && els.underGroup) els.underGroup.value = "";
  }

  function setLedgerKind(kind) {
    const value = normalizeKind(kind);
    document.querySelectorAll('input[name="swLedgerKind"]').forEach(function (radio) {
      radio.checked = normalizeKind(radio.value) === value;
    });
    syncChartGroupVisibility();
  }

  function ledgerBadge(kind) {
    if (kind === "Expense") return '<span class="badge text-bg-danger">Expense</span>';
    if (kind === "Misc.") return '<span class="badge text-bg-warning text-dark">Misc.</span>';
    if (kind === "Income") return '<span class="badge text-bg-success">Income</span>';
    return '<span class="badge text-bg-secondary">' + escapeHtml(kind || "-") + "</span>";
  }

  function syncUnderGroupFromWork() {
    if (!els.underGroup || !els.workId) return;
    if (isMiscKind(selectedLedgerKind())) {
      els.underGroup.value = "";
      return;
    }
    const opt = els.workId.selectedOptions && els.workId.selectedOptions[0];
    const label = (opt && opt.dataset.underGroup) || "";
    els.underGroup.value = label || "";
  }

  function fillWorkOptions(kind, selectedWorkId, selectedWorkName) {
    if (typeof window.swFillWorkOptions === "function") {
      const filled = window.swFillWorkOptions(kind, selectedWorkId, selectedWorkName);
      if (filled) {
        syncUnderGroupFromWork();
        return;
      }
    }
    if (!els.workId) return;
    const rows = worksForKind(kind);
    els.workId.innerHTML = '<option value="">-- Select Work --</option>';
    rows.forEach(function (row) {
      const opt = document.createElement("option");
      opt.value = String(row.work_id);
      opt.textContent = row.work_name;
      opt.dataset.workName = row.work_name || "";
      opt.dataset.underGroup = row.under_group || "";
      opt.dataset.kind = normalizeKind(row.ledger_kind || kind);
      if (row.chart_group_id != null) {
        opt.dataset.chartGroupId = String(row.chart_group_id);
      }
      els.workId.appendChild(opt);
    });
    if (selectedWorkId && Array.from(els.workId.options).some(function (o) {
      return o.value === String(selectedWorkId);
    })) {
      els.workId.value = String(selectedWorkId);
      syncUnderGroupFromWork();
      return;
    }
    if (selectedWorkName) {
      const match = Array.from(els.workId.options).find(function (o) {
        return (o.dataset.workName || o.textContent) === selectedWorkName;
      });
      if (match) els.workId.value = match.value;
    }
    syncUnderGroupFromWork();
  }

  function loadWorksFromApi(kind, selectedWorkId, selectedWorkName) {
    const want = normalizeKind(kind);
    fillWorkOptions(want, selectedWorkId, selectedWorkName);
    if (!api || !api.works) {
      return Promise.resolve();
    }
    // Do not put "Misc." at the end of the URL — some stacks drop a trailing ".".
    const params = new URLSearchParams();
    params.set("ledger_kind", want === "Misc." ? "misc" : want);
    const join = String(api.works).indexOf("?") >= 0 ? "&" : "?";
    const url = api.works + join + params.toString();
    return fetch(url, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load works.");
          return data.rows || [];
        });
      })
      .then(function (rows) {
        if (rows && rows.length) {
          workGroups[want] = rows;
        }
        fillWorkOptions(want, selectedWorkId, selectedWorkName);
      })
      .catch(function () {
        fillWorkOptions(want, selectedWorkId, selectedWorkName);
      });
  }

  function renderRows(rows) {
    if (!els.body) return;
    cachedRows = rows || [];
    els.body.innerHTML = "";
    const hideChart = isMiscKind(els.filterKind?.value);
    document.querySelectorAll(".sw-col-chart").forEach(function (el) {
      el.classList.toggle("d-none", hideChart);
    });
    if (!cachedRows.length) {
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = cachedRows.length + " record" + (cachedRows.length === 1 ? "" : "s");
    }
    cachedRows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.id = String(row.work_type_id);
      tr.innerHTML =
        "<td>" +
        escapeHtml(row.work_type_id) +
        "</td>" +
        "<td>" +
        ledgerBadge(row.ledger_kind) +
        "</td>" +
        "<td>" +
        escapeHtml(row.work_name || row.work_type_name) +
        "</td>" +
        '<td class="sw-col-chart">' +
        escapeHtml(isMiscKind(row.ledger_kind) ? "—" : row.under_group || "—") +
        "</td>" +
        "<td>" +
        escapeHtml(row.sub_work_type) +
        "</td>" +
        "<td>" +
        (row.active_status
          ? '<span class="badge text-bg-success">Active</span>'
          : '<span class="badge text-bg-secondary">Inactive</span>') +
        "</td>" +
        '<td class="text-end text-nowrap">' +
        '<button type="button" class="btn btn-outline-primary btn-sm me-1 sw-edit" data-id="' +
        row.work_type_id +
        '"><i class="bi bi-pencil"></i> Edit</button>' +
        '<button type="button" class="btn btn-outline-danger btn-sm sw-delete" data-id="' +
        row.work_type_id +
        '"><i class="bi bi-trash"></i> Delete</button>' +
        "</td>";
      els.body.appendChild(tr);
    });
  }

  function isDuplicateSubWork(workName, subWorkType, excludeId) {
    const name = String(workName || "").trim().toLowerCase();
    const sub = String(subWorkType || "").trim().toLowerCase();
    if (!name || !sub) return false;
    return cachedRows.some(function (row) {
      if (excludeId && String(row.work_type_id) === String(excludeId)) return false;
      const rowName = String(row.work_name || row.work_type_name || "").trim().toLowerCase();
      const rowSub = String(row.sub_work_type || "").trim().toLowerCase();
      return rowName === name && rowSub === sub;
    });
  }

  function loadRows() {
    const params = new URLSearchParams();
    const q = (els.search?.value || "").trim();
    const kind = normalizeKind(els.filterKind?.value || "");
    if (q) params.set("search", q);
    if (kind) params.set("ledger_kind", kind === "Misc." ? "misc" : kind);
    return fetch(api.list + "?" + params.toString(), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(parseJsonResponse)
      .then(function (data) {
        renderRows(data.rows || []);
      })
      .catch(function (err) {
        showStatus(err.message || "Load failed.", "danger");
      });
  }

  function openAdd() {
    if (els.id) els.id.value = "";
    if (els.subWorkType) els.subWorkType.value = "";
    if (els.underGroup) els.underGroup.value = "";
    setLedgerKind("Misc.");
    if (els.modalTitle) els.modalTitle.textContent = "Add Sub Work";
    fillWorkOptions("Misc.", null, null);
    syncChartGroupVisibility();
    showModal();
    return loadWorksFromApi("Misc.", null, null)
      .then(function () {
        syncChartGroupVisibility();
        els.workId?.focus();
      })
      .catch(function (err) {
        showStatus(err.message || "Unable to load works.", "danger");
      });
  }

  function openEdit(id) {
    fetch(apiUrl(api.record, id), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(parseJsonResponse)
      .then(function (data) {
        return data.record;
      })
      .then(function (record) {
        if (els.id) els.id.value = String(record.work_type_id || "");
        if (els.subWorkType) els.subWorkType.value = record.sub_work_type || "";
        const kind = record.ledger_kind || "Misc.";
        setLedgerKind(kind);
        if (els.modalTitle) els.modalTitle.textContent = "Edit Sub Work";
        return loadWorksFromApi(kind, record.work_id, record.work_name || record.work_type_name).then(
          function () {
            syncChartGroupVisibility();
            showModal();
          }
        );
      })
      .catch(function (err) {
        alert(err.message || "Unable to load.");
      });
  }

  function save(event) {
    if (event) event.preventDefault();
    if (saving) return;
    const id = (els.id?.value || "").trim();
    const kind = selectedLedgerKind();
    const workOption = els.workId?.selectedOptions?.[0];
    const payload = {
      ledger_kind: kind,
      work_id: (els.workId?.value || "").trim(),
      work_name: (workOption && (workOption.dataset.workName || workOption.textContent)) || "",
      sub_work_type: (els.subWorkType?.value || "").trim(),
    };
    if (!payload.work_id) {
      alert("Select Work Name (from Work Master).");
      els.workId?.focus();
      return;
    }
    if (!payload.sub_work_type) {
      alert("Sub Work Type is required.");
      els.subWorkType?.focus();
      return;
    }
    if (isDuplicateSubWork(payload.work_name, payload.sub_work_type, id)) {
      alert(
        "'" + payload.sub_work_type + "' already exists under '" + payload.work_name + "'."
      );
      els.subWorkType?.focus();
      return;
    }
    const url = id ? apiUrl(api.update, id) : api.create;
    saving = true;
    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken(),
        "X-Requested-With": "XMLHttpRequest",
      },
      body: JSON.stringify(payload),
    })
      .then(parseJsonResponse)
      .then(function (data) {
        hideModal();
        showStatus(data.message || "Saved.", "success");
        return loadRows();
      })
      .catch(function (err) {
        alert(err.message || "Save failed.");
      })
      .then(function () {
        saving = false;
      });
  }

  async function remove(id) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Delete this sub work?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this sub work?" });
      if (!creds) return;
    }
    const headers = {
      Accept: "application/json",
      "X-CSRFToken": csrfToken(),
      "X-Requested-With": "XMLHttpRequest",
    };
    const options = { method: "POST", headers: headers };
    if (creds) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify({
        user_id: creds.user_id,
        password: creds.password,
      });
    }
    fetch(apiUrl(api.delete, id), options)
      .then(parseJsonResponse)
      .then(function (data) {
        showStatus(data.message || "Deleted.", "info");
        return loadRows();
      })
      .catch(function (err) {
        alert(err.message || "Delete failed.");
      });
  }

  document.querySelectorAll('input[name="swLedgerKind"]').forEach(function (radio) {
    radio.addEventListener("change", function () {
      syncChartGroupVisibility();
      loadWorksFromApi(selectedLedgerKind(), null, null);
    });
  });

  els.workId?.addEventListener("change", syncUnderGroupFromWork);

  document.addEventListener("click", function (event) {
    const addBtn = event.target.closest("#swAddBtn, #swAddNewBtn");
    if (addBtn) {
      openAdd();
    }
  });
  els.refreshBtn?.addEventListener("click", loadRows);
  els.form?.addEventListener("submit", save);
  els.filterKind?.addEventListener("change", loadRows);
  els.search?.addEventListener("input", function () {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadRows, 250);
  });
  els.body?.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".sw-edit");
    if (editBtn) {
      openEdit(editBtn.getAttribute("data-id"));
      return;
    }
    const delBtn = event.target.closest(".sw-delete");
    if (delBtn) remove(delBtn.getAttribute("data-id"));
  });

  try {
    renderRows(window.SUB_WORK_INITIAL_ROWS || []);
  } catch (err) {
    showStatus((err && err.message) || "Unable to render list.", "danger");
  }
  loadRows();
})();
