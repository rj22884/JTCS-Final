(function () {
  "use strict";

  const dataEl = document.getElementById("jtcsWhatsNewData");
  const listEl = document.getElementById("jtcsWhatsNewList");
  const badgeEl = document.getElementById("jtcsWhatsNewBadge");
  const modalEl = document.getElementById("jtcsWhatsNewModal");
  if (!listEl || !modalEl) return;

  let items = [];
  try {
    items = dataEl ? JSON.parse(dataEl.textContent || "[]") : [];
  } catch (_e) {
    items = [];
  }

  const titleEl = document.getElementById("jtcsWnTitle");
  const metaEl = document.getElementById("jtcsWnMeta");
  const stepsEl = document.getElementById("jtcsWnSteps");
  const openEl = document.getElementById("jtcsWnOpen");
  const videoEl = document.getElementById("jtcsWnVideo");
  const canvasEl = document.getElementById("jtcsWnCanvas");
  let playTimer = null;
  let stepIndex = 0;
  let activeSteps = [];
  let activeTitle = "";
  let lastUnread = null;

  function escapeHtml(value) {
    if (window.CrmCommon && CrmCommon.escapeHtml) return CrmCommon.escapeHtml(value);
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setBadge(total) {
    if (!badgeEl) return;
    const count = parseInt(total, 10) || 0;
    if (lastUnread != null && count > lastUnread) {
      badgeEl.classList.add("jtcs-wn-badge-pop");
    }
    lastUnread = count;
    if (count > 0) {
      badgeEl.textContent = String(count);
      badgeEl.classList.remove("d-none");
    } else {
      badgeEl.textContent = "0";
      badgeEl.classList.add("d-none");
    }
  }

  function renderList() {
    if (!items.length) {
      listEl.innerHTML = '<div class="jtcs-notify-empty">No recent updates.</div>';
      return;
    }
    listEl.innerHTML = items
      .map(function (item) {
        const unread = item.is_unread ? " is-unread" : "";
        const detail = item.detail ? " · " + String(item.detail).slice(0, 110) : "";
        const badge = item.badge
          ? ' <span class="jtcs-wn-badge">' + escapeHtml(item.badge) + "</span>"
          : "";
        return (
          '<button type="button" class="dropdown-item jtcs-notify-item jtcs-wn-open' +
          unread +
          '" data-entry-id="' +
          escapeHtml(item.entry_id) +
          '"><div class="jtcs-notify-title"><i class="bi bi-stars"></i> ' +
          escapeHtml(item.title || "Update") +
          badge +
          '</div><div class="jtcs-notify-meta">' +
          escapeHtml(item.date_display || "") +
          escapeHtml(detail) +
          "</div></button>"
        );
      })
      .join("");
  }

  function stepsOf(item) {
    return String(item.workflow || item.detail || "")
      .split(/\n+/)
      .map(function (line) {
        return line.trim();
      })
      .filter(Boolean);
  }

  function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
    const words = String(text || "").split(/\s+/);
    let line = "";
    let drawn = 0;
    words.forEach(function (word) {
      const test = line ? line + " " + word : word;
      if (ctx.measureText(test).width > maxWidth && line) {
        ctx.fillText(line, x, y);
        line = word;
        y += lineHeight;
        drawn += 1;
      } else {
        line = test;
      }
    });
    if (line && drawn < 6) ctx.fillText(line, x, y);
  }

  function drawFrame() {
    if (!canvasEl) return;
    const ctx = canvasEl.getContext("2d");
    const w = canvasEl.width;
    const h = canvasEl.height;
    ctx.fillStyle = "#dbe4f0";
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(48, 36, w - 96, h - 72);
    ctx.fillStyle = "#16324f";
    ctx.fillRect(48, 36, w - 96, 54);
    ctx.fillStyle = "#ffffff";
    ctx.font = "600 26px sans-serif";
    ctx.fillText("JTCS", 72, 72);
    ctx.font = "500 20px sans-serif";
    ctx.fillText(activeTitle.slice(0, 52), 160, 72);
    const step = activeSteps[stepIndex] || "";
    ctx.fillStyle = "#64748b";
    ctx.font = "600 18px sans-serif";
    ctx.fillText("Step " + (stepIndex + 1) + " of " + activeSteps.length, 78, 130);
    ctx.fillStyle = "#0f172a";
    ctx.font = "600 32px sans-serif";
    wrapText(ctx, step, 78, 190, w - 170, 42);
    const dotY = h - 78;
    activeSteps.forEach(function (_step, index) {
      ctx.beginPath();
      ctx.arc(78 + index * 28, dotY, index === stepIndex ? 7 : 4, 0, Math.PI * 2);
      ctx.fillStyle = index === stepIndex ? "#1d4ed8" : "#cbd5e1";
      ctx.fill();
    });
  }

  function stopScreen() {
    if (playTimer) {
      clearInterval(playTimer);
      playTimer = null;
    }
    if (videoEl) {
      videoEl.pause();
      videoEl.removeAttribute("src");
      videoEl.srcObject = null;
      videoEl.load();
    }
  }

  function playScreen() {
    if (!videoEl || !canvasEl || !activeSteps.length) return;
    drawFrame();
    try {
      videoEl.srcObject = canvasEl.captureStream(8);
    } catch (_e) {
      return;
    }
    videoEl.muted = true;
    videoEl.play().catch(function () {});
    if (playTimer) clearInterval(playTimer);
    playTimer = setInterval(function () {
      stepIndex = (stepIndex + 1) % activeSteps.length;
      drawFrame();
    }, 2800);
  }

  function playFile(url) {
    if (!videoEl) return;
    videoEl.srcObject = null;
    videoEl.muted = false;
    videoEl.src = url;
    videoEl.play().catch(function () {});
  }

  function findItem(entryId) {
    const id = String(entryId);
    return items.find(function (item) {
      return String(item.entry_id) === id;
    });
  }

  function markRead(entryId) {
    const url = "/api/whats-new/" + encodeURIComponent(entryId) + "/read";
    const task = window.CrmCommon
      ? CrmCommon.apiFetch(url, { method: "POST", body: {} })
      : fetch(url, { method: "POST", credentials: "same-origin" }).then(function (r) {
          return r.json();
        });
    task
      .then(function (data) {
        items.forEach(function (item) {
          if (String(item.entry_id) === String(entryId)) item.is_unread = false;
        });
        renderList();
        if (data && data.unread_count != null) setBadge(data.unread_count);
      })
      .catch(function () {});
  }

  function openItem(entryId) {
    const item = findItem(entryId);
    if (!item) return;
    stopScreen();
    activeTitle = item.title || "What's New";
    activeSteps = stepsOf(item);
    if (!activeSteps.length) activeSteps = ["Open this page and follow the work shown there."];
    stepIndex = 0;
    if (titleEl) titleEl.textContent = activeTitle;
    if (metaEl) metaEl.textContent = [item.date_display, item.badge].filter(Boolean).join(" · ");
    if (stepsEl) {
      stepsEl.innerHTML = activeSteps
        .map(function (step) {
          return "<li>" + escapeHtml(step) + "</li>";
        })
        .join("");
    }
    if (openEl) {
      if (item.href) {
        openEl.href = item.href;
        openEl.classList.remove("disabled");
        openEl.removeAttribute("aria-disabled");
      } else {
        openEl.href = "#";
        openEl.classList.add("disabled");
        openEl.setAttribute("aria-disabled", "true");
      }
    }
    const modal = window.bootstrap && bootstrap.Modal.getOrCreateInstance(modalEl);
    if (modal) modal.show();
    if (item.video) playFile(item.video);
    else playScreen();
    if (item.is_unread) markRead(item.entry_id);
  }

  listEl.addEventListener("click", function (event) {
    const btn = event.target.closest(".jtcs-wn-open");
    if (!btn) return;
    event.preventDefault();
    openItem(btn.getAttribute("data-entry-id"));
  });

  modalEl.addEventListener("hidden.bs.modal", stopScreen);

  window.jtcsApplyWhatsNew = function (data) {
    if (!data || !Array.isArray(data.whats_new_rows)) return;
    items = data.whats_new_rows;
    renderList();
    setBadge(data.whats_new_unread);
  };

  if (badgeEl && !badgeEl.classList.contains("d-none")) {
    lastUnread = parseInt(badgeEl.textContent, 10) || 0;
  } else {
    lastUnread = 0;
  }
})();
