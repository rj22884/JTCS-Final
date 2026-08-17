/**
 * JTCS illustration icon layer.
 * Maps existing Bootstrap Icon classes to a shared 3D-ish flat SVG set.
 * Leaves MenuMaster / routes / business logic unchanged.
 */
(function () {
  "use strict";

  var SKIP = {
    "bi-chevron-down": 1,
    "bi-chevron-up": 1,
    "bi-chevron-left": 1,
    "bi-chevron-right": 1,
    "bi-caret-down": 1,
    "bi-caret-up": 1,
    "bi-caret-down-fill": 1,
    "bi-x": 1,
    "bi-x-lg": 1,
    "bi-x-circle": 1,
    "bi-grip-vertical": 1,
    "bi-three-dots": 1,
    "bi-three-dots-vertical": 1,
    "bi-dot": 1,
    "bi-list": 1,
    "bi-arrow-down-up": 1,
    "bi-arrow-up": 1,
    "bi-arrow-down": 1,
    "bi-sort-down": 1,
    "bi-sort-up": 1,
    "bi-filter": 1,
  };

  var SKIP_ROOTS = "#biPickerModal, .mcust-icon-grid, .mcust-icon-pick, .jtcs-illu-skip, thead, .dash-sort-icon, .dash-th-label";

  function wrap(inner) {
    return (
      '<svg class="jtcs-illu-svg" viewBox="0 0 32 32" aria-hidden="true" focusable="false">' +
      '<ellipse class="jtcs-illu-shadow" cx="16" cy="28.6" rx="9.5" ry="2.1"/>' +
      inner +
      "</svg>"
    );
  }

  var G = {
    document: wrap(
      '<path d="M9 5.5h11.2l4.3 4.3V25a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V7.5a2 2 0 0 1 2-2z" fill="#fff" stroke="#2e5aac" stroke-width="1.3"/>' +
        '<path d="M20.2 5.5V10h4.3" fill="#d6e4f7" stroke="#2e5aac" stroke-width="1.3" stroke-linejoin="round"/>' +
        '<rect x="11" y="14" width="10" height="1.4" rx=".6" fill="#8fb0de"/>' +
        '<rect x="11" y="17.6" width="7.5" height="1.4" rx=".6" fill="#c5d6ef"/>'
    ),
    invoice: wrap(
      '<path d="M8.5 5.2h12l4.2 4.2V25.2a2 2 0 0 1-2 2h-14.2a2 2 0 0 1-2-2V7.2a2 2 0 0 1 2-2z" fill="#fff" stroke="#0b2545" stroke-width="1.25"/>' +
        '<rect x="8.5" y="5.2" width="16.2" height="5.2" rx="1.2" fill="#2e5aac"/>' +
        '<text x="16.6" y="9.1" text-anchor="middle" font-size="4.4" font-weight="700" fill="#fff">₹</text>' +
        '<rect x="11.2" y="13.6" width="10" height="1.3" rx=".5" fill="#e85d00"/>' +
        '<rect x="11.2" y="17" width="8" height="1.2" rx=".5" fill="#d7e0ea"/>' +
        '<rect x="11.2" y="20.3" width="6.2" height="1.2" rx=".5" fill="#d7e0ea"/>'
    ),
    ledger: wrap(
      '<path d="M8 6.2h13.5a2 2 0 0 1 2 2v16.2H10a2 2 0 0 1-2-2V6.2z" fill="#f4f7fb" stroke="#2e5aac" stroke-width="1.25"/>' +
        '<path d="M8 6.2v16.2A2.4 2.4 0 0 0 10.5 25H24" fill="none" stroke="#2e5aac" stroke-width="1.25"/>' +
        '<rect x="11.2" y="10" width="8.5" height="1.3" rx=".5" fill="#e8a317"/>' +
        '<rect x="11.2" y="13.6" width="8.5" height="1.2" rx=".5" fill="#b9c9e3"/>' +
        '<rect x="11.2" y="17.1" width="6.5" height="1.2" rx=".5" fill="#b9c9e3"/>'
    ),
    chart: wrap(
      '<rect x="6.5" y="6.5" width="19" height="18.5" rx="3" fill="#fff" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<rect x="10" y="16.2" width="3" height="5.8" rx=".8" fill="#2e5aac"/>' +
        '<rect x="14.6" y="12.4" width="3" height="9.6" rx=".8" fill="#2e9b6a"/>' +
        '<rect x="19.2" y="9.6" width="3" height="12.4" rx=".8" fill="#e85d00"/>'
    ),
    reports: wrap(
      '<rect x="7" y="6" width="13.5" height="18" rx="2" fill="#fff" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<path d="M16 8.2l7.2 3.1v10.4c0 2.4-3.2 3.8-7.2 3.8" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.15"/>' +
        '<polyline points="11,16 13.4,13.4 15.6,15 18.8,11.4" fill="none" stroke="#e85d00" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    customer: wrap(
      '<circle cx="16" cy="11.2" r="4.4" fill="#d6e4f7" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<path d="M8.4 24.2c.7-4.4 3.6-6.6 7.6-6.6s6.9 2.2 7.6 6.6" fill="#fff" stroke="#2e5aac" stroke-width="1.2" stroke-linecap="round"/>' +
        '<rect x="20.2" y="16.4" width="6.4" height="7.4" rx="1.2" fill="#fff4eb" stroke="#e85d00" stroke-width="1.05"/>' +
        '<rect x="21.4" y="18.2" width="4" height=".9" rx=".4" fill="#e85d00"/>'
    ),
    users: wrap(
      '<circle cx="12.2" cy="11" r="3.6" fill="#d6e4f7" stroke="#2e5aac" stroke-width="1.15"/>' +
        '<circle cx="20.4" cy="11.6" r="3.1" fill="#f3eefe" stroke="#6f42c1" stroke-width="1.1"/>' +
        '<path d="M6.8 23.8c.6-3.6 2.9-5.4 5.6-5.4 2.6 0 4.8 1.7 5.5 5.4" fill="#fff" stroke="#2e5aac" stroke-width="1.1"/>' +
        '<path d="M16.6 23.8c.4-2.6 2-4.2 4-4.2 2.1 0 3.7 1.5 4.2 4.2" fill="#fff" stroke="#6f42c1" stroke-width="1.05"/>'
    ),
    bank: wrap(
      '<path d="M6.8 12.2 16 6.6l9.2 5.6" fill="#e8f1fc" stroke="#0b2545" stroke-width="1.2" stroke-linejoin="round"/>' +
        '<rect x="8.2" y="12.2" width="15.6" height="10.6" fill="#fff" stroke="#2e5aac" stroke-width="1.15"/>' +
        '<rect x="10.4" y="14.4" width="2.4" height="5.4" rx=".4" fill="#2e5aac"/>' +
        '<rect x="14.8" y="14.4" width="2.4" height="5.4" rx=".4" fill="#8fb0de"/>' +
        '<rect x="19.2" y="14.4" width="2.4" height="5.4" rx=".4" fill="#2e5aac"/>' +
        '<rect x="7.4" y="22.6" width="17.2" height="2.2" rx=".6" fill="#e8a317"/>'
    ),
    cash: wrap(
      '<rect x="6.5" y="9.2" width="19" height="13.2" rx="2.4" fill="#e7f6ee" stroke="#2e9b6a" stroke-width="1.2"/>' +
        '<circle cx="16" cy="15.8" r="3.6" fill="#fff" stroke="#2e9b6a" stroke-width="1.15"/>' +
        '<text x="16" y="17.4" text-anchor="middle" font-size="5.2" font-weight="700" fill="#2e9b6a">₹</text>'
    ),
    payment: wrap(
      '<rect x="6.4" y="10.2" width="19.2" height="12.2" rx="2.2" fill="#2e5aac"/>' +
        '<rect x="6.4" y="13.4" width="19.2" height="2.4" fill="#0b2545"/>' +
        '<rect x="9" y="18.2" width="6.4" height="1.6" rx=".5" fill="#e8a317"/>' +
        '<circle cx="22.2" cy="18.8" r="1.5" fill="#fff" opacity=".85"/>'
    ),
    item: wrap(
      '<path d="M8.2 12.4 16 8.2l7.8 4.2v9.2L16 25.6l-7.8-3.8z" fill="#fff4eb" stroke="#e85d00" stroke-width="1.2" stroke-linejoin="round"/>' +
        '<path d="M8.2 12.4 16 16.4l7.8-4" fill="none" stroke="#e85d00" stroke-width="1.15"/>' +
        '<path d="M16 16.4V25.6" fill="none" stroke="#e85d00" stroke-width="1.15"/>'
    ),
    stamp: wrap(
      '<rect x="8.2" y="7.2" width="15.6" height="17.6" rx="2" fill="#fff" stroke="#6f42c1" stroke-width="1.2"/>' +
        '<circle cx="16" cy="15.4" r="4.6" fill="none" stroke="#e85d00" stroke-width="1.5"/>' +
        '<text x="16" y="17.2" text-anchor="middle" font-size="4.2" font-weight="700" fill="#e85d00">S</text>'
    ),
    tax: wrap(
      '<rect x="7.4" y="6.6" width="17.2" height="18.8" rx="2" fill="#fff" stroke="#0b2545" stroke-width="1.2"/>' +
        '<rect x="7.4" y="6.6" width="17.2" height="5" fill="#2e5aac"/>' +
        '<text x="16" y="10.4" text-anchor="middle" font-size="3.8" font-weight="700" fill="#fff">TAX</text>' +
        '<rect x="10.4" y="14.4" width="11.2" height="1.3" rx=".5" fill="#e8a317"/>' +
        '<rect x="10.4" y="18" width="8" height="1.2" rx=".5" fill="#c5d6ef"/>'
    ),
    gst: wrap(
      '<rect x="7.2" y="6.8" width="17.6" height="18.6" rx="2" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<text x="16" y="18.4" text-anchor="middle" font-size="7" font-weight="700" fill="#2e5aac">GST</text>'
    ),
    warning: wrap(
      '<path d="M16 6.4 26.2 23.6H5.8z" fill="#fff8e1" stroke="#e8a317" stroke-width="1.25" stroke-linejoin="round"/>' +
        '<rect x="15.1" y="12.2" width="1.8" height="6.2" rx=".7" fill="#e85d00"/>' +
        '<circle cx="16" cy="20.6" r="1.05" fill="#e85d00"/>'
    ),
    court: wrap(
      '<rect x="7" y="20.8" width="18" height="3.2" rx=".8" fill="#0b2545"/>' +
        '<rect x="9.4" y="11.2" width="2" height="9.8" fill="#8fb0de"/>' +
        '<rect x="15" y="11.2" width="2" height="9.8" fill="#2e5aac"/>' +
        '<rect x="20.6" y="11.2" width="2" height="9.8" fill="#8fb0de"/>' +
        '<path d="M6.6 11.2h18.8L16 6.6z" fill="#e8f1fc" stroke="#0b2545" stroke-width="1.15" stroke-linejoin="round"/>'
    ),
    add: wrap(
      '<rect x="7.2" y="7.2" width="17.6" height="17.6" rx="4.2" fill="#e7f6ee" stroke="#2e9b6a" stroke-width="1.2"/>' +
        '<rect x="15.1" y="11" width="1.8" height="10" rx=".8" fill="#2e9b6a"/>' +
        '<rect x="11" y="15.1" width="10" height="1.8" rx=".8" fill="#2e9b6a"/>'
    ),
    edit: wrap(
      '<path d="M8.2 21.6 20.4 9.4l3.4 3.4L11.6 25H8.2z" fill="#fff4eb" stroke="#e85d00" stroke-width="1.2" stroke-linejoin="round"/>' +
        '<path d="M19.2 8.2l3.6 3.6 1.5-1.5a1.6 1.6 0 0 0 0-2.2L22.9 6.7a1.6 1.6 0 0 0-2.2 0z" fill="#e85d00"/>'
    ),
    delete: wrap(
      '<rect x="10" y="12.2" width="12" height="12.4" rx="2" fill="#fff1f2" stroke="#e11d48" stroke-width="1.2"/>' +
        '<rect x="8.4" y="9.4" width="15.2" height="2.4" rx="1" fill="#e11d48"/>' +
        '<rect x="13.4" y="7.2" width="5.2" height="2.4" rx=".8" fill="#0b2545"/>'
    ),
    save: wrap(
      '<rect x="7.4" y="7.2" width="17.2" height="17.8" rx="2.2" fill="#2e5aac"/>' +
        '<rect x="11.2" y="7.2" width="9.6" height="6.2" rx="1" fill="#d6e4f7"/>' +
        '<rect x="10.4" y="16.6" width="11.2" height="6.2" rx="1" fill="#fff"/>'
    ),
    refresh: wrap(
      '<circle cx="16" cy="16" r="8.2" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<path d="M16 9.2a6.8 6.8 0 1 1-5.4 2.6" fill="none" stroke="#2e5aac" stroke-width="1.6" stroke-linecap="round"/>' +
        '<path d="M9.4 8.6v4.2h4.2" fill="none" stroke="#e85d00" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    search: wrap(
      '<circle cx="14.2" cy="14" r="6.2" fill="#fff" stroke="#2e5aac" stroke-width="1.35"/>' +
        '<path d="M18.8 18.6 24.4 24.2" stroke="#e85d00" stroke-width="2.1" stroke-linecap="round"/>'
    ),
    preview: wrap(
      '<ellipse cx="16" cy="16.2" rx="10.4" ry="6.6" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<circle cx="16" cy="16.2" r="3.3" fill="#fff" stroke="#2e5aac" stroke-width="1.15"/>' +
        '<circle cx="16" cy="16.2" r="1.3" fill="#0b2545"/>'
    ),
    pdf: wrap(
      '<path d="M9 5.8h10.6L24 10.2V24.6a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V7.8a2 2 0 0 1 2-2z" fill="#fff1f2" stroke="#e11d48" stroke-width="1.2"/>' +
        '<text x="15.4" y="18.6" text-anchor="middle" font-size="6.2" font-weight="700" fill="#e11d48">PDF</text>'
    ),
    settings: wrap(
      '<circle cx="16" cy="16" r="4.1" fill="#fff" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<path d="M16 6.4l1.3 2.6 2.8-.4 1.4 2.6 2.6 1.1-.4 2.8 2.6 1.3-1.3 2.6.4 2.8-2.6 1.1-1.4 2.6-2.8-.4L16 25.6l-1.3-2.6-2.8.4-1.4-2.6-2.6-1.1.4-2.8L6.7 16l1.3-2.6-.4-2.8 2.6-1.1 1.4-2.6 2.8.4z" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.05" stroke-linejoin="round"/>'
    ),
    tools: wrap(
      '<rect x="13.4" y="8.2" width="5.2" height="16" rx="1.4" transform="rotate(40 16 16)" fill="#8fb0de" stroke="#0b2545" stroke-width="1.1"/>' +
        '<rect x="8.6" y="14.8" width="14.8" height="4.4" rx="1.4" fill="#e8a317" stroke="#0b2545" stroke-width="1.1"/>'
    ),
    dashboard: wrap(
      '<rect x="7" y="7" width="8.2" height="8.2" rx="1.8" fill="#2e5aac"/>' +
        '<rect x="16.8" y="7" width="8.2" height="5.4" rx="1.6" fill="#2e9b6a"/>' +
        '<rect x="7" y="17.2" width="8.2" height="7.6" rx="1.8" fill="#e8a317"/>' +
        '<rect x="16.8" y="14.2" width="8.2" height="10.6" rx="1.8" fill="#6f42c1"/>'
    ),
    crm: wrap(
      '<circle cx="11.6" cy="12.2" r="3.4" fill="#d6e4f7" stroke="#2e5aac" stroke-width="1.1"/>' +
        '<circle cx="20.6" cy="12.2" r="3.4" fill="#fff4eb" stroke="#e85d00" stroke-width="1.1"/>' +
        '<path d="M7.4 23.4c.6-3.3 2.6-5 4.6-5s4 1.7 4.6 5" fill="#fff" stroke="#2e5aac" stroke-width="1.05"/>' +
        '<path d="M16.2 23.4c.6-3.3 2.6-5 4.6-5s4 1.7 4.6 5" fill="#fff" stroke="#e85d00" stroke-width="1.05"/>'
    ),
    calendar: wrap(
      '<rect x="7.2" y="8.4" width="17.6" height="16.2" rx="2.2" fill="#fff" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<rect x="7.2" y="8.4" width="17.6" height="4.4" fill="#2e5aac"/>' +
        '<rect x="11.2" y="6.6" width="1.8" height="3.6" rx=".6" fill="#0b2545"/>' +
        '<rect x="19" y="6.6" width="1.8" height="3.6" rx=".6" fill="#0b2545"/>' +
        '<rect x="11" y="16.2" width="3" height="3" rx=".6" fill="#e85d00"/>' +
        '<rect x="15.6" y="16.2" width="3" height="3" rx=".6" fill="#d7e0ea"/>'
    ),
    bell: wrap(
      '<path d="M16 6.8a6.6 6.6 0 0 1 6.6 6.6v5.2l1.6 2.2H7.8l1.6-2.2v-5.2A6.6 6.6 0 0 1 16 6.8z" fill="#fff8e1" stroke="#e8a317" stroke-width="1.2"/>' +
        '<path d="M13.2 22.8a2.8 2.8 0 0 0 5.6 0" fill="none" stroke="#e85d00" stroke-width="1.3" stroke-linecap="round"/>'
    ),
    clock: wrap(
      '<circle cx="16" cy="16" r="8.4" fill="#fff" stroke="#2e5aac" stroke-width="1.25"/>' +
        '<path d="M16 10.2v6.2l4 2.2" fill="none" stroke="#e85d00" stroke-width="1.5" stroke-linecap="round"/>'
    ),
    logout: wrap(
      '<rect x="7.2" y="7.4" width="11.4" height="17.2" rx="2" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<path d="M15.4 16h9.2" stroke="#e11d48" stroke-width="1.7" stroke-linecap="round"/>' +
        '<path d="M21.2 12.6 25.2 16l-4 3.4" fill="none" stroke="#e11d48" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    back: wrap(
      '<circle cx="16" cy="16" r="8.4" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<path d="M18.6 10.8 12.4 16l6.2 5.2" fill="none" stroke="#2e5aac" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    transfer: wrap(
      '<path d="M7.4 12.4h13.2l-3.2-3.2" fill="none" stroke="#e85d00" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>' +
        '<path d="M24.6 19.6H11.4l3.2 3.2" fill="none" stroke="#2e5aac" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    income: wrap(
      '<circle cx="16" cy="16" r="8.5" fill="#e7f6ee" stroke="#2e9b6a" stroke-width="1.2"/>' +
        '<path d="M16 21.4V10.8" stroke="#2e9b6a" stroke-width="1.8" stroke-linecap="round"/>' +
        '<path d="M11.8 14.6 16 10.4l4.2 4.2" fill="none" stroke="#2e9b6a" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    expense: wrap(
      '<circle cx="16" cy="16" r="8.5" fill="#fff1f2" stroke="#e11d48" stroke-width="1.2"/>' +
        '<path d="M16 10.6v10.6" stroke="#e11d48" stroke-width="1.8" stroke-linecap="round"/>' +
        '<path d="M11.8 17.4 16 21.6l4.2-4.2" fill="none" stroke="#e11d48" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    whatsapp: wrap(
      '<circle cx="16" cy="16" r="8.6" fill="#25D366"/>' +
        '<path d="M12.2 20.8 11 23.4l2.7-1.1a7 7 0 1 0-1.5-1.5z" fill="#fff"/>' +
        '<path d="M13.2 15.2c.2-.4.3-.4.6-.4h.5c.2 0 .4.1.5.4l.4 1c.1.2 0 .4-.1.5l-.4.4c.6 1.1 1.6 2 2.8 2.6l.4-.4c.2-.2.4-.2.6-.1l1 .4c.3.1.4.3.4.5v.5c0 .3 0 .4-.4.6a4.4 4.4 0 0 1-5.8-5.6z" fill="#25D366"/>'
    ),
    mail: wrap(
      '<rect x="6.6" y="9.4" width="18.8" height="13.4" rx="2" fill="#fff" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<path d="M7.2 10.2 16 16.6l8.8-6.4" fill="none" stroke="#e85d00" stroke-width="1.3" stroke-linejoin="round"/>'
    ),
    phone: wrap(
      '<rect x="11.2" y="5.8" width="9.6" height="20.4" rx="2.4" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<circle cx="16" cy="22.8" r="1.1" fill="#2e5aac"/>'
    ),
    qr: wrap(
      '<rect x="7.2" y="7.2" width="7.2" height="7.2" rx="1.1" fill="#0b2545"/>' +
        '<rect x="17.6" y="7.2" width="7.2" height="7.2" rx="1.1" fill="#2e5aac"/>' +
        '<rect x="7.2" y="17.6" width="7.2" height="7.2" rx="1.1" fill="#2e5aac"/>' +
        '<rect x="17.6" y="17.6" width="3" height="3" fill="#e85d00"/>' +
        '<rect x="21.6" y="17.6" width="3.2" height="7.2" fill="#0b2545"/>'
    ),
    health: wrap(
      '<path d="M16 25.2s-8.4-5.4-8.4-11.2A4.7 4.7 0 0 1 16 10a4.7 4.7 0 0 1 8.4 4c0 5.8-8.4 11.2-8.4 11.2z" fill="#fff1f2" stroke="#e11d48" stroke-width="1.2"/>' +
        '<path d="M11.6 14.8h2.4l1.2-2.4 1.8 5 1.2-2.6H20" fill="none" stroke="#e11d48" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    sync: wrap(
      '<path d="M10.2 13.2A6.6 6.6 0 0 1 21.6 12" fill="none" stroke="#2e5aac" stroke-width="1.6" stroke-linecap="round"/>' +
        '<path d="M21.8 18.8A6.6 6.6 0 0 1 10.4 20" fill="none" stroke="#e85d00" stroke-width="1.6" stroke-linecap="round"/>' +
        '<path d="M21.6 8.8v4.2h-4" fill="none" stroke="#2e5aac" stroke-width="1.5" stroke-linecap="round"/>' +
        '<path d="M10.4 23.2v-4.2h4" fill="none" stroke="#e85d00" stroke-width="1.5" stroke-linecap="round"/>'
    ),
    excel: wrap(
      '<rect x="7.4" y="6.4" width="17.2" height="19.2" rx="2" fill="#e7f6ee" stroke="#2e9b6a" stroke-width="1.2"/>' +
        '<text x="16" y="19" text-anchor="middle" font-size="7" font-weight="700" fill="#2e9b6a">X</text>'
    ),
    print: wrap(
      '<rect x="9.2" y="6.2" width="13.6" height="6.2" rx="1" fill="#d6e4f7" stroke="#2e5aac" stroke-width="1.1"/>' +
        '<rect x="7.2" y="11.6" width="17.6" height="9" rx="2" fill="#2e5aac"/>' +
        '<rect x="10.4" y="16.8" width="11.2" height="7.4" rx="1" fill="#fff" stroke="#2e5aac" stroke-width="1.05"/>'
    ),
    keyboard: wrap(
      '<rect x="5.8" y="10.4" width="20.4" height="12.2" rx="2.2" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<rect x="8.2" y="13.2" width="2.2" height="2.2" rx=".4" fill="#2e5aac"/>' +
        '<rect x="11.4" y="13.2" width="2.2" height="2.2" rx=".4" fill="#8fb0de"/>' +
        '<rect x="14.6" y="13.2" width="2.2" height="2.2" rx=".4" fill="#2e5aac"/>' +
        '<rect x="17.8" y="13.2" width="2.2" height="2.2" rx=".4" fill="#8fb0de"/>' +
        '<rect x="10.6" y="17.6" width="10.8" height="2.2" rx=".5" fill="#e85d00"/>'
    ),
    database: wrap(
      '<ellipse cx="16" cy="10" rx="8.2" ry="3.2" fill="#d6e4f7" stroke="#2e5aac" stroke-width="1.15"/>' +
        '<path d="M7.8 10v8.4c0 1.8 3.7 3.2 8.2 3.2s8.2-1.4 8.2-3.2V10" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.15"/>' +
        '<path d="M7.8 14.2c0 1.8 3.7 3.2 8.2 3.2s8.2-1.4 8.2-3.2" fill="none" stroke="#2e5aac" stroke-width="1.05"/>'
    ),
    folder: wrap(
      '<path d="M6.8 10.4h7.2l1.8 1.8H25a1.6 1.6 0 0 1 1.6 1.6V23a1.8 1.8 0 0 1-1.8 1.8H8.4A1.6 1.6 0 0 1 6.8 23.2z" fill="#fff8e1" stroke="#e8a317" stroke-width="1.2" stroke-linejoin="round"/>'
    ),
    ticket: wrap(
      '<rect x="6.6" y="10.4" width="18.8" height="11.4" rx="2.2" fill="#f3eefe" stroke="#6f42c1" stroke-width="1.2"/>' +
        '<circle cx="6.6" cy="16.1" r="1.6" fill="#fff"/>' +
        '<circle cx="25.4" cy="16.1" r="1.6" fill="#fff"/>' +
        '<rect x="12.4" y="13.6" width="7.2" height="1.3" rx=".5" fill="#6f42c1"/>'
    ),
    cart: wrap(
      '<path d="M8 9.2h2.2l2.2 10.2h10.6" fill="none" stroke="#2e5aac" stroke-width="1.5" stroke-linecap="round"/>' +
        '<path d="M11.2 12.2h13.2l-1.4 6.6H13z" fill="#fff4eb" stroke="#e85d00" stroke-width="1.15"/>' +
        '<circle cx="14.2" cy="22.8" r="1.4" fill="#0b2545"/>' +
        '<circle cx="21.4" cy="22.8" r="1.4" fill="#0b2545"/>'
    ),
    receipt: wrap(
      '<path d="M10 5.8h12v20.4l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4-2 1.4z" fill="#fff" stroke="#e85d00" stroke-width="1.2"/>' +
        '<rect x="12.4" y="9.4" width="7.2" height="1.3" rx=".5" fill="#2e5aac"/>' +
        '<rect x="12.4" y="12.8" width="7.2" height="1.2" rx=".5" fill="#d7e0ea"/>' +
        '<rect x="12.4" y="16.2" width="5.2" height="1.2" rx=".5" fill="#d7e0ea"/>'
    ),
    building: wrap(
      '<rect x="8.2" y="9.2" width="15.6" height="15.2" rx="1.2" fill="#e8f1fc" stroke="#0b2545" stroke-width="1.2"/>' +
        '<rect x="11" y="12.2" width="2.4" height="2.4" fill="#2e5aac"/>' +
        '<rect x="15.8" y="12.2" width="2.4" height="2.4" fill="#8fb0de"/>' +
        '<rect x="11" y="16.4" width="2.4" height="2.4" fill="#8fb0de"/>' +
        '<rect x="15.8" y="16.4" width="2.4" height="2.4" fill="#2e5aac"/>' +
        '<rect x="13.8" y="20.4" width="4.4" height="4" fill="#0b2545"/>'
    ),
    info: wrap(
      '<circle cx="16" cy="16" r="8.4" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<rect x="15.1" y="13.6" width="1.8" height="7" rx=".7" fill="#2e5aac"/>' +
        '<circle cx="16" cy="10.8" r="1.15" fill="#2e5aac"/>'
    ),
    success: wrap(
      '<circle cx="16" cy="16" r="8.4" fill="#e7f6ee" stroke="#2e9b6a" stroke-width="1.2"/>' +
        '<path d="M11.2 16.2 14.4 19.4 21 12.6" fill="none" stroke="#2e9b6a" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    error: wrap(
      '<circle cx="16" cy="16" r="8.4" fill="#fff1f2" stroke="#e11d48" stroke-width="1.2"/>' +
        '<path d="M12.4 12.4 19.6 19.6M19.6 12.4 12.4 19.6" stroke="#e11d48" stroke-width="1.8" stroke-linecap="round"/>'
    ),
    fullscreen: wrap(
      '<rect x="8" y="8" width="16" height="16" rx="2" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<path d="M12.2 12.2H9.4V9.4M19.8 12.2h2.8V9.4M12.2 19.8H9.4v2.8M19.8 19.8h2.8v2.8" fill="none" stroke="#e85d00" stroke-width="1.4" stroke-linecap="round"/>'
    ),
    copy: wrap(
      '<rect x="10.6" y="9.2" width="12.2" height="14.6" rx="1.8" fill="#fff" stroke="#2e5aac" stroke-width="1.15"/>' +
        '<rect x="7.6" y="6.4" width="12.2" height="14.6" rx="1.8" fill="#e8f1fc" stroke="#2e5aac" stroke-width="1.15"/>'
    ),
    download: wrap(
      '<path d="M16 8.4v11.2" stroke="#2e5aac" stroke-width="1.8" stroke-linecap="round"/>' +
        '<path d="M11.6 15.6 16 20.2l4.4-4.6" fill="none" stroke="#2e5aac" stroke-width="1.6" stroke-linecap="round"/>' +
        '<rect x="8.4" y="22.2" width="15.2" height="2.2" rx="1" fill="#e85d00"/>'
    ),
    upload: wrap(
      '<path d="M16 20.4V9.2" stroke="#2e5aac" stroke-width="1.8" stroke-linecap="round"/>' +
        '<path d="M11.6 13.2 16 8.6l4.4 4.6" fill="none" stroke="#2e5aac" stroke-width="1.6" stroke-linecap="round"/>' +
        '<rect x="8.4" y="22.2" width="15.2" height="2.2" rx="1" fill="#2e9b6a"/>'
    ),
    grid: wrap(
      '<rect x="7.4" y="7.4" width="7" height="7" rx="1.4" fill="#2e5aac"/>' +
        '<rect x="17.6" y="7.4" width="7" height="7" rx="1.4" fill="#8fb0de"/>' +
        '<rect x="7.4" y="17.6" width="7" height="7" rx="1.4" fill="#8fb0de"/>' +
        '<rect x="17.6" y="17.6" width="7" height="7" rx="1.4" fill="#e85d00"/>'
    ),
    activity: wrap(
      '<rect x="6.6" y="8.2" width="18.8" height="15.8" rx="2.4" fill="#fff" stroke="#2e5aac" stroke-width="1.2"/>' +
        '<polyline points="9.4,18.2 12.6,14.4 15.2,16.6 19.4,11.6 22.6,15.2" fill="none" stroke="#2e9b6a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
    ),
    rupee: wrap(
      '<circle cx="16" cy="16" r="8.6" fill="#fff4eb" stroke="#e85d00" stroke-width="1.2"/>' +
        '<text x="16" y="19.4" text-anchor="middle" font-size="11" font-weight="700" fill="#e85d00">₹</text>'
    ),
  };

  var CLASS_MAP = {
    "bi-save": "save",
    "bi-floppy": "save",
    "bi-pencil": "edit",
    "bi-pencil-square": "edit",
    "bi-pencil-fill": "edit",
    "bi-trash": "delete",
    "bi-trash-fill": "delete",
    "bi-plus-lg": "add",
    "bi-plus": "add",
    "bi-plus-circle": "add",
    "bi-plus-square": "add",
    "bi-person-plus": "customer",
    "bi-arrow-clockwise": "refresh",
    "bi-arrow-repeat": "sync",
    "bi-arrow-left": "back",
    "bi-arrow-right": "logout",
    "bi-box-arrow-right": "logout",
    "bi-box-arrow-up-right": "preview",
    "bi-box-arrow-in-down-left": "download",
    "bi-arrow-left-right": "transfer",
    "bi-eye": "preview",
    "bi-eye-fill": "preview",
    "bi-eye-slash": "preview",
    "bi-file-earmark-pdf": "pdf",
    "bi-file-earmark-excel": "excel",
    "bi-file-earmark-spreadsheet": "excel",
    "bi-file-earmark-bar-graph": "reports",
    "bi-file-earmark-text": "document",
    "bi-file-earmark": "document",
    "bi-file-text": "document",
    "bi-journal-text": "ledger",
    "bi-journal-bookmark": "ledger",
    "bi-book": "ledger",
    "bi-clipboard-data": "reports",
    "bi-graph-up": "chart",
    "bi-bar-chart": "chart",
    "bi-bar-chart-line": "chart",
    "bi-pie-chart": "chart",
    "bi-people": "users",
    "bi-people-fill": "users",
    "bi-person": "customer",
    "bi-person-circle": "customer",
    "bi-person-badge": "customer",
    "bi-person-gear": "settings",
    "bi-person-check": "customer",
    "bi-person-vcard": "customer",
    "bi-bank": "bank",
    "bi-building": "building",
    "bi-buildings": "building",
    "bi-cash": "cash",
    "bi-cash-stack": "cash",
    "bi-cash-coin": "cash",
    "bi-currency-rupee": "rupee",
    "bi-credit-card": "payment",
    "bi-wallet2": "payment",
    "bi-receipt": "receipt",
    "bi-receipt-cutoff": "invoice",
    "bi-cart-plus": "cart",
    "bi-box": "item",
    "bi-box-seam": "item",
    "bi-collection": "grid",
    "bi-ui-checks-grid": "grid",
    "bi-grid": "grid",
    "bi-grid-3x3-gap": "dashboard",
    "bi-speedometer2": "dashboard",
    "bi-house": "dashboard",
    "bi-house-door": "dashboard",
    "bi-search": "search",
    "bi-funnel": "search",
    "bi-bell": "bell",
    "bi-bell-fill": "bell",
    "bi-calendar3": "calendar",
    "bi-calendar": "calendar",
    "bi-calendar-event": "calendar",
    "bi-clock": "clock",
    "bi-clock-history": "clock",
    "bi-gear": "settings",
    "bi-gear-fill": "settings",
    "bi-sliders": "settings",
    "bi-tools": "tools",
    "bi-wrench": "tools",
    "bi-hdd-rack": "database",
    "bi-database": "database",
    "bi-database-check": "database",
    "bi-heart-pulse": "health",
    "bi-activity": "activity",
    "bi-clipboard-pulse": "health",
    "bi-whatsapp": "whatsapp",
    "bi-envelope": "mail",
    "bi-envelope-fill": "mail",
    "bi-telephone": "phone",
    "bi-qr-code": "qr",
    "bi-qr-code-scan": "qr",
    "bi-printer": "print",
    "bi-download": "download",
    "bi-upload": "upload",
    "bi-cloud-arrow-up": "upload",
    "bi-cloud-arrow-down": "download",
    "bi-copy": "copy",
    "bi-clipboard": "copy",
    "bi-check2": "success",
    "bi-check-circle": "success",
    "bi-check-circle-fill": "success",
    "bi-x-circle-fill": "error",
    "bi-exclamation-triangle": "warning",
    "bi-exclamation-triangle-fill": "warning",
    "bi-exclamation-octagon": "warning",
    "bi-info-circle": "info",
    "bi-info-circle-fill": "info",
    "bi-slash-circle-fill": "error",
    "bi-keyboard": "keyboard",
    "bi-arrows-fullscreen": "fullscreen",
    "bi-fullscreen": "fullscreen",
    "bi-fullscreen-exit": "fullscreen",
    "bi-folder": "folder",
    "bi-folder2": "folder",
    "bi-diagram-3": "activity",
    "bi-list-check": "activity",
    "bi-ticket": "ticket",
    "bi-ticket-perforated": "ticket",
    "bi-stamp": "stamp",
    "bi-patch-check": "success",
    "bi-shield-check": "success",
    "bi-life-preserver": "health",
    "bi-chat-dots": "crm",
    "bi-inbox": "mail",
    "bi-kanban": "crm",
    "bi-briefcase": "crm",
    "bi-graph-up-arrow": "income",
    "bi-graph-down-arrow": "expense",
    "bi-arrow-up-circle": "income",
    "bi-arrow-down-circle": "expense",
    "bi-box-arrow-in-right": "logout",
    "bi-door-open": "logout",
    "bi-moon-stars": "settings",
    "bi-sun": "settings",
    "bi-circle": "document",
  };

  var HINT_MAP = [
    [/ledger/, "ledger"],
    [/financial|balance|profit|p&l|statement/, "reports"],
    [/stamp/, "stamp"],
    [/ecourt|e-court|court/, "court"],
    [/customer/, "customer"],
    [/gst/, "gst"],
    [/tds/, "tax"],
    [/tax/, "tax"],
    [/item/, "item"],
    [/bank/, "bank"],
    [/payment|receipt/, "payment"],
    [/invoice|sale|purchase|voucher/, "invoice"],
    [/dashboard/, "dashboard"],
    [/crm|lead|follow/, "crm"],
    [/report|analys/, "reports"],
    [/master/, "folder"],
    [/account/, "ledger"],
    [/expense/, "expense"],
    [/income/, "income"],
    [/ticket/, "ticket"],
    [/qr/, "qr"],
    [/cash/, "cash"],
  ];

  var TONE = {
    save: "blue",
    edit: "orange",
    delete: "rose",
    add: "green",
    refresh: "blue",
    sync: "orange",
    preview: "blue",
    pdf: "rose",
    excel: "green",
    customer: "blue",
    users: "purple",
    bank: "teal",
    cash: "green",
    payment: "blue",
    invoice: "orange",
    receipt: "orange",
    item: "orange",
    stamp: "purple",
    tax: "blue",
    gst: "blue",
    warning: "yellow",
    court: "blue",
    chart: "green",
    reports: "blue",
    ledger: "blue",
    dashboard: "purple",
    crm: "orange",
    calendar: "blue",
    bell: "yellow",
    settings: "blue",
    tools: "yellow",
    logout: "rose",
    income: "green",
    expense: "rose",
    whatsapp: "green",
    success: "green",
    error: "rose",
    transfer: "orange",
    cart: "orange",
    rupee: "orange",
    ticket: "purple",
    qr: "blue",
    health: "rose",
  };

  function glyphClass(el) {
    var list = el.classList;
    for (var i = 0; i < list.length; i++) {
      if (list[i].indexOf("bi-") === 0 && list[i] !== "bi") return list[i];
    }
    return "";
  }

  function hintKey(el) {
    var node = el.closest("[data-jtcs-hint], [data-menu-key], a, button");
    var text = "";
    if (el.getAttribute("data-jtcs-hint")) text = el.getAttribute("data-jtcs-hint");
    else if (node) {
      text =
        (node.getAttribute("data-jtcs-hint") || "") +
        " " +
        (node.getAttribute("href") || "") +
        " " +
        (node.getAttribute("data-menu-key") || "") +
        " " +
        (node.textContent || "");
    }
    text = String(text).toLowerCase();
    for (var i = 0; i < HINT_MAP.length; i++) {
      if (HINT_MAP[i][0].test(text)) return HINT_MAP[i][1];
    }
    return "";
  }

  function resolveKey(el) {
    var forced = el.getAttribute("data-jtcs-icon");
    if (forced && G[forced]) return forced;
    var cls = glyphClass(el);
    if (CLASS_MAP[cls]) return CLASS_MAP[cls];
    var hinted = hintKey(el);
    if (hinted) return hinted;
    return "document";
  }

  function needsTile(el) {
    return !!(
      el.closest(".jtcs-ribbon-btn, .inv-hub-tile, .jtcs-report-card, .jtcs-page-icon, .cp-module-icon")
    );
  }

  function paintBi(el) {
    if (!el || !el.classList || !el.classList.contains("bi")) return;
    if (el.closest(SKIP_ROOTS)) return;
    var cls = glyphClass(el);
    if (!cls || SKIP[cls]) {
      if (el.classList.contains("jtcs-illu")) {
        el.classList.remove("jtcs-illu", "jtcs-illu-tile");
        el.removeAttribute("data-jtcs-svg");
        el.removeAttribute("data-tone");
        el.innerHTML = "";
      }
      return;
    }
    var key = resolveKey(el);
    var svg = G[key] || G.document;
    var mark = key + (needsTile(el) ? "-tile" : "");
    if (el.getAttribute("data-jtcs-svg") === mark && el.querySelector("svg")) return;
    el.classList.add("jtcs-illu");
    el.classList.toggle("jtcs-illu-tile", needsTile(el));
    var tone = TONE[key] || "blue";
    el.setAttribute("data-tone", tone);
    el.setAttribute("data-jtcs-svg", mark);
    el.innerHTML = svg;
  }

  function paintHost(el) {
    var key = el.getAttribute("data-jtcs-icon");
    if (!key || !G[key]) key = "document";
    if (el.getAttribute("data-jtcs-svg") === key && el.querySelector("svg")) return;
    el.setAttribute("data-jtcs-svg", key);
    el.innerHTML = G[key] || G.document;
  }

  function scan(root) {
    var scope = root && root.querySelectorAll ? root : document;
    var icons = scope.querySelectorAll ? scope.querySelectorAll("i.bi") : [];
    for (var i = 0; i < icons.length; i++) paintBi(icons[i]);
    var hosts = scope.querySelectorAll ? scope.querySelectorAll("[data-jtcs-icon]") : [];
    for (var j = 0; j < hosts.length; j++) {
      if (hosts[j].matches && hosts[j].matches("i.bi")) continue;
      paintHost(hosts[j]);
    }
    if (root && root.matches) {
      if (root.matches("i.bi")) paintBi(root);
      if (root.matches("[data-jtcs-icon]") && !root.matches("i.bi")) paintHost(root);
    }
  }

  function boot() {
    scan(document);
    if (typeof MutationObserver === "undefined") return;
    var obs = new MutationObserver(function (records) {
      for (var i = 0; i < records.length; i++) {
        var rec = records[i];
        if (rec.type === "attributes" && rec.target && rec.target.matches) {
          if (rec.target.matches("i.bi")) paintBi(rec.target);
          continue;
        }
        var nodes = rec.addedNodes || [];
        for (var n = 0; n < nodes.length; n++) {
          var node = nodes[n];
          if (node.nodeType !== 1) continue;
          scan(node);
        }
      }
    });
    obs.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class"],
    });
  }

  window.JTCSIcons = {
    paint: paintBi,
    scan: scan,
    svg: function (key) {
      return G[key] || G.document;
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
