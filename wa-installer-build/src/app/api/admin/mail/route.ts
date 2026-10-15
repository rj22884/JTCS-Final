import { requireAdmin, requireAdminSession } from "@/lib/admin";
import { ensureRequestTime, json } from "@/lib/http";
import { mailConfigStatus, smtpConnectionStatus, verifyMailConnection } from "@/lib/mail";
import type { NextRequest } from "next/server";

export async function GET(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdminSession(request);
  if (gate.error) return gate.error;
  const status = mailConfigStatus();
  const connection = smtpConnectionStatus();
  return json({
    ok: true,
    configured: status.configured,
    host: status.host,
    port: status.port,
    secure: status.secure,
    from: status.from,
    userSet: status.userSet,
    passSet: status.passSet,
    connection: connection.connection,
    checkedAt: connection.lastCheckedAt,
    detail: connection.detail,
  });
}

export async function POST(request: NextRequest) {
  await ensureRequestTime();
  const gate = requireAdmin(request);
  if (gate.error) return gate.error;
  const result = await verifyMailConnection();
  return json(
    {
      ok: result.ok,
      connection: result.connection,
      checkedAt: result.checkedAt,
      detail: result.detail,
    },
    result.ok ? 200 : 502,
  );
}
