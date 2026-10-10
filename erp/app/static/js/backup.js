(function () {
  const cfg = window.BACKUP_PAGE || {};
  const createBtn = document.getElementById("backupCreateBtn");
  const statusEl = document.getElementById("backupStatus");
  const bodyEl = document.getElementById("backupGridBody");
  const pollTimers = {};

  function setStatus(message, type) {
    if (!statusEl) return;
    statusEl.className = "alert alert-" + (type || "info") + " mb-3";
    statusEl.textContent = message || "";
    statusEl.classList.toggle("d-none", !message);
  }

  function downloadUrl(fileName) {
    return String(cfg.downloadBase || "").replace("__FILE__", encodeURIComponent(fileName));
  }

  function jobStatusUrl(jobId) {
    return String(cfg.driveJobStatusBase || "").replace("__JOB__", encodeURIComponent(jobId));
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function driveStatusHtml(meta) {
    const status = String((meta && meta.upload_status) || "").toLowerCase();
    if (status === "success") return "Upload successful ✅";
    if (status === "failed") return "Upload failed ❌";
    if (status === "uploading" || status === "queued") {
      const pct = Number((meta && meta.progress_percent) || 0);
      return "Uploading… " + (Number.isFinite(pct) ? pct : 0) + "%";
    }
    return "";
  }

  function setRowDriveStatus(fileName, text, isError) {
    const el = bodyEl?.querySelector('[data-drive-status-for="' + CSS.escape(fileName) + '"]');
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("text-danger", !!isError);
    el.classList.toggle("text-success", !isError && /successful/i.test(text || ""));
  }

  function renderRows(rows) {
    if (!bodyEl) return;
    if (!rows || !rows.length) {
      bodyEl.innerHTML =
        '<tr class="backup-empty-row"><td colspan="4" class="text-center text-muted py-4">No backups yet.</td></tr>';
      return;
    }
    const showDrive = cfg.kind === "database" && !!cfg.driveUploadUrl;
    bodyEl.innerHTML = rows
      .map(function (row) {
        const meta = row.drive_upload || {};
        const statusText = showDrive ? driveStatusHtml(meta) : "";
        const driveBtn = showDrive
          ? '<button type="button" class="btn btn-outline-success btn-sm backup-drive-btn" data-file="' +
            escapeHtml(row.file_name) +
            '" data-drive-status="' +
            escapeHtml(meta.upload_status || "") +
            '">☁ Upload to Drive</button> '
          : "";
        const driveStatus = showDrive
          ? '<div class="backup-drive-status small text-muted mt-1" data-drive-status-for="' +
            escapeHtml(row.file_name) +
            '">' +
            escapeHtml(statusText) +
            "</div>"
          : "";
        return (
          '<tr data-file="' +
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
          '<td class="text-end backup-actions">' +
          '<a class="btn btn-outline-primary btn-sm" href="' +
          downloadUrl(row.file_name) +
          '"><i class="bi bi-download"></i> Download</a> ' +
          driveBtn +
          '<button type="button" class="btn btn-outline-danger btn-sm backup-delete-btn" data-file="' +
          escapeHtml(row.file_name) +
          '"><i class="bi bi-trash"></i></button>' +
          driveStatus +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function refreshList() {
    if (!cfg.listUrl) return;
    const res = await fetch(cfg.listUrl, {
      headers: { "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Failed to load backups.");
    renderRows(data.rows || []);
  }

  async function createBackup() {
    if (!cfg.createUrl) {
      setStatus("Backup URL missing. Refresh the page (Ctrl+F5) and try again.", "danger");
      return;
    }
    const confirmed =
      window.JTCSDialog && typeof window.JTCSDialog.confirm === "function"
        ? await window.JTCSDialog.confirm(
            cfg.kind === "full"
              ? "Create a full backup (database + application ZIP)? This may take a minute."
              : "Create a SQL Server database backup (.bak) now?",
            { title: "Create backup", okLabel: "Create" }
          )
        : window.confirm(
            cfg.kind === "full"
              ? "Create a full backup (database + application ZIP)? This may take a minute."
              : "Create a SQL Server database backup (.bak) now?"
          );
    if (!confirmed) return;
    createBtn.disabled = true;
    setStatus("Creating backup… please wait.", "info");
    try {
      const res = await fetch(cfg.createUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": cfg.csrf || "",
        },
        body: "{}",
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Backup failed.");
      setStatus(data.message || "Backup created.", "success");
      await refreshList();
    } catch (err) {
      setStatus(err.message || String(err), "danger");
    } finally {
      createBtn.disabled = false;
    }
  }

  async function deleteBackup(fileName) {
    if (!fileName || !cfg.deleteUrl) return;
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!(await window.JTCSDialog.confirm("Delete backup file " + fileName + "?"))) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Delete backup file " + fileName + "?",
      });
      if (!creds) return;
    }
    try {
      const res = await fetch(cfg.deleteUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": cfg.csrf || "",
        },
        body: JSON.stringify(
          creds
            ? window.JTCSDeleteConfirm.withCreds({ file_name: fileName }, creds)
            : { file_name: fileName }
        ),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Delete failed.");
      setStatus(data.message || "Deleted.", "success");
      await refreshList();
    } catch (err) {
      setStatus(err.message || String(err), "danger");
    }
  }

  function connectDriveUrl() {
    const base = String(cfg.driveConnectUrl || "");
    const returnTo = encodeURIComponent(cfg.returnTo || window.location.pathname);
    return base + (base.indexOf("?") >= 0 ? "&" : "?") + "return_to=" + returnTo;
  }

  async function ensureDriveConnected() {
    if (!cfg.driveStatusUrl) return { connected: false };
    setStatus("Connecting…", "info");
    const url =
      cfg.driveStatusUrl +
      (cfg.driveStatusUrl.indexOf("?") >= 0 ? "&" : "?") +
      "return_to=" +
      encodeURIComponent(cfg.returnTo || window.location.pathname);
    const res = await fetch(url, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await res.json().catch(function () {
      return {};
    });
    if (data.connected) return data;
    const authorizeUrl = data.authorize_url || connectDriveUrl();
    const go =
      window.JTCSDialog && typeof window.JTCSDialog.confirm === "function"
        ? await window.JTCSDialog.confirm(
            "Google Drive is not connected. Connect Google Drive now?",
            { title: "Connect Google Drive", okLabel: "Connect Google Drive" }
          )
        : window.confirm("Google Drive is not connected. Connect Google Drive now?");
    if (go && authorizeUrl) {
      window.location.href = authorizeUrl;
    }
    return data;
  }

  function stopPoll(fileName) {
    if (pollTimers[fileName]) {
      clearInterval(pollTimers[fileName]);
      delete pollTimers[fileName];
    }
  }

  function pollJob(fileName, jobId) {
    stopPoll(fileName);
    pollTimers[fileName] = setInterval(async function () {
      try {
        const res = await fetch(jobStatusUrl(jobId), {
          headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
        });
        const data = await res.json();
        if (!res.ok || !data.ok) throw new Error(data.error || "Status check failed.");
        const status = String(data.status || "").toLowerCase();
        const pct = Number(data.progress || 0);
        if (status === "uploading" || status === "queued") {
          setRowDriveStatus(fileName, "Uploading… " + pct + "%", false);
          setStatus("Uploading… " + pct + "%", "info");
          return;
        }
        stopPoll(fileName);
        if (status === "success") {
          setRowDriveStatus(fileName, "Upload successful ✅", false);
          setStatus("Upload successful ✅", "success");
          await refreshList();
          return;
        }
        setRowDriveStatus(fileName, "Upload failed ❌", true);
        setStatus((data.error || "Upload failed ❌") + " — use Upload to Drive to retry.", "danger");
      } catch (err) {
        stopPoll(fileName);
        setRowDriveStatus(fileName, "Upload failed ❌", true);
        setStatus(err.message || "Upload status failed.", "danger");
      }
    }, 1500);
  }

  async function uploadToDrive(fileName) {
    if (!fileName || !cfg.driveUploadUrl) return;
    const btn = bodyEl?.querySelector(
      '.backup-drive-btn[data-file="' + CSS.escape(fileName) + '"]'
    );
    if (btn) btn.disabled = true;
    try {
      const connected = await ensureDriveConnected();
      if (!connected.connected) {
        if (btn) btn.disabled = false;
        return;
      }
      setRowDriveStatus(fileName, "Uploading… 0%", false);
      setStatus("Uploading…", "info");
      const res = await fetch(cfg.driveUploadUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": cfg.csrf || "",
        },
        body: JSON.stringify({
          file_name: fileName,
          provider: "google_drive",
          return_to: cfg.returnTo || window.location.pathname,
        }),
      });
      const data = await res.json().catch(function () {
        return {};
      });
      if (data.needs_oauth) {
        setStatus(data.error || "Connect Google Drive first.", "warning");
        if (data.authorize_url) window.location.href = data.authorize_url;
        return;
      }
      if (!res.ok || !data.ok) throw new Error(data.error || "Unable to start upload.");
      pollJob(fileName, data.job_id);
    } catch (err) {
      setRowDriveStatus(fileName, "Upload failed ❌", true);
      setStatus((err.message || "Upload failed ❌") + " — retry with Upload to Drive.", "danger");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  createBtn?.addEventListener("click", function () {
    createBackup().catch(function (err) {
      setStatus(err.message || String(err), "danger");
      if (createBtn) createBtn.disabled = false;
    });
  });
  bodyEl?.addEventListener("click", function (e) {
    const delBtn = e.target.closest(".backup-delete-btn");
    if (delBtn) {
      deleteBackup(delBtn.getAttribute("data-file") || "");
      return;
    }
    const driveBtn = e.target.closest(".backup-drive-btn");
    if (driveBtn) {
      uploadToDrive(driveBtn.getAttribute("data-file") || "");
    }
  });

  if (/[?&]drive_connected=1(?:&|$)/.test(window.location.search || "")) {
    setStatus("Google Drive connected. You can upload backups now.", "success");
  } else if (/[?&]drive_oauth_error=1(?:&|$)/.test(window.location.search || "")) {
    setStatus("Google Drive connection failed. Try Connect again from Upload to Drive.", "danger");
  }
})();
