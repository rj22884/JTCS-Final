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
    subWorkType: document.getElementById("swSubWorkType"),
  };

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let searchTimer = null;
  const workGroups = window.SUB_WORK_GROUPS || {};

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
    return (checked && checked.value) || "Misc.";
  }

  function setLedgerKind(kind) {
    const value = kind || "Misc.";
    document.querySelectorAll('input[name="swLedgerKind"]').forEach(function (radio) {
      radio.checked = radio.value === value;
    });
  }

  function ledgerBadge(kind) {
    if (kind === "Expense") return '<span class="badge text-bg-danger">Expense</span>';
    if (kind === "Misc.") return '<span class="badge text-bg-warning text-dark">Misc.</span>';
    if (kind === "Income") return '<span class="badge text-bg-success">Income</span>';
    return '<span class="badge text-bg-secondary">' + escapeHtml(kind || "-") + "</span>";
  }

  function fillWorkOptions(kind, selectedWorkId, selectedWorkName) {
    if (!els.workId) return;
    const rows = workGroups[kind] || [];
    els.workId.innerHTML = '<option value="">-- Select Work --</option>';
    rows.forEach(function (row) {
      const opt = document.createElement("option");
      opt.value = String(row.work_id);
      opt.textContent = row.work_name;
      opt.dataset.workName = row.work_name || "";
      els.workId.appendChild(opt);
    });
    if (selectedWorkId && Array.from(els.workId.options).some(function (o) {
      return o.value === String(selectedWorkId);
    })) {
      els.workId.value = String(selectedWorkId);
      return;
    }
    if (selectedWorkName) {
      const match = Array.from(els.workId.options).find(function (o) {
        return (o.dataset.workName || o.textContent) === selectedWorkName;
      });
      if (match) els.workId.value = match.value;
    }
  }

  function loadWorksFromApi(kind, selectedWorkId, selectedWorkName) {
    if (!api.works) {
      fillWorkOptions(kind, selectedWorkId, selectedWorkName);
      return Promise.resolve();
    }
    const url = api.works + "?ledger_kind=" + encodeURIComponent(kind || "");
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
        workGroups[kind] = rows;
        fillWorkOptions(kind, selectedWorkId, selectedWorkName);
      })
      .catch(function () {
        fillWorkOptions(kind, selectedWorkId, selectedWorkName);
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

  function loadRows() {
    const params = new URLSearchParams();
    const q = (els.search?.value || "").trim();
    const kind = (els.filterKind?.value || "").trim();
    if (q) params.set("search", q);
    if (kind) params.set("ledger_kind", kind);
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
    if (els.subWorkType) els.subWorkType.value = "";
    setLedgerKind("Misc.");
    if (els.modalTitle) els.modalTitle.textContent = "Add Sub Work";
    loadWorksFromApi("Misc.", null, null).then(function () {
      modal?.show();
      els.workId?.focus();
    });
  }

  function openEdit(id) {
    fetch(apiUrl(api.record, id), {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Unable to load.");
          return data.record;
        });
      })
      .then(function (record) {
        if (els.id) els.id.value = String(record.work_type_id || "");
        if (els.subWorkType) els.subWorkType.value = record.sub_work_type || "";
        const kind = record.ledger_kind || "Misc.";
        setLedgerKind(kind);
        if (els.modalTitle) els.modalTitle.textContent = "Edit Sub Work";
        return loadWorksFromApi(kind, record.work_id, record.work_name || record.work_type_name).then(
          function () {
            modal?.show();
          }
        );
      })
      .catch(function (err) {
        alert(err.message || "Unable to load.");
      });
  }

  function save(event) {
    event.preventDefault();
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
    const url = id ? apiUrl(api.update, id) : api.create;
    fetch(url, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "X-CSRFToken": window.SUB_WORK_CSRF || "",
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

  async function remove(id) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!window.confirm("Delete this sub work?")) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete this sub work?" });
      if (!creds) return;
    }
    fetch(apiUrl(api.delete, id), {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": window.SUB_WORK_CSRF || "", "X-Requested-With": "XMLHttpRequest" },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok || !data.ok) throw new Error(data.error || "Delete failed.");
          return data;
        });
      })
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
      loadWorksFromApi(selectedLedgerKind(), null, null);
    });
  });

  els.addBtn?.addEventListener("click", openAdd);
  els.addNewBtn?.addEventListener("click", openAdd);
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

  renderRows(window.SUB_WORK_INITIAL_ROWS || []);
})();
