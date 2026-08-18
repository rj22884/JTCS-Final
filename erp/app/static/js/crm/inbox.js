(function () {
  "use strict";

  const page = document.getElementById("crmInboxPage");
  if (!page) return;

  const api = {
    list: page.dataset.apiList,
    detail: page.dataset.apiDetail,
    messages: page.dataset.apiMessages,
    reply: page.dataset.apiReply,
    update: page.dataset.apiUpdate,
    attachments: page.dataset.apiAttachments,
    quickReplies: page.dataset.apiQuickReplies,
    templates: page.dataset.apiTemplates,
    emailSync: page.dataset.apiEmailSync,
    staff: page.dataset.apiStaff,
    labels: page.dataset.apiLabels,
    simulate: page.dataset.apiSimulate,
    link: page.dataset.apiLink,
    convLabels: page.dataset.apiConvLabels,
    tasks: page.dataset.apiTasks,
    followups: page.dataset.apiFollowups,
    simulateStatus: page.dataset.apiSimulateStatus,
    customer360: page.dataset.customer360,
  };
  const testMode = page.dataset.testMode === "1";
  const pollSeconds = Math.max(5, parseInt(page.dataset.pollSeconds, 10) || 15);
  let activeChannel = page.dataset.initialChannel || "";
  let activeConvId = page.dataset.initialConversation
    ? parseInt(page.dataset.initialConversation, 10)
    : null;
  let activeConvMeta = null;
  let lastUnreadTotal = null;
  let pollTimer = null;
  let activeBucket = "";
  let staffRows = [];
  let allLabels = [];

  const convList = document.getElementById("crmConvList");
  const convEmpty = document.getElementById("crmConvEmpty");
  const msgThread = document.getElementById("crmMsgThread");
  const replyWrap = document.getElementById("crmInboxReplyWrap");
  const subjectEl = document.getElementById("crmInboxSubject");
  const channelEl = document.getElementById("crmInboxChannel");
  const detailName = document.getElementById("crmDetailName");
  const detailContact = document.getElementById("crmDetailContact");
  const callBtn = document.getElementById("crmDetailCallBtn");
  const emailBtn = document.getElementById("crmDetailEmailBtn");
  const waBtn = document.getElementById("crmDetailWaBtn");
  const timelineEl = document.getElementById("crmInboxTimeline");
  const assignModalEl = document.getElementById("crmInboxAssignModal");
  const assignModal = assignModalEl ? bootstrap.Modal.getOrCreateInstance(assignModalEl) : null;
  const convActions = document.getElementById("crmConvActions");
  const notifySound = document.getElementById("crmNotifySound");

  function staticUrl(path) {
    if (!path) return "";
    if (path.indexOf("http") === 0 || path.indexOf("/") === 0) return path;
    return "/static/" + path.replace(/^uploads\//, "uploads/");
  }

  function statusTicks(status) {
    const s = (status || "").toLowerCase();
    if (s === "failed") return '<span class="wa-ticks is-failed" title="Failed">!</span>';
    if (s === "read") return '<span class="wa-ticks is-read" title="Read">✓✓</span>';
    if (s === "delivered") return '<span class="wa-ticks" title="Delivered">✓✓</span>';
    if (s === "sent" || s === "queued") return '<span class="wa-ticks" title="Sent">✓</span>';
    return "";
  }

  function renderConversations(rows) {
    if (!rows.length) {
      convList.innerHTML = "";
      convEmpty.classList.remove("d-none");
      return;
    }
    convEmpty.classList.add("d-none");
    convList.innerHTML = rows
      .map(function (c) {
        const id = c.ConversationID;
        const unread = (c.UnreadCount || 0) > 0 ? " is-unread" : "";
        const active = id === activeConvId ? " is-active" : "";
        const name =
          c.IsUnknown
            ? "Unknown WhatsApp Contact"
            : c.CustomerName || c.LeadName || c.Subject || "Conversation #" + id;
        const pin = c.IsPinned ? '<i class="bi bi-pin-angle-fill wa-pin"></i> ' : "";
        const badge =
          (c.UnreadCount || 0) > 0
            ? '<span class="wa-unread-pill">' + c.UnreadCount + "</span>"
            : "";
        const mobile =
          c.ContactMobile || c.WhatsAppNumber || c.MobileNumber || c.LeadMobile || "";
        const preview = c.LastMessagePreview || "";
        const pri = c.Priority && c.Priority !== "Normal" ? " · " + c.Priority : "";
        const unk = c.IsUnknown ? ' <span class="wa-unknown">Unknown</span>' : "";
        return (
          '<li><button type="button" class="crm-conv-item' +
          unread +
          active +
          '" data-id="' +
          id +
          '">' +
          '<div class="d-flex justify-content-between gap-2">' +
          '<div class="crm-conv-subject">' +
          pin +
          CrmCommon.escapeHtml(name) +
          unk +
          "</div>" +
          badge +
          "</div>" +
          '<div class="crm-conv-meta">' +
          CrmCommon.escapeHtml(mobile) +
          (c.LastMessageAt ? " · " + CrmCommon.formatDate(c.LastMessageAt) : "") +
          pri +
          "</div>" +
          (preview
            ? '<div class="crm-conv-preview">' + CrmCommon.escapeHtml(preview) + "</div>"
            : "") +
          "</button></li>"
        );
      })
      .join("");
  }

  function renderMessages(rows) {
    if (!rows.length) {
      msgThread.innerHTML = '<div class="crm-grid-empty">No messages yet.</div>';
      return;
    }
    msgThread.innerHTML =
      '<div class="crm-msg-thread">' +
      rows
        .map(function (m) {
          const isNote = !!m.IsInternalNote;
          const outbound = m.Direction === "Outbound" || m.Direction === "Internal";
          const cls =
            "wa-msg" +
            (isNote ? " wa-msg--note" : outbound ? " wa-msg--out" : "");
          let mediaHtml = "";
          if (m.AttachmentPath) {
            const url = staticUrl(m.AttachmentPath);
            const mime = (m.AttachmentMimeType || "").toLowerCase();
            if (mime.indexOf("image/") === 0 || (m.MediaType || "") === "image") {
              mediaHtml =
                '<a href="' +
                CrmCommon.escapeHtml(url) +
                '" target="_blank" rel="noopener"><img class="wa-attach" src="' +
                CrmCommon.escapeHtml(url) +
                '" alt=""></a>';
            } else if (mime.indexOf("audio/") === 0 || (m.MediaType || "") === "audio") {
              mediaHtml =
                '<audio class="wa-attach" controls src="' +
                CrmCommon.escapeHtml(url) +
                '"></audio>';
            } else if (mime.indexOf("video/") === 0 || (m.MediaType || "") === "video") {
              mediaHtml =
                '<video class="wa-attach" controls src="' +
                CrmCommon.escapeHtml(url) +
                '"></video>';
            } else {
              mediaHtml =
                '<a class="small" href="' +
                CrmCommon.escapeHtml(url) +
                '" target="_blank" rel="noopener"><i class="bi bi-file-earmark"></i> ' +
                CrmCommon.escapeHtml(m.AttachmentName || "Attachment") +
                "</a>";
            }
          }
          const testBadge = m.IsTest
            ? '<span class="wa-test-flag">TEST MESSAGE</span> '
            : "";
          return (
            '<div class="' +
            cls +
            '"><div class="wa-bubble">' +
            testBadge +
            CrmCommon.escapeHtml(m.Body || "") +
            mediaHtml +
            '<div class="wa-msg-time">' +
            CrmCommon.formatDate(m.CreatedDate || m.SentAt) +
            (outbound && !isNote ? statusTicks(m.DeliveryStatus) : "") +
            "</div></div></div>"
          );
        })
        .join("") +
      "</div>";
    msgThread.scrollTop = msgThread.scrollHeight;
  }

  function renderTimeline(rows) {
    timelineEl.innerHTML =
      (rows || [])
        .map(function (ev) {
          return (
            '<li class="crm-timeline-item">' +
            '<div class="crm-timeline-title">' +
            CrmCommon.escapeHtml(ev.Title || ev.EventType || "Event") +
            "</div>" +
            '<div class="crm-timeline-meta">' +
            CrmCommon.formatDate(ev.CreatedDate) +
            "</div>" +
            (ev.Description
              ? '<div class="crm-timeline-desc">' +
                CrmCommon.escapeHtml(ev.Description) +
                "</div>"
              : "") +
            "</li>"
          );
        })
        .join("") || '<li class="text-muted small">No timeline events.</li>';
  }

  function setContactActions(conv) {
    activeConvMeta = conv;
    const mobile =
      conv.ContactMobile ||
      conv.MobileNumber ||
      conv.WhatsAppNumber ||
      conv.LeadMobile ||
      "";
    const email = conv.ContactEmail || conv.EmailID || conv.LeadEmail || "";
    detailName.textContent = conv.IsUnknown
      ? "Unknown WhatsApp Contact"
      : conv.CustomerName || conv.LeadName || conv.Subject || "—";
    detailContact.textContent = [mobile, email].filter(Boolean).join(" · ") || "—";

    const unknownBanner = document.getElementById("crmUnknownBanner");
    if (unknownBanner) unknownBanner.hidden = !conv.IsUnknown;

    const st = document.getElementById("crmDetailStatus");
    if (st && conv.Status) st.value = conv.Status;
    const pr = document.getElementById("crmDetailPriority");
    if (pr && conv.Priority) pr.value = conv.Priority;
    const asg = document.getElementById("crmDetailAssignSelect");
    if (asg) asg.value = conv.AssignedUserID || "";

    const c360 = document.getElementById("crmDetail360Btn");
    if (c360) {
      if (conv.CustomerID && api.customer360) {
        c360.href = api.customer360.replace(/\/?$/, "/") + conv.CustomerID;
        c360.classList.remove("d-none");
      } else c360.classList.add("d-none");
    }

    if (mobile) {
      callBtn.href = "tel:" + mobile.replace(/\s/g, "");
      callBtn.classList.remove("d-none");
    } else callBtn.classList.add("d-none");
    if (email) {
      emailBtn.href = "mailto:" + email;
      emailBtn.classList.remove("d-none");
    } else emailBtn.classList.add("d-none");
    if (conv.wa_url) {
      waBtn.href = conv.wa_url;
      waBtn.classList.remove("d-none");
    } else waBtn.classList.add("d-none");

    const ch = conv.Channel || "WhatsApp";
    const replyCh = document.getElementById("crmReplyChannel");
    if (replyCh) {
      const opt = Array.from(replyCh.options).find(function (o) {
        return o.value === ch;
      });
      if (opt) replyCh.value = ch;
    }
    if (convActions) convActions.hidden = false;
  }

  function maybeNotify(totalUnread) {
    if (lastUnreadTotal == null) {
      lastUnreadTotal = totalUnread;
      return;
    }
    if (totalUnread > lastUnreadTotal) {
      if (notifySound) {
        try {
          notifySound.currentTime = 0;
          notifySound.play().catch(function () {});
        } catch (_e) {}
      }
      if (typeof Notification !== "undefined" && Notification.permission === "granted") {
        try {
          new Notification("JTCS Communication Center", {
            body: "You have new customer messages",
            tag: "jtcs-crm-inbox",
          });
        } catch (_e) {}
      }
    }
    lastUnreadTotal = totalUnread;
  }

  async function loadConversations() {
    const params = new URLSearchParams();
    const status = document.getElementById("crmInboxStatusFilter");
    const dateF = document.getElementById("crmInboxDateFilter");
    const search = document.getElementById("crmInboxSearch");
    const unreadOnly = document.getElementById("crmInboxUnreadOnly");
    if (status && status.value) params.set("status", status.value);
    if (dateF && dateF.value) params.set("date", dateF.value);
    if (search && search.value.trim()) params.set("search", search.value.trim());
    if (unreadOnly && unreadOnly.checked) params.set("unread", "1");
    if (activeBucket) params.set("bucket", activeBucket);
    if (activeChannel) params.set("channel", activeChannel);
    const labelF = document.getElementById("crmInboxLabelFilter");
    if (labelF && labelF.value) params.set("label_id", labelF.value);
    const data = await CrmCommon.apiFetch(api.list + "?" + params.toString());
    renderConversations(data.rows || []);
    const unreadSum = (data.rows || []).reduce(function (n, r) {
      return n + (parseInt(r.UnreadCount, 10) || 0);
    }, 0);
    maybeNotify(unreadSum);
  }

  async function selectConversation(id) {
    activeConvId = id;
    const detailUrl = CrmCommon.urlTemplate(api.detail, id);
    const data = await CrmCommon.apiFetch(detailUrl);
    const conv = data.conversation || {};
    subjectEl.textContent =
      conv.CustomerName || conv.LeadName || conv.Subject || "Conversation #" + id;
    channelEl.textContent = conv.Channel || "";
    replyWrap.classList.remove("d-none");
    setContactActions(conv);
    renderTimeline(data.timeline || []);
    const msgData = await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.messages, id));
    renderMessages(msgData.rows || []);
    loadConversations();
  }

  async function pollMessages() {
    if (!activeConvId) return;
    try {
      const msgData = await CrmCommon.apiFetch(
        CrmCommon.urlTemplate(api.messages, activeConvId)
      );
      renderMessages(msgData.rows || []);
    } catch (_e) {}
  }

  async function loadQuickRepliesAndTemplates() {
    try {
      if (api.quickReplies) {
        const qr = await CrmCommon.apiFetch(
          api.quickReplies + (activeChannel ? "?channel=" + encodeURIComponent(activeChannel) : "")
        );
        const sel = document.getElementById("crmQuickReplySelect");
        if (sel) {
          sel.innerHTML =
            '<option value="">Quick replies…</option>' +
            (qr.rows || [])
              .map(function (r) {
                return (
                  '<option value="' +
                  CrmCommon.escapeHtml(r.Body || "") +
                  '" data-shortcut="' +
                  CrmCommon.escapeHtml(r.Shortcut || "") +
                  '">' +
                  CrmCommon.escapeHtml((r.Shortcut ? r.Shortcut + " — " : "") + (r.Title || "Reply")) +
                  "</option>"
                );
              })
              .join("");
        }
      }
      if (api.templates) {
        const tp = await CrmCommon.apiFetch(
          api.templates + (activeChannel ? "?channel=" + encodeURIComponent(activeChannel) : "")
        );
        const sel = document.getElementById("crmTemplateSelect");
        if (sel) {
          sel.innerHTML =
            '<option value="">Templates…</option>' +
            (tp.rows || [])
              .map(function (r) {
                return (
                  '<option value="' +
                  CrmCommon.escapeHtml(r.Body || "") +
                  '">' +
                  CrmCommon.escapeHtml(r.Name || "Template") +
                  "</option>"
                );
              })
              .join("");
        }
      }
    } catch (_e) {}
  }

  async function patchConv(body) {
    if (!activeConvId) return;
    await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.update, activeConvId), {
      method: "PATCH",
      body: body,
    });
    selectConversation(activeConvId);
  }

  document.querySelectorAll(".wa-channel-tab").forEach(function (tab) {
    if (tab.dataset.channel === activeChannel) {
      document.querySelectorAll(".wa-channel-tab").forEach(function (t) {
        t.classList.remove("is-active");
      });
      tab.classList.add("is-active");
    }
    tab.addEventListener("click", function () {
      document.querySelectorAll(".wa-channel-tab").forEach(function (t) {
        t.classList.remove("is-active");
      });
      tab.classList.add("is-active");
      activeChannel = tab.dataset.channel || "";
      loadConversations();
      loadQuickRepliesAndTemplates();
    });
  });

  convList.addEventListener("click", function (e) {
    const btn = e.target.closest(".crm-conv-item");
    if (!btn) return;
    selectConversation(parseInt(btn.dataset.id, 10)).catch(function (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    });
  });

  const replyForm = document.getElementById("crmInboxReplyForm");
  if (replyForm) {
    replyForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (!activeConvId) return;
      const body = document.getElementById("crmReplyBody").value.trim();
      const fileInput = document.getElementById("crmReplyFile");
      try {
        if (fileInput && fileInput.files && fileInput.files[0]) {
          const fd = new FormData();
          fd.append("file", fileInput.files[0]);
          fd.append("caption", body);
          fd.append("channel", document.getElementById("crmReplyChannel").value);
          const token =
            (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
          const resp = await fetch(CrmCommon.urlTemplate(api.attachments, activeConvId), {
            method: "POST",
            credentials: "same-origin",
            headers: token ? { "X-CSRFToken": token } : {},
            body: fd,
          });
          const data = await resp.json();
          if (!resp.ok || data.ok === false) {
            throw Object.assign(new Error(data.error || "Upload failed"), { data: data });
          }
          if (data.warning) CrmCommon.showAlert(data.warning, "warning");
          fileInput.value = "";
        } else {
          if (!body) return;
          const data = await CrmCommon.apiFetch(
            CrmCommon.urlTemplate(api.reply, activeConvId),
            {
              method: "POST",
              body: {
                body: body,
                channel: document.getElementById("crmReplyChannel").value,
                is_internal_note: document.getElementById("crmReplyNote").checked,
              },
            }
          );
          if (data.warning) CrmCommon.showAlert(data.warning, "warning");
        }
        document.getElementById("crmReplyBody").value = "";
        selectConversation(activeConvId);
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });
  }

  ["crmQuickReplySelect", "crmTemplateSelect"].forEach(function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", function () {
      if (!el.value) return;
      document.getElementById("crmReplyBody").value = el.value;
      el.selectedIndex = 0;
    });
  });

  document.getElementById("crmDetailCloseBtn").addEventListener("click", async function () {
    if (!activeConvId || !window.confirm("Close this conversation?")) return;
    try {
      await patchConv({ status: "Closed" });
      loadConversations();
    } catch (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    }
  });

  document.getElementById("crmDetailAssignBtn").addEventListener("click", function () {
    if (!activeConvId) return;
    if (assignModal) assignModal.show();
  });

  document.getElementById("crmInboxAssignForm").addEventListener("submit", async function (e) {
    e.preventDefault();
    if (!activeConvId) return;
    const userId = parseInt(document.getElementById("crmInboxAssignUserId").value, 10);
    try {
      await patchConv({ assigned_user_id: userId || null });
      if (assignModal) assignModal.hide();
    } catch (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    }
  });

  const pinBtn = document.getElementById("crmPinBtn");
  if (pinBtn) {
    pinBtn.addEventListener("click", function () {
      patchConv({ is_pinned: !(activeConvMeta && activeConvMeta.IsPinned) }).catch(function (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      });
    });
  }
  const starBtn = document.getElementById("crmStarBtn");
  if (starBtn) {
    starBtn.addEventListener("click", function () {
      patchConv({ is_starred: !(activeConvMeta && activeConvMeta.IsStarred) }).catch(function (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      });
    });
  }
  const archiveBtn = document.getElementById("crmArchiveBtn");
  if (archiveBtn) {
    archiveBtn.addEventListener("click", function () {
      patchConv({ is_archived: true }).catch(function (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      });
    });
  }

  const emailSyncBtn = document.getElementById("crmEmailSyncBtn");
  if (emailSyncBtn && api.emailSync) {
    emailSyncBtn.addEventListener("click", async function () {
      try {
        const data = await CrmCommon.apiFetch(api.emailSync, { method: "POST", body: {} });
        if (data.ok) {
          CrmCommon.showAlert(
            "IMAP sync: imported " + (data.imported || 0) + ", skipped " + (data.skipped || 0),
            "success"
          );
          loadConversations();
        } else {
          CrmCommon.showAlert(data.error || "IMAP sync failed", "warning");
        }
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });
  }

  const notifyBtn = document.getElementById("crmNotifyEnableBtn");
  if (notifyBtn && typeof Notification !== "undefined") {
    notifyBtn.addEventListener("click", function () {
      Notification.requestPermission();
    });
  }

  ["crmInboxStatusFilter", "crmInboxDateFilter", "crmInboxUnreadOnly", "crmInboxLabelFilter"].forEach(function (id) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", loadConversations);
  });
  const searchEl = document.getElementById("crmInboxSearch");
  if (searchEl) {
    searchEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter") loadConversations();
    });
  }

  document.querySelectorAll("#crmInboxBuckets .wa-bucket").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll("#crmInboxBuckets .wa-bucket").forEach(function (b) {
        b.classList.remove("is-active");
      });
      btn.classList.add("is-active");
      activeBucket = btn.dataset.bucket || "";
      loadConversations();
    });
  });

  function fillStaffSelects() {
    const opts =
      '<option value="">Unassigned</option>' +
      staffRows
        .map(function (u) {
          return (
            '<option value="' +
            u.UserID +
            '">' +
            CrmCommon.escapeHtml(u.FullName || "User " + u.UserID) +
            "</option>"
          );
        })
        .join("");
    ["crmInboxAssignUserId", "crmDetailAssignSelect", "crmFuAssign", "crmTaskAssign"].forEach(function (id) {
      const el = document.getElementById(id);
      if (el) el.innerHTML = opts;
    });
  }

  async function loadStaffAndLabels() {
    try {
      if (api.staff) {
        const data = await CrmCommon.apiFetch(api.staff);
        staffRows = data.rows || [];
        fillStaffSelects();
      }
    } catch (_e) {}
    try {
      if (api.labels) {
        const data = await CrmCommon.apiFetch(api.labels);
        allLabels = data.rows || [];
        const picker = document.getElementById("crmLabelPicker");
        const labelFilter = document.getElementById("crmInboxLabelFilter");
        const opts = allLabels
          .map(function (l) {
            return (
              '<option value="' +
              l.LabelID +
              '">' +
              CrmCommon.escapeHtml(l.LabelName) +
              "</option>"
            );
          })
          .join("");
        if (picker) picker.innerHTML = opts;
        if (labelFilter) {
          labelFilter.innerHTML = '<option value="">All labels</option>' + opts;
        }
      }
    } catch (_e) {}
    const simWrap = document.getElementById("crmSimulateWrap");
    if (simWrap) simWrap.hidden = !testMode;
  }

  document.getElementById("crmUnknownBanner") &&
    document.getElementById("crmUnknownBanner").addEventListener("click", async function (e) {
      const btn = e.target.closest("[data-link-action]");
      if (!btn || !activeConvId || !api.link) return;
      const action = btn.getAttribute("data-link-action");
      const name = window.prompt("Name for this contact", activeConvMeta && (activeConvMeta.Subject || "")) || "";
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.link, activeConvId), {
          method: "POST",
          body: { action: action, full_name: name },
        });
        selectConversation(activeConvId);
        loadConversations();
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });

  const detailStatus = document.getElementById("crmDetailStatus");
  if (detailStatus) {
    detailStatus.addEventListener("change", function () {
      patchConv({ status: detailStatus.value });
    });
  }
  const detailPri = document.getElementById("crmDetailPriority");
  if (detailPri) {
    detailPri.addEventListener("change", function () {
      patchConv({ priority: detailPri.value });
    });
  }
  const detailAssign = document.getElementById("crmDetailAssignSelect");
  if (detailAssign) {
    detailAssign.addEventListener("change", function () {
      const val = detailAssign.value ? parseInt(detailAssign.value, 10) : null;
      patchConv({ assigned_user_id: val });
    });
  }
  const labelSave = document.getElementById("crmLabelSaveBtn");
  if (labelSave && api.convLabels) {
    labelSave.addEventListener("click", async function () {
      if (!activeConvId) return;
      const picker = document.getElementById("crmLabelPicker");
      const ids = picker ? Array.from(picker.selectedOptions).map(function (o) { return parseInt(o.value, 10); }) : [];
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.convLabels, activeConvId), {
          method: "POST",
          body: { label_ids: ids },
        });
        CrmCommon.showAlert("Labels saved", "success");
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });
  }

  const fuModalEl = document.getElementById("crmFollowupModal");
  const fuModal = fuModalEl ? bootstrap.Modal.getOrCreateInstance(fuModalEl) : null;
  const taskModalEl = document.getElementById("crmTaskModal");
  const taskModal = taskModalEl ? bootstrap.Modal.getOrCreateInstance(taskModalEl) : null;
  const fuBtn = document.getElementById("crmDetailFollowupBtn");
  if (fuBtn) fuBtn.addEventListener("click", function () { if (fuModal) fuModal.show(); });
  const taskBtn = document.getElementById("crmDetailTaskBtn");
  if (taskBtn) taskBtn.addEventListener("click", function () { if (taskModal) taskModal.show(); });

  const fuForm = document.getElementById("crmFollowupForm");
  if (fuForm && api.followups) {
    fuForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (!activeConvId || !activeConvMeta) return;
      try {
        await CrmCommon.apiFetch(api.followups, {
          method: "POST",
          body: {
            followup_type: document.getElementById("crmFuType").value,
            due_at: document.getElementById("crmFuDue").value,
            notes: document.getElementById("crmFuNotes").value,
            priority: (document.getElementById("crmFuPriority") || {}).value || "Normal",
            assigned_user_id: (function () {
              const el = document.getElementById("crmFuAssign");
              return el && el.value ? parseInt(el.value, 10) : null;
            })(),
            assigned_user_name: (function () {
              const el = document.getElementById("crmFuAssign");
              if (!el || !el.value) return null;
              const opt = el.options[el.selectedIndex];
              return opt ? opt.textContent : null;
            })(),
            customer_id: activeConvMeta.CustomerID,
            lead_id: activeConvMeta.LeadID,
            conversation_id: activeConvId,
          },
        });
        if (fuModal) fuModal.hide();
        CrmCommon.showAlert("Follow-up created", "success");
        selectConversation(activeConvId);
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });
  }
  const taskForm = document.getElementById("crmTaskForm");
  if (taskForm && api.tasks) {
    taskForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (!activeConvId || !activeConvMeta) return;
      try {
        await CrmCommon.apiFetch(api.tasks, {
          method: "POST",
          body: {
            title: document.getElementById("crmTaskTitle").value,
            deadline: document.getElementById("crmTaskDue").value || null,
            priority: document.getElementById("crmTaskPriority").value,
            assigned_user_id: (function () {
              const el = document.getElementById("crmTaskAssign");
              return el && el.value ? parseInt(el.value, 10) : null;
            })(),
            assigned_user_name: (function () {
              const el = document.getElementById("crmTaskAssign");
              if (!el || !el.value) return null;
              const opt = el.options[el.selectedIndex];
              return opt ? opt.textContent : null;
            })(),
            customer_id: activeConvMeta.CustomerID,
            lead_id: activeConvMeta.LeadID,
            conversation_id: activeConvId,
            source: "WhatsApp",
          },
        });
        if (taskModal) taskModal.hide();
        CrmCommon.showAlert("Task created", "success");
        selectConversation(activeConvId);
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });
  }

  const simBtn = document.getElementById("crmSimSendBtn");
  if (simBtn && api.simulate) {
    simBtn.addEventListener("click", async function () {
      try {
        const data = await CrmCommon.apiFetch(api.simulate, {
          method: "POST",
          body: {
            mobile: document.getElementById("crmSimMobile").value,
            display_name: document.getElementById("crmSimName").value,
            body: document.getElementById("crmSimBody").value,
          },
        });
        CrmCommon.showAlert("Test message received", "success");
        if (data.conversation_id) selectConversation(data.conversation_id);
        else loadConversations();
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });
  }

  const replyBody = document.getElementById("crmReplyBody");
  if (replyBody) {
    replyBody.addEventListener("input", function () {
      const raw = replyBody.value.trim();
      if (!raw.startsWith("/") || raw.indexOf(" ") >= 0) return;
      const sel = document.getElementById("crmQuickReplySelect");
      if (!sel) return;
      for (let i = 0; i < sel.options.length; i++) {
        const opt = sel.options[i];
        const shortcut = (opt.getAttribute("data-shortcut") || "").trim().toLowerCase();
        if (shortcut && shortcut === raw.toLowerCase() && opt.value) {
          replyBody.value = opt.value;
          replyBody.focus();
          return;
        }
      }
    });
  }

  loadStaffAndLabels();
  loadConversations()
    .then(function () {
      if (activeConvId) return selectConversation(activeConvId);
    })
    .catch(function () {});
  loadQuickRepliesAndTemplates();
  pollTimer = setInterval(function () {
    loadConversations().catch(function () {});
    pollMessages();
  }, pollSeconds * 1000);
})();
