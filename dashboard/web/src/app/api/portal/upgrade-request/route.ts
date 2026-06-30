/**
 * POST /api/portal/upgrade-request { tier, billing? } — แจ้งความสนใจอัปเกรดแพ็กเกจ
 * line_user_id มาจาก session; relay ไป engine (แจ้ง admin ทาง Discord) ด้วย X-BMS-Secret
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

  let tier = "", billing = "";
  try {
    const body = await req.json();
    tier = (body.tier ?? "").toString().trim();
    billing = (body.billing ?? "").toString().trim();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  if (!tier) return NextResponse.json({ ok: false, error: "tier required" }, { status: 400 });

  try {
    const r = await fetch(`${BMS_API_URL}/api/portal/upgrade-request`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BMS-Secret": BMS_SECRET },
      body: JSON.stringify({ line_user_id: session.lineUserId, tier, billing }),
      cache: "no-store",
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.ok ? 200 : r.status });
  } catch (e) {
    console.error("[/api/portal/upgrade-request]", e);
    return NextResponse.json({ ok: false, error: "engine unreachable" }, { status: 502 });
  }
}
