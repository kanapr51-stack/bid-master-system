/**
 * portal-jobs.ts — ดึงงานที่ลูกค้าติดตามจริงจาก engine (bms_api) สำหรับบอร์ด /portal/world
 */
const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export type JobStage = "won" | "prelim" | "bidding" | "pre" | "cancelled";

export interface TrackedJob {
  project_id: string;
  name: string;
  location: string;
  deadline: string;
  deadline_time: string;
  budget: number;
  pred_lo: number | null;
  pred_hi: number | null;
  winner: string | null;
  winner_price: number | null;
  winner_disc: number | null;
  starred: boolean;
}

export type JobGroups = Record<JobStage, TrackedJob[]>;

const EMPTY: JobGroups = { won: [], prelim: [], bidding: [], pre: [], cancelled: [] };

export async function getPortalJobs(lineUserId: string): Promise<JobGroups> {
  if (!lineUserId) return EMPTY;
  const url = `${BMS_API_URL}/api/portal/jobs?line_user_id=${encodeURIComponent(lineUserId)}`;
  const res = await fetch(url, {
    headers: { "X-BMS-Secret": BMS_SECRET },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`engine GET jobs failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; jobs: JobGroups };
  return data.jobs ?? EMPTY;
}

export interface DiscoverJob {
  project_id: string;
  name: string;
  location: string;
  province: string;
  deadline: string;
  deadline_time: string;
  budget: number;
  matched_keywords: string[];
  stage: "biddable" | "planning";
}

export interface DiscoverGroups {
  biddable: DiscoverJob[];
  planning: DiscoverJob[];
}

const EMPTY_DISCOVER: DiscoverGroups = { biddable: [], planning: [] };

export async function getDiscoverJobs(lineUserId: string): Promise<DiscoverGroups> {
  if (!lineUserId) return EMPTY_DISCOVER;
  const url = `${BMS_API_URL}/api/portal/discover?line_user_id=${encodeURIComponent(lineUserId)}`;
  const res = await fetch(url, { headers: { "X-BMS-Secret": BMS_SECRET }, cache: "no-store" });
  if (!res.ok) throw new Error(`engine GET discover failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; jobs: DiscoverGroups };
  return data.jobs ?? EMPTY_DISCOVER;
}
