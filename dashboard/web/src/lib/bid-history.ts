/**
 * bid-history.ts — ข้อมูลแท็บ "ประวัติ" จาก engine จริง (SQLite ผ่าน bms_api)
 * N+217: แทนที่ Neon Postgres เดิมที่ไม่เชื่อมกับฐานข้อมูลจริงมานานแล้ว (คนละก้อนข้อมูล
 * ทำให้แท็บนี้ค้างที่ "469 บริษัท จาก 300 งาน" — ดู progress_log) เดิมยิง SQL ตรง;
 * ตอนนี้ยิงผ่าน /api/portal/job-detail, /api/portal/company-detail, /api/portal/company-search
 * แล้ว adapt shape ให้ type เดิมที่ history/_client.tsx ใช้อยู่ไม่ต้องแก้โครง
 */
const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

// ── Types (คงรูปเดิมที่ _client.tsx ใช้อยู่) ─────────────────────────────────────

export interface BidderRow {
  bidder_name: string;
  bidder_tin: string;
  price_proposal: string;
  price_agree: string;
  is_winner: boolean;
  is_sme: boolean;
  is_joint_venture: boolean;
  jv_partners: string;
  result_flag: string;
  consider_desc: string;
}

export interface JobInfo {
  job_id: string;
  title: string;
  department: string;
  budget: string;
  deadline: string;
  province: string;
}

export interface JobBiddersResult {
  job: JobInfo;
  bidders: BidderRow[];
  total: number;
}

export interface CompetitorProfile {
  bidder_tin: string;
  company_name: string;
  total_bids: number;
  total_wins: number;
  win_rate_pct: number;
  is_sme: boolean;
  has_jv: boolean;
  first_seen: string;
  last_seen: string;
  provinces: string[];
  proc_types: string[];
  avg_discount_pct: number | null;
  avg_discount_from_budget_pct: number | null;
  stddev_discount_pct: number | null;
}

export interface RecentJobRow {
  job_id: string;
  title: string;
  department: string;
  province: string;
  publish_date: string;
  budget: string;
  is_winner: boolean;
  price_proposal: string;
  price_agree: string;
}

export interface CompetitorProfileResult {
  profile: CompetitorProfile;
  recent_jobs: RecentJobRow[];
}

// ── Engine payload shapes (ตาม portal_views.job_detail / company_profile) ──────

interface EngineJob {
  project_id: string;
  name: string;
  department?: string;
  province?: string;
  budget: number;
  deadline: string | null;
}

interface EngineBidder {
  name: string;
  tin: string;
  price: number | null;
  agree: number | null;
  is_winner: boolean;
  is_sme: boolean;
}

interface EngineJobDetail {
  job: EngineJob;
  bidders: EngineBidder[];
}

interface EngineYearJob {
  project_id: string;
  name: string;
  is_winner: boolean;
  price: number | null;
  price_agree: number | null;
  province: string;
  budget: number;
}

interface EngineYearGroup {
  year: number | null;
  bids: number;
  wins: number;
  jobs: EngineYearJob[];
}

interface EngineCompanyProfile {
  name: string;
  tin: string;
  is_sme: boolean;
  total_bids: number;
  wins: number;
  win_rate: number;
  provinces: string[];
  discount_avg: number | null;
  discount_stddev: number | null;
  first_seen: string;
  last_seen: string;
  by_year: EngineYearGroup[];
}

function num(n: number | null | undefined): string {
  return n == null ? "" : String(n);
}

function toProfile(p: EngineCompanyProfile): CompetitorProfile {
  return {
    bidder_tin: p.tin,
    company_name: p.name,
    total_bids: p.total_bids,
    total_wins: p.wins,
    win_rate_pct: p.win_rate,
    is_sme: p.is_sme,
    has_jv: false, // engine ไม่มีคอลัมน์ JV ในข้อมูลนี้ (ดู progress_log N+217)
    first_seen: p.first_seen,
    last_seen: p.last_seen,
    provinces: p.provinces ?? [],
    proc_types: [],
    avg_discount_pct: null,
    avg_discount_from_budget_pct: p.discount_avg,
    stddev_discount_pct: p.discount_stddev,
  };
}

function toRecentJobs(byYear: EngineYearGroup[]): RecentJobRow[] {
  const rows: RecentJobRow[] = [];
  for (const g of byYear) {
    for (const j of g.jobs) {
      rows.push({
        job_id: j.project_id,
        title: j.name,
        department: "",
        province: j.province || "",
        publish_date: g.year ? `ปี ${g.year}` : "",
        budget: num(j.budget),
        is_winner: j.is_winner,
        price_proposal: num(j.price),
        price_agree: num(j.price_agree),
      });
    }
  }
  return rows;
}

// ── Queries ───────────────────────────────────────────────────────────────────

export async function queryJobBidders(
  lineUserId: string,
  jobId: string,
): Promise<JobBiddersResult | { error: string }> {
  const qs = new URLSearchParams({ line_user_id: lineUserId, pid: jobId });
  const res = await fetch(`${BMS_API_URL}/api/portal/job-detail?${qs.toString()}`, {
    headers: { "X-BMS-Secret": BMS_SECRET },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`engine GET job-detail failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; data?: EngineJobDetail };
  if (!data.ok || !data.data) return { error: "not_found" };
  const { job, bidders } = data.data;
  return {
    job: {
      job_id: job.project_id,
      title: job.name,
      department: job.department || "",
      budget: num(job.budget),
      deadline: job.deadline || "",
      province: job.province || "",
    },
    bidders: bidders.map((b) => ({
      bidder_name: b.name,
      bidder_tin: b.tin,
      price_proposal: num(b.price),
      price_agree: num(b.agree),
      is_winner: b.is_winner,
      is_sme: b.is_sme,
      is_joint_venture: false,
      jv_partners: "",
      result_flag: "",
      consider_desc: "",
    })),
    total: bidders.length,
  };
}

export async function queryCompetitorProfile(
  lineUserId: string,
  tin: string,
): Promise<CompetitorProfileResult | { error: string }> {
  const qs = new URLSearchParams({ line_user_id: lineUserId, tin });
  const res = await fetch(`${BMS_API_URL}/api/portal/company-detail?${qs.toString()}`, {
    headers: { "X-BMS-Secret": BMS_SECRET },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`engine GET company-detail failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; data?: { profile: EngineCompanyProfile } };
  if (!data.ok || !data.data) return { error: "not_found" };
  const p = data.data.profile;
  return {
    profile: toProfile(p),
    recent_jobs: toRecentJobs(p.by_year),
  };
}

export async function searchCompetitors(query: string): Promise<CompetitorProfile[]> {
  const qs = new URLSearchParams({ query });
  const res = await fetch(`${BMS_API_URL}/api/portal/company-search?${qs.toString()}`, {
    headers: { "X-BMS-Secret": BMS_SECRET },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`engine GET company-search failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; results?: EngineCompanyProfile[] };
  return (data.results ?? []).map(toProfile);
}

export async function searchOwnBids(companyName: string): Promise<{ jobs: RecentJobRow[]; total: number }> {
  const qs = new URLSearchParams({ query: companyName });
  const res = await fetch(`${BMS_API_URL}/api/portal/company-search?${qs.toString()}`, {
    headers: { "X-BMS-Secret": BMS_SECRET },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`engine GET company-search failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; results?: EngineCompanyProfile[] };
  const seen = new Set<string>();
  const jobs: RecentJobRow[] = [];
  for (const p of data.results ?? []) {
    for (const row of toRecentJobs(p.by_year)) {
      if (seen.has(row.job_id)) continue;
      seen.add(row.job_id);
      jobs.push(row);
    }
  }
  jobs.sort((a, b) => (a.job_id < b.job_id ? 1 : -1));
  return { jobs, total: jobs.length };
}
