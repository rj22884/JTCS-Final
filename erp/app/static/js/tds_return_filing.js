(function () {
  "use strict";

  const cfg = window.TDS_RF || {};
  const els = {
    body: document.getElementById("tdsRfTableBody"),
    empty: document.getElementById("tdsRfEmpty"),
    selectAll: document.getElementById("tdsRfSelectAll"),
    deleteBtn: document.getElementById("tdsRfDeleteBtn"),
    exportBtn: document.getElementById("tdsRfExportBtn"),
    recentCount: document.getElementById("tdsRfRecentCount"),
    allCount: document.getElementById("tdsRfAllCount"),
  };

  let activeTab = "recent";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function currentRows() {
    return activeTab === "all" ? cfg.all || [] : cfg.recent || [];
  }

  function apiUrl(template, id) {
    return String(template || "").replace("/0", "/" + String(id));
  }

  function render() {
    const rows = currentRows();
    if (els.recentCount) els.recentCount.textContent = String((cfg.recent || []).length);
    if (els.allCount) els.allCount.textContent = String((cfg.all || []).length);

    if (!els.body) return;
    if (!rows.length) {
      els.body.innerHTML = "";
      els.empty?.classList.remove("d-none");
      if (els.selectAll) els.selectAll.checked = false;
      return;
    }
    els.empty?.classList.add("d-none");

    els.body.innerHTML = rows
      .map(function (row) {
        return (
          '<tr data-id="' +
          row.customer_id +
          '">' +
          '<td class="tds-rf-check-col"><input type="checkbox" class="tds-rf-row-check" value="' +
          row.customer_id +
          '"></td>' +
          '<td class="tds-rf-name">' +
          escapeHtml(row.deductor_name) +
          "</td>" +
          "<td>" +
          escapeHtml(row.tan || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(row.location || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(row.deductor_type || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(row.mobile_number || "—") +
          "</td>" +
          '<td class="tds-rf-muted">' +
          escapeHtml(row.email_id || "—") +
          "</td>" +
          '<td class="text-end">' +
          '<a class="tds-rf-edit-btn" href="' +
          escapeHtml(cfg.customerMasterUrl || "/masters/customer") +
          '" title="Edit"><i class="bi bi-pencil"></i></a>' +
          "</td>" +
          "</tr>"
        );
      })
      .join("");

    if (els.selectAll) els.selectAll.checked = false;
  }

  function selectedIds() {
    return Array.from(document.querySelectorAll(".tds-rf-row-check:checked")).map(function (el) {
      return parseInt(el.value, 10);
    });
  }

  function removeLocal(id) {
    cfg.recent = (cfg.recent || []).filter(function (row) {
      return row.customer_id !== id;
    });
    cfg.all = (cfg.all || []).filter(function (row) {
      return row.customer_id !== id;
    });
  }

  async function deleteSelected() {
    const ids = selectedIds();
    if (!ids.length) {
      alert("Select at least one client to delete.");
      return;
    }
    let creds = null;
    if (!window.JTCSDeleteConfirm?.ask) {
      if (!window.confirm("Delete " + ids.length + " selected client(s)?")) return;
    } else {
      creds = await window.JTCSDeleteConfirm.ask({
        message: "Delete " + ids.length + " selected client(s)?",
      });
      if (!creds) return;
    }

    const chain = ids.reduce(function (promise, id) {
      return promise.then(function () {
        return fetch(apiUrl(cfg.deleteUrlTemplate, id), {
          method: "POST",
          headers: Object.assign(
            { Accept: "application/json", "X-CSRFToken": cfg.csrfToken || "" },
            creds ? { "Content-Type": "application/json" } : {}
          ),
          ...(creds
            ? { body: JSON.stringify({ user_id: creds.user_id, password: creds.password }) }
            : {}),
        }).then(function (res) {
          return res.json().then(function (data) {
            if (!res.ok || !data.ok) {
              throw new Error(data.error || "Delete failed for #" + id);
            }
            removeLocal(id);
          });
        });
      });
    }, Promise.resolve());

    chain
      .then(function () {
        render();
      })
      .catch(function (err) {
        alert(err.message || "Delete failed.");
        render();
      });
  }

  function exportCsv() {
    const rows = currentRows();
    const header = [
      "Deductor Name",
      "TAN",
      "Location",
      "Deductor Type",
      "Mobile No.",
      "Email Address",
    ];
    const lines = [header.join(",")].concat(
      rows.map(function (row) {
        return [
          row.deductor_name,
          row.tan,
          row.location,
          row.deductor_type,
          row.mobile_number,
          row.email_id,
        ]
          .map(function (value) {
            const text = String(value == null ? "" : value).replace(/"/g, '""');
            return '"' + text + '"';
          })
          .join(",");
      })
    );
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "deductor-master-" + activeTab + ".csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  document.querySelectorAll(".tds-rf-tab").forEach(function (tab) {
    tab.addEventListener("click", function () {
      activeTab = tab.getAttribute("data-tab") || "recent";
      document.querySelectorAll(".tds-rf-tab").forEach(function (el) {
        el.classList.toggle("is-active", el === tab);
      });
      render();
    });
  });

  if (els.selectAll) {
    els.selectAll.addEventListener("change", function () {
      document.querySelectorAll(".tds-rf-row-check").forEach(function (box) {
        box.checked = !!els.selectAll.checked;
      });
    });
  }

  els.deleteBtn?.addEventListener("click", deleteSelected);
  els.exportBtn?.addEventListener("click", exportCsv);

  // Hide empty page head title leftover for this module.
  const pageTitle = document.querySelector(".jtcs-page-title");
  if (pageTitle && !pageTitle.textContent.trim()) {
    const head = pageTitle.closest(".jtcs-page-head");
    if (head) head.style.display = "none";
  }

  render();
})();
