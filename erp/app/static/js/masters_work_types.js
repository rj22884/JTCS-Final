(function () {
  "use strict";

  const gridBody = document.getElementById("workMasterGridBody");
  if (!gridBody) return;

  const els = {
    addBtn: document.getElementById("workMasterAddBtn"),
    editBtn: document.getElementById("workMasterEditBtn"),
    deleteBtn: document.getElementById("workMasterDeleteBtn"),
    refreshBtn: document.getElementById("workMasterRefreshBtn"),
    count: document.getElementById("workMasterCount"),
    empty: document.getElementById("workMasterEmpty"),
    modalEl: document.getElementById("workMasterModal"),
    modalTitle: document.getElementById("workMasterModalTitle"),
    form: document.getElementById("workMasterForm"),
    workId: document.getElementById("workMasterId"),
    workName: document.getElementById("workMasterName"),
  };

  const modal = els.modalEl ? new bootstrap.Modal(els.modalEl) : null;
  let rows = Array.isArray(window.WORK_MASTER_INITIAL_ROWS) ? window.WORK_MASTER_INITIAL_ROWS : [];
  let selectedId = null;

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setToolbarState() {
    const hasSelection = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !hasSelection;
    if (els.deleteBtn) els.deleteBtn.disabled = !hasSelection;
  }

  function clearSelection() {
    selectedId = null;
    gridBody.querySelectorAll("tr.selected").forEach(function (row) {
      row.classList.remove("selected");
    });
    setToolbarState();
  }

  function selectRow(workId) {
    selectedId = workId;
    gridBody.querySelectorAll("tr").forEach(function (row) {
      row.classList.toggle("selected", parseInt(row.dataset.id, 10) === workId);
    });
    setToolbarState();
  }

  function renderGrid(data) {
    rows = data || [];
    gridBody.innerHTML = "";
    if (!rows.length) {
      els.empty?.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      clearSelection();
      return;
    }
    els.empty?.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }

    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.id = String(row.work_id);
      tr.innerHTML =
        "<td>" + escapeHtml(row.work_id) + "</td>" +
        "<td>" + escapeHtml(row.work_name) + "</td>" +
        "<td>" + escapeHtml(row.ledger_kind || window.WORK_MASTER_LEDGER_KIND) + "</td>" +
        "<td class=\"text-end\">" +
        "<button type=\"button\" class=\"btn btn-outline-primary btn-sm me-1 work-master-edit\" data-id=\"" +
        row.work_id +
        "\">Edit</button>" +
        "<button type=\"button\" class=\"btn btn-outline-danger btn-sm work-master-delete\" data-id=\"" +
        row.work_id +
        "\">Delete</button>" +
        "</td>";
      gridBody.appendChild(tr);
    });
    clearSelection();
  }

  function openModal(mode, row) {
    if (!modal) return;
    const isEdit = mode === "edit" && row;
    if (els.modalTitle) {
      els.modalTitle.textContent = isEdit ? "Edit Work Type" : "Add Work Type";
    }
    if (els.workId) els.workId.value = isEdit ? String(row.work_id) : "";
    if (els.workName) els.workName.value = isEdit ? row.work_name || "" : "";
    modal.show();
    if (els.workName) els.workName.focus();
  }

  function loadGrid() {
    const url = window.WORK_MASTER_LIST_URL;
    if (!url) return Promise.resolve();
    return fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || "Unable to load work types.");
        renderGrid(data.rows || []);
      })
      .catch(function (err) {
        if (els.empty) {
          els.empty.textContent = err.message || "Unable to load work types.";
          els.empty.classList.remove("d-none");
        }
      });
  }

  function saveWorkType(event) {
    event.preventDefault();
    const name = (els.workName?.value || "").trim();
    if (!name) {
      alert("Work name is required.");
      return;
    }
    const editId = els.workId?.value || "";
    const payload = {
      work_name: name,
      ledger_kind: window.WORK_MASTER_LEDGER_KIND || "Income",
    };
    const url = editId
      ? apiUrl(window.WORK_MASTER_UPDATE_URL, editId)
      : window.WORK_MASTER_CREATE_URL;
    const method = "POST";

    fetch(url, {
      method: method,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        "X-CSRFToken": window.WORK_MASTER_CSRF || "",
      },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          throw new Error(result.data.error || "Unable to save work type.");
        }
        modal?.hide();
        return loadGrid();
      })
      .catch(function (err) {
        alert(err.message || "Unable to save work type.");
      });
  }

  async function deleteWorkType(workId) {
    if (!workId) return;
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await JTCSDialog.confirm("Deactivate this work type?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Deactivate this work type?" });
      if (!creds) return;
    }
    const url = apiUrl(window.WORK_MASTER_DELETE_URL, workId);
    fetch(url, {
      method: "POST",
      headers: Object.assign(
        { Accept: "application/json", "X-CSRFToken": window.WORK_MASTER_CSRF || "" },
        creds ? { "Content-Type": "application/json" } : {}
      ),
      ...(creds
        ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
        : {}),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.ok) {
          throw new Error(result.data.error || "Unable to delete work type.");
        }
        return loadGrid();
      })
      .catch(function (err) {
        alert(err.message || "Unable to delete work type.");
      });
  }

  els.addBtn?.addEventListener("click", function () {
    openModal("add");
  });

  els.editBtn?.addEventListener("click", function () {
    if (!selectedId) return;
    const row = rows.find(function (item) {
      return item.work_id === selectedId;
    });
    if (row) openModal("edit", row);
  });

  els.deleteBtn?.addEventListener("click", function () {
    if (selectedId) deleteWorkType(selectedId);
  });

  els.refreshBtn?.addEventListener("click", loadGrid);
  els.form?.addEventListener("submit", saveWorkType);

  gridBody.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".work-master-edit");
    if (editBtn) {
      const row = rows.find(function (item) {
        return item.work_id === parseInt(editBtn.dataset.id, 10);
      });
      if (row) openModal("edit", row);
      return;
    }
    const deleteBtn = event.target.closest(".work-master-delete");
    if (deleteBtn) {
      deleteWorkType(parseInt(deleteBtn.dataset.id, 10));
      return;
    }
    const tr = event.target.closest("tr");
    if (tr && tr.dataset.id) {
      selectRow(parseInt(tr.dataset.id, 10));
    }
  });

  renderGrid(rows);
  setToolbarState();
})();
