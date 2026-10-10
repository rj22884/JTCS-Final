(function () {
  const cfg = window.SYSTEM_MAINTENANCE || {};
  const statusEl = document.getElementById("smStatus");
  const scanBtn = document.getElementById("smScanBtn");
  const cleanupBtn = document.getElementById("smCleanupBtn");
  const refreshBtn = document.getElementById("smRefreshSummaryBtn");
  const resultsBox = document.getElementById("smResults");
  const resultSummary = document.getElementById("smResultSummary");
  const resultList = document.getElementById("smResultList");
  const auditBody = document.getElementById("smAuditBody");
  const folderBody = document.getElementById("smFolderBody");

  function setStatus(message, type) {
    if (!statusEl) return;
    statusEl.className = "alert alert-" + (type || "info") + " mb-3";
    statusEl.textContent = message || "";
    statusEl.classList.toggle("d-none", !message);
  }

  function selectedCategories() {
    return Array.prototype.map
      .call(document.querySelectorAll(".sm-cat-check:checked"), function (el) {
        return el.value;
      })
      .filter(Boolean);
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showResults(data) {
    if (!resultsBox || !resultList || !resultSummary) return;
    resultsBox.classList.remove("d-none");
    const totals = data.totals || {};
    resultSummary.textContent =
      data.message ||
      ("Items: " +
        (totals.items || data.items_removed || 0) +
        " · Size: " +
        (totals.bytes_label || data.bytes_freed_label || "0 B"));
    const cats = data.categories || [];
    resultList.innerHTML = cats
      .map(function (cat) {
        return (
          "<li><strong>" +
          escapeHtml(cat.label || cat.key) +
          "</strong>: " +
          escapeHtml(String(cat.items || 0)) +
          " item(s), " +
          escapeHtml(cat.bytes_label || "0 B") +
          (cat.note ? " — " + escapeHtml(cat.note) : "") +
          "</li>"
        );
      })
      .join("");
  }

  function renderFolders(rows) {
    if (!folderBody) return;
    if (!rows || !rows.length) {
      folderBody.innerHTML =
        '<tr><td colspan="4" class="text-muted text-center py-3">No folder data.</td></tr>';
      return;
    }
    folderBody.innerHTML = rows
      .map(function (row) {
        return (
          "<tr><td>" +
          escapeHtml(row.label) +
          "</td><td><code class=\"small\">" +
          escapeHtml(row.path) +
          "</code></td><td class=\"text-end\">" +
          escapeHtml(row.size_label) +
          "</td><td>" +
          (row.protected
            ? '<span class="badge text-bg-secondary">Protected</span>'
            : '<span class="badge text-bg-success">Cleanup eligible</span>') +
          "</td></tr>"
        );
      })
      .join("");
  }

  function renderAudit(rows) {
    if (!auditBody) return;
    if (!rows || !rows.length) {
      auditBody.innerHTML =
        '<tr class="sm-audit-empty"><td colspan="6" class="text-muted text-center py-3">No cleanup actions yet.</td></tr>';
      return;
    }
    auditBody.innerHTML = rows
      .map(function (row) {
        return (
          "<tr><td>" +
          escapeHtml(row.created_at) +
          "</td><td>" +
          escapeHtml(row.action_type) +
          (row.dry_run ? " (dry)" : "") +
          "</td><td><code class=\"small\">" +
          escapeHtml(row.categories) +
          "</code></td><td class=\"text-end\">" +
          escapeHtml(row.items_removed) +
          "</td><td class=\"text-end\">" +
          escapeHtml(row.bytes_freed_label) +
          "</td><td>" +
          escapeHtml(row.actor) +
          "</td></tr>"
        );
      })
      .join("");
  }

  async function refreshSummary() {
    if (!cfg.summaryUrl) return;
    const res = await fetch(cfg.summaryUrl, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Summary failed.");
    const disk = data.disk || {};
    const setText = function (id, value) {
      const el = document.getElementById(id);
      if (el) el.textContent = value || "—";
    };
    setText("smDiskTotal", disk.total_label);
    setText("smDiskUsed", disk.used_label);
    setText("smDiskFree", disk.free_label);
    renderFolders(data.folders || []);
  }

  async function refreshAudit() {
    if (!cfg.auditUrl) return;
    const res = await fetch(cfg.auditUrl, {
      headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
    });
    const data = await res.json();
    if (!res.ok || !data.ok) return;
    renderAudit(data.rows || []);
  }

  async function runScan() {
    const categories = selectedCategories();
    if (!categories.length) {
      setStatus("Select at least one cleanup category.", "warning");
      return;
    }
    scanBtn.disabled = true;
    setStatus("Scanning…", "info");
    try {
      const res = await fetch(cfg.scanUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": cfg.csrf || "",
        },
        body: JSON.stringify({ categories: categories }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Scan failed.");
      showResults(data);
      setStatus(data.message || "Scan complete (nothing deleted).", "success");
      await refreshAudit();
      await refreshSummary();
    } catch (err) {
      setStatus(err.message || String(err), "danger");
    } finally {
      scanBtn.disabled = false;
    }
  }

  async function runCleanup() {
    const categories = selectedCategories();
    if (!categories.length) {
      setStatus("Select at least one cleanup category.", "warning");
      return;
    }
    const confirmed =
      window.JTCSDialog && typeof window.JTCSDialog.confirm === "function"
        ? await window.JTCSDialog.confirm(
            "Run cleanup for the selected categories? Protected areas (DB, backups, uploads, .env, source) will not be touched.",
            { title: "Confirm cleanup", okLabel: "Run Cleanup" }
          )
        : window.confirm("Run cleanup for the selected categories?");
    if (!confirmed) return;
    cleanupBtn.disabled = true;
    setStatus("Cleaning…", "info");
    try {
      const res = await fetch(cfg.cleanupUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          "X-Requested-With": "XMLHttpRequest",
          "X-CSRFToken": cfg.csrf || "",
        },
        body: JSON.stringify({
          categories: categories,
          dry_run: false,
          confirm: true,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Cleanup failed.");
      showResults(data);
      setStatus(data.message || "Cleanup complete.", "success");
      await refreshAudit();
      await refreshSummary();
    } catch (err) {
      setStatus(err.message || String(err), "danger");
    } finally {
      cleanupBtn.disabled = false;
    }
  }

  scanBtn?.addEventListener("click", function () {
    runScan();
  });
  cleanupBtn?.addEventListener("click", function () {
    runCleanup();
  });
  refreshBtn?.addEventListener("click", function () {
    refreshSummary()
      .then(function () {
        setStatus("Disk summary refreshed.", "success");
      })
      .catch(function (err) {
        setStatus(err.message || String(err), "danger");
      });
  });
})();
