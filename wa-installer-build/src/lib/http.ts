import "server-only";

import { connection, NextResponse } from "next/server";

export async function ensureRequestTime() {
  await connection();
}

export function json(body: unknown, status = 200) {
  return NextResponse.json(body, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}
