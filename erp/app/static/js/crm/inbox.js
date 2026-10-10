(function () {
  "use strict";

  const page = document.getElementById("crmInboxPage");
  if (!page) return;

  const api = {
    list: page.dataset.apiList,
    detail: page.dataset.apiDetail,
    messages: page.dataset.apiMessages,
    messageFile: page.dataset.apiMessageFile,
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
    matches: page.dataset.apiMatches,
    convLabels: page.dataset.apiConvLabels,
    tasks: page.dataset.apiTasks,
    followups: page.dataset.apiFollowups,
    simulateStatus: page.dataset.apiSimulateStatus,
    start: page.dataset.apiStart,
    search: page.dataset.apiSearch,
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
  let templateRows = [];
  let templateDefaults = {};
  let activeTemplate = null;
  let allLabels = [];
  const convById = {};

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
    const normalized = String(path).replace(/\\/g, "/");
    if (normalized.indexOf("http") === 0 || normalized.indexOf("/") === 0) return encodeURI(normalized);
    return encodeURI("/static/" + normalized.replace(/^uploads\//, "uploads/"));
  }

  function messageFileUrl(messageId) {
    const id = parseInt(messageId, 10);
    if (!Number.isFinite(id) || id <= 0) return "";
    return "/api/crm/messages/" + id + "/file";
  }

  function fileHref(message) {
    return messageFileUrl(message.MessageID) || staticUrl(message.AttachmentPath);
  }

  function isBrowserImage(message) {
    const mime = (message.AttachmentMimeType || "").toLowerCase();
    const name = (message.AttachmentName || message.AttachmentPath || "").toLowerCase();
    if (mime.indexOf("image/tiff") === 0 || name.endsWith(".tif") || name.endsWith(".tiff")) return false;
    return mime.indexOf("image/") === 0 || (message.MediaType || "") === "image";
  }

  function statusTicks(status, error) {
    const s = (status || "").toLowerCase();
    const reason = (error || "").trim();
    if (s === "failed") {
      return (
        '<span class="wa-ticks is-failed" title="' +
        CrmCommon.escapeHtml(reason || "Not delivered") +
        '">!</span>'
      );
    }
    if (s === "read") return '<span class="wa-ticks is-read" title="Read">✓✓</span>';
    if (s === "delivered") return '<span class="wa-ticks" title="Delivered">✓✓</span>';
    if (s === "sent" || s === "queued") return '<span class="wa-ticks" title="Sent">✓</span>';
    return "";
  }

  const promptedThisPage = {};
  let linkDialogConvId = null;
  let linkDialogMatches = [];
  let linkDialogPhase = "choose";
  let linkDialogMainId = null;
  let linkDialogMergeIds = [];
  let mergeLinkBusy = false;

  function conversationTitle(c) {
    if (!c) return "Unknown WhatsApp Contact";
    if (c.CustomerName) return c.CustomerName;
    if (c.LeadName) return c.LeadName;
    const subject = String(c.Subject || "").trim();
    if (
      !subject ||
      subject === "Unknown WhatsApp Contact" ||
      subject === "Multiple Customers Found" ||
      subject === "Unlinked WhatsApp Contact"
    ) {
      return "Unknown WhatsApp Contact";
    }
    return subject;
  }

  function contactMobileOf(c) {
    if (!c) return "";
    return c.ContactMobile || c.WhatsAppNumber || c.MobileNumber || c.LeadMobile || "";
  }

  function candidateList(conv) {
    const raw = (conv && (conv.link_candidates || conv.match_candidates)) || [];
    return raw
      .map(function (row) {
        return {
          customer_id: row.customer_id || row.CustomerID,
          customer_name: row.customer_name || row.CustomerName || "",
          mobile: row.mobile || row.MobileNumber || row.WhatsAppNumber || row.AlternateMobile || "",
          email: row.email || row.EmailID || "",
        };
      })
      .filter(function (row) {
        return row.customer_id;
      });
  }

  function linkModal() {
    const el = document.getElementById("crmWaLinkModal");
    if (!el || !window.bootstrap) return null;
    return bootstrap.Modal.getOrCreateInstance(el);
  }

  function selectedLinkCustomerId() {
    const picked = document.querySelector("#crmWaLinkChoices input[name='crmWaCustomer']:checked");
    if (picked) return parseInt(picked.value, 10);
    const conv = convById[linkDialogConvId] || activeConvMeta;
    const rows = candidateList(conv);
    if (rows.length === 1) return parseInt(rows[0].customer_id, 10);
    return null;
  }

  function openCustomerRecord(customerId) {
    const base = api.customer360 || "/crm/customer-360";
    const url = String(base).replace(/\/?$/, "/") + customerId;
    const host = window.top || window;
    if (host.jtcsOpenPageWindow) host.jtcsOpenPageWindow(url, "Customer");
    else window.location.href = url;
  }

  async function confirmCustomerLink() {
    const customerId = selectedLinkCustomerId();
    if (!customerId || !linkDialogConvId || !api.link) {
      CrmCommon.showAlert("Select the Customer Master record to link.", "warning");
      return;
    }
    const convId = linkDialogConvId;
    await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.link, convId), {
      method: "POST",
      body: { action: "link_customer", customer_id: customerId },
    });
    promptedThisPage[convId] = true;
    linkDialogConvId = null;
    const modal = linkModal();
    if (modal) modal.hide();
    if (activeConvId === convId) await selectConversation(convId);
    else await loadConversations();
  }

  function mergeHelpers() {
    return window.JtcsWaMergeLink || null;
  }

  function showMergeError(err) {
    CrmCommon.showAlert((err && err.data && err.data.error) || (err && err.message) || "Merge & Link failed.", "danger");
  }

  async function submitMergeLink(convId, mainId, mergeIds) {
    if (mergeLinkBusy) return null;
    mergeLinkBusy = true;
    const helpers = mergeHelpers();
    try {
      const data = await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.link, convId), {
        method: "POST",
        body: {
          action: "merge_and_link",
          customer_id: mainId,
          merge_customer_ids: mergeIds || [],
        },
      });
      promptedThisPage[convId] = true;
      linkDialogConvId = null;
      const modal = linkModal();
      if (modal) modal.hide();
      const message = (data && data.message) || (helpers && helpers.resultMessage(data)) || "WhatsApp contact linked.";
      CrmCommon.showAlert(message, "success");
      if (activeConvId === convId) await selectConversation(convId);
      else await loadConversations();
      return data;
    } finally {
      mergeLinkBusy = false;
    }
  }

  function bindMainMergeToggles() {
    const choices = document.getElementById("crmWaLinkChoices");
    if (!choices) return;
    choices.querySelectorAll("input[name='crmWaMain']").forEach(function (radio) {
      radio.addEventListener("change", function () {
        choices.querySelectorAll("input[name='crmWaMerge']").forEach(function (box) {
          const isMain = box.value === radio.value;
          if (isMain) box.checked = false;
          box.disabled = isMain;
        });
      });
    });
  }

  function renderMergeDialog() {
    const helpers = mergeHelpers();
    const modal = linkModal();
    if (!helpers || !modal) return;
    const ui = helpers.renderDialog({
      phase: linkDialogPhase,
      matches: linkDialogMatches,
      mainId: linkDialogMainId,
      mergeIds: linkDialogMergeIds,
    });
    const title = document.getElementById("crmWaLinkTitle");
    const message = document.getElementById("crmWaLinkMessage");
    const choices = document.getElementById("crmWaLinkChoices");
    const review = document.getElementById("crmWaLinkReview");
    const actions = document.getElementById("crmWaLinkActions");
    const customerBlock = document.getElementById("crmWaLinkCustomerBlock");
    const phoneEl = document.getElementById("crmWaLinkPhone");
    const conv = convById[linkDialogConvId] || activeConvMeta || {};
    if (phoneEl) phoneEl.textContent = contactMobileOf(conv) || "—";
    if (title) title.textContent = ui.title;
    if (message) message.textContent = ui.message;
    if (customerBlock) customerBlock.classList.add("d-none");
    if (choices) {
      choices.innerHTML = ui.choicesHtml || "";
      choices.classList.toggle("d-none", !ui.showChoices);
    }
    if (review) {
      review.innerHTML = ui.reviewHtml || "";
      review.classList.toggle("d-none", !ui.showReview);
    }
    if (actions) actions.innerHTML = ui.actionsHtml || "";
    bindMainMergeToggles();
    modal.show();
  }

  async function startMergeAndLink(convId) {
    if (mergeLinkBusy) return;
    const helpers = mergeHelpers();
    if (!helpers || !api.matches || !convId) {
      CrmCommon.showAlert("Merge & Link is not available.", "danger");
      return;
    }
    const data = await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.matches, convId));
    const matches = data.matches || [];
    const decision = helpers.decideMergeLink(matches);
    if (decision.kind === "none") {
      CrmCommon.showAlert(
        "No Customer Master record matches this WhatsApp contact. Use Create Customer, Create Lead, or Ignore.",
        "warning"
      );
      return;
    }
    if (decision.kind === "auto") {
      await submitMergeLink(convId, decision.mainId, []);
      return;
    }
    linkDialogConvId = convId;
    linkDialogMatches = matches;
    linkDialogPhase = "choose";
    linkDialogMainId = null;
    linkDialogMergeIds = [];
    renderMergeDialog();
  }

  function openLinkDialog(conv, mode) {
    const modal = linkModal();
    if (!modal || !conv) return;
    linkDialogConvId = conv.ConversationID;
    const candidates = candidateList(conv);
    const multiple = candidates.length > 1;
    const phone = contactMobileOf(conv) || "—";
    const title = document.getElementById("crmWaLinkTitle");
    const message = document.getElementById("crmWaLinkMessage");
    const phoneEl = document.getElementById("crmWaLinkPhone");
    const customerBlock = document.getElementById("crmWaLinkCustomerBlock");
    const customerEl = document.getElementById("crmWaLinkCustomer");
    const choices = document.getElementById("crmWaLinkChoices");
    const actions = document.getElementById("crmWaLinkActions");
    if (phoneEl) phoneEl.textContent = phone;
    if (multiple) {
      if (title) title.textContent = "Select Customer Master record";
      if (message) {
        message.textContent =
          "Multiple Customer Master records match this WhatsApp contact. Please select the correct customer.";
      }
      if (customerBlock) customerBlock.classList.add("d-none");
      if (choices) {
        choices.classList.remove("d-none");
        choices.innerHTML = candidates
          .map(function (row, index) {
            return (
              '<label class="list-group-item">' +
              '<input class="form-check-input me-2" type="radio" name="crmWaCustomer" value="' +
              row.customer_id +
              '"' +
              (index === 0 ? " checked" : "") +
              "> " +
              "<strong>" +
              CrmCommon.escapeHtml(row.customer_name || "Customer") +
              "</strong>" +
              "<div class=\"small text-muted\">" +
              CrmCommon.escapeHtml(row.mobile || "") +
              " · Customer ID " +
              row.customer_id +
              "</div></label>"
            );
          })
          .join("");
      }
    } else {
      const one = candidates[0] || {};
      if (title) title.textContent = mode === "exists" ? "Customer already exists" : "Link WhatsApp contact";
      if (message) {
        message.textContent =
          mode === "exists"
            ? "Customer already exists in Customer Master."
            : "An existing Customer Master record matches this WhatsApp contact. Do you want to link/merge this WhatsApp contact with the existing Customer Master record?";
      }
      if (customerBlock) customerBlock.classList.remove("d-none");
      if (customerEl) {
        customerEl.textContent = [one.customer_name || "Customer", one.mobile || ""]
          .filter(Boolean)
          .join("\n");
        customerEl.style.whiteSpace = "pre-line";
      }
      if (choices) {
        choices.classList.add("d-none");
        choices.innerHTML = "";
      }
    }
    if (actions) {
      const buttons = [];
      if (mode === "exists") {
        buttons.push(
          '<button type="button" class="btn btn-outline-primary btn-sm" data-wa-link="open">Open Customer</button>'
        );
        buttons.push(
          '<button type="button" class="btn btn-outline-primary btn-sm" data-wa-link="link">Link WhatsApp</button>'
        );
      }
      buttons.push(
        '<button type="button" class="btn btn-primary btn-sm" data-wa-link="merge">Merge &amp; Link</button>'
      );
      if (mode !== "exists") {
        buttons.push(
          '<button type="button" class="btn btn-outline-secondary btn-sm" data-wa-link="later">Not Now</button>'
        );
      }
      buttons.push(
        '<button type="button" class="btn btn-outline-secondary btn-sm" data-bs-dismiss="modal">Cancel</button>'
      );
      actions.innerHTML = buttons.join("");
    }
    modal.show();
  }

  function renderConversations(rows) {
    if (!rows.length) {
      convList.innerHTML = "";
      convEmpty.classList.remove("d-none");
      return;
    }
    convEmpty.classList.add("d-none");
    rows.forEach(function (c) {
      convById[c.ConversationID] = c;
    });
    convList.innerHTML = rows
      .map(function (c) {
        const id = c.ConversationID;
        const unread = (c.UnreadCount || 0) > 0 ? " is-unread" : "";
        const active = id === activeConvId ? " is-active" : "";
        const name = conversationTitle(c);
        const pin = c.IsPinned ? '<i class="bi bi-pin-angle-fill wa-pin"></i> ' : "";
        const badge =
          (c.UnreadCount || 0) > 0
            ? '<span class="wa-unread-pill">' + c.UnreadCount + "</span>"
            : "";
        const mobile = contactMobileOf(c);
        const preview = c.LastMessagePreview || "";
        const when = c.LastMessageAt ? CrmCommon.formatDate(c.LastMessageAt) : "";
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
          "</div>" +
          (when
            ? '<div class="crm-conv-meta">' + CrmCommon.escapeHtml(when) + pri + "</div>"
            : "") +
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
          const isEmail = (m.Channel || "").toLowerCase() === "email";
          const formatted = isEmail && m.BodyHtml;
          const cls =
            "wa-msg" +
            (isNote ? " wa-msg--note" : outbound ? " wa-msg--out" : "") +
            (formatted ? " wa-msg--email" : "");
          let mediaHtml = "";
          const mime = (m.AttachmentMimeType || "").toLowerCase();
          const hideInlineImage = formatted && /<img\b/i.test(m.BodyHtml || "") && mime.indexOf("image/") === 0;
          if (!hideInlineImage && (m.AttachmentPath || m.AttachmentName)) {
            const url = fileHref(m);
            const safeUrl = CrmCommon.escapeHtml(url);
            if (url && isBrowserImage(m)) {
              mediaHtml =
                '<a class="wa-file-link" data-message-id="' +
                parseInt(m.MessageID, 10) +
                '" href="' +
                safeUrl +
                '" target="_blank" rel="noopener"><img class="wa-attach" src="' +
                safeUrl +
                '" alt=""></a>';
            } else if (url && (mime.indexOf("audio/") === 0 || (m.MediaType || "") === "audio")) {
              mediaHtml = '<audio class="wa-attach" controls src="' + safeUrl + '"></audio>';
            } else if (url && (mime.indexOf("video/") === 0 || (m.MediaType || "") === "video")) {
              mediaHtml = '<video class="wa-attach" controls src="' + safeUrl + '"></video>';
            } else if (url) {
              mediaHtml =
                '<a class="small wa-file-link" data-message-id="' +
                parseInt(m.MessageID, 10) +
                '" href="' +
                safeUrl +
                '" target="_blank" rel="noopener"><i class="bi bi-file-earmark"></i> ' +
                CrmCommon.escapeHtml(m.AttachmentName || m.Body || "Attachment") +
                "</a>";
            }
          }
          const testBadge = m.IsTest
            ? '<span class="wa-test-flag">TEST MESSAGE</span> '
            : "";
          return (
            '<div class="' +
            cls +
            '" data-message-id="' +
            parseInt(m.MessageID, 10) +
            '" data-body="' +
            CrmCommon.escapeHtml(m.Body || "") +
            '" data-file="' +
            CrmCommon.escapeHtml(fileHref(m)) +
            '" data-file-name="' +
            CrmCommon.escapeHtml(m.AttachmentName || "attachment") +
            '"><div class="wa-bubble">' +
            testBadge +
            (formatted
              ? '<div class="wa-email-html">' + m.BodyHtml + "</div>"
              : '<div class="wa-email-text">' +
                CrmCommon.escapeHtml(m.Body || "").replace(/\n/g, "<br>") +
                "</div>") +
            mediaHtml +
            '<div class="wa-msg-time">' +
            CrmCommon.formatDate(m.CreatedDate || m.SentAt) +
            (outbound && !isNote ? statusTicks(m.DeliveryStatus, m.ErrorDetail) : "") +
            "</div>" +
            (outbound && !isNote && (m.DeliveryStatus || "").toLowerCase() === "failed" && m.ErrorDetail
              ? '<div class="wa-fail-reason">' + CrmCommon.escapeHtml(m.ErrorDetail) + "</div>"
              : "") +
            "</div></div>"
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
    detailName.textContent = conversationTitle(conv);
    detailContact.textContent = [mobile, email].filter(Boolean).join(" · ") || "—";

    const unknownBanner = document.getElementById("crmUnknownBanner");
    const linkExistingBtn = document.getElementById("crmLinkExistingBtn");
    const hasCustomerMatch = !conv.CustomerID && candidateList(conv).length > 0;
    if (linkExistingBtn) linkExistingBtn.classList.toggle("d-none", !hasCustomerMatch);
    if (unknownBanner) unknownBanner.hidden = !!conv.CustomerID || (!conv.IsUnknown && !hasCustomerMatch);

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

  function showConversation(conv, id) {
    const row = conv || {};
    subjectEl.textContent = conversationTitle(row) || "Conversation #" + id;
    channelEl.textContent = row.Channel || "WhatsApp";
    replyWrap.classList.remove("d-none");
    setContactActions(row);
  }

  async function selectConversation(id) {
    const numericId = parseInt(id, 10);
    if (!Number.isFinite(numericId) || numericId <= 0) {
      throw new Error("Yeh chat nahi khul rahi.");
    }
    activeConvId = numericId;
    let conv = convById[numericId] || convById[String(numericId)] || null;
    try {
      const data = await CrmCommon.apiFetch("/api/crm/conversations/" + numericId);
      conv = data.conversation || conv;
      renderTimeline(data.timeline || []);
    } catch (_err) {
      renderTimeline([]);
    }
    if (conv) showConversation(conv, numericId);
    const msgData = await CrmCommon.apiFetch("/api/crm/conversations/" + numericId + "/messages");
    renderMessages(msgData.rows || []);
    const host = window.top || window;
    if (host && typeof host.jtcsClearTaskAlertsForConversation === "function") {
      host.jtcsClearTaskAlertsForConversation(numericId);
    }
    if (!conv && !(msgData.rows || []).length) {
      throw new Error("Yeh chat nahi mili.");
    }
    if (!conv) showConversation({ Subject: "WhatsApp", Channel: "WhatsApp", IsUnknown: 1 }, numericId);
    loadConversations();
  }

  async function pollMessages() {
    if (!activeConvId) return;
    try {
      const msgData = await CrmCommon.apiFetch(
        "/api/crm/conversations/" + activeConvId + "/messages"
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
    } catch (_qrErr) {}
    try {
      if (api.templates) {
        const params = new URLSearchParams();
        if (activeChannel) params.set("channel", activeChannel);
        if (!activeChannel || activeChannel === "WhatsApp") params.set("source", "meta");
        const query = params.toString();
        const tp = await CrmCommon.apiFetch(api.templates + (query ? "?" + query : ""));
        templateRows = tp.rows || [];
        templateDefaults = tp.defaults || {};
        const sel = document.getElementById("crmTemplateSelect");
        const helpers = window.JtcsInboxTemplates;
        if (sel && helpers) {
          const rendered = helpers.renderTemplateOptions(templateRows, tp.meta_error || "");
          sel.innerHTML = rendered.html;
          showTemplateNotice(rendered.notice);
          hideTemplateVars();
        } else if (sel) {
          sel.innerHTML =
            '<option value="">Templates…</option>' +
            templateRows
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
    } catch (err) {
      const sel = document.getElementById("crmTemplateSelect");
      const message = (err && err.message) || "WhatsApp templates could not be loaded.";
      if (sel && window.JtcsInboxTemplates) {
        sel.innerHTML = window.JtcsInboxTemplates.renderTemplateOptions([], message).html;
      }
      showTemplateNotice(message);
      hideTemplateVars();
    }
  }

  function showTemplateNotice(message) {
    const notice = document.getElementById("crmTemplateNotice");
    if (!notice) return;
    if (!message) {
      notice.textContent = "";
      notice.classList.add("d-none");
      return;
    }
    notice.textContent = message;
    notice.classList.remove("d-none");
  }

  function hideTemplateVars() {
    const box = document.getElementById("crmTemplateVars");
    if (!box) return;
    box.classList.add("d-none");
    box.innerHTML = "";
  }

  function applySelectedTemplate(row) {
    const helpers = window.JtcsInboxTemplates;
    const body = document.getElementById("crmReplyBody");
    const box = document.getElementById("crmTemplateVars");
    if (!helpers || !body || !box || !row) return;
    activeTemplate = row;
    const fields = helpers.variableFields(row, templateDefaults, activeConvMeta);
    if (!fields.length) {
      hideTemplateVars();
      body.value = row.Body || "";
      return;
    }
    const values = {};
    fields.forEach(function (field) {
      values[field.key] = field.value;
    });
    body.value = helpers.fillTemplateBody(row.Body || "", values);
    const buttons = (row.Buttons || [])
      .map(function (button) {
        return button.text || button.type || "";
      })
      .filter(Boolean);
    box.classList.remove("d-none");
    box.innerHTML =
      fields
        .map(function (field) {
          return (
            '<label>' +
            CrmCommon.escapeHtml(field.label) +
            '<input type="text" data-template-var="' +
            CrmCommon.escapeHtml(field.key) +
            '" value="' +
            CrmCommon.escapeHtml(field.value) +
            '">' +
            "</label>"
          );
        })
        .join("") +
      (buttons.length
        ? '<div class="wa-template-buttons">Template buttons: ' +
          CrmCommon.escapeHtml(buttons.join(", ")) +
          "</div>"
        : "");
    box.querySelectorAll("[data-template-var]").forEach(function (input) {
      input.addEventListener("input", function () {
        const next = {};
        box.querySelectorAll("[data-template-var]").forEach(function (field) {
          next[field.getAttribute("data-template-var")] = field.value;
        });
        body.value = helpers.fillTemplateBody(row.Body || "", next);
      });
    });
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

  msgThread.addEventListener("click", async function (e) {
    const link = e.target.closest("a.wa-file-link");
    if (!link) return;
    e.preventDefault();
    const messageId = parseInt(link.getAttribute("data-message-id"), 10);
    const fileUrl = Number.isFinite(messageId) && messageId > 0
      ? "/api/crm/messages/" + messageId + "/file"
      : link.getAttribute("href");
    const popup = window.open("about:blank", "_blank");
    try {
      const resp = await fetch(fileUrl, { credentials: "same-origin" });
      const ct = resp.headers.get("content-type") || "";
      if (!resp.ok) {
        if (popup) popup.close();
        let message = "Yeh file nahi mili.";
        if (ct.indexOf("application/json") !== -1) {
          const data = await resp.json();
          message = (data && data.error) || message;
        }
        CrmCommon.showAlert(message, "danger");
        return;
      }
      const blob = await resp.blob();
      const objectUrl = URL.createObjectURL(blob);
      if (popup) {
        popup.location = objectUrl;
        return;
      }
      const download = document.createElement("a");
      download.href = objectUrl;
      download.download = (link.textContent || "file").trim() || "file";
      document.body.appendChild(download);
      download.click();
      download.remove();
    } catch (err) {
      if (popup) popup.close();
      CrmCommon.showAlert(err.message || "Yeh file nahi khul saki.", "danger");
    }
  });

  const pendingFiles = [];
  const attachPreview = document.getElementById("crmAttachPreview");

  function fileLabel(file) {
    const rel = (file.webkitRelativePath || "").replace(/\\/g, "/").replace(/^\/+/, "");
    return rel || file.name || "file";
  }

  function addPendingFiles(fileList) {
    Array.from(fileList || []).forEach(function (file) {
      if (!file || !file.name) return;
      const label = fileLabel(file);
      const dup = pendingFiles.some(function (item) {
        return item.label === label && item.file.size === file.size;
      });
      if (!dup) pendingFiles.push({ file: file, label: label });
    });
    renderPendingFiles();
  }

  function renderPendingFiles() {
    if (!attachPreview) return;
    if (!pendingFiles.length) {
      attachPreview.classList.add("d-none");
      attachPreview.innerHTML = "";
      return;
    }
    attachPreview.classList.remove("d-none");
    const groups = {};
    const loose = [];
    pendingFiles.forEach(function (item, index) {
      const parts = item.label.split("/");
      if (parts.length > 1) {
        const folder = parts[0];
        if (!groups[folder]) groups[folder] = [];
        groups[folder].push({ item: item, index: index });
      } else {
        loose.push({ item: item, index: index });
      }
    });
    let html = "";
    Object.keys(groups).forEach(function (folder) {
      html += '<div class="wa-attach-folder"><i class="bi bi-folder-fill"></i> ' + CrmCommon.escapeHtml(folder) + "</div>";
      groups[folder].forEach(function (row) {
        html += pendingChip(row.item.label.split("/").slice(1).join("/"), row.index);
      });
    });
    loose.forEach(function (row) {
      html += pendingChip(row.item.label, row.index);
    });
    attachPreview.innerHTML = html;
  }

  function pendingChip(label, index) {
    return (
      '<div class="wa-attach-chip"><i class="bi bi-file-earmark"></i><span>' +
      CrmCommon.escapeHtml(label) +
      '</span><button type="button" data-remove-file="' +
      index +
      '" aria-label="Remove">&times;</button></div>'
    );
  }

  async function uploadPendingFile(item, caption) {
    const fd = new FormData();
    fd.append("file", item.file, item.file.name);
    fd.append("display_name", item.label);
    fd.append("caption", caption || "");
    fd.append("channel", document.getElementById("crmReplyChannel").value);
    const token = (document.querySelector('meta[name="csrf-token"]') || {}).content || "";
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
    return data;
  }

  const replyForm = document.getElementById("crmInboxReplyForm");
  const replyBody = document.getElementById("crmReplyBody");
  if (replyForm) {
    replyForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      if (!activeConvId) return;
      const body = replyBody.value.trim();
      if (!body && !pendingFiles.length) return;
      const sendBtn = document.getElementById("crmReplySendBtn");
      if (sendBtn) sendBtn.disabled = true;
      try {
        if (body) {
          const note = document.getElementById("crmReplyNote").checked;
          const channel = document.getElementById("crmReplyChannel").value;
          const payload = {
            body: body,
            channel: channel,
            is_internal_note: note,
          };
          if (activeTemplate && channel === "WhatsApp" && !note) {
            const vars = {};
            document.querySelectorAll("#crmTemplateVars [data-template-var]").forEach(function (field) {
              vars[field.getAttribute("data-template-var")] = field.value;
            });
            payload.template_name = activeTemplate.ExternalTemplateName || activeTemplate.Name || "";
            payload.language = activeTemplate.LanguageCode || "en";
            payload.template_vars = vars;
          }
          const data = await CrmCommon.apiFetch(
            CrmCommon.urlTemplate(api.reply, activeConvId),
            {
              method: "POST",
              body: payload,
            }
          );
          if (data.warning) CrmCommon.showAlert(data.warning, "warning");
        }
        const queued = pendingFiles.slice();
        for (let i = 0; i < queued.length; i += 1) {
          const data = await uploadPendingFile(queued[i], "");
          if (data.warning) CrmCommon.showAlert(data.warning, "warning");
        }
        pendingFiles.length = 0;
        renderPendingFiles();
        replyBody.value = "";
        activeTemplate = null;
        hideTemplateVars();
        const fileInput = document.getElementById("crmReplyFile");
        const folderInput = document.getElementById("crmReplyFolder");
        if (fileInput) fileInput.value = "";
        if (folderInput) folderInput.value = "";
        selectConversation(activeConvId);
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      } finally {
        if (sendBtn) sendBtn.disabled = false;
      }
    });
  }

  if (replyBody) {
    replyBody.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        if (replyForm) replyForm.requestSubmit();
      }
    });
    replyBody.addEventListener("paste", function (e) {
      const files = e.clipboardData && e.clipboardData.files;
      if (!files || !files.length) return;
      e.preventDefault();
      addPendingFiles(files);
    });
  }

  const fileInput = document.getElementById("crmReplyFile");
  if (fileInput) {
    fileInput.addEventListener("change", function () {
      addPendingFiles(fileInput.files);
      fileInput.value = "";
    });
  }
  const folderInput = document.getElementById("crmReplyFolder");
  if (folderInput) {
    folderInput.addEventListener("change", function () {
      addPendingFiles(folderInput.files);
      folderInput.value = "";
    });
  }
  if (attachPreview) {
    attachPreview.addEventListener("click", function (e) {
      const btn = e.target.closest("[data-remove-file]");
      if (!btn) return;
      const index = parseInt(btn.getAttribute("data-remove-file"), 10);
      if (!Number.isNaN(index)) pendingFiles.splice(index, 1);
      renderPendingFiles();
    });
  }
  const pasteBtn = document.getElementById("crmReplyPaste");
  if (pasteBtn) {
    pasteBtn.addEventListener("click", async function () {
      if (replyBody) replyBody.focus();
      if (!navigator.clipboard || !navigator.clipboard.read) {
        CrmCommon.showAlert("Copied file par Ctrl+V dabayein.", "warning");
        return;
      }
      try {
        const items = await navigator.clipboard.read();
        const collected = [];
        for (let i = 0; i < items.length; i += 1) {
          const item = items[i];
          const types = item.types || [];
          for (let t = 0; t < types.length; t += 1) {
            if (types[t].indexOf("text/") === 0) continue;
            const blob = await item.getType(types[t]);
            const ext = (types[t].split("/")[1] || "bin").split(";")[0];
            collected.push(new File([blob], "pasted-" + Date.now() + "." + ext, { type: types[t] }));
          }
        }
        if (!collected.length) {
          CrmCommon.showAlert("Copied file par Ctrl+V dabayein.", "warning");
          return;
        }
        addPendingFiles(collected);
      } catch (_err) {
        CrmCommon.showAlert("Copied file par Ctrl+V dabayein.", "warning");
      }
    });
  }

  ["crmQuickReplySelect", "crmTemplateSelect"].forEach(function (id) {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", function () {
      if (id === "crmTemplateSelect") {
        const opt = el.options[el.selectedIndex];
        const index = opt ? parseInt(opt.getAttribute("data-index"), 10) : NaN;
        const row = templateRows[index];
        if (row && Array.isArray(row.Variables) && row.Variables.length) {
          applySelectedTemplate(row);
          return;
        }
        activeTemplate = row || null;
        hideTemplateVars();
      } else {
        activeTemplate = null;
      }
      if (!el.value) return;
      document.getElementById("crmReplyBody").value = el.value;
      el.selectedIndex = 0;
    });
  });

  document.getElementById("crmDetailCloseBtn").addEventListener("click", async function () {
    if (!activeConvId || !(await JTCSDialog.confirm("Close this conversation?"))) return;
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
      const conv = activeConvMeta || convById[activeConvId] || {};
      if (action === "review_match") {
        try {
          await startMergeAndLink(activeConvId);
        } catch (err) {
          showMergeError(err);
        }
        return;
      }
      if (action === "create_customer" && candidateList(conv).length) {
        openLinkDialog(conv, "exists");
        return;
      }
      let name = "";
      if (action !== "ignore") {
        name =
          (await JTCSDialog.prompt(
            "Name for this contact",
            activeConvMeta && (activeConvMeta.Subject || "")
          )) || "";
      }
      try {
        await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.link, activeConvId), {
          method: "POST",
          body: { action: action, full_name: name },
        });
        selectConversation(activeConvId);
        loadConversations();
      } catch (err) {
        if (err.data && err.data.already_exists) {
          conv.link_candidates = err.data.candidates || candidateList(conv);
          openLinkDialog(conv, "exists");
          return;
        }
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
      }
    });

  document.getElementById("crmWaLinkModal") &&
    document.getElementById("crmWaLinkModal").addEventListener("click", async function (e) {
      const btn = e.target.closest("[data-wa-link]");
      if (!btn) return;
      const kind = btn.getAttribute("data-wa-link");
      const convId = linkDialogConvId;
      if (kind === "later") {
        promptedThisPage[convId] = true;
        try {
          await CrmCommon.apiFetch(CrmCommon.urlTemplate(api.link, convId), {
            method: "POST",
            body: { action: "dismiss_link" },
          });
        } catch (err) {
          CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
        }
        const modal = linkModal();
        if (modal) modal.hide();
        linkDialogConvId = null;
        loadConversations();
        return;
      }
      if (kind === "open") {
        const customerId = selectedLinkCustomerId();
        if (!customerId) {
          CrmCommon.showAlert("Select the Customer Master record to open.", "warning");
          return;
        }
        openCustomerRecord(customerId);
        return;
      }
      if (kind === "merge") {
        const convId = linkDialogConvId;
        const modal = linkModal();
        if (modal) modal.hide();
        linkDialogConvId = null;
        try {
          await startMergeAndLink(convId);
        } catch (err) {
          showMergeError(err);
        }
        return;
      }
      if (kind === "review-merge") {
        const helpers = mergeHelpers();
        const mainPicked = document.querySelector("#crmWaLinkChoices input[name='crmWaMain']:checked");
        const mergePicked = Array.from(
          document.querySelectorAll("#crmWaLinkChoices input[name='crmWaMerge']:checked")
        ).map(function (box) {
          return parseInt(box.value, 10);
        });
        const mainId = mainPicked ? parseInt(mainPicked.value, 10) : null;
        const plan = helpers
          ? helpers.payloadForSelection(linkDialogMatches, mainId, mergePicked)
          : { ok: false, error: "Select one main customer." };
        if (!plan.ok) {
          CrmCommon.showAlert(plan.error, "warning");
          return;
        }
        linkDialogMainId = plan.body.customer_id;
        linkDialogMergeIds = plan.body.merge_customer_ids;
        linkDialogPhase = "review";
        renderMergeDialog();
        return;
      }
      if (kind === "back-merge") {
        linkDialogPhase = "choose";
        renderMergeDialog();
        return;
      }
      if (kind === "confirm-merge") {
        const helpers = mergeHelpers();
        const plan = helpers
          ? helpers.payloadForSelection(linkDialogMatches, linkDialogMainId, linkDialogMergeIds)
          : { ok: false, error: "Select one main customer." };
        if (!plan.ok) {
          CrmCommon.showAlert(plan.error, "warning");
          return;
        }
        try {
          await submitMergeLink(linkDialogConvId, plan.body.customer_id, plan.body.merge_customer_ids);
        } catch (err) {
          showMergeError(err);
        }
        return;
      }
      if (kind === "link") {
        try {
          await confirmCustomerLink();
        } catch (err) {
          CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
        }
      }
    });
  document.getElementById("crmWaLinkModal") &&
    document.getElementById("crmWaLinkModal").addEventListener("hidden.bs.modal", function () {
      if (linkDialogConvId) promptedThisPage[linkDialogConvId] = true;
      linkDialogConvId = null;
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

  const newMsgBtn = document.getElementById("crmNewMessageBtn");
  const newMsgModalEl = document.getElementById("crmNewMessageModal");
  const newMsgModal = newMsgModalEl ? bootstrap.Modal.getOrCreateInstance(newMsgModalEl) : null;
  const newSearch = document.getElementById("crmNewSearch");
  const newResults = document.getElementById("crmNewSearchResults");
  let newSearchTimer = null;

  function fillNewRecipient(name, mobile, customerId) {
    const nameEl = document.getElementById("crmNewName");
    const mobileEl = document.getElementById("crmNewMobile");
    const idEl = document.getElementById("crmNewCustomerId");
    if (nameEl) nameEl.value = name || "";
    if (mobileEl) mobileEl.value = mobile || "";
    if (idEl) idEl.value = customerId || "";
  }

  async function startChat(body) {
    const data = await CrmCommon.apiFetch(api.start, { method: "POST", body: body });
    if (newMsgModal) newMsgModal.hide();
    if (data.conversation_id) await selectConversation(data.conversation_id);
  }

  if (newMsgBtn && newMsgModal) {
    newMsgBtn.addEventListener("click", function () {
      fillNewRecipient("", "", "");
      if (newSearch) newSearch.value = "";
      if (newResults) newResults.innerHTML = "";
      newMsgModal.show();
      if (newSearch) setTimeout(function () { newSearch.focus(); }, 200);
    });
  }

  if (newSearch && newResults && api.search) {
    newSearch.addEventListener("input", function () {
      const q = newSearch.value.trim();
      if (newSearchTimer) clearTimeout(newSearchTimer);
      if (q.length < 2) {
        newResults.innerHTML = "";
        return;
      }
      newSearchTimer = setTimeout(async function () {
        try {
          const data = await CrmCommon.apiFetch(api.search + "?q=" + encodeURIComponent(q));
          const rows = data.customers || [];
          if (!rows.length) {
            newResults.innerHTML = '<div class="text-muted px-1 py-1">Koi saved customer nahi mila. Neeche number likh kar Open chat dabao.</div>';
            return;
          }
          newResults.innerHTML = rows.slice(0, 8).map(function (c) {
            const mobile = c.mobile_number || "";
            return (
              '<button type="button" class="list-group-item list-group-item-action py-1" data-customer-id="' +
              CrmCommon.escapeHtml(String(c.customer_id || "")) +
              '" data-name="' +
              CrmCommon.escapeHtml(c.customer_name || c.title || "") +
              '" data-mobile="' +
              CrmCommon.escapeHtml(mobile) +
              '"><strong>' +
              CrmCommon.escapeHtml(c.customer_name || c.title || "Customer") +
              "</strong><div class=\"text-muted\">" +
              CrmCommon.escapeHtml(mobile || "Mobile missing") +
              "</div></button>"
            );
          }).join("");
        } catch (_err) {
          newResults.innerHTML = "";
        }
      }, 250);
    });
    newResults.addEventListener("click", function (e) {
      const btn = e.target.closest("[data-customer-id]");
      if (!btn) return;
      fillNewRecipient(btn.getAttribute("data-name") || "", btn.getAttribute("data-mobile") || "", btn.getAttribute("data-customer-id") || "");
      const form = document.getElementById("crmNewMessageForm");
      if (form) form.requestSubmit();
    });
  }

  const newForm = document.getElementById("crmNewMessageForm");
  if (newForm) {
    newForm.addEventListener("submit", async function (e) {
      e.preventDefault();
      const customerId = (document.getElementById("crmNewCustomerId").value || "").trim();
      const mobile = (document.getElementById("crmNewMobile").value || "").trim();
      const name = (document.getElementById("crmNewName").value || "").trim();
      try {
        await startChat({
          customer_id: customerId ? parseInt(customerId, 10) : null,
          mobile: mobile,
          name: name,
        });
      } catch (err) {
        CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
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

  const ctxMenu = document.createElement("div");
  ctxMenu.className = "wa-ctx";
  ctxMenu.hidden = true;
  ctxMenu.innerHTML =
    '<button type="button" data-act="cut">Cut</button>' +
    '<button type="button" data-act="copy">Copy</button>' +
    '<button type="button" data-act="paste">Paste</button>' +
    '<button type="button" data-act="delete">Delete</button>' +
    '<hr>' +
    '<button type="button" data-act="save">Save</button>' +
    '<button type="button" data-act="select">Select all</button>';
  document.body.appendChild(ctxMenu);

  let ctxMessage = null;
  const replyBox = document.getElementById("crmReplyBody");

  function hideCtx() {
    ctxMenu.hidden = true;
    ctxMessage = null;
  }

  function selectedText() {
    const sel = window.getSelection();
    return sel ? String(sel.toString() || "") : "";
  }

  function messageText(node) {
    if (!node) return "";
    return node.getAttribute("data-body") || "";
  }

  function isWhatsAppContext() {
    const channel = (
      (activeConvMeta && activeConvMeta.Channel) ||
      activeChannel ||
      ""
    ).toLowerCase();
    return !channel || channel === "whatsapp";
  }

  function setCtxEnabled(act, on) {
    const btn = ctxMenu.querySelector('[data-act="' + act + '"]');
    if (btn) btn.disabled = !on;
  }

  document.addEventListener("contextmenu", function (event) {
    const threadHit = event.target.closest("#crmMsgThread, #crmInboxReplyWrap");
    if (!threadHit || !isWhatsAppContext()) return;
    event.preventDefault();
    ctxMessage = event.target.closest(".wa-msg");
    const inReply = !!event.target.closest("#crmReplyBody");
    const hasText = !!(selectedText() || (ctxMessage && messageText(ctxMessage)));
    const hasFile = !!(ctxMessage && ctxMessage.getAttribute("data-file"));
    setCtxEnabled("cut", hasText || inReply);
    setCtxEnabled("copy", hasText || hasFile || inReply);
    setCtxEnabled("paste", !!replyBox);
    setCtxEnabled("delete", !!ctxMessage);
    setCtxEnabled("save", hasFile);
    setCtxEnabled("select", !!(ctxMessage || replyBox));
    ctxMenu.hidden = false;
    const left = Math.min(event.clientX, window.innerWidth - 220);
    const top = Math.min(event.clientY, window.innerHeight - 240);
    ctxMenu.style.left = left + "px";
    ctxMenu.style.top = top + "px";
  });

  document.addEventListener("click", hideCtx);
  window.addEventListener("blur", hideCtx);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") hideCtx();
  });

  ctxMenu.addEventListener("click", async function (event) {
    const btn = event.target.closest("[data-act]");
    if (!btn || btn.disabled) return;
    event.stopPropagation();
    const act = btn.getAttribute("data-act");
    const text = selectedText() || messageText(ctxMessage);
    const file = ctxMessage ? ctxMessage.getAttribute("data-file") || "" : "";
    const fileName = ctxMessage ? ctxMessage.getAttribute("data-file-name") || "attachment" : "attachment";
    if (act === "copy" || act === "cut") {
      try {
        await navigator.clipboard.writeText(text || file);
      } catch (_err) {}
      if (act === "cut" && replyBox && document.activeElement === replyBox) {
        const start = replyBox.selectionStart || 0;
        const end = replyBox.selectionEnd || 0;
        replyBox.value = replyBox.value.slice(0, start) + replyBox.value.slice(end);
      } else if (act === "cut" && ctxMessage) {
        const id = parseInt(ctxMessage.getAttribute("data-message-id"), 10);
        if (id) {
          try {
            await CrmCommon.apiFetch("/api/crm/messages/" + id + "/delete", { method: "POST", body: {} });
            if (activeConvId) await selectConversation(activeConvId);
          } catch (err) {
            CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
          }
        }
      }
    } else if (act === "paste" && replyBox) {
      try {
        const clip = await navigator.clipboard.readText();
        const start = replyBox.selectionStart || replyBox.value.length;
        const end = replyBox.selectionEnd || start;
        replyBox.value = replyBox.value.slice(0, start) + clip + replyBox.value.slice(end);
        replyBox.focus();
      } catch (_err) {}
    } else if (act === "save" && file) {
      const link = document.createElement("a");
      link.href = file;
      link.download = fileName;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } else if (act === "select") {
      if (document.activeElement === replyBox && replyBox) replyBox.select();
      else if (ctxMessage) {
        const range = document.createRange();
        range.selectNodeContents(ctxMessage);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      }
    } else if (act === "delete" && ctxMessage) {
      const id = parseInt(ctxMessage.getAttribute("data-message-id"), 10);
      if (id) {
        try {
          await CrmCommon.apiFetch("/api/crm/messages/" + id + "/delete", { method: "POST", body: {} });
          if (activeConvId) await selectConversation(activeConvId);
        } catch (err) {
          CrmCommon.showAlert((err.data && err.data.error) || err.message, "danger");
        }
      }
    }
    hideCtx();
  });
})();
