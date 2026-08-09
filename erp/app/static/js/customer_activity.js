(function () {
  const cfg = window.CUSTOMER_ACTIVITY;
  if (!cfg) return;

  const els = {
    refresh: document.getElementById("caRefreshBtn"),
    loggedCount: document.getElementById("caLoggedCount"),
    passwordCount: document.getElementById("caPasswordCount"),
    totalCount: document.getElementById("caTotalCount"),
    customerFilter: document.getElementById("caCustomerFilter"),
    customerSearch: document.getElementById("caCustomerSearch"),
    customersBody: document.getElementById("caCustomersBody"),
    attemptPeriod: document.getElementById("caAttemptPeriod"),
    attemptSearch: document.getElementById("caAttemptSearch"),
    attemptsBody: document.getElementById("caAttemptsBody"),
  };

  let customerTimer = null;
  let attemptTimer = null;

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function resultClass(result) {
    const r = String(result || "").toLowerCase();
    if (r === "success" || r === "reset_success") return "is-ok";
    if (r === "must_change_password") return "is-warn";
    return "is-bad";
  }

  async function parseJson(res) {
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || ("HTTP " + res.status));
    }
    return data;
  }

  async function loadSummary() {
    const res = await fetch(cfg.summaryUrl, { headers: { Accept: "application/json" } });
    const data = await parseJson(res);
    if (els.loggedCount) els.loggedCount.textContent = String(data.logged_count || 0);
    if (els.passwordCount) els.passwordCount.textContent = String(data.password_set_count || 0);
    if (els.totalCount) els.totalCount.textContent = String(data.total_customers || 0);
  }

  async function loadCustomers() {
    if (!els.customersBody) return;
    const params = new URLSearchParams();
    params.set("filter", els.customerFilter?.value || "logged");
    const q = (els.customerSearch?.value || "").trim();
    if (q) params.set("q", q);
    params.set("limit", "200");
    els.customersBody.innerHTML =
      '<tr><td colspan="7" class="text-muted small py-3">Loading…</td></tr>';
    try {
      const res = await fetch(cfg.customersUrl + "?" + params.toString(), {
        headers: { Accept: "application/json" },
      });
      const data = await parseJson(res);
      const rows = data.rows || [];
      if (!rows.length) {
        els.customersBody.innerHTML =
          '<tr><td colspan="7" class="text-muted small py-3">No customers found.</td></tr>';
        return;
      }
      els.customersBody.innerHTML = rows
        .map(function (row) {
          const light = row.logged
            ? '<span class="ca-logged-light is-on" title="Logged"></span>'
            : '<span class="ca-logged-light is-off" title="Not logged"></span>';
          return (
            "<tr>" +
            '<td class="text-center">' +
            light +
            "</td>" +
            "<td>" +
            escapeHtml(row.customer_id) +
            "</td>" +
            "<td><strong>" +
            escapeHtml(row.customer_name) +
            "</strong></td>" +
            "<td>" +
            escapeHtml(row.pan_number || "—") +
            "</td>" +
            "<td>" +
            escapeHtml(row.aadhaar_number || "—") +
            "</td>" +
            "<td>" +
            escapeHtml(row.mobile_number || "—") +
            "</td>" +
            "<td>" +
            escapeHtml(row.last_login || "—") +
            "</td>" +
            "</tr>"
          );
        })
        .join("");
    } catch (err) {
      els.customersBody.innerHTML =
        '<tr><td colspan="7" class="text-danger small py-3">' +
        escapeHtml(err.message || "Failed to load") +
        "</td></tr>";
    }
  }

  async function loadAttempts() {
    if (!els.attemptsBody) return;
    const params = new URLSearchParams();
    params.set("period", els.attemptPeriod?.value || "7d");
    const q = (els.attemptSearch?.value || "").trim();
    if (q) params.set("q", q);
    params.set("limit", "100");
    els.attemptsBody.innerHTML =
      '<tr><td colspan="5" class="text-muted small py-3">Loading…</td></tr>';
    try {
      const res = await fetch(cfg.attemptsUrl + "?" + params.toString(), {
        headers: { Accept: "application/json" },
      });
      const data = await parseJson(res);
      const rows = data.rows || [];
      if (!rows.length) {
        els.attemptsBody.innerHTML =
          '<tr><td colspan="5" class="text-muted small py-3">No login attempts.</td></tr>';
        return;
      }
      els.attemptsBody.innerHTML = rows
        .map(function (row) {
          const name = row.customer_name
            ? escapeHtml(row.customer_name) +
              (row.customer_id ? " <span class=\"text-muted\">#" + row.customer_id + "</span>" : "")
            : row.customer_id
              ? "#" + row.customer_id
              : "—";
          return (
            "<tr>" +
            "<td>" +
            escapeHtml(row.created_date || "—") +
            "</td>" +
            "<td>" +
            name +
            "</td>" +
            "<td>" +
            escapeHtml(row.user_id_input || "—") +
            "</td>" +
            "<td>" +
            escapeHtml(row.detected_type || "—") +
            "</td>" +
            '<td><span class="ca-result ' +
            resultClass(row.attempt_result) +
            '">' +
            escapeHtml(row.attempt_result || "—") +
            "</span></td>" +
            "</tr>"
          );
        })
        .join("");
    } catch (err) {
      els.attemptsBody.innerHTML =
        '<tr><td colspan="5" class="text-danger small py-3">' +
        escapeHtml(err.message || "Failed to load") +
        "</td></tr>";
    }
  }

  function refreshAll() {
    loadSummary().catch(function () {});
    loadCustomers();
    loadAttempts();
  }

  els.refresh?.addEventListener("click", refreshAll);
  els.customerFilter?.addEventListener("change", loadCustomers);
  els.attemptPeriod?.addEventListener("change", loadAttempts);
  els.customerSearch?.addEventListener("input", function () {
    clearTimeout(customerTimer);
    customerTimer = setTimeout(loadCustomers, 300);
  });
  els.attemptSearch?.addEventListener("input", function () {
    clearTimeout(attemptTimer);
    attemptTimer = setTimeout(loadAttempts, 300);
  });

  refreshAll();
  setInterval(refreshAll, 30000);
})();
