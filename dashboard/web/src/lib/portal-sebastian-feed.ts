/**
 * portal-sebastian-feed.ts — ประวัติแจ้งเตือนสไตล์แชท (แท็บ Sebastian)
 * อ่านจาก engine /api/portal/sebastian-feed (notification_queue + format_notification, เก่า→ใหม่)
 */
import type { SentJobStage } from "./portal-all-jobs";

const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export interface SebastianMessage {
  project_id: string;
  message: string; // ข้อความเต็มหลายบรรทัด เหมือน LINE จริง
  sent_at: string; // ISO
  stage: SentJobStage;
  starred: boolean;
}

export interface SebastianFeed {
  count: number;
  messages: SebastianMessage[];
}

export async function getSebastianFeed(lineUserId: string, limit = 30): Promise<SebastianFeed> {
  if (!lineUserId) return { count: 0, messages: [] };
  const url = `${BMS_API_URL}/api/portal/sebastian-feed?line_user_id=${encodeURIComponent(lineUserId)}&limit=${limit}`;
  const res = await fetch(url, { headers: { "X-BMS-Secret": BMS_SECRET }, cache: "no-store" });
  if (!res.ok) throw new Error(`engine GET sebastian-feed failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; count?: number; messages?: SebastianMessage[] };
  return { count: data.count ?? 0, messages: data.messages ?? [] };
}
