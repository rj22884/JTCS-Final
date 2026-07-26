/**
 * JTCS global hotkeys (Ctrl / Alt).
 * Auto-binds common action buttons and shows key labels + help (Ctrl+/).
 */
(function () {
  "use strict";

  if (window.__JTCS_HOTKEYS__) return;
  window.__JTCS_HOTKEYS__ = true;

  var BINDINGS = [];

  // NOTE: Browsers reserve Ctrl+N (new window/tab). Web pages cannot reliably
  // cancel it, so New/Add uses Alt+N. Ctrl+N is still intercepted when possible.
  var NEW_CHORD = "alt+n";
  var NEW_CHORD_FALLBACK = "ctrl+n";

  var ID_RULES = [
    { re: /(SaveBtn|SaveButton|ConfirmImportBtn|ConfirmSaleBtn|ConfirmBtn)$/i, chord: "ctrl+s", action: "Save / Confirm" },
    { re: /(AddBtn|AddNewBtn|NewEntryBtn|NewBtn|AddRowBtn)$/i, chord: NEW_CHORD, action: "New / Add" },
    { re: /EditBtn$/i, chord: "alt+e", action: "Edit" },
    { re: /DeleteBtn$/i, chord: "ctrl+d", action: "Delete" },
    { re: /(SearchBtn|FilterApplyBtn)$/i, chord: "alt+f", action: "Search" },
    { re: /BackBtn$/i, chord: "alt+b", action: "Back" },
    { re: /(OpenImportBtn|ImportBtn)$/i, chord: "alt+i", action: "Import" },
    { re: /OpenManualBtn$/i, chord: "alt+m", action: "Manual Entry" },
    { re: /SellSelectedBtn$/i, chord: "alt+s", action: "Sell Selected" },
    { re: /ReadPdfBtn$/i, chord: "ctrl+enter", action: "Read PDF" },
  ];

  // Chords that must work even while focus is inside an input/textarea.
  var ALLOW_WHILE_TYPING = {
    "ctrl+s": true,
    "alt+n": true,
    "ctrl+n": true,
    "escape": true,
    "ctrl+/": true,
    "alt+h": true,
  };

  function normalizeChord(raw) {
    return String(raw || "")
      .toLowerCase()
      .replace(/\s+/g, "")
      .split("+")
      .filter(Boolean)
      .sort(function (a, b) {
        var order = { ctrl: 0, alt: 1, shift: 2 };
        var oa = order[a];
        var ob = order[b];
        if (oa != null && ob != null) return oa - ob;
        if (oa != null) return -1;
        if (ob != null) return 1;
        return a < b ? -1 : a > b ? 1 : 0;
      })
      .join("+");
  }

  function formatChord(chord) {
    return String(chord || "")
      .split("+")
      .map(function (part) {
        if (part === "ctrl") return "Ctrl";
        if (part === "alt") return "Alt";
        if (part === "shift") return "Shift";
        if (part === "/") return "/";
        if (part === "escape") return "Esc";
        if (part === "enter") return "Enter";
        return part.length === 1 ? part.toUpperCase() : part;
      })
      .join("+");
  }

  function eventChord(e) {
    var parts = [];
    if (e.ctrlKey || e.metaKey) parts.push("ctrl");
    if (e.altKey) parts.push("alt");
    if (e.shiftKey) parts.push("shift");
    var key = e.key;
    if (!key) return "";
    if (key === "Escape") key = "escape";
    else if (key === "Enter") key = "enter";
    else if (key === "/") key = "/";
    else if (key.length === 1) key = key.toLowerCase();
    else key = key.toLowerCase();
    if (key === "control" || key === "alt" || key === "shift" || key === "meta") return "";
    parts.push(key);
    return normalizeChord(parts.join("+"));
  }

  function isTypingTarget(el) {
    if (!el || el === document.body) return false;
    var tag = (el.tagName || "").toLowerCase();
    if (tag === "textarea" || tag === "select" || el.isContentEditable) return true;
    if (tag === "input") {
      var type = (el.type || "text").toLowerCase();
      return !["button", "submit", "reset", "checkbox", "radio", "file", "color", "range"].includes(type);
    }
    return false;
  }

  function isVisible(el) {
    if (!el) return false;
    if (el.disabled || el.getAttribute("aria-disabled") === "true") return false;
    if (el.hidden || el.getAttribute("hidden") != null) return false;
    var style = window.getComputedStyle(el);
    if (style.display === "none" || style.visibility === "hidden") return false;
    var rect = el.getBoundingClientRect();
    return rect.width > 0 || rect.height > 0 || style.position === "fixed";
  }

  function openModalRoot() {
    var modals = document.querySelectorAll(".modal.show");
    return modals.length ? modals[modals.length - 1] : null;
  }

  function resolveTargets(chord) {
    var modal = openModalRoot();
    var scope = modal || document;
    var list = [];
    scope.querySelectorAll("[data-hotkey]").forEach(function (el) {
      if (normalizeChord(el.getAttribute("data-hotkey")) === chord && isVisible(el)) {
        list.push(el);
      }
    });
    if (!list.length && modal) {
      document.querySelectorAll("[data-hotkey]").forEach(function (el) {
        if (normalizeChord(el.getAttribute("data-hotkey")) === chord && isVisible(el)) {
          list.push(el);
        }
      });
    }
    return list;
  }

  function clickTarget(el) {
    if (!el || !isVisible(el)) return false;
    try {
      el.focus({ preventScroll: true });
    } catch (err) {
      /* ignore focus errors */
    }
    el.click();
    return true;
  }

  function stopBrowserChord(e) {
    e.preventDefault();
    e.stopPropagation();
    if (typeof e.stopImmediatePropagation === "function") {
      e.stopImmediatePropagation();
    }
    return false;
  }

  function findNewEntryTarget() {
    var targets = resolveTargets(NEW_CHORD);
    if (!targets.length) targets = resolveTargets(NEW_CHORD_FALLBACK);
    if (!targets.length) {
      // Last resort: common New Entry button ids even if badge not yet bound
      var candidates = document.querySelectorAll(
        "button[id$='NewEntryBtn'], button[id$='NewBtn'], button[id$='AddBtn'], button[id$='AddNewBtn'], button[id$='AddRowBtn']"
      );
      candidates.forEach(function (el) {
        if (isVisible(el)) targets.push(el);
      });
    }
    return targets.find(isVisible) || targets[0] || null;
  }

  function focusSearch() {
    var modal = openModalRoot();
    var scope = modal || document;
    var candidates = scope.querySelectorAll(
      'input[type="search"], input[id*="Search" i], input[id*="Filter" i], input[name*="search" i], .ecourt-col-filter'
    );
    for (var i = 0; i < candidates.length; i++) {
      if (isVisible(candidates[i])) {
        candidates[i].focus();
        candidates[i].select?.();
        return true;
      }
    }
    return false;
  }

  function closeTopModal() {
    var modal = openModalRoot();
    if (!modal || !window.bootstrap) return false;
    var inst = window.bootstrap.Modal.getInstance(modal);
    if (inst) {
      inst.hide();
      return true;
    }
    return false;
  }

  function ensureBadge(el, chord) {
    if (!el || el.querySelector(":scope > .jtcs-hotkey-badge, .jtcs-hotkey-badge")) return;
    if (el.getAttribute("data-hotkey-badge") === "off") return;
    var label = formatChord(chord);
    var badge = document.createElement("kbd");
    badge.className = "jtcs-hotkey-badge";
    badge.textContent = label;
    badge.title = "Shortcut: " + label;
    var span = el.querySelector("span:not(.jtcs-hotkey-badge)");
    if (span && span.parentElement === el) {
      span.appendChild(document.createTextNode(" "));
      span.appendChild(badge);
    } else {
      el.appendChild(document.createTextNode(" "));
      el.appendChild(badge);
    }
    var title = el.getAttribute("title") || "";
    if (title.indexOf(label) === -1) {
      el.setAttribute("title", (title ? title + " · " : "") + label);
    }
  }

  function bindElement(el, chord, action) {
    if (!el || el.dataset.hotkeyBound === "1") return;
    var normalized = normalizeChord(chord);
    el.setAttribute("data-hotkey", normalized);
    el.dataset.hotkeyBound = "1";
    if (action) el.setAttribute("data-hotkey-action", action);
    ensureBadge(el, normalized);
    BINDINGS.push({ el: el, chord: normalized, action: action || el.getAttribute("data-hotkey-action") || "" });
  }

  function autoBind() {
    ID_RULES.forEach(function (rule) {
      document.querySelectorAll("button[id], a[id], input[type='submit'][id]").forEach(function (el) {
        if (!el.id || !rule.re.test(el.id)) return;
        if (el.hasAttribute("data-hotkey") && el.dataset.hotkeyBound === "1") return;
        if (el.hasAttribute("data-hotkey") && !el.dataset.hotkeyBound) {
          bindElement(el, el.getAttribute("data-hotkey"), rule.action);
          return;
        }
        bindElement(el, rule.chord, rule.action);
      });
    });

    document.querySelectorAll(".jtcs-ribbon-btn-primary").forEach(function (el) {
      if (el.dataset.hotkeyBound === "1") return;
      var text = (el.textContent || "").toLowerCase();
      if (/add|new/.test(text)) bindElement(el, NEW_CHORD, "New / Add");
    });

    document.querySelectorAll('a.jtcs-ribbon-btn[href*="exit"], a.jtcs-ribbon-btn[title="Exit"]').forEach(function (el) {
      if (el.dataset.hotkeyBound === "1") return;
      bindElement(el, "alt+b", "Exit / Back");
    });

    document.querySelectorAll("[data-ribbon-action]").forEach(function (el) {
      if (el.dataset.hotkeyBound === "1") return;
      var action = el.getAttribute("data-ribbon-action");
      if (action === "print") bindElement(el, "ctrl+p", "Print");
      else if (action === "export-excel") bindElement(el, "alt+x", "Export Excel");
      else if (action === "export-pdf") bindElement(el, "alt+p", "Export PDF");
      else if (action === "refresh") bindElement(el, "alt+r", "Refresh");
    });

    document.querySelectorAll("[data-hotkey]").forEach(function (el) {
      if (el.dataset.hotkeyBound === "1") return;
      bindElement(el, el.getAttribute("data-hotkey"), el.getAttribute("data-hotkey-action") || "");
    });

    // Generic primary Save in open/page forms without *SaveBtn id
    document.querySelectorAll('button.btn-primary[type="submit"], button.btn-primary').forEach(function (el) {
      if (el.dataset.hotkeyBound === "1" || el.id) return;
      var text = (el.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();
      if (text === "save" || text.indexOf("save ") === 0) {
        bindElement(el, "ctrl+s", "Save");
      }
    });
  }

  function uniqueHelpRows() {
    var seen = {};
    var rows = [];
    var defaults = [
      { chord: "ctrl+s", action: "Save / Confirm" },
      { chord: "alt+n", action: "New / Add" },
      { chord: "alt+e", action: "Edit" },
      { chord: "ctrl+d", action: "Delete" },
      { chord: "alt+f", action: "Focus Search / Filter" },
      { chord: "alt+b", action: "Back / Exit" },
      { chord: "alt+i", action: "Import" },
      { chord: "alt+m", action: "Manual Entry" },
      { chord: "alt+s", action: "Sell Selected" },
      { chord: "ctrl+enter", action: "Read PDF" },
      { chord: "ctrl+p", action: "Print" },
      { chord: "alt+x", action: "Export Excel" },
      { chord: "alt+p", action: "Export PDF" },
      { chord: "alt+r", action: "Refresh" },
      { chord: "escape", action: "Close dialog" },
      { chord: "ctrl+/", action: "Show this help" },
      { chord: "alt+h", action: "Show this help" },
    ];
    defaults.forEach(function (row) {
      seen[row.chord] = true;
      rows.push(row);
    });
    BINDINGS.forEach(function (b) {
      if (!b.chord || seen[b.chord]) return;
      if (!isVisible(b.el)) return;
      seen[b.chord] = true;
      rows.push({ chord: b.chord, action: b.action || b.el.getAttribute("data-hotkey-action") || "Action" });
    });
    return rows;
  }

  function renderHelp() {
    var body = document.getElementById("jtcsHotkeyHelpBody");
    if (!body) return;
    autoBind();
    var rows = uniqueHelpRows();
    body.innerHTML = rows
      .map(function (row) {
        return (
          "<tr><td><kbd class=\"jtcs-hotkey-badge jtcs-hotkey-badge-lg\">" +
          formatChord(row.chord) +
          "</kbd></td><td>" +
          (row.action || "") +
          "</td></tr>"
        );
      })
      .join("");
  }

  function showHelp() {
    renderHelp();
    var el = document.getElementById("jtcsHotkeyHelpModal");
    if (!el || !window.bootstrap) return;
    window.bootstrap.Modal.getOrCreateInstance(el).show();
  }

  function handleKeydown(e) {
    if (e.__jtcsHotkeyHandled) return;
    var chord = eventChord(e);
    if (!chord) return;

    // New Entry: Alt+N is reliable. Ctrl+N is browser-reserved (new window/tab);
    // still try to route it to New Entry and cancel the browser action when allowed.
    if (chord === NEW_CHORD || chord === NEW_CHORD_FALLBACK) {
      var newEl = findNewEntryTarget();
      if (newEl) {
        e.__jtcsHotkeyHandled = true;
        stopBrowserChord(e);
        clickTarget(newEl);
        return;
      }
      // Even with no target, block Ctrl+N inside the ERP so a stray tab is less likely.
      if (chord === NEW_CHORD_FALLBACK) {
        e.__jtcsHotkeyHandled = true;
        stopBrowserChord(e);
      }
      return;
    }

    if (chord === "ctrl+/" || chord === "alt+h") {
      e.__jtcsHotkeyHandled = true;
      stopBrowserChord(e);
      showHelp();
      return;
    }

    if (chord === "escape") {
      if (closeTopModal()) {
        e.__jtcsHotkeyHandled = true;
        stopBrowserChord(e);
      }
      return;
    }

    if (chord === "alt+f") {
      if (focusSearch()) {
        e.__jtcsHotkeyHandled = true;
        stopBrowserChord(e);
      }
      return;
    }

    var typing = isTypingTarget(e.target);
    if (typing && !ALLOW_WHILE_TYPING[chord]) {
      // Plain letters while typing stay in the field; Alt/Ctrl app chords below still run.
      if (!(e.ctrlKey || e.altKey || e.metaKey)) return;
    }

    var targets = resolveTargets(chord);
    if (!targets.length) return;

    var el = targets.find(isVisible) || targets[0];
    if (!el) return;
    e.__jtcsHotkeyHandled = true;
    stopBrowserChord(e);
    clickTarget(el);
  }

  function init() {
    autoBind();
    // Capture on window first, then document — early preventDefault for app chords.
    window.addEventListener("keydown", handleKeydown, true);
    document.addEventListener("keydown", handleKeydown, true);
    document.addEventListener("shown.bs.modal", function () {
      autoBind();
    });
    document.getElementById("jtcsHotkeyHelpBtn")?.addEventListener("click", function (e) {
      e.preventDefault();
      showHelp();
    });

    // Re-scan after delayed UI paint
    setTimeout(autoBind, 400);
    setTimeout(autoBind, 1200);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.JTCSHotkeys = {
    refresh: autoBind,
    showHelp: showHelp,
  };
})();
