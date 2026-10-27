/** Pure auth policy helpers (safe to unit-test without SQLite). */

export const SESSION_MS_DEFAULT = 12 * 60 * 60 * 1000;
export const SESSION_MS_REMEMBER = 30 * 24 * 60 * 60 * 1000;
export const OTP_TTL_MS = 10 * 60 * 1000;
export const OTP_RESEND_COOLDOWN_MS = 60 * 1000;
export const LOGIN_WINDOW_MS = 10 * 60 * 1000;
export const LOGIN_MAX_ATTEMPTS = 8;
export const EMAIL_SEND_WINDOW_MS = 15 * 60 * 1000;
export const EMAIL_SEND_MAX = 5;

export function sessionTtlMs(rememberMe: boolean) {
  return rememberMe ? SESSION_MS_REMEMBER : SESSION_MS_DEFAULT;
}

export function isSessionToken(value: string) {
  return /^[a-f0-9]{64}$/.test(value);
}

/** Registration must not reveal whether the email is already registered. */
export function registrationPublicOk() {
  return { ok: true as const };
}

/** Forgot-password / forgot-user-id always look the same to the client. */
export function recoveryPublicOk() {
  return { ok: true as const };
}

export function otpExpired(expiresAt: number, now = Date.now()) {
  return expiresAt <= now;
}

export function resendCooldownMs(lastSendAt: number | null, now = Date.now()) {
  if (lastSendAt == null) return 0;
  const elapsed = now - lastSendAt;
  if (elapsed >= OTP_RESEND_COOLDOWN_MS) return 0;
  return OTP_RESEND_COOLDOWN_MS - elapsed;
}

/** WhatsApp Cloud API cannot deliver custom font/size/color. */
export function composerAppearanceSendable(kind: "fontFamily" | "fontSize" | "textColor") {
  void kind;
  return false;
}
