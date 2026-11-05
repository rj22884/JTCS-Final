export const CONVERSATION_STATUSES = ["open", "pending", "resolved"] as const;
export type ConversationStatus = (typeof CONVERSATION_STATUSES)[number];

/** Contact service groups (tickable). Misc is exclusive with the others. */
export const LABELS = ["GST", "TDS", "DSC", "ITR", "Misc"] as const;
export type Label = (typeof LABELS)[number];

export const FILTERS = [
  { id: "all", label: "All" },
  { id: "archived", label: "Archived" },
  { id: "unread", label: "Unread" },
  { id: "open", label: "Open" },
  { id: "pending", label: "Pending" },
  { id: "resolved", label: "Resolved" },
  { id: "GST", label: "GST" },
  { id: "TDS", label: "TDS" },
  { id: "DSC", label: "DSC" },
  { id: "ITR", label: "ITR" },
  { id: "Misc", label: "Misc" },
] as const;
export type ConversationFilter = (typeof FILTERS)[number]["id"];

export type MuteDuration = "8h" | "1w" | "always";

export type MessageDirection = "inbound" | "outbound";
export type DeliveryState = "sent" | "delivered" | "read" | "failed" | "not_sent";
export type MessageKind =
  | "text"
  | "image"
  | "document"
  | "audio"
  | "video"
  | "template"
  | "location"
  | "contact"
  | "unknown";

export type MessageAttachment = {
  id: string;
  kind: Exclude<MessageKind, "text" | "template" | "location" | "contact" | "unknown"> | "document";
  filename: string;
  mediaId: string | null;
  mimeType: string | null;
};

/** Click-to-WhatsApp / Facebook ad referral (first inbound message only). */
export type MessageReferral = {
  sourceType: string | null;
  sourceId: string | null;
  sourceUrl: string | null;
  headline: string | null;
  body: string | null;
  mediaType: string | null;
  imageUrl: string | null;
  videoUrl: string | null;
  thumbnailUrl: string | null;
  ctwaClid: string | null;
};

export type Message = {
  id: string;
  direction: MessageDirection;
  body: string;
  at: string;
  delivery: DeliveryState | null;
  /** Graph / Meta failure detail when delivery is failed. */
  deliveryError?: string | null;
  kind?: MessageKind;
  attachments?: MessageAttachment[];
  referral?: MessageReferral | null;
};

export type ActivityEntry = {
  id: string;
  at: string;
  label: string;
};

export type ConversationSummary = {
  id: string;
  name: string;
  phone: string;
  status: ConversationStatus;
  labels: Label[];
  assignee: string;
  unreadCount: number;
  lastMessage: string;
  lastMessageAt: string;
  lastDirection: MessageDirection;
  /** CRM-uploaded contact photo (WhatsApp Cloud API does not provide peer avatars). */
  avatarUrl?: string | null;
  sample?: boolean;
  archived?: boolean;
  pinned?: boolean;
  /** ISO timestamp, "always", or null/undefined when not muted. */
  mutedUntil?: string | null;
  favourite?: boolean;
  /** When true, outbound send is blocked and new inbound messages are dropped. */
  blocked?: boolean;
};

export type ConversationDetail = ConversationSummary & {
  notes: string;
  messages: Message[];
  activity: ActivityEntry[];
};

export type CredentialFlag = {
  env: string;
  configured: boolean;
  preview: string | null;
};

export type CredentialKey =
  | "businessAccountId"
  | "phoneNumberId"
  | "displayPhone"
  | "appId"
  | "accessToken"
  | "verifyToken"
  | "appSecret"
  | "webhookUrl"
  | "businessId"
  | "graphApiVersion";

export type IntegrationCheck = {
  id: "phoneVerified" | "businessVerified" | "wabaAccessible" | "phoneOnWaba" | "webhookSubscribed" | "messageSending";
  label: string;
  state: "verified" | "not_verified" | "not_checked";
  badge: string;
  detail: string;
};

export type PublicWhatsAppStatus = {
  connection: "connected" | "not_connected";
  demoMode: boolean;
  integrationEnabled: boolean;
  webhookPath: "/api/whatsapp/webhook";
  productionWebhookUrl: string | null;
  adminConfigured: boolean;
  canEdit: boolean;
  credentials: Record<CredentialKey, CredentialFlag>;
  tokenInvalid: boolean;
  detail: string;
  checks: IntegrationCheck[];
  idsDistinct: boolean | null;
};

export type AdminSessionState = {
  authenticated: boolean;
  adminConfigured: boolean;
  csrfToken: string;
  email?: string | null;
  name?: string | null;
  role?: "admin" | "member" | null;
  avatarUrl?: string | null;
};
