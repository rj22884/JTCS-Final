export type CheckState = "verified" | "not_verified" | "not_checked";

const LIVE_CHECK_IDS = ["phoneVerified", "businessVerified", "wabaAccessible", "phoneOnWaba", "webhookSubscribed"] as const;

export function liveReady(states: Record<string, string | undefined>) {
  return LIVE_CHECK_IDS.every((id) => states[id] === "verified");
}

export type SubscribePlan =
  | { post: true }
  | {
      post: false;
      reason:
        | "missing_phone"
        | "missing_waba"
        | "missing_token"
        | "missing_app"
        | "missing_business"
        | "id_mismatch"
        | "business_inaccessible"
        | "waba_inaccessible"
        | "phone_not_on_waba"
        | "phone_list_unread"
        | "subscription_unread"
        | "already_subscribed";
    };

export function planSubscribe(input: {
  phoneNumberId: string | null;
  businessAccountId: string | null;
  appId: string | null;
  businessId: string | null;
  accessTokenPresent: boolean;
  businessState: CheckState;
  wabaState: CheckState;
  phoneOnWaba: CheckState;
  appSubscribed: boolean | null;
}): SubscribePlan {
  if (!input.accessTokenPresent) return { post: false, reason: "missing_token" };
  if (!input.businessAccountId) return { post: false, reason: "missing_waba" };
  if (!input.phoneNumberId) return { post: false, reason: "missing_phone" };
  if (!input.appId) return { post: false, reason: "missing_app" };
  if (!input.businessId) return { post: false, reason: "missing_business" };
  const ids = [input.phoneNumberId, input.businessAccountId, input.businessId];
  if (new Set(ids).size !== ids.length) return { post: false, reason: "id_mismatch" };
  if (input.businessState !== "verified") return { post: false, reason: "business_inaccessible" };
  if (input.wabaState !== "verified") return { post: false, reason: "waba_inaccessible" };
  if (input.phoneOnWaba === "not_verified") return { post: false, reason: "phone_not_on_waba" };
  if (input.phoneOnWaba !== "verified") return { post: false, reason: "phone_list_unread" };
  if (input.appSubscribed === null) return { post: false, reason: "subscription_unread" };
  if (input.appSubscribed) return { post: false, reason: "already_subscribed" };
  return { post: true };
}

export function idsAreDistinct(phoneNumberId: string | null, businessAccountId: string | null, businessId: string | null = null) {
  const ids = [phoneNumberId, businessAccountId, businessId].filter((id): id is string => Boolean(id));
  if (ids.length < 2) return ids.length === 0 ? null : true;
  return new Set(ids).size === ids.length;
}
