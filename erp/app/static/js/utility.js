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

    deployBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        runDeploy(btn.getAttribute("data-deploy-target") || "app");
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
