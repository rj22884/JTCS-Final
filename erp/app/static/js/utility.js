(function () {
  function $(id) {
    return document.getElementById(id);
  }

  function showStatus(el, ok, message) {
    if (!el) return;
    el.classList.remove("d-none", "alert-success", "alert-danger", "alert-info");
    el.classList.add(ok === true ? "alert-success" : ok === false ? "alert-danger" : "alert-info");
    el.textContent = message || "";
  }

  function headers(csrf) {
    return {
      "Content-Type": "application/json",
      "X-CSRFToken": csrf || "",
      "X-Requested-With": "XMLHttpRequest",
    };
  }

  async function postJson(url, csrf, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: headers(csrf),
      body: JSON.stringify(body || {}),
      credentials: "same-origin",
    });
    const data = await res.json().catch(function () {
      return { ok: false, error: "Invalid server response" };
    });
    if (!res.ok || data.ok === false) {
      throw new Error(data.error || data.message || ("HTTP " + res.status));
    }
    return data;
  }

  function appendLog(line, level) {
    var log = $("utilityLog");
    if (!log) return;
    if (log.dataset.empty === "1" || log.textContent.indexOf("yahan live log") >= 0) {
      log.textContent = "";
      log.dataset.empty = "0";
    }
    var row = document.createElement("div");
    if (level === "warn") row.className = "log-warn";
    else if (level === "error") row.className = "log-error";
    else if (level === "ok") row.className = "log-ok";
    row.textContent = line;
    log.appendChild(row);
    log.scrollTop = log.scrollHeight;
  }

  function clearLog() {
    var log = $("utilityLog");
    if (!log) return;
    log.textContent = "";
    log.dataset.empty = "1";
  }

  var sync = window.UTILITY_SYNC;
  if (sync) {
    var status = $("utilityStatus");
    var deployBtns = document.querySelectorAll("[data-deploy-target]");
    var downloadBtn = $("utilityDownloadBtn");
    var clearBtn = $("utilityLogClearBtn");
    var deployLabels = {
      app: "App",
      web: "Web",
      both: "App + Web",
    };
    var selectedTarget = "app";
    var changeReport = null;
    var decisions = {};
    var selectedModules = {};
    var userPicked = {};
    var lastPreview = null;
    var previewTimer = null;

    function escapeHtml(text) {
      return String(text == null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    function markTarget(target) {
      selectedTarget = target || "app";
      deployBtns.forEach(function (btn) {
        var on = btn.getAttribute("data-deploy-target") === selectedTarget;
        btn.classList.toggle("is-selected", on);
        btn.classList.toggle("utility-target-btn", true);
      });
      var label = $("utilityTargetLabel");
      if (label) label.textContent = "Target: " + (deployLabels[selectedTarget] || selectedTarget);
    }

    function selectionPayload() {
      var modules = Object.keys(selectedModules).filter(function (id) {
        return selectedModules[id];
      });
      return {
        target: selectedTarget,
        selected_modules: modules,
        decisions: decisions,
        files: (lastPreview && lastPreview.file_keys) || [],
      };
    }

    function renderManifest(preview) {
      var list = $("utilityManifest");
      if (!list) return;
      var files = (preview && preview.files) || [];
      if (!files.length) {
        list.innerHTML = "<li>No module files selected.</li>";
        return;
      }
      list.innerHTML = files
        .map(function (file) {
          return "<li><code>" + escapeHtml(file.status) + "</code> " + escapeHtml(file.path) + "</li>";
        })
        .join("");
    }

    function renderReview() {
      var host = $("utilityReview");
      if (!host || !changeReport) return;
      var groups = changeReport.groups || {};
      var order = [
        ["shared", "Shared"],
        ["unmapped", "Unmapped"],
        ["deletes_renames", "Deletes / renames"],
        ["uncertain", "Uncertain"],
      ];
      var html = "";
      order.forEach(function (pair) {
        var rows = groups[pair[0]] || [];
        if (!rows.length) return;
        html += "<h5 class=\"h6 mb-1\">" + escapeHtml(pair[1]) + " (" + rows.length + ")</h5>";
        rows.forEach(function (file) {
          var choice = decisions[file.key] || "";
          html +=
            "<div class=\"utility-review-row\">" +
            "<div>" +
            "<select class=\"form-select form-select-sm\" data-decision=\"" + escapeHtml(file.key) + "\">" +
            "<option value=\"\">Choose…</option>" +
            "<option value=\"include\"" + (choice === "include" ? " selected" : "") + ">Include</option>" +
            "<option value=\"skip\"" + (choice === "skip" ? " selected" : "") + ">Skip</option>" +
            "</select></div>" +
            "<div><code>" + escapeHtml(file.status) + "</code> " + escapeHtml(file.path) +
            (file.old_path ? " <span class=\"text-muted\">from " + escapeHtml(file.old_path) + "</span>" : "") +
            (file.suggested_module ? " <span class=\"text-muted\">(" + escapeHtml(file.suggested_module) + ")</span>" : "") +
            "</div></div>";
        });
      });
      host.innerHTML = html || "<p class=\"small text-muted mb-0\">No shared, unmapped, deleted, or uncertain files.</p>";
      host.querySelectorAll("[data-decision]").forEach(function (select) {
        select.addEventListener("change", function () {
          var key = select.getAttribute("data-decision");
          if (!select.value) delete decisions[key];
          else decisions[key] = select.value;
          schedulePreview();
        });
      });
    }

    function expandSelection() {
      var active = {};
      var modules = (changeReport && changeReport.modules) || [];
      modules.forEach(function (mod) {
        if (mod.mandatory || userPicked[mod.id]) active[mod.id] = true;
      });
      var guard = 0;
      var grew = true;
      while (grew && guard < 25) {
        grew = false;
        guard += 1;
        modules.forEach(function (mod) {
          if (!active[mod.id]) return;
          (mod.requires || []).forEach(function (dep) {
            if (dep && !active[dep]) {
              active[dep] = true;
              grew = true;
            }
          });
        });
      }
      selectedModules = active;
    }

    function moduleIsLocked(mod) {
      if (!mod || mod.mandatory) return !!mod;
      var modules = (changeReport && changeReport.modules) || [];
      return modules.some(function (other) {
        return other.id !== mod.id && selectedModules[other.id] && (other.requires || []).indexOf(mod.id) >= 0;
      });
    }

    function renderReport() {
      expandSelection();
      var wrap = $("utilityChanges");
      var body = $("utilityFileBody");
      var modules = $("utilityModules");
      if (!changeReport || !wrap || !body || !modules) return;
      wrap.classList.remove("d-none");
      var files = changeReport.files || [];
      body.innerHTML = files.length
        ? files.map(function (file) {
          var group = file.review ? file.group : file.module_label;
          return "<tr><td>" + escapeHtml(file.status) + "</td><td>" + escapeHtml(file.path) +
            "</td><td>" + escapeHtml(group || "") + "</td></tr>";
        }).join("")
        : "<tr><td colspan=\"3\">No local git changes for this target.</td></tr>";
      var moduleRows = changeReport.modules || [];
      modules.innerHTML = moduleRows.length
        ? moduleRows.map(function (mod) {
          var locked = moduleIsLocked(mod);
          var checked = selectedModules[mod.id] ? " checked" : "";
          var disabled = locked ? " disabled" : "";
          var required = locked ? " <span class=\"utility-required\">Required</span>" : "";
          var related = mod.related_review_count
            ? " <span class=\"text-muted\">+" + mod.related_review_count + " need a choice</span>"
            : "";
          return "<label class=\"utility-module" + (locked ? " is-mandatory" : "") + "\"><span><input type=\"checkbox\" data-module=\"" +
            escapeHtml(mod.id) + "\"" + checked + disabled + "> <strong>" + escapeHtml(mod.label) +
            "</strong>" + required + " <span class=\"text-muted\">" + mod.count + " file(s)" +
            (mod.repo && mod.repo !== "app" ? ", " + escapeHtml(mod.repo) : "") +
            "</span>" + related + "</span><ul>" +
            (mod.files || []).map(function (path) {
              return "<li>" + escapeHtml(path) + "</li>";
            }).join("") +
            "</ul></label>";
        }).join("")
        : "<p class=\"small text-muted mb-0\">No module-mapped files. Review the groups below.</p>";
      modules.querySelectorAll("[data-module]").forEach(function (box) {
        box.addEventListener("change", function () {
          userPicked[box.getAttribute("data-module")] = box.checked;
          renderReport();
        });
      });
      renderReview();
      schedulePreview();
    }

    function schedulePreview() {
      if (previewTimer) clearTimeout(previewTimer);
      previewTimer = setTimeout(refreshPreview, 200);
    }

    async function refreshPreview() {
      if (!changeReport) return;
      var payload = selectionPayload();
      var res = await fetch(sync.previewUrl, {
        method: "POST",
        headers: headers(sync.csrf),
        body: JSON.stringify({
          target: payload.target,
          selected_modules: payload.selected_modules,
          decisions: payload.decisions,
        }),
        credentials: "same-origin",
      });
      var data = await res.json().catch(function () {
        return { ok: false, error: "Invalid preview response" };
      });
      if (!res.ok || data.ok === false) {
        lastPreview = null;
        showStatus(status, false, data.error || "Could not build the file list.");
        return;
      }
      lastPreview = data;
      renderManifest(data);
      if (data.blocked && data.blocked.length) {
        showStatus(status, null, data.blocked.length + " file(s) still need Include or Skip.");
      } else {
        showStatus(status, true, (data.files || []).length + " file(s) ready for " + (deployLabels[selectedTarget] || selectedTarget) + ".");
      }
    }

    function setDeployButtonsDisabled(disabled) {
      deployBtns.forEach(function (btn) {
        btn.disabled = disabled;
      });
    }

    if (clearBtn) {
      clearBtn.addEventListener("click", function () {
        clearLog();
        appendLog("Log cleared.", "info");
      });
    }

    async function runDeploy(target) {
      var password = ($("utilityVpsPass") && $("utilityVpsPass").value) || "";
      var commitMessage = ($("utilityCommitMsg") && $("utilityCommitMsg").value) || "";
      if (!password) {
        showStatus(status, false, "VPS password required. App aur Web dono ke liye same password.");
        return;
      }
      var label = deployLabels[target] || target;
      setDeployButtonsDisabled(true);
      clearLog();
      showStatus(status, null, "Uploading " + label + "… neeche live log dekhte raho.");
      appendLog("Starting upload (" + label + ")…", "info");
      try {
        var res = await fetch(sync.deployStreamUrl || sync.deployUrl, {
          method: "POST",
          headers: headers(sync.csrf),
          body: JSON.stringify({
            password: password,
            commit_message: commitMessage,
            target: target,
            selected_modules: (lastPreview && lastPreview.selected_modules) || [],
            decisions: decisions,
            files: (lastPreview && lastPreview.file_keys) || [],
          }),
          credentials: "same-origin",
        });
        if (!res.ok) {
          var errBody = await res.json().catch(function () {
            return {};
          });
          throw new Error(errBody.error || ("HTTP " + res.status));
        }

        // Streaming NDJSON
        if (res.body && sync.deployStreamUrl) {
          var reader = res.body.getReader();
          var decoder = new TextDecoder();
          var buffer = "";
          var finalOk = null;
          var finalMsg = "";
          while (true) {
            var chunk = await reader.read();
            if (chunk.done) break;
            buffer += decoder.decode(chunk.value, { stream: true });
            var parts = buffer.split("\n");
            buffer = parts.pop() || "";
            for (var i = 0; i < parts.length; i++) {
              var raw = parts[i].trim();
              if (!raw) continue;
              var event;
              try {
                event = JSON.parse(raw);
              } catch (e) {
                appendLog(raw, "warn");
                continue;
              }
              if (event.type === "log") {
                appendLog(event.line || "", event.level || "info");
              } else if (event.type === "done") {
                finalOk = true;
                finalMsg = event.message || "Upload complete.";
                appendLog(finalMsg, "ok");
              } else if (event.type === "error") {
                finalOk = false;
                finalMsg = event.error || "Upload failed.";
                appendLog(finalMsg, "error");
              }
            }
          }
          if (buffer.trim()) {
            try {
              var last = JSON.parse(buffer.trim());
              if (last.type === "done") {
                finalOk = true;
                finalMsg = last.message || "Upload complete.";
                appendLog(finalMsg, "ok");
              } else if (last.type === "error") {
                finalOk = false;
                finalMsg = last.error || "Upload failed.";
                appendLog(finalMsg, "error");
              } else if (last.type === "log") {
                appendLog(last.line || "", last.level || "info");
              }
            } catch (e2) {
              appendLog(buffer.trim(), "warn");
            }
          }
          if (finalOk === true) {
            showStatus(status, true, finalMsg || "Upload complete.");
            if ($("utilityVpsPass")) $("utilityVpsPass").value = "";
          } else if (finalOk === false) {
            showStatus(status, false, finalMsg || "Upload failed.");
          } else {
            showStatus(status, false, "Upload ended without SUCCESS marker — log check karo.");
          }
        } else {
          var data = await res.json();
          if (data.ok === false) throw new Error(data.error || "Upload failed");
          appendLog(data.message || "Upload complete.", "ok");
          showStatus(status, true, data.message || "Upload complete.");
          if ($("utilityVpsPass")) $("utilityVpsPass").value = "";
        }
      } catch (err) {
        appendLog(err.message || String(err), "error");
        showStatus(status, false, err.message || String(err));
      } finally {
        setDeployButtonsDisabled(false);
      }
    }

    function confirmHtml() {
      var payload = selectionPayload();
      var files = (lastPreview && lastPreview.files) || [];
      var modules = Array.from(document.querySelectorAll("#utilityModules [data-module]:checked")).map(function (box) {
        var strong = box.parentElement && box.parentElement.querySelector("strong");
        var name = strong ? strong.textContent : box.getAttribute("data-module");
        var repo = box.closest(".utility-module");
        var repoNote = repo && /,\s*web/.test(repo.textContent) ? " (web)" : "";
        return name + repoNote;
      });
      var message = ($("utilityCommitMsg") && $("utilityCommitMsg").value) || "(default deploy message)";
      var lines = [
        "<p><strong>Target:</strong> " + escapeHtml(deployLabels[selectedTarget] || selectedTarget) + "</p>",
        "<p><strong>Commit message:</strong> " + escapeHtml(message) + "</p>",
        "<p><strong>Modules:</strong> " + escapeHtml(modules.join(", ") || "none") + "</p>",
        "<p><strong>Exact files (" + files.length + "):</strong></p><ul>",
      ];
      if (!files.length) {
        lines.push("<li>No selected file changes. The current branch is pushed without these local edits.</li>");
      } else {
        files.forEach(function (file) {
          lines.push("<li><code>" + escapeHtml(file.status) + "</code> " + escapeHtml(file.path) + "</li>");
        });
      }
      lines.push("</ul>");
      return lines.join("");
    }

    function openConfirm(target) {
      if (selectedTarget !== target) {
        markTarget(target);
        changeReport = null;
        lastPreview = null;
        var wrap = $("utilityChanges");
        if (wrap) wrap.classList.add("d-none");
        showStatus(status, null, "Target changed. Detect Changes dabao, phir files confirm karo.");
        return;
      }
      if (!changeReport || changeReport.target !== selectedTarget) {
        showStatus(status, false, "Pehle Detect Changes dabao.");
        return;
      }
      if (!lastPreview) {
        showStatus(status, false, "File list abhi ready nahi hai.");
        return;
      }
      if (!lastPreview.ready) {
        showStatus(status, false, "Shared, unmapped, deleted, renamed, ya uncertain files par Include ya Skip choose karo.");
        return;
      }
      var body = $("utilityConfirmBody");
      if (body) body.innerHTML = confirmHtml();
      var modalEl = $("utilityConfirmModal");
      if (!modalEl || !window.bootstrap) {
        showStatus(status, false, "Confirmation dialog nahi khul saka.");
        return;
      }
      window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    markTarget("app");
    var detectBtn = $("utilityDetectBtn");
    if (detectBtn) {
      detectBtn.addEventListener("click", async function () {
        detectBtn.disabled = true;
        showStatus(status, null, "Git changes detect ho rahe hain…");
        try {
          var res = await fetch(sync.changesUrl, {
            method: "POST",
            headers: headers(sync.csrf),
            body: JSON.stringify({ target: selectedTarget }),
            credentials: "same-origin",
          });
          var data = await res.json().catch(function () {
            return { ok: false, error: "Invalid response" };
          });
          if (!res.ok || data.ok === false) {
            throw new Error(data.error || ("HTTP " + res.status));
          }
          changeReport = data;
          decisions = {};
          selectedModules = {};
          userPicked = {};
          lastPreview = null;
          renderReport();
          var count = (data.files || []).length;
          showStatus(status, true, count + " changed file(s) for " + (deployLabels[selectedTarget] || selectedTarget) + ".");
        } catch (err) {
          showStatus(status, false, err.message || String(err));
        } finally {
          detectBtn.disabled = false;
        }
      });
    }
    var confirmBtn = $("utilityConfirmBtn");
    if (confirmBtn) {
      confirmBtn.addEventListener("click", function () {
        var modalEl = $("utilityConfirmModal");
        if (modalEl && window.bootstrap) {
          var instance = window.bootstrap.Modal.getInstance(modalEl);
          if (instance) instance.hide();
        }
        runDeploy(selectedTarget);
      });
    }

    deployBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var target = btn.getAttribute("data-deploy-target") || "app";
        if (target !== selectedTarget) {
          markTarget(target);
          changeReport = null;
          lastPreview = null;
          var wrap = $("utilityChanges");
          if (wrap) wrap.classList.add("d-none");
          showStatus(status, null, (deployLabels[target] || target) + " selected. Detect Changes dabao.");
          return;
        }
        openConfirm(target);
      });
    });

    if (downloadBtn) {
      downloadBtn.addEventListener("click", async function () {
        downloadBtn.disabled = true;
        clearLog();
        showStatus(status, null, "Creating full ZIP (database + app)…");
        appendLog("Creating download package on VPS…", "info");
        try {
          var data = await postJson(sync.createDownloadUrl, sync.csrf, {});
          var fileName = data.file_name;
          if (!fileName) throw new Error("ZIP file name missing.");
          appendLog("ZIP ready: " + fileName, "ok");
          showStatus(status, true, (data.message || "ZIP ready.") + " Download starting…");
          var url = sync.downloadBase.replace("__FILE__", encodeURIComponent(fileName));
          window.location.href = url;
        } catch (err) {
          appendLog(err.message || String(err), "error");
          showStatus(status, false, err.message || String(err));
        } finally {
          downloadBtn.disabled = false;
        }
      });
    }
  }

  var cacheCfg = window.UTILITY_CACHE;
  if (cacheCfg) {
    var cacheBtn = $("utilityClearCacheBtn");
    var cacheStatus = $("utilityStatus");
    if (cacheBtn) {
      cacheBtn.addEventListener("click", async function () {
        cacheBtn.disabled = true;
        showStatus(cacheStatus, null, "Clearing caches…");
        try {
          var data = await postJson(cacheCfg.clearUrl, cacheCfg.csrf, {});
          showStatus(cacheStatus, true, data.message || "Cache cleared.");
        } catch (err) {
          showStatus(cacheStatus, false, err.message || String(err));
        } finally {
          cacheBtn.disabled = false;
        }
      });
    }
  }

  var healthCfg = window.UTILITY_HEALTH;
  if (healthCfg) {
    var refreshBtn = $("utilityHealthRefresh");
    var healthStatus = $("utilityStatus");
    var box = $("utilityHealthBox");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", async function () {
        refreshBtn.disabled = true;
        showStatus(healthStatus, null, "Checking…");
        try {
          var res = await fetch(healthCfg.healthUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            credentials: "same-origin",
          });
          var data = await res.json();
          if (box) {
            box.innerHTML =
              "<div><span class=\"utility-meta-label\">Database</span> " +
              (data.database_ok
                ? "<span class=\"text-success\">OK</span>"
                : "<span class=\"text-danger\">FAIL</span> " + (data.database_error || "")) +
              "</div>" +
              "<div><span class=\"utility-meta-label\">Public health</span> " +
              (data.public_health_ok
                ? "<span class=\"text-success\">OK</span>"
                : data.public_health_ok === false
                  ? "<span class=\"text-danger\">FAIL</span>"
                  : "<span class=\"text-muted\">n/a</span>") +
              " <code class=\"ms-1\">" +
              (data.public_health_body || "") +
              "</code></div>" +
              "<div><span class=\"utility-meta-label\">Mode</span> " +
              ((data.info && data.info.mode) || "") +
              "</div>";
          }
          showStatus(healthStatus, !!data.ok, data.ok ? "Health check OK." : "Database check failed.");
        } catch (err) {
          showStatus(healthStatus, false, err.message || String(err));
        } finally {
          refreshBtn.disabled = false;
        }
      });
    }
  }
})();
