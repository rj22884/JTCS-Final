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

  var sync = window.UTILITY_SYNC;
  if (sync) {
    var status = $("utilityStatus");
    var deployBtn = $("utilityDeployBtn");
    var downloadBtn = $("utilityDownloadBtn");

    if (deployBtn) {
      deployBtn.addEventListener("click", async function () {
        var password = ($("utilityVpsPass") && $("utilityVpsPass").value) || "";
        var commitMessage = ($("utilityCommitMsg") && $("utilityCommitMsg").value) || "";
        if (!password) {
          showStatus(status, false, "VPS password required.");
          return;
        }
        deployBtn.disabled = true;
        showStatus(status, null, "Deploying to VPS… git push + remote deploy.sh (2–5 min).");
        try {
          var data = await postJson(sync.deployUrl, sync.csrf, {
            password: password,
            commit_message: commitMessage,
          });
          showStatus(status, true, data.message || "Deploy complete.");
          if ($("utilityVpsPass")) $("utilityVpsPass").value = "";
        } catch (err) {
          showStatus(status, false, err.message || String(err));
        } finally {
          deployBtn.disabled = false;
        }
      });
    }

    if (downloadBtn) {
      downloadBtn.addEventListener("click", async function () {
        downloadBtn.disabled = true;
        showStatus(status, null, "Creating full ZIP (database + app)…");
        try {
          var data = await postJson(sync.createDownloadUrl, sync.csrf, {});
          var fileName = data.file_name;
          if (!fileName) throw new Error("ZIP file name missing.");
          showStatus(status, true, (data.message || "ZIP ready.") + " Download starting…");
          var url = sync.downloadBase.replace("__FILE__", encodeURIComponent(fileName));
          window.location.href = url;
        } catch (err) {
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
