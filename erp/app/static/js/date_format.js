(function (global) {
  "use strict";

  function pad2(value) {
    return String(value).padStart(2, "0");
  }

  function parseDateValue(value) {
    if (value == null || value === "") return null;
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    }

    const raw = String(value).trim();
    if (!raw) return null;

    const iso = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (iso) {
      return new Date(Number(iso[1]), Number(iso[2]) - 1, Number(iso[3]));
    }

    const dmy = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (dmy) {
      return new Date(Number(dmy[3]), Number(dmy[2]) - 1, Number(dmy[1]));
    }

    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) return null;
    return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  }

  function formatDisplayDate(value, empty) {
    const emptyText = empty == null ? "—" : empty;
    const dateValue = parseDateValue(value);
    if (!dateValue) {
      return value == null || value === "" ? emptyText : String(value);
    }
    return pad2(dateValue.getDate()) + "/" + pad2(dateValue.getMonth() + 1) + "/" + dateValue.getFullYear();
  }

  function hasTimeComponent(value) {
    const raw = String(value == null ? "" : value).trim();
    if (/[T ]\d{1,2}:\d{2}/.test(raw)) return true;
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return value.getHours() !== 0 || value.getMinutes() !== 0 || value.getSeconds() !== 0;
    }
    return false;
  }

  function formatDisplayDateTime(value, empty) {
    const emptyText = empty == null ? "—" : empty;
    if (value == null || value === "") return emptyText;
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return formatClockParts(value);
    }
    const raw = String(value).trim();
    const isoDateTime = raw.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{1,2}):(\d{2})(?::(\d{2}))?/);
    if (isoDateTime) {
      const datePart = formatDisplayDate(
        isoDateTime[1] + "-" + isoDateTime[2] + "-" + isoDateTime[3],
        emptyText
      );
      const seconds = isoDateTime[6] != null ? pad2(isoDateTime[6]) : "00";
      return datePart + " " + pad2(isoDateTime[4]) + ":" + pad2(isoDateTime[5]) + ":" + seconds;
    }
    const displayDateTime = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})[ T](\d{1,2}):(\d{2})(?::(\d{2}))?/);
    if (displayDateTime) {
      const seconds = displayDateTime[6] != null ? pad2(displayDateTime[6]) : "00";
      return (
        pad2(displayDateTime[1]) +
        "/" +
        pad2(displayDateTime[2]) +
        "/" +
        displayDateTime[3] +
        " " +
        pad2(displayDateTime[4]) +
        ":" +
        pad2(displayDateTime[5]) +
        ":" +
        seconds
      );
    }
    const dateOnly = formatDisplayDate(value, "");
    if (dateOnly) return dateOnly;
    return raw;
  }

  function formatDisplaySmart(value, empty) {
    if (hasTimeComponent(value)) return formatDisplayDateTime(value, empty);
    return formatDisplayDate(value, empty);
  }

  function toIsoDate(value) {
    const dateValue = parseDateValue(value);
    if (!dateValue) return "";
    return dateValue.getFullYear() + "-" + pad2(dateValue.getMonth() + 1) + "-" + pad2(dateValue.getDate());
  }

  function formatClockParts(dateObj) {
    try {
      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Asia/Kolkata",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
        hourCycle: "h23",
      }).formatToParts(dateObj);
      const get = function (type) {
        const found = parts.find(function (part) {
          return part.type === type;
        });
        return found ? found.value : "";
      };
      let hour = get("hour");
      if (hour === "24") hour = "00";
      return (
        get("day") +
        "/" +
        get("month") +
        "/" +
        get("year") +
        " " +
        pad2(hour) +
        ":" +
        pad2(get("minute")) +
        ":" +
        pad2(get("second"))
      );
    } catch (_err) {
      return (
        pad2(dateObj.getDate()) +
        "/" +
        pad2(dateObj.getMonth() + 1) +
        "/" +
        dateObj.getFullYear() +
        " " +
        pad2(dateObj.getHours()) +
        ":" +
        pad2(dateObj.getMinutes()) +
        ":" +
        pad2(dateObj.getSeconds())
      );
    }
  }

  function parseServerIso(iso) {
    const raw = String(iso || "").trim();
    if (!raw) return NaN;
    if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(raw)) {
      return Date.parse(raw);
    }
    // Naive stamps from older servers were UTC wall-clock; do not treat them as local.
    return NaN;
  }

  function startLiveClocks(root) {
    if (typeof document === "undefined") return;
    const scope = root && root.querySelectorAll ? root : document;
    const nodes = scope.querySelectorAll
      ? scope.querySelectorAll(".jtcs-live-clock")
      : [];
    if (!nodes.length) return;

    const anchors = [];
    nodes.forEach(function (el) {
      const iso = (el.getAttribute("data-server-iso") || "").trim();
      let serverMs = parseServerIso(iso);
      if (Number.isNaN(serverMs)) serverMs = Date.now();
      anchors.push({
        el: el,
        offsetMs: serverMs - Date.now(),
      });
    });

    function tick() {
      anchors.forEach(function (item) {
        const now = new Date(Date.now() + item.offsetMs);
        item.el.textContent = formatClockParts(now);
      });
    }

    tick();
    if (!global.__JTCS_LIVE_CLOCK_TIMER__) {
      global.__JTCS_LIVE_CLOCK_TIMER__ = global.setInterval(tick, 1000);
    }
  }

  const api = {
    DISPLAY_FORMAT: "dd/mm/yyyy",
    parseDateValue: parseDateValue,
    formatDisplayDate: formatDisplayDate,
    formatDisplayDateTime: formatDisplayDateTime,
    formatDisplaySmart: formatDisplaySmart,
    hasTimeComponent: hasTimeComponent,
    toIsoDate: toIsoDate,
    startLiveClocks: startLiveClocks,
  };

  global.JTCS = global.JTCS || {};
  global.JTCS.date = api;
  global.formatDisplayDate = formatDisplayDate;
  global.formatDisplayDateTime = formatDisplayDateTime;
  global.formatDisplaySmart = formatDisplaySmart;
  global.JtcsFormatDisplayDate = formatDisplaySmart;
  global.JtcsFormatDisplayDateTime = formatDisplayDateTime;
  global.toIsoDate = toIsoDate;

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () {
        startLiveClocks(document);
      });
    } else {
      startLiveClocks(document);
    }
  }
})(typeof window !== "undefined" ? window : globalThis);
