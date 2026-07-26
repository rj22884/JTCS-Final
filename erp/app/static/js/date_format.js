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

  function formatDisplayDateTime(value, empty) {
    const emptyText = empty == null ? "—" : empty;
    if (value == null || value === "") return emptyText;
    const raw = String(value).trim();
    const isoDateTime = raw.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/);
    if (isoDateTime) {
      const datePart = formatDisplayDate(
        isoDateTime[1] + "-" + isoDateTime[2] + "-" + isoDateTime[3],
        emptyText
      );
      const seconds = isoDateTime[6] != null ? isoDateTime[6] : "00";
      return datePart + " " + isoDateTime[4] + ":" + isoDateTime[5] + ":" + seconds;
    }
    const dateOnly = formatDisplayDate(value, "");
    if (dateOnly) return dateOnly;
    return raw;
  }

  function toIsoDate(value) {
    const dateValue = parseDateValue(value);
    if (!dateValue) return "";
    return dateValue.getFullYear() + "-" + pad2(dateValue.getMonth() + 1) + "-" + pad2(dateValue.getDate());
  }

  const api = {
    DISPLAY_FORMAT: "dd/mm/yyyy",
    parseDateValue: parseDateValue,
    formatDisplayDate: formatDisplayDate,
    formatDisplayDateTime: formatDisplayDateTime,
    toIsoDate: toIsoDate,
  };

  global.JTCS = global.JTCS || {};
  global.JTCS.date = api;
  global.formatDisplayDate = formatDisplayDate;
  global.formatDisplayDateTime = formatDisplayDateTime;
  global.toIsoDate = toIsoDate;
})(typeof window !== "undefined" ? window : globalThis);
