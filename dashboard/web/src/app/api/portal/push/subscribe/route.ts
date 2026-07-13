/**
 * POST /api/portal/push/subscribe {endpoint, p256dh, auth, user_agent}
 * line_user_id มาจาก session; relay ไป engine ด้วย X-BMS-Secret (ไม่หลุด client)
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

  // ช่วงทดลอง: จำกัดเฉพาะบัญชีใน PUSH_ALLOWLIST (comma-separated line_user_id, ว่าง = เปิดทุกคน)
  const allow = (process.env.PUSH_ALLOWLIST ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  if (allow.length && !allow.includes(session.lineUserId)) {
    return NextResponse.json({ ok: false, error: "not enabled for this account" }, { status: 403 });
  }

  let body: { endpoint?: string; p256dh?: string; auth?: string; user_agent?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, error: "Invalid JSON" }, { status: 400 });
  }
  if (!body.endpoint || !body.p256dh || !body.auth) {
    return NextResponse.json({ ok: false, error: "endpoint + keys required" }, { status: 400 });
  }

  try {
    const r = await fetch(`${BMS_API_URL}/api/portal/push-subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BMS-Secret": BMS_SECRET },
      body: JSON.stringify({
        line_user_id: session.lineUserId,
        endpoint: body.endpoint,
        p256dh: body.p256dh,
        auth: body.auth,
        user_agent: body.user_agent ?? "",
      }),
      cache: "no-store",
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.ok ? 200 : r.status });
  } catch (e) {
    console.error("[/api/portal/push/subscribe]", e);
    return NextResponse.json({ ok: false, error: "engine unreachable" }, { status: 502 });
  }
}
