/** Shared mobile normalization for CustomerMaster sync and contact CRUD. */

import { DIAL_CODES_LONGEST_FIRST } from "@/lib/country-codes";

export { CONTACT_COUNTRY_CODES } from "@/lib/country-codes";

export const DEFAULT_COUNTRY_CODE = "91";

export type NormalizedMobile = {
  valid: boolean;
  /** Full international digits without + (country + national). */
  digits: string;
  phoneKey: string;
  display: string;
  countryCode: string;
  /** National / local number (ERP mobile or form mobile field). */
  national: string;
  reason?: string;
};

/** Strip spaces, hyphens, brackets and other non-digits. */
export function normalizePhoneDigits(input: string) {
  return input.replace(/\D/g, "");
}

export function normalizeCountryCode(input: string | null | undefined) {
  const digits = normalizePhoneDigits(input ?? "");
  return digits || DEFAULT_COUNTRY_CODE;
}

/**
 * Canonical key for uniqueness / matching.
 * India convention in this app: compare on last 10 digits when longer (e.g. 91xxxxxxxxxx).
 */
export function phoneKeyFromDigits(digits: string) {
  if (!digits) return "";
  return digits.length > 10 ? digits.slice(-10) : digits;
}

/** Split a stored full or local mobile into country code + national number. */
export function splitStoredMobile(mobileDigits: string, countryCodeHint = DEFAULT_COUNTRY_CODE) {
  const digits = normalizePhoneDigits(mobileDigits);
  const cc = normalizeCountryCode(countryCodeHint);
  if (!digits) {
    return { countryCode: cc, national: "", fullDigits: "" };
  }
  if (digits.startsWith(cc) && digits.length > cc.length + 7) {
    return { countryCode: cc, national: digits.slice(cc.length), fullDigits: digits };
  }
  // Typical India local 10-digit from ERP.
  if (digits.length === 10) {
    return { countryCode: cc, national: digits, fullDigits: `${cc}${digits}` };
  }
  return { countryCode: cc, national: digits, fullDigits: `${cc}${digits}` };
}

export function formatContactDisplay(countryCode: string, national: string) {
  const cc = normalizeCountryCode(countryCode);
  const nat = normalizePhoneDigits(national);
  if (!nat) return `+${cc}`;
  return `+${cc} ${nat}`;
}

/** True when the value is mostly digits (a phone), not a person name. */
export function looksLikePhone(value: string) {
  const digits = normalizePhoneDigits(value);
  const compact = value.replace(/[\s\-()+]/g, "");
  return digits.length >= 8 && digits.length >= Math.max(1, Math.floor(compact.length * 0.7));
}

/** True when the value looks like a person name (letters, few digits). */
export function looksLikePersonName(value: string) {
  const trimmed = value.trim();
  if (!trimmed) return false;
  const digits = normalizePhoneDigits(trimmed);
  return /[A-Za-z\u0900-\u097F]/.test(trimmed) && digits.length < 6;
}

/**
 * If Name/Mobile were filled swapped, put them back before save.
 * Example: Name=`7817840614`, Mobile=`Chandra Joshi` → swapped.
 */
export function coerceContactNameMobile(name: string, mobile: string) {
  const nameTrim = name.trim();
  const mobileTrim = mobile.trim();
  if (looksLikePhone(nameTrim) && looksLikePersonName(mobileTrim)) {
    return { name: mobileTrim, mobile: nameTrim, swapped: true as const };
  }
  return { name: nameTrim, mobile: mobileTrim, swapped: false as const };
}

/**
 * Compose country code + national (or pasted full) number.
 * Default country code is +91 India.
 */
export function normalizeContactMobile(countryCode: string, nationalOrFull: string): NormalizedMobile {
  const cc = normalizeCountryCode(countryCode);
  let national = normalizePhoneDigits(nationalOrFull);
  if (!national) {
    const hasLetters = /[A-Za-z\u0900-\u097F]/.test(nationalOrFull || "");
    return {
      valid: false,
      digits: "",
      phoneKey: "",
      display: "",
      countryCode: cc,
      national: "",
      reason: hasLetters
        ? "Enter digits in Mobile. Put the person name in the Name field."
        : "Mobile number is required.",
    };
  }
  // Paste of full international into the mobile field — strip matching country code once.
  if (national.startsWith(cc) && national.length > cc.length + 7) {
    national = national.slice(cc.length);
  }
  const full = `${cc}${national}`;
  if (full.length < 8 || full.length > 15) {
    return {
      valid: false,
      digits: full,
      phoneKey: "",
      display: formatContactDisplay(cc, national),
      countryCode: cc,
      national,
      reason: "Mobile number must be 8 to 15 digits after adding the country code.",
    };
  }
  if (/^0+$/.test(national) || /^0+$/.test(full)) {
    return {
      valid: false,
      digits: full,
      phoneKey: "",
      display: formatContactDisplay(cc, national),
      countryCode: cc,
      national,
      reason: "Mobile number is not valid.",
    };
  }
  const phoneKey = phoneKeyFromDigits(full);
  if (phoneKey.length < 8) {
    return {
      valid: false,
      digits: full,
      phoneKey: "",
      display: formatContactDisplay(cc, national),
      countryCode: cc,
      national,
      reason: "Mobile number is not valid.",
    };
  }
  return {
    valid: true,
    digits: full,
    phoneKey,
    display: formatContactDisplay(cc, national),
    countryCode: cc,
    national,
  };
}

/** Normalize a single free-text mobile (may already include country code). Defaults to +91. */
export function normalizeMobile(input: string): NormalizedMobile {
  const digits = normalizePhoneDigits(input);
  if (!digits) {
    return {
      valid: false,
      digits: "",
      phoneKey: "",
      display: "",
      countryCode: DEFAULT_COUNTRY_CODE,
      national: "",
      reason: "Mobile number is required.",
    };
  }
  if (digits.length === 10) {
    return normalizeContactMobile(DEFAULT_COUNTRY_CODE, digits);
  }
  if (digits.startsWith(DEFAULT_COUNTRY_CODE) && digits.length >= 12) {
    return normalizeContactMobile(DEFAULT_COUNTRY_CODE, digits.slice(DEFAULT_COUNTRY_CODE.length));
  }
  // Unknown longer number: match longest dial code first (e.g. 971 before 97).
  for (const code of DIAL_CODES_LONGEST_FIRST) {
    if (digits.startsWith(code) && digits.length > code.length + 7) {
      return normalizeContactMobile(code, digits.slice(code.length));
    }
  }
  return normalizeContactMobile(DEFAULT_COUNTRY_CODE, digits);
}

export function phoneMatchKeys(input: string) {
  const digits = normalizePhoneDigits(input);
  if (!digits) return [] as string[];
  const keys = new Set<string>([digits, phoneKeyFromDigits(digits)]);
  if (digits.length === 10) keys.add(`91${digits}`);
  return [...keys];
}
