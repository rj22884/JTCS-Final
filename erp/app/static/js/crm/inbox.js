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
  };
  const pollSeconds = Math.max(5, parseInt(page.dataset.pollSeconds, 10) || 15);
  let activeChannel = page.dataset.initialChannel || "";
  let activeConvId = page.dataset.initialConversation
    ? parseInt(page.dataset.initialConversation, 10)
    : null;
  let activeConvMeta = null;
  let lastUnreadTotal = null;
  let pollTimer = null;

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
          c.CustomerName || c.LeadName || c.Subject || "Conversation #" + id;
        const pin = c.IsPinned ? '<i class="bi bi-pin-angle-fill wa-pin"></i> ' : "";
        const badge =
          (c.UnreadCount || 0) > 0
            ? '<span class="wa-unread-pill">' + c.UnreadCount + "</span>"
            : "";
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
          "</div>" +
          badge +
          "</div>" +
          '<div class="crm-conv-meta">' +
          CrmCommon.escapeHtml(c.Channel || "") +
          (c.LastMessageAt ? " · " + CrmCommon.formatDate(c.LastMessageAt) : "") +
          "</div></button></li>"
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
          return (
            '<div class="' +
            cls +
            '"><div class="wa-bubble">' +
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
    detailName.textContent =
      conv.CustomerName || conv.LeadName || conv.Subject || "—";
    detailContact.textContent = [mobile, email].filter(Boolean).join(" · ") || "—";

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
    if (activeChannel) params.set("channel", activeChannel);
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
                  '">' +
                  CrmCommon.escapeHtml(r.Title || "Reply") +
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
      await patchConv({ assigned_user_id: userId });
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

  ["crmInboxStatusFilter", "crmInboxDateFilter", "crmInboxUnreadOnly"].forEach(function (id) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", loadConversations);
  });
  const searchEl = document.getElementById("crmInboxSearch");
  if (searchEl) {
    searchEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter") loadConversations();
    });
  }

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
