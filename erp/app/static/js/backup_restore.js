(function () {
  const cfg = window.RESTORE_PAGE || {};
  const statusEl = document.getElementById("restoreStatus");
  const dbBody = document.getElementById("restoreDbBody");
  const fullBody = document.getElementById("restoreFullBody");
  const uploadBtn = document.getElementById("restoreUploadBtn");
  const uploadFile = document.getElementById("restoreUploadFile");
  const uploadKind = document.getElementById("restoreUploadKind");

  function setStatus(message, type) {
    if (!statusEl) return;
    statusEl.className = "alert alert-" + (type || "info") + " mb-3";
    statusEl.textContent = message || "";
    statusEl.classList.toggle("d-none", !message);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function readJson(res) {
    const text = await res.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch (_err) {
      const snippet = (text || "").replace(/\s+/g, " ").slice(0, 180);
      throw new Error(
        res.status === 413
          ? "Backup file is too large for browser upload. Copy the VPS .bak/.zip into the Local data/full folder shown above, refresh, then click Restore."
          : "Local server returned an unexpected response (HTTP " +
              res.status +
              "). " +
              (snippet || "Refresh the page (Ctrl+F5) and try again.")
      );
    }
  }

  function networkErrorMessage(err, action) {
    const raw = (err && err.message) || String(err || "");
    if (/failed to fetch|networkerror|load failed/i.test(raw)) {
      return (
        action +
        " failed — connection dropped. " +
        "Large VPS .bak files: copy into the Local data folder (shown above), then click Restore. " +
        "If the file is under 2 GB, refresh (Ctrl+F5) and retry Upload to Local."
      );
    }
    return raw || action + " failed.";
  }

  function renderRows(bodyEl, rows, kind, emptyText) {
    if (!bodyEl) return;
    if (!rows || !rows.length) {
      bodyEl.innerHTML =
        '<tr class="backup-empty-row"><td colspan="4" class="text-center text-muted py-4">' +
        escapeHtml(emptyText) +
        "</td></tr>";
      return;
    }
    bodyEl.innerHTML = rows
      .map(function (row) {
        return (
          '<tr data-kind="' +
          escapeHtml(kind) +
          '" data-file="' +
          escapeHtml(row.file_name) +
          '">' +
          "<td><code>" +
          escapeHtml(row.file_name) +
          "</code></td>" +
          "<td>" +
          escapeHtml(row.modified_label || "") +
          "</td>" +
          '<td class="text-end">' +
          escapeHtml(row.size_label || "") +
          "</td>" +
          '<td class="text-end">' +
          '<button type="button" class="btn btn-warning btn-sm restore-run-btn" data-kind="' +
          escapeHtml(kind) +
          '" data-file="' +
          escapeHtml(row.file_name) +
          '"><i class="bi bi-arrow-counterclockwise"></i> Restore</button>' +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function refreshList() {
    if (!cfg.listUrl) return;
    const res = await fetch(cfg.listUrl, {
      headers: { "X-Requested-With": "XMLHttpRequest", Accept: "application/json" },
    });
    const data = await readJson(res);
    if (!res.ok || !data.ok) throw new Error(data.error || "Failed to load backups.");
    renderRows(dbBody, data.database || [], "database", "No local database backups yet. Upload a VPS .bak first.");
    renderRows(fullBody, data.full || [], "full", "No local full backups yet. Upload a VPS .zip first.");
  }

  async function uploadBackup() {
    if (!cfg.uploadUrl || !uploadFile || !uploadFile.files || !uploadFile.files[0]) {
      setStatus("Select a .bak or .zip file to upload.", "warning");
      return;
    }
    const file = uploadFile.files[0];
    const kind = (uploadKind && uploadKind.value) || "auto";
    const form = new FormData();
    form.append("file", file, file.name);
    if (kind && kind !== "auto") form.append("kind", kind);
    if (cfg.csrf) form.append("csrf_token", cfg.csrf);

    uploadBtn.disabled = true;
    setStatus(
      "Uploading to local PC: " + file.name + " (" + Math.round(file.size / (1024 * 1024)) + " MB)…",
      "info"
    );
    try {
      const res = await fetch(cfg.uploadUrl, {
        method: "POST",
        headers: {
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
          "X-CSRFToken": cfg.csrf || "",
        },
        body: form,
        credentials: "same-origin",
      });
      const data = await readJson(res);
      if (!res.ok || !data.ok) throw new Error(data.error || "Upload to local failed.");
      setStatus(data.message || "Saved on local PC. Ab Restore dabayein.", "success");
      uploadFile.value = "";
      await refreshList();
    } catch (err) {
      setStatus(networkErrorMessage(err, "Upload to Local"), "danger");
    } finally {
      uploadBtn.disabled = false;
    }
  }

  async function runRestore(kind, fileName) {
    if (!kind || !fileName || !cfg.restoreUrl) return;

    const dbName = cfg.database || "database";
    const confirmMsg =
      kind === "full"
        ? "FULL RESTORE from " +
          fileName +
          "?\n\nThis will REPLACE database [" +
          dbName +
          "] and overwrite application files from the ZIP (.env / venv are preserved).\n\nContinue?"
        : "LOCAL RESTORE — database [" +
          dbName +
          "] from " +
          fileName +
          "?\n\nIs PC ka current data replace ho jayega (VPS backup → local). Continue?";

    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!window.confirm(confirmMsg)) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({
        message: confirmMsg,
        title: "Confirm Restore",
        confirmLabel: "Confirm Restore",
        confirmIcon: "bi-arrow-repeat",
        variant: "warning",
      });
      if (!creds) return;
    }

    setStatus(
      "Restoring " + fileName + " to local database… 1–3 minutes lag sakta hai. Page band mat karein.",
      "info"
    );
    document.querySelectorAll(".restore-run-btn").forEach(function (btn) {
      btn.disabled = true;
    });

    try {
      const body = creds
        ? window.JTCSDeleteConfirm.withCreds({ kind: kind, file_name: fileName }, creds)
        : { kind: kind, file_name: fileName };
      if (cfg.csrf && body && typeof body === "object") body.csrf_token = cfg.csrf;
      const res = await fetch(cfg.restoreUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          Accept: "application/json",
          "X-CSRFToken": cfg.csrf || "",
        },
        body: JSON.stringify(body),
        credentials: "same-origin",
      });
      const data = await readJson(res);
      if (!res.ok || !data.ok) throw new Error(data.error || "Restore failed.");
      setStatus(
        (data.message || "Local restore complete.") +
          " Agar menu/login odd lage to page refresh (Ctrl+F5) karein.",
        "success"
      );
      try {
        await refreshList();
      } catch (_listErr) {
        // DB briefly reconnects after RESTORE — list refresh is optional.
      }
      if (data.reload_recommended) {
        setTimeout(function () {
          setStatus(
            (data.message || "Local restore complete.") +
              " Recommended: Ctrl+F5 se page refresh karein.",
            "success"
          );
        }, 500);
      }
    } catch (err) {
      setStatus(networkErrorMessage(err, "Restore"), "danger");
    } finally {
      document.querySelectorAll(".restore-run-btn").forEach(function (btn) {
        btn.disabled = false;
      });
    }
  }

  uploadBtn?.addEventListener("click", uploadBackup);

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".restore-run-btn");
    if (!btn) return;
    runRestore(btn.getAttribute("data-kind") || "", btn.getAttribute("data-file") || "");
  });
})();
