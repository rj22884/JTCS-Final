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
  };
  const pollSeconds = Math.max(5, parseInt(page.dataset.pollSeconds, 10) || 15);

  let activeConvId = null;
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
        return (
          '<li><button type="button" class="crm-conv-item' + unread + active + '" data-id="' + id + '">' +
          '<div class="crm-conv-subject">' + CrmCommon.escapeHtml(c.Subject || "Conversation #" + id) + "</div>" +
          '<div class="crm-conv-meta">' + CrmCommon.escapeHtml(c.Channel || "") +
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
    msgThread.innerHTML = '<div class="crm-msg-thread">' + rows
      .map(function (m) {
        const note = m.IsInternalNote ? " crm-msg-bubble--note" : "";
        const outbound = m.Direction === "Outbound" ? " crm-msg-bubble--outbound" : "";
        return (
          '<div class="crm-msg-bubble' + outbound + note + '">' +
          CrmCommon.escapeHtml(m.Body || m.MessageBody || "") +
          '<div class="crm-msg-time">' + CrmCommon.formatDate(m.CreatedDate || m.SentAt) + "</div></div>"
        );
      })
      .join("") + "</div>";
    msgThread.scrollTop = msgThread.scrollHeight;
  }

  function renderTimeline(rows) {
    timelineEl.innerHTML = (rows || [])
      .map(function (ev) {
        return (
          '<li class="crm-timeline-item">' +
          '<div class="crm-timeline-title">' + CrmCommon.escapeHtml(ev.Title || ev.EventType || "Event") + "</div>" +
          '<div class="crm-timeline-meta">' + CrmCommon.formatDate(ev.CreatedDate) + "</div>" +
          (ev.Description ? '<div class="crm-timeline-desc">' + CrmCommon.escapeHtml(ev.Description) + "</div>" : "") +
          "</li>"
        );
      })
      .join("") || '<li class="text-muted small">No timeline events.</li>';
  }

  function setContactActions(conv) {
    const mobile = conv.MobileNumber || conv.WhatsAppNumber || conv.LeadMobile || "";
    const email = conv.EmailID || conv.LeadEmail || "";
    detailName.textContent = conv.CustomerName || conv.LeadFullName || conv.Subject || "—";
    detailContact.textContent = [mobile, email].filter(Boolean).join(" · ") || "—";

    if (mobile) {
      callBtn.href = "tel:" + mobile.replace(/\s/g, "");
      callBtn.classList.remove("d-none");
    } else {
      callBtn.classList.add("d-none");
    }
    if (email) {
      emailBtn.href = "mailto:" + email;
      emailBtn.classList.remove("d-none");
    } else {
      emailBtn.classList.add("d-none");
    }
    if (conv.wa_url) {
      waBtn.href = conv.wa_url;
      waBtn.classList.remove("d-none");
    } else {
      waBtn.classList.add("d-none");
    }
  }

  async function loadConversations() {
    const params = new URLSearchParams();
    const status = document.getElementById("crmInboxStatusFilter");
    const priority = document.getElementById("crmInboxPriorityFilter");
    const search = document.getElementById("crmInboxSearch");
    if (status && status.value) params.set("status", status.value);
    if (priority && priority.value) params.set("priority", priority.value);
    if (search && search.value.trim()) params.set("search", search.value.trim());
    const data = await CrmCommon.apiFetch(api.list + "?" + params.toString());
    renderConversations(data.rows || []);
  }

  async function selectConversation(id) {
    activeConvId = id;
    const detailUrl = CrmCommon.urlTemplate(api.detail, id);
    const data = await CrmCommon.apiFetch(detailUrl);
    const conv = data.conversation || {};
    subjectEl.textContent = conv.Subject || "Conversation #" + id;
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
      const msgData = await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.messages, activeConvId));
      renderMessages(msgData.rows || []);
    } catch (_e) { /* ignore */ }
  }

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
      if (!body) return;
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.reply, activeConvId), {
          method: "POST",
          body: {
            body: body,
            channel: document.getElementById("crmReplyChannel").value,
            is_internal_note: document.getElementById("crmReplyNote").checked,
          },
        });
        document.getElementById("crmReplyBody").value = "";
        selectConversation(activeConvId);
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });
  }

  document.getElementById("crmDetailCloseBtn").addEventListener("click", async function () {
    if (!activeConvId || !window.confirm("Close this conversation?")) return;
    try {
      await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.update, activeConvId), {
        method: "PATCH",
        body: { status: "Closed" },
      });
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
      await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.update, activeConvId), {
        method: "PATCH",
        body: { assigned_user_id: userId },
      });
      if (assignModal) assignModal.hide();
      selectConversation(activeConvId);
    } catch (err) {
      CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
    }
  });

  ["crmInboxStatusFilter", "crmInboxPriorityFilter"].forEach(function (id) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("change", loadConversations);
  });
  const searchEl = document.getElementById("crmInboxSearch");
  if (searchEl) {
    searchEl.addEventListener("keydown", function (e) {
      if (e.key === "Enter") loadConversations();
    });
  }

  loadConversations().catch(function () { /* ignore */ });
  pollTimer = setInterval(function () {
    loadConversations().catch(function () { /* ignore */ });
    pollMessages();
  }, pollSeconds * 1000);
})();
