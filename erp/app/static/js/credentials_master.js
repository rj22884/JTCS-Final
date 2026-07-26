(function () {
  const els = {
    addBtn: document.getElementById("credAddBtn"),
    addNewBtn: document.getElementById("credAddNewBtn"),
    editBtn: document.getElementById("credEditBtn"),
    deleteBtn: document.getElementById("credDeleteBtn"),
    refreshBtn: document.getElementById("credRefreshBtn"),
    search: document.getElementById("credSearch"),
    count: document.getElementById("credCount"),
    gridBody: document.getElementById("credGridBody"),
    empty: document.getElementById("credEmpty"),
    modalEl: document.getElementById("credModal"),
    modalTitle: document.getElementById("credModalTitle"),
    form: document.getElementById("credForm"),
    credId: document.getElementById("credId"),
    activity: document.getElementById("credActivity"),
    url: document.getElementById("credUrl"),
    userId: document.getElementById("credUserId"),
    password: document.getElementById("credPassword"),
    togglePassword: document.getElementById("credTogglePassword"),
    email: document.getElementById("credEmail"),
    mobile: document.getElementById("credMobile"),
    activeStatus: document.getElementById("credActiveStatus"),
  };

  if (!els.gridBody || !window.CREDENTIALS_MASTER_API) return;

  const modal = els.modalEl && window.bootstrap ? new bootstrap.Modal(els.modalEl) : null;
  let rows = [];
  let selectedId = null;
  let searchTimer = null;

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
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

  function maskPassword(value) {
    if (!value) return "";
    return "••••••••";
  }

  function passwordCellHtml(row) {
    const hasPassword = !!(row.password || "").trim();
    if (!hasPassword) {
      return '<span class="cred-password-text text-muted">—</span>';
    }
    return (
      '<span class="cred-password-wrap d-inline-flex align-items-center gap-1">' +
      '<span class="cred-password-text" data-masked="1" data-password="' +
      escapeHtml(row.password) +
      '">' +
      escapeHtml(maskPassword(row.password)) +
      "</span>" +
      '<button type="button" class="btn btn-sm btn-outline-secondary cred-password-toggle py-0 px-1" ' +
      'title="Show / hide password" aria-label="Show or hide password">' +
      '<i class="bi bi-eye"></i></button>' +
      "</span>"
    );
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

  function setSelected(credentialId) {
    selectedId = credentialId ? parseInt(credentialId, 10) : null;
    const hasSelection = !!selectedId;
    if (els.editBtn) els.editBtn.disabled = !hasSelection;
    if (els.deleteBtn) els.deleteBtn.disabled = !hasSelection;
    Array.from(els.gridBody.querySelectorAll("tr")).forEach(function (row) {
      row.classList.toggle("table-active", parseInt(row.dataset.credentialId, 10) === selectedId);
    });
  }

  function renderRows(data) {
    rows = data || [];
    els.gridBody.innerHTML = "";
    if (!rows.length) {
      if (els.empty) els.empty.classList.remove("d-none");
      if (els.count) els.count.textContent = "0 records";
      setSelected(null);
      return;
    }
    if (els.empty) els.empty.classList.add("d-none");
    if (els.count) {
      els.count.textContent = rows.length + " record" + (rows.length === 1 ? "" : "s");
    }

    rows.forEach(function (row) {
      const tr = document.createElement("tr");
      tr.dataset.credentialId = String(row.credential_id);
      const urlHtml = row.url
        ? '<a href="' + escapeHtml(row.url) + '" target="_blank" rel="noopener noreferrer" class="cred-url-link">' +
          escapeHtml(row.url) + "</a>"
        : "";
      tr.innerHTML =
        "<td>" + escapeHtml(row.activity) + "</td>" +
        '<td class="cred-url-cell" title="' + escapeHtml(row.url) + '">' + urlHtml + "</td>" +
        "<td>" + escapeHtml(row.user_id) + "</td>" +
        "<td>" + passwordCellHtml(row) + "</td>" +
        "<td>" + escapeHtml(row.email_id) + "</td>" +
        "<td>" + escapeHtml(row.mobile_number) + "</td>" +
        "<td>" + (row.active_status
          ? '<span class="badge text-bg-success">Active</span>'
          : '<span class="badge text-bg-secondary">Inactive</span>') + "</td>" +
        '<td class="text-end text-nowrap">' +
          '<button type="button" class="btn btn-sm btn-outline-primary me-1 cred-edit-btn" data-id="' + row.credential_id + '" title="Edit"><i class="bi bi-pencil"></i></button>' +
          '<button type="button" class="btn btn-sm btn-outline-danger cred-delete-btn" data-id="' + row.credential_id + '" title="Delete"><i class="bi bi-trash"></i></button>' +
        "</td>";
      tr.addEventListener("click", function (ev) {
        if (ev.target.closest("button") || ev.target.closest("a")) return;
        setSelected(row.credential_id);
      });
      els.gridBody.appendChild(tr);
    });
    setSelected(selectedId);
  }

  async function loadRows(search) {
    const url = new URL(window.CREDENTIALS_MASTER_API.list, window.location.origin);
    if (search) url.searchParams.set("search", search);
    const res = await fetch(url.toString(), { headers: { Accept: "application/json" } });
    const data = await parseJsonResponse(res);
    renderRows(data.rows || []);
  }

  function resetForm() {
    els.form.reset();
    els.credId.value = "";
    if (els.password) els.password.type = "password";
    if (els.activeStatus) els.activeStatus.checked = true;
  }

  function openCreate() {
    resetForm();
    if (els.modalTitle) els.modalTitle.textContent = "Add Credential";
    if (modal) modal.show();
    els.activity?.focus();
  }

  async function openEdit(credentialId) {
    const res = await fetch(apiUrl(window.CREDENTIALS_MASTER_API.record, credentialId), {
      headers: { Accept: "application/json" },
    });
    const data = await parseJsonResponse(res);
    const row = data.record;
    els.credId.value = row.credential_id;
    els.activity.value = row.activity || "";
    els.url.value = row.url || "";
    els.userId.value = row.user_id || "";
    els.password.value = row.password || "";
    els.email.value = row.email_id || "";
    els.mobile.value = row.mobile_number || "";
    els.activeStatus.checked = !!row.active_status;
    if (els.password) els.password.type = "password";
    if (els.modalTitle) els.modalTitle.textContent = "Edit Credential";
    if (modal) modal.show();
  }

  async function deleteRecord(credentialId) {
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!window.confirm("Delete / deactivate this credential?")) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({ message: "Delete / deactivate this credential?" });
      if (!creds) return;
    }
    const res = await fetch(apiUrl(window.CREDENTIALS_MASTER_API.delete, credentialId), {
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
    selectedId = null;
    await loadRows(els.search ? els.search.value.trim() : "");
  }

  els.form.addEventListener("submit", async function (ev) {
    ev.preventDefault();
    const id = els.credId.value ? parseInt(els.credId.value, 10) : null;
    const url = id
      ? apiUrl(window.CREDENTIALS_MASTER_API.update, id)
      : window.CREDENTIALS_MASTER_API.create;
    const body = new FormData(els.form);
    if (!els.activeStatus.checked) body.set("ActiveStatus", "0");
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { Accept: "application/json", "X-CSRFToken": csrfToken() },
        body: body,
      });
      const data = await parseJsonResponse(res);
      alert(data.message || "Saved.");
      if (modal) modal.hide();
      await loadRows(els.search ? els.search.value.trim() : "");
    } catch (err) {
      alert(err.message || "Save failed.");
    }
  });

  els.gridBody.addEventListener("click", function (ev) {
    const toggleBtn = ev.target.closest(".cred-password-toggle");
    if (toggleBtn) {
      ev.preventDefault();
      ev.stopPropagation();
      const wrap = toggleBtn.closest(".cred-password-wrap");
      const textEl = wrap?.querySelector(".cred-password-text");
      const icon = toggleBtn.querySelector("i");
      if (!textEl) return;
      const shown = textEl.getAttribute("data-masked") === "0";
      if (shown) {
        textEl.textContent = maskPassword(textEl.getAttribute("data-password") || "");
        textEl.setAttribute("data-masked", "1");
        if (icon) icon.className = "bi bi-eye";
        toggleBtn.title = "Show password";
      } else {
        textEl.textContent = textEl.getAttribute("data-password") || "";
        textEl.setAttribute("data-masked", "0");
        if (icon) icon.className = "bi bi-eye-slash";
        toggleBtn.title = "Hide password";
      }
      return;
    }

    const editBtn = ev.target.closest(".cred-edit-btn");
    const deleteBtn = ev.target.closest(".cred-delete-btn");
    if (editBtn) {
      openEdit(editBtn.dataset.id).catch(function (err) {
        alert(err.message || "Unable to load record.");
      });
    } else if (deleteBtn) {
      deleteRecord(deleteBtn.dataset.id).catch(function (err) {
        alert(err.message || "Unable to delete.");
      });
    }
  });

  els.togglePassword?.addEventListener("click", function () {
    if (!els.password) return;
    const show = els.password.type === "password";
    els.password.type = show ? "text" : "password";
    const icon = els.togglePassword.querySelector("i");
    if (icon) {
      icon.className = show ? "bi bi-eye-slash" : "bi bi-eye";
    }
  });

  if (els.addBtn) els.addBtn.addEventListener("click", openCreate);
  if (els.addNewBtn) els.addNewBtn.addEventListener("click", openCreate);
  if (els.editBtn) {
    els.editBtn.addEventListener("click", function () {
      if (!selectedId) return;
      openEdit(selectedId).catch(function (err) {
        alert(err.message || "Unable to load record.");
      });
    });
  }
  if (els.deleteBtn) {
    els.deleteBtn.addEventListener("click", function () {
      if (!selectedId) return;
      deleteRecord(selectedId).catch(function (err) {
        alert(err.message || "Unable to delete.");
      });
    });
  }
  if (els.refreshBtn) {
    els.refreshBtn.addEventListener("click", function () {
      loadRows(els.search ? els.search.value.trim() : "").catch(function (err) {
        alert(err.message || "Unable to refresh.");
      });
    });
  }
  if (els.search) {
    els.search.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        loadRows(els.search.value.trim()).catch(function () {});
      }, 250);
    });
  }

  renderRows(window.CREDENTIALS_MASTER_INITIAL_ROWS || []);
})();
