/**
 * POST /api/portal/job-calc { pid, my_price, selected_names[], extra_names[] }
 * คำนวณโอกาสชนะเจาะจงคู่แข่ง (โมเดล Gates) ของหน้า /portal/job/[pid] — relay ไป engine
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
  if (!pid) return NextResponse.json({ ok: false, error: "pid required" }, { status: 400 });

  try {
    const r = await fetch(`${BMS_API_URL}/api/portal/job-calc`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BMS-Secret": BMS_SECRET },
      body: JSON.stringify({ ...body, pid, line_user_id: session.lineUserId }),
      cache: "no-store",
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.ok ? 200 : r.status });
  } catch (e) {
    console.error("[/api/portal/job-calc]", e);
    return NextResponse.json({ ok: false, error: "engine unreachable" }, { status: 502 });
  }
}
