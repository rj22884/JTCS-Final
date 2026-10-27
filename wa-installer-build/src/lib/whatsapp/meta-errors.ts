export type GraphCause =
  | "expired_token"
  | "id_mismatch"
  | "wrong_waba"
  | "missing_permission"
  | "unsupported_operation"
  | "not_found"
  | "unknown"
  | "timeout";

export type GraphFailure = {
  tokenInvalid: boolean;
  httpStatus: number | null;
  code: number | null;
  subcode: number | null;
  traceId: string | null;
  cause: GraphCause;
  detail: string;
};

export function accessTokenInvalid(code: number | null, message: string) {
  return code === 190 || /session has been invalidated|error validating access token/i.test(message);
}

export function redactSecrets(message: string, secrets: string[]) {
  let output = message;
  for (const secret of secrets) {
    if (secret.length < 6) continue;
    output = output.split(secret).join("[redacted]");
  }
  return output.replace(/Bearer\s+[^\s"']+/gi, "Bearer [redacted]").replace(/EAA[A-Za-z0-9]+/g, "[token]");
}

export function cleanGraphMessage(message: string) {
  return redactSecrets(message, [])
    .replace(/\b\d{6,}\b/g, "[id]")
    .replace(/\s+/g, " ")
    .trim();
}

function numberField(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function stringField(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : "";
}

export function graphCause(input: { code: number | null; subcode: number | null; message: string }): GraphCause {
  if (accessTokenInvalid(input.code, input.message)) return "expired_token";
  const notFound = /does not exist/i.test(input.message);
  const permission = /missing permissions|does not have permission/i.test(input.message);
  const unsupported = /does not support this operation|unsupported (get|post) request/i.test(input.message);
  const signals = [notFound, permission, unsupported].filter(Boolean).length;
  if (signals > 1) return "unknown";
  if (input.subcode === 33 && signals !== 1) return "unknown";
  if (signals === 1 && permission) return "missing_permission";
  if ((input.code === 10 || input.code === 200) && signals === 0) return "missing_permission";
  if (signals === 1 && unsupported) return "unsupported_operation";
  if (signals === 1 && notFound) return "not_found";
  if (input.code === 100 || input.code === 803 || input.subcode === 33) return "unknown";
  return "unknown";
}

function failureDetail(input: {
  cause: GraphCause;
  httpStatus: number | null;
  code: number | null;
  subcode: number | null;
  traceId: string | null;
  message: string;
}) {
  if (input.cause === "expired_token") {
    return "This access token is no longer valid. In Settings, choose Replace on Access token and save a new system user token.";
  }
  if (input.cause === "timeout") return "Meta did not answer in time.";
  // Free-form session messages outside the 24h customer care window (common on image 5 failures).
  if (
    input.code === 131047 ||
    input.code === 131026 ||
    /re-engagement|outside.*allowed window|24.?hour|customer care window/i.test(input.message)
  ) {
    return (
      "Meta blocked this free-form text: the 24-hour customer care window is closed. " +
      "Ask the customer to message first, or send an approved template from Contacts → Bulk template / Cloud templates. " +
      `Code ${input.code ?? "unknown"}.`
    ).slice(0, 500);
  }
  const parts = [
    "Meta refused this object.",
    input.httpStatus ? `HTTP ${input.httpStatus}.` : "HTTP unknown.",
    `Code ${input.code ?? "unknown"}, subcode ${input.subcode ?? "none"}.`,
    `Cause: ${input.cause}.`,
  ];
  if (input.traceId) parts.push(`Trace ${input.traceId}.`);
  parts.push("This is not an expired token.");
  if (input.message) parts.push(`Meta said: ${input.message}`);
  return parts.join(" ").slice(0, 500);
}

export function summarizeGraphFailure(input: {
  code: number | null;
  subcode: number | null;
  message: string;
  httpStatus?: number | null;
  traceId?: string | null;
  cause?: GraphCause;
}): GraphFailure {
  const message = cleanGraphMessage(input.message);
  const cause = input.cause ?? graphCause({ code: input.code, subcode: input.subcode, message });
  const traceId = input.traceId && /^[A-Za-z0-9_-]{6,80}$/.test(input.traceId) ? input.traceId : null;
  return {
    tokenInvalid: cause === "expired_token",
    httpStatus: input.httpStatus ?? null,
    code: input.code,
    subcode: input.subcode,
    traceId,
    cause,
    detail: failureDetail({
      cause,
      httpStatus: input.httpStatus ?? null,
      code: input.code,
      subcode: input.subcode,
      traceId,
      message,
    }),
  };
}

export function parseGraphError(raw: string, httpStatus: number | null, secrets: string[] = []): GraphFailure {
  const safe = redactSecrets(raw, secrets).slice(0, 1500);
  if (/timeout|aborted/i.test(safe) && !safe.includes("{")) {
    return summarizeGraphFailure({ code: null, subcode: null, message: "", httpStatus, cause: "timeout" });
  }
  let code: number | null = null;
  let subcode: number | null = null;
  let message = "";
  let traceId: string | null = null;
  try {
    const parsed = JSON.parse(safe) as { error?: unknown };
    const error =
      parsed.error && typeof parsed.error === "object" ? (parsed.error as Record<string, unknown>) : (parsed as Record<string, unknown>);
    code = numberField(error.code);
    subcode = numberField(error.error_subcode);
    message = stringField(error.message);
    const trace = stringField(error.fbtrace_id);
    traceId = trace || null;
  } catch {
    code = Number(safe.match(/"code"\s*:\s*(\d+)/)?.[1]);
    subcode = Number(safe.match(/"error_subcode"\s*:\s*(\d+)/)?.[1]);
    const matched = safe.match(/"message"\s*:\s*"((?:\\.|[^"\\])*)"/);
    message = matched ? matched[1].replace(/\\"/g, '"').replace(/\\n/g, " ") : "";
    traceId = safe.match(/"fbtrace_id"\s*:\s*"([^"]+)"/)?.[1] ?? null;
    if (!Number.isFinite(code)) code = null;
    if (!Number.isFinite(subcode)) subcode = null;
  }
  return summarizeGraphFailure({ code, subcode, message, httpStatus, traceId });
}

export function localGraphFailure(cause: GraphCause, detail: string): GraphFailure {
  return {
    tokenInvalid: false,
    httpStatus: null,
    code: null,
    subcode: null,
    traceId: null,
    cause,
    detail,
  };
}
