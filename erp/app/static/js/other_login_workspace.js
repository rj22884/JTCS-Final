(function () {
  const cfg = window.OTHER_LOGIN_WORKSPACE || {};
  const statusEl = document.getElementById("olWorkspaceStatus");
  const errorEl = document.getElementById("olWorkspaceError");
  const portalEl = document.getElementById("olPortalUrl");
  const portalOpen = document.getElementById("olPortalOpen");
  const notesEl = document.getElementById("olNotes");
  const recordsEl = document.getElementById("olRecords");
  const addBtn = document.getElementById("olAddRecord");
  const saveBtn = document.getElementById("olSaveBtn");
  const folderHint = document.getElementById("olFolderHint");
  let records = [];

  function showError(message) {
    if (!errorEl) return;
    errorEl.textContent = message || "";
    errorEl.classList.toggle("d-none", !message);
  }

  function setStatus(message) {
    if (statusEl) statusEl.textContent = message || "";
  }

  function syncPortalLink() {
    if (!portalOpen) return;
    const url = (portalEl && portalEl.value || "").trim();
    portalOpen.href = url || "#";
    portalOpen.classList.toggle("disabled", !url);
  }

  function recordRow(record, index) {
    const wrap = document.createElement("div");
    wrap.className = "ol-record card card-body mb-2";
    wrap.innerHTML = `
      <div class="row g-2">
        <div class="col-md-4">
          <label class="form-label small">Label</label>
          <input class="form-control form-control-sm" data-field="label" value="">
        </div>
        <div class="col-md-4">
          <label class="form-label small">User ID</label>
          <input class="form-control form-control-sm" data-field="user_id" value="">
        </div>
        <div class="col-md-4">
          <label class="form-label small">Password</label>
          <input class="form-control form-control-sm" data-field="password" type="password" value="">
        </div>
        <div class="col-md-4">
          <label class="form-label small">Email</label>
          <input class="form-control form-control-sm" data-field="email" value="">
        </div>
        <div class="col-md-4">
          <label class="form-label small">Mobile</label>
          <input class="form-control form-control-sm" data-field="mobile" value="">
        </div>
        <div class="col-md-4">
          <label class="form-label small">Row notes</label>
          <input class="form-control form-control-sm" data-field="notes" value="">
        </div>
      </div>
      <button type="button" class="btn btn-link btn-sm text-danger px-0 mt-1" data-remove="${index}">Remove</button>
    `;
    wrap.querySelectorAll("[data-field]").forEach((input) => {
      const field = input.getAttribute("data-field");
      input.value = record[field] || "";
      input.addEventListener("input", () => {
        records[index][field] = input.value;
      });
    });
    const removeBtn = wrap.querySelector("[data-remove]");
    if (removeBtn) {
      removeBtn.addEventListener("click", () => {
        records.splice(index, 1);
        renderRecords();
      });
    }
    return wrap;
  }

  function renderRecords() {
    if (!recordsEl) return;
    recordsEl.innerHTML = "";
    records.forEach((record, index) => recordsEl.appendChild(recordRow(record, index)));
  }

  function collectPayload() {
    return {
      portal_url: portalEl ? portalEl.value : "",
      notes: notesEl ? notesEl.value : "",
      records: records.map((row) => ({
        id: row.id || "",
        label: row.label || "",
        user_id: row.user_id || "",
        password: row.password || "",
        email: row.email || "",
        mobile: row.mobile || "",
        notes: row.notes || "",
      })),
    };
  }

  function applyWorkspace(data) {
    if (portalEl) portalEl.value = data.portal_url || "";
    if (notesEl) notesEl.value = data.notes || "";
    records = Array.isArray(data.records) ? data.records.slice() : [];
    renderRecords();
    syncPortalLink();
    if (folderHint) {
      folderHint.textContent = data.folder ? `Folder: ${data.folder}` : "";
    }
  }

  async function api(method, body) {
    const headers = {
      Accept: "application/json",
      "X-Requested-With": "XMLHttpRequest",
      "X-CSRFToken": cfg.csrf || "",
    };
    const options = { method, headers };
    if (body) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    const res = await fetch(cfg.api, options);
    const payload = await res.json().catch(() => ({}));
    if (!res.ok || !payload.ok) {
      throw new Error(payload.error || "Unable to read E:\\Web-Data.");
    }
    return payload.data || {};
  }

  async function load() {
    showError("");
    setStatus("Loading local data…");
    try {
      const data = await api("GET");
      applyWorkspace(data);
      setStatus("Loaded from E:\\Web-Data.");
    } catch (err) {
      showError(err.message);
      setStatus("");
    }
  }

  if (addBtn) {
    addBtn.addEventListener("click", () => {
      records.push({ id: "", label: "", user_id: "", password: "", email: "", mobile: "", notes: "" });
      renderRecords();
    });
  }
  if (portalEl) portalEl.addEventListener("input", syncPortalLink);
  if (saveBtn) {
    saveBtn.addEventListener("click", async () => {
      showError("");
      setStatus("Saving…");
      saveBtn.disabled = true;
      try {
        const data = await api("POST", collectPayload());
        applyWorkspace(data);
        setStatus("Saved to E:\\Web-Data.");
      } catch (err) {
        showError(err.message);
        setStatus("");
      } finally {
        saveBtn.disabled = false;
      }
    });
  }
  load();
})();
