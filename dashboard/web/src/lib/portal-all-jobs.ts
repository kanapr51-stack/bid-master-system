/**
 * portal-all-jobs.ts — งานทั้งหมดที่เคยส่งแจ้งเตือนให้ลูกค้า (การ์ด "งานทั้งหมด" Board B)
 * อ่านจาก engine /api/portal/all-jobs (notification_queue, dedup ต่อ project เอารอบล่าสุด)
 */
const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export type SentJobStage = "bidding" | "prelim" | "won" | "pre" | "cancelled";

export interface SentJob {
  project_id: string;
  name: string;
  province: string;
  budget: number;
  sent_at: string; // ISO — เวลาส่งแจ้งเตือนรอบล่าสุด
  stage: SentJobStage;
  starred: boolean;
}

export interface AllJobs {
  count: number;
  jobs: SentJob[];
}

export async function getAllJobs(lineUserId: string, limit = 500): Promise<AllJobs> {
  if (!lineUserId) return { count: 0, jobs: [] };
  const url = `${BMS_API_URL}/api/portal/all-jobs?line_user_id=${encodeURIComponent(lineUserId)}&limit=${limit}`;
  const res = await fetch(url, { headers: { "X-BMS-Secret": BMS_SECRET }, cache: "no-store" });
  if (!res.ok) throw new Error(`engine GET all-jobs failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; count?: number; jobs?: SentJob[] };
  return { count: data.count ?? 0, jobs: data.jobs ?? [] };
}
