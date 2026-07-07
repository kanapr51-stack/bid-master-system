/**
 * portal-job-detail.ts — ดึงรายละเอียดงานจาก engine สำหรับหน้า /portal/job/[pid] (ธีม Board B)
 * โครง data เดียวกับหน้า detail ของ engine (portal_views.job_detail) + notes/overview/starred
 */
const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export interface JobNote {
  id: number;
  entry_date: string;
  note: string;
}

export interface JobBidder {
  name: string;
  tin: string;
  price: number | null;
  agree: number | null;
  is_winner: boolean;
  is_sme: boolean;
  discount: number | null;
  href?: string; // หน้าบริษัทธีม B — relative /portal/company/<tin> (engine mint, N+188)
}

export interface CompanyRow {
  name: string;
  tin?: string | null;
  median?: number | null;
  games: number;
  href?: string;
}

export interface CompanyTable {
  label: string;
  n: number;
  conf_tag: string;
  companies: CompanyRow[];
}

export interface WinrateTable {
  ns: number[];
  rows: [number, number[]][]; // [ราคายื่น, โอกาส% ต่อจำนวนผู้ยื่น]
  budget: number;
  n_mean: number;
  n_sd: number;
  n_auctions: number;
  n_bids: number;
  conf?: [string, string] | null; // [emoji, คำอธิบาย scope]
}

export interface CalcBreakdown {
  name: string;
  source?: string;
  win_pct_against: number;
}

export interface CustomCalc {
  overall_win_pct: number;
  my_discount_pct: number;
  breakdown: CalcBreakdown[];
}

export interface JobDetail {
  job: {
    project_id: string;
    name: string;
    location: string;
    budget: number;
    deadline: string | null;
    deadline_time: string | null;
    pred_lo: number | null;
    pred_hi: number | null;
  };
  bidders: JobBidder[];
  company_tables?: CompanyTable[] | null;
  winrate_table?: WinrateTable | null;
  notes: JobNote[];
  overview: string;
  starred: boolean;
}

export async function getJobDetail(lineUserId: string, pid: string): Promise<JobDetail | null> {
  if (!lineUserId || !pid) return null;
  const url = `${BMS_API_URL}/api/portal/job-detail?line_user_id=${encodeURIComponent(lineUserId)}&pid=${encodeURIComponent(pid)}`;
  const res = await fetch(url, { headers: { "X-BMS-Secret": BMS_SECRET }, cache: "no-store" });
  if (!res.ok) throw new Error(`engine GET job-detail failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; data?: JobDetail };
  return data.ok && data.data ? data.data : null;
}
