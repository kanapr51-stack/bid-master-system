/**
 * POST /api/portal/job-note { pid, action, note_id?, entry_date?, note? }
 * โน้ตไทม์ไลน์/ภาพรวมของหน้า /portal/job/[pid] — relay ไป engine ด้วย X-BMS-Secret
 * line_user_id มาจาก session (ไม่หลุด client)
 */
import { NextRequest, NextResponse } from "next/server";
import { parseSessionCookie, COOKIE_NAME } from "@/lib/session";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export async function POST(req: NextRequest) {
  const sessionValue = req.cookies.get(COOKIE_NAME)?.value;
  if (!sessionValue) return NextResponse.json({ ok: false, error: "Unauthorized" }, { status: 401 });
  const session = await parseSessionCookie(sessionValue);
  if (!session) return NextResponse.json({ ok: false, error: "Invalid session" }, { status: 401 });

  let body: Record<string, unknown>;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  const pid = (body.pid ?? "").toString().trim();
  const action = (body.action ?? "").toString().trim();
  if (!pid || !action) return NextResponse.json({ ok: false, error: "pid + action required" }, { status: 400 });

  try {
    const r = await fetch(`${BMS_API_URL}/api/portal/job-note`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BMS-Secret": BMS_SECRET },
      body: JSON.stringify({ ...body, pid, action, line_user_id: session.lineUserId }),
      cache: "no-store",
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.ok ? 200 : r.status });
  } catch (e) {
    console.error("[/api/portal/job-note]", e);
    return NextResponse.json({ ok: false, error: "engine unreachable" }, { status: 502 });
  }
}
