(function () {
  const cfg = window.BACKUP_PAGE || {};
  const createBtn = document.getElementById("backupCreateBtn");
  const statusEl = document.getElementById("backupStatus");
  const bodyEl = document.getElementById("backupGridBody");

  function setStatus(message, type) {
    if (!statusEl) return;
    statusEl.className = "alert alert-" + (type || "info") + " mb-3";
    statusEl.textContent = message || "";
    statusEl.classList.toggle("d-none", !message);
  }

  function downloadUrl(fileName) {
    return String(cfg.downloadBase || "").replace("__FILE__", encodeURIComponent(fileName));
  }

  function renderRows(rows) {
    if (!bodyEl) return;
    if (!rows || !rows.length) {
      bodyEl.innerHTML =
        '<tr class="backup-empty-row"><td colspan="4" class="text-center text-muted py-4">No backups yet.</td></tr>';
      return;
    }
    bodyEl.innerHTML = rows
      .map(function (row) {
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
          '<td class="text-end">' +
          '<a class="btn btn-outline-primary btn-sm" href="' +
          downloadUrl(row.file_name) +
          '"><i class="bi bi-download"></i> Download</a> ' +
          '<button type="button" class="btn btn-outline-danger btn-sm backup-delete-btn" data-file="' +
          escapeHtml(row.file_name) +
          '"><i class="bi bi-trash"></i></button>' +
          "</td></tr>"
        );
      })
      .join("");
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
    if (!cfg.createUrl) return;
    if (
      !window.confirm(
        cfg.kind === "full"
          ? "Create a full backup (database + application ZIP)? This may take a minute."
          : "Create a SQL Server database backup (.bak) now?"
      )
    ) {
      return;
    }
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
      if (!window.confirm("Delete backup file " + fileName + "?")) return;
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

  createBtn?.addEventListener("click", createBackup);
  bodyEl?.addEventListener("click", function (e) {
    const btn = e.target.closest(".backup-delete-btn");
    if (!btn) return;
    deleteBackup(btn.getAttribute("data-file") || "");
  });
})();
