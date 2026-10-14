import { requireSession } from "@/lib/admin";
import { CUSTOMER_MASTER_LOGIN_URL, matchCustomerMaster, normalizePhoneDigits } from "@/lib/customer-master";
import { lookupCachedCustomer } from "@/lib/customer-sync";
import { ensureRequestTime, json } from "@/lib/http";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireSession(request);
  if (gate.error) return gate.error;
  const phone = request.nextUrl.searchParams.get("phone") ?? "";
  if (!normalizePhoneDigits(phone)) return json({ error: "invalid_phone" }, 400);
  const sample = matchCustomerMaster(phone, []);
  if (sample.state === "sample") return json(sample);
  const cached = lookupCachedCustomer(phone);
  if (cached.state === "none") {
    return json({ state: "unavailable", loginUrl: CUSTOMER_MASTER_LOGIN_URL, matches: [] });
  }
  return json(cached);
}
