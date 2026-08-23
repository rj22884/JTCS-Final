(function () {
  const form = document.getElementById("exStampUploadForm");
  const fileInput = document.getElementById("exStampFile");
  const uploadBtn = document.getElementById("exStampUploadBtn");
  const refreshBtn = document.getElementById("exRefreshStateBtn");
  const errorEl = document.getElementById("exStampError");
  const successEl = document.getElementById("exStampSuccess");
  const reviewModalEl = document.getElementById("exStampReviewModal");
  const reviewBody = document.getElementById("exStampReviewBody");
  const reviewMeta = document.getElementById("exStampReviewMeta");
  const reviewCount = document.getElementById("exStampReviewCount");
  const reviewError = document.getElementById("exStampReviewError");
  const finalImportBtn = document.getElementById("exStampFinalImportBtn");

  const reviewModal =
    reviewModalEl && window.bootstrap
      ? window.bootstrap.Modal.getOrCreateInstance(reviewModalEl)
      : null;

  let pendingReview = {
    file_name: "",
    date_from: "",
    date_to: "",
    rows: [],
  };

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatDate(value) {
    if (window.formatDisplaySmart) return window.formatDisplaySmart(value, "—");
    if (!value) return "—";
    const parts = String(value).slice(0, 10).split("-");
    if (parts.length !== 3) return value;
    return parts[2] + "/" + parts[1] + "/" + parts[0];
  }

  function setError(message) {
    if (!errorEl) return;
    if (!message) {
      errorEl.classList.add("d-none");
      errorEl.textContent = "";
      return;
    }
    errorEl.textContent = message;
    errorEl.classList.remove("d-none");
  }

  function setSuccess(message) {
    if (!successEl) return;
    if (!message) {
      successEl.classList.add("d-none");
      successEl.textContent = "";
      return;
    }
    successEl.textContent = message;
    successEl.classList.remove("d-none");
  }

  function setReviewError(message) {
    if (!reviewError) return;
    if (!message) {
      reviewError.classList.add("d-none");
      reviewError.textContent = "";
      return;
    }
    reviewError.textContent = message;
    reviewError.classList.remove("d-none");
  }

  function renderTable(bodyId, emptyId, rows, renderRow) {
    const body = document.getElementById(bodyId);
    const empty = document.getElementById(emptyId);
    if (!body) return;
    if (!rows || !rows.length) {
      body.innerHTML = "";
      if (empty) empty.classList.remove("d-none");
      return;
    }
    if (empty) empty.classList.add("d-none");
    body.innerHTML = rows.map(renderRow).join("");
  }

  function renderImportedList(rows) {
    const body = document.getElementById("exImportedBody");
    const empty = document.getElementById("exImportedEmpty");
    const countEl = document.getElementById("exImportedCount");
    const list = rows || [];
    if (countEl) countEl.textContent = String(list.length);
    if (!body) return;
    if (!list.length) {
      body.innerHTML = "";
      if (empty) empty.classList.remove("d-none");
      return;
    }
    if (empty) empty.classList.add("d-none");
    body.innerHTML = list
      .map(function (row) {
        const dateVal =
          row.report_date || row.report_date_from || row.imported_date || "";
        return (
          "<tr><td>" +
          escapeHtml(row.certificate_number) +
          '</td><td class="text-end">' +
          escapeHtml(row.stamp_duty_amount) +
          "</td><td>" +
          escapeHtml(formatDate(dateVal)) +
          "</td></tr>"
        );
      })
      .join("");
  }

  function renderPreviouslyUploaded(rows, summary) {
    const countEl = document.getElementById("exPreviouslyUploadedCount");
    const messageEl = document.getElementById("exPreviouslyUploadedMessage");
    const emptyEl = document.getElementById("exPreviouslyUploadedEmpty");
    const body = document.getElementById("exPreviouslyUploadedBody");
    const list = rows || [];
    const count =
      summary && summary.previously_uploaded != null
        ? summary.previously_uploaded
        : list.length;
    if (countEl) countEl.textContent = String(count);
    if (messageEl) {
      if (count > 0) {
        messageEl.classList.remove("d-none");
        messageEl.textContent =
          count +
          " certificate number(s) were already imported earlier and were skipped permanently.";
      } else {
        messageEl.classList.add("d-none");
        messageEl.textContent = "";
      }
    }
    if (body) {
      if (!list.length) {
        body.innerHTML = "";
      } else {
        body.innerHTML = list
          .map(function (row) {
            return (
              "<tr><td>" +
              escapeHtml(row.certificate_number) +
              '</td><td class="text-end">' +
              escapeHtml(row.stamp_duty_amount) +
              "</td><td>" +
              escapeHtml(row.previous_file_name || "—") +
              "</td></tr>"
            );
          })
          .join("");
      }
    }
    if (emptyEl) {
      if (count > 0) {
        emptyEl.classList.add("d-none");
      } else {
        emptyEl.classList.remove("d-none");
      }
    }
  }

  function renderResults(data) {
    const summary = data.summary || {};

    const csvOnlyCount = document.getElementById("exCsvOnlyCount");
    const dbOnlyCount = document.getElementById("exDbOnlyCount");
    const matchedCount = document.getElementById("exMatchedCount");
    if (csvOnlyCount) csvOnlyCount.textContent = String(summary.csv_only || 0);
    if (dbOnlyCount) dbOnlyCount.textContent = String(summary.db_only || 0);
    if (matchedCount) matchedCount.textContent = String(summary.matched || 0);

    renderTable("exCsvOnlyBody", "exCsvOnlyEmpty", data.csv_only_rows || [], function (row) {
      return (
        "<tr><td>" +
        escapeHtml(row.certificate_number) +
        "</td><td>" +
        escapeHtml(formatDate(row.generated_on || row.report_date || row.report_date_from || "")) +
        '</td><td class="text-end">' +
        escapeHtml(row.stamp_duty_amount) +
        "</td></tr>"
      );
    });

    renderTable("exDbOnlyBody", "exDbOnlyEmpty", data.db_only_rows || [], function (row) {
      return (
        "<tr><td>" +
        escapeHtml(row.certificate_number) +
        "</td><td>" +
        escapeHtml(formatDate(row.transaction_date)) +
        '</td><td class="text-end">' +
        escapeHtml(row.stamp_duty_amount) +
        "</td></tr>"
      );
    });

    renderTable("exMatchedBody", "exMatchedEmpty", data.matched_rows || [], function (row) {
      return (
        "<tr><td>" +
        escapeHtml(row.certificate_number) +
        '</td><td class="text-end">' +
        escapeHtml(row.csv_stamp_duty_amount != null ? row.csv_stamp_duty_amount : row.stamp_duty_amount) +
        '</td><td class="text-end">' +
        escapeHtml(row.db_stamp_duty_amount != null ? row.db_stamp_duty_amount : "—") +
        "</td><td>" +
        escapeHtml(formatDate(row.transaction_date)) +
        "</td><td>" +
        escapeHtml(row.customer_name) +
        "</td></tr>"
      );
    });

    renderImportedList(data.imported_rows || []);
    renderPreviouslyUploaded(data.previously_uploaded_rows || [], summary);
  }

  function syncReviewRowsFromDom() {
    if (!reviewBody) return [];
    const synced = [];
    reviewBody.querySelectorAll("tr").forEach(function (tr) {
      const cert = (tr.dataset.certificate || "").trim().toUpperCase();
      const previous = pendingReview.rows[Number(tr.dataset.index)] || {};
      const row = {
        certificate_number: cert,
        generated_on: previous.generated_on || previous.report_date || "",
        generated_on_raw: previous.generated_on_raw || previous.generated_on || "",
        report_date: previous.generated_on || previous.report_date || "",
        stamp_duty_amount_raw: previous.stamp_duty_amount_raw || "",
      };
      tr.querySelectorAll("[data-field]").forEach(function (input) {
        row[input.dataset.field] = input.value.trim();
      });
      // Keep original CSV amount text unless user edited the review amount.
      if (
        row.stamp_duty_amount != null &&
        String(row.stamp_duty_amount) !== String(previous.stamp_duty_amount ?? "")
      ) {
        row.stamp_duty_amount_raw = String(row.stamp_duty_amount);
      } else if (!row.stamp_duty_amount_raw) {
        row.stamp_duty_amount_raw = String(row.stamp_duty_amount || "");
      }
      synced.push(row);
    });
    pendingReview.rows = synced;
    return synced;
  }

  function renderReviewGrid(rows) {
    if (!reviewBody) return;
    const list = rows || [];
    if (!list.length) {
      reviewBody.innerHTML =
        '<tr><td colspan="6" class="text-muted text-center py-3">No new rows to import (all skipped).</td></tr>';
      if (reviewCount) reviewCount.textContent = "0 rows";
      if (finalImportBtn) finalImportBtn.disabled = true;
      return;
    }
    if (finalImportBtn) finalImportBtn.disabled = false;
    reviewBody.innerHTML = list
      .map(function (row, index) {
        return (
          '<tr data-index="' +
          index +
          '" data-certificate="' +
          escapeHtml(row.certificate_number) +
          '">' +
          "<td>" +
          (index + 1) +
          "</td>" +
          '<td><div class="ex-cert-locked">' +
          escapeHtml(row.certificate_number) +
          "</div></td>" +
          '<td><input type="text" class="form-control form-control-sm text-end" data-field="stamp_duty_amount" value="' +
          escapeHtml(row.stamp_duty_amount) +
          '"></td>' +
          '<td><input type="text" class="form-control form-control-sm" data-field="stamp_duty_type" value="' +
          escapeHtml(row.stamp_duty_type || "") +
          '"></td>' +
          '<td><input type="text" class="form-control form-control-sm" data-field="paid_by" value="' +
          escapeHtml(row.paid_by || "") +
          '"></td>' +
          '<td><input type="text" class="form-control form-control-sm" data-field="certificate_status" value="' +
          escapeHtml(row.certificate_status || "") +
          '"></td>' +
          "</tr>"
        );
      })
      .join("");
    if (reviewCount) reviewCount.textContent = list.length + " row(s) ready for Final Import";
  }

  function openReviewModal(payload) {
    const summary = payload.summary || {};
    pendingReview = {
      file_name: payload.file_name || "",
      date_from: summary.date_from || "",
      date_to: summary.date_to || "",
      rows: (payload.review_rows || []).map(function (row) {
        return {
          certificate_number: row.certificate_number,
          stamp_duty_amount: row.stamp_duty_amount,
          stamp_duty_amount_raw: row.stamp_duty_amount_raw || "",
          stamp_duty_type: row.stamp_duty_type || "",
          paid_by: row.paid_by || "",
          certificate_status: row.certificate_status || "",
          generated_on: row.generated_on || row.report_date || "",
          generated_on_raw: row.generated_on_raw || "",
          report_date: row.generated_on || row.report_date || "",
        };
      }),
    };
    setReviewError("");
    if (reviewMeta) {
      reviewMeta.textContent =
        (pendingReview.file_name || "CSV") +
        " | Period: " +
        formatDate(pendingReview.date_from) +
        " - " +
        formatDate(pendingReview.date_to) +
        " | New: " +
        pendingReview.rows.length +
        " | Skipped: " +
        (summary.previously_uploaded || 0);
    }
    renderReviewGrid(pendingReview.rows);
    if (reviewModal) {
      reviewModal.show();
    }
  }

  function loadPageState() {
    return fetch(window.EX_STAMP_API.state, { credentials: "same-origin" })
      .then(function (response) {
        return response.json().then(function (payload) {
          return { ok: response.ok, payload: payload };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.payload.ok) {
          throw new Error((result.payload && result.payload.error) || "Unable to load saved imports.");
        }
        renderResults({
          file_name: result.payload.file_name || "Saved imports",
          summary: result.payload.summary,
          imported_rows: result.payload.imported_rows || [],
          db_only_rows: result.payload.db_only_rows || [],
          csv_only_rows: result.payload.csv_only_rows || [],
          duplicate_rows: result.payload.duplicate_rows || [],
          matched_rows: result.payload.matched_rows || [],
          previously_uploaded_rows: result.payload.previously_uploaded_rows || [],
        });
      });
  }

  if (refreshBtn) {
    refreshBtn.addEventListener("click", function () {
      setError("");
      setSuccess("");
      loadPageState().catch(function (error) {
        setError(error.message || "Unable to refresh.");
      });
    });
  }

  loadPageState().catch(function () {
    /* first load can fail before schema exists; upload will create it */
  });

  if (finalImportBtn) {
    finalImportBtn.addEventListener("click", function () {
      setReviewError("");
      const rows = syncReviewRowsFromDom();
      if (!rows.length) {
        setReviewError("No rows to import.");
        return;
      }

      finalImportBtn.disabled = true;
      finalImportBtn.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1"></span> Importing...';

      fetch(window.EX_STAMP_API.import, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": (window.EX_STAMP_API && window.EX_STAMP_API.csrf) || "",
        },
        body: JSON.stringify({
          rows: rows,
          file_name: pendingReview.file_name,
          date_from: pendingReview.date_from,
          date_to: pendingReview.date_to,
          csrf_token: (window.EX_STAMP_API && window.EX_STAMP_API.csrf) || "",
        }),
      })
        .then(function (response) {
          return response.json().then(function (payload) {
            return { ok: response.ok, payload: payload };
          });
        })
        .then(function (result) {
          if (!result.ok || !result.payload.ok) {
            throw new Error((result.payload && result.payload.error) || "Import failed.");
          }
          if (reviewModal) reviewModal.hide();
          renderResults(result.payload);
          setSuccess(
            "Final Import complete. " +
              (result.payload.summary && result.payload.summary.registered_new
                ? result.payload.summary.registered_new
                : 0) +
              " certificate(s) saved to SQL."
          );
          setError("");
          if (fileInput) fileInput.value = "";
          pendingReview = { file_name: "", date_from: "", date_to: "", rows: [] };
          return loadPageState();
        })
        .catch(function (error) {
          setReviewError(error.message || "Unable to import.");
        })
        .finally(function () {
          finalImportBtn.disabled = false;
          finalImportBtn.innerHTML = '<i class="bi bi-check2-circle"></i> Final Import';
        });
    });
  }

  if (!form) return;

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    setError("");
    setSuccess("");
    if (!fileInput || !fileInput.files || !fileInput.files.length) {
      setError("Select a SHCIL CSV file.");
      return;
    }

    const formData = new FormData();
    formData.append("stamp_file", fileInput.files[0]);
    const csrfInput = form.querySelector('input[name="csrf_token"]');
    if (csrfInput && csrfInput.value) {
      formData.append("csrf_token", csrfInput.value);
    } else if (window.EX_STAMP_API && window.EX_STAMP_API.csrf) {
      formData.append("csrf_token", window.EX_STAMP_API.csrf);
    }

    if (uploadBtn) {
      uploadBtn.disabled = true;
      uploadBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Comparing...';
    }

    fetch(window.EX_STAMP_API.compare, {
      method: "POST",
      body: formData,
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.json().then(function (payload) {
          return { ok: response.ok, payload: payload };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.payload.ok) {
          throw new Error((result.payload && result.payload.error) || "Comparison failed.");
        }
        renderResults(result.payload);
        openReviewModal(result.payload);
      })
      .catch(function (error) {
        setError(error.message || "Unable to compare file.");
      })
      .finally(function () {
        if (uploadBtn) {
          uploadBtn.disabled = false;
          uploadBtn.innerHTML = '<i class="bi bi-upload"></i> Upload & Compare';
        }
      });
  });
})();
