import { NextResponse } from "next/server";
import crypto from "node:crypto";
import { getCustomerByLineId, upsertCustomer } from "@/lib/customers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const LINE_REPLY_API = "https://api.line.me/v2/bot/message/reply";
const LINE_PROFILE_API = "https://api.line.me/v2/bot/profile";

interface LineEvent {
  type: string;
  replyToken?: string;
  source?: { userId?: string; type?: string };
  message?: { type: string; text?: string };
}

interface LineProfile {
  userId: string;
  displayName?: string;
  pictureUrl?: string;
  language?: string;
}

function verifySignature(body: string, signature: string | null, secret: string): boolean {
  if (!signature) return false;
  const expected = crypto.createHmac("sha256", secret).update(body).digest("base64");
  return crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(signature));
}

async function fetchProfile(userId: string, token: string): Promise<LineProfile | null> {
  try {
    const r = await fetch(`${LINE_PROFILE_API}/${userId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!r.ok) return null;
    return (await r.json()) as LineProfile;
  } catch {
    return null;
  }
}

async function replyMessage(replyToken: string, text: string, token: string): Promise<void> {
  await fetch(LINE_REPLY_API, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      replyToken,
      messages: [{ type: "text", text }],
    }),
  });
}

function settingsLink(userId: string): string {
  const base = process.env.VERCEL_DASHBOARD_URL ?? "https://bid-master-dashboard.vercel.app";
  return `${base}/customer/${encodeURIComponent(userId)}`;
}

function welcomeMessage(userId: string, displayName: string): string {
  return [
    `สวัสดีครับ คุณ${displayName} 🎩`,
    `ผมคือ Sebastian — บัตเลอร์ส่วนตัวด้านงานประมูล eGP`,
    ``,
    `🎁 เริ่มต้นใช้ฟรี 14 วัน`,
    ``,
    `กรุณาตั้งค่าจังหวัด/อำเภอที่นี่:`,
    settingsLink(userId),
    ``,
    `เมื่อตั้งค่าเสร็จ ทุกเช้า 06:00 ผมจะส่งสรุปงานประมูลใหม่ที่ตรงกับเงื่อนไขของคุณ`,
  ].join("\n");
}

function settingsMessage(userId: string): string {
  return [
    `ตั้งค่าได้ที่:`,
    settingsLink(userId),
    ``,
    `🤖 พิมพ์ "ช่วย" เพื่อดูคำสั่งทั้งหมด`,
  ].join("\n");
}

function helpMessage(): string {
  return [
    `📖 คำสั่งของ Sebastian`,
    ``,
    `• "ตั้งค่า" — เปิดหน้าตั้งค่าจังหวัด/อำเภอ`,
    `• "สถานะ" — ดูสถานะบัญชีคุณ`,
    `• "ช่วย" — แสดงคำสั่งทั้งหมด`,
    ``,
    `ระบบส่งสรุปงานประมูลทุกเช้า 06:00 น.`,
  ].join("\n");
}

async function statusMessage(userId: string): Promise<string> {
  const customer = await getCustomerByLineId(userId);
  if (!customer) {
    return `ยังไม่ได้ลงทะเบียน\n\nเริ่มที่: ${settingsLink(userId)}`;
  }
  return [
    `📋 สถานะของคุณ`,
    ``,
    `ชื่อ: ${customer.display_name || "(ยังไม่ตั้ง)"}`,
    `จังหวัด: ${customer.จังหวัด || "(ยังไม่ตั้ง)"}`,
    `อำเภอ: ${customer.อำเภอ || "(ทั้งจังหวัด)"}`,
    `สถานะ: ${customer.status}`,
    `หมดอายุ: ${customer.expires_at ? customer.expires_at.slice(0, 10) : "—"}`,
    ``,
    `แก้ไข: ${settingsLink(userId)}`,
  ].join("\n");
}

export async function POST(req: Request) {
  const token = process.env.SEBASTIAN_LINE_TOKEN;
  const secret = process.env.SEBASTIAN_LINE_SECRET;
  if (!token) {
    return NextResponse.json(
      { ok: false, error: "SEBASTIAN_LINE_TOKEN not set" },
      { status: 500 },
    );
  }

  const rawBody = await req.text();

  // Optional signature verification (skip if no secret configured — MVP)
  if (secret) {
    const signature = req.headers.get("x-line-signature");
    if (!verifySignature(rawBody, signature, secret)) {
      console.error("[webhook] signature mismatch");
      return NextResponse.json({ ok: false, error: "invalid signature" }, { status: 401 });
    }
  }

  let payload: { events?: LineEvent[] };
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ ok: false, error: "invalid json" }, { status: 400 });
  }

  const events = payload.events ?? [];
  for (const event of events) {
    const userId = event.source?.userId;
    if (!userId || !event.replyToken) continue;

    try {
      if (event.type === "follow") {
        // New follower — create trial customer + send welcome
        const profile = await fetchProfile(userId, token);
        const displayName = profile?.displayName ?? "ลูกค้า";
        await upsertCustomer({
          line_user_id: userId,
          display_name: displayName,
          status: "trial",
        });
        await replyMessage(event.replyToken, welcomeMessage(userId, displayName), token);
        continue;
      }

      if (event.type === "message" && event.message?.type === "text") {
        const text = (event.message.text ?? "").trim().toLowerCase();
        // Ensure customer exists (handle 'follow' missing case)
        const profile = await fetchProfile(userId, token);
        if (profile && !(await getCustomerByLineId(userId))) {
          await upsertCustomer({
            line_user_id: userId,
            display_name: profile.displayName ?? "ลูกค้า",
            status: "trial",
          });
        }

        let reply: string;
        if (text === "ช่วย" || text === "help" || text === "?") {
          reply = helpMessage();
        } else if (text === "สถานะ" || text === "status") {
          reply = await statusMessage(userId);
        } else if (text === "ตั้งค่า" || text.includes("settings") || text.includes("ลงทะเบียน")) {
          reply = settingsMessage(userId);
        } else {
          // Default — guide to settings
          reply = settingsMessage(userId);
        }

        await replyMessage(event.replyToken, reply, token);
        continue;
      }
    } catch (e) {
      console.error("[webhook event]", e);
    }
  }

  return NextResponse.json({ ok: true });
}

export async function GET() {
  return NextResponse.json({
    ok: true,
    hint: "POST line webhook events here",
    expected_envs: ["SEBASTIAN_LINE_TOKEN", "SEBASTIAN_LINE_SECRET (optional)"],
  });
}
