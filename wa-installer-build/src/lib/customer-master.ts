import { normalizeMobile, normalizePhoneDigits, phoneMatchKeys } from "@/lib/phone";

export const CUSTOMER_MASTER_LOGIN_URL = "https://app.jtcsxpert.com/login";
export const CUSTOMER_MASTER_BASE_URL = "https://app.jtcsxpert.com";

export type CustomerMasterRecord = {
  id: string;
  name: string;
  mobile: string;
};

export type CustomerMatch =
  | { state: "sample"; matches: [] }
  | { state: "none"; matches: [] }
  | { state: "one"; matches: [CustomerMasterRecord] }
  | { state: "many"; matches: CustomerMasterRecord[] }
  | { state: "login_required"; loginUrl: string; matches: [] }
  | { state: "unavailable"; loginUrl: string; matches: [] };

export { normalizePhoneDigits, phoneMatchKeys, normalizeMobile };

export function matchCustomerMaster(phone: string, records: readonly CustomerMasterRecord[]): CustomerMatch {
  const keys = new Set(phoneMatchKeys(phone));
  if (keys.size === 0) return { state: "none", matches: [] };
  if (keys.has("16315551181")) return { state: "sample", matches: [] };
  const matches = records.filter((record) => phoneMatchKeys(record.mobile).some((key) => keys.has(key)));
  if (matches.length === 0) return { state: "none", matches: [] };
  if (matches.length === 1) return { state: "one", matches: [matches[0]] };
  return { state: "many", matches };
}

export function customerMasterWithoutErp(): CustomerMatch {
  return { state: "unavailable", loginUrl: CUSTOMER_MASTER_LOGIN_URL, matches: [] };
}

export function erpBaseUrl(value?: string | null) {
  const trimmed = (value ?? process.env.ERP_BASE_URL ?? CUSTOMER_MASTER_BASE_URL).trim().replace(/\/+$/, "");
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "https:") return CUSTOMER_MASTER_BASE_URL;
    return url.origin;
  } catch {
    return CUSTOMER_MASTER_BASE_URL;
  }
}
