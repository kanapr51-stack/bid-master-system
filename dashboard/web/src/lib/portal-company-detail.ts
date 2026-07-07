/**
 * portal-company-detail.ts — ดึงประวัติบริษัทจาก engine สำหรับหน้า /portal/company/[tin] (ธีม Board B)
 * โครง data เดียวกับหน้าบริษัทของ engine (portal_views.company_profile/head_to_head/won_portfolio/area_portfolio)
 */
const BMS_API_URL = process.env.BMS_API_URL ?? "https://api.butler-bms.com";
const BMS_SECRET = process.env.BMS_INTERNAL_SECRET ?? "";

export interface CompanyJob {
  project_id: string;
  name: string;
  is_winner: boolean;
  price: number | null;
  discount: number | null;
}

export interface CompanyYearGroup {
  year: number | null;
  bids: number;
  wins: number;
  jobs: CompanyJob[];
}

export interface CompanyProfile {
  name: string;
  tin: string;
  is_sme: boolean;
  total_bids: number;
  wins: number;
  win_rate: number;
  provinces: string[];
  discount_hist: { lo: number; hi: number | null; count: number }[];
  discount_avg: number | null;
  by_year: CompanyYearGroup[];
}

export interface HeadToHead {
  our_name: string;
  shared: number;
  our_wins: number;
  their_wins: number;
  other: number;
  jobs: {
    project_id: string;
    name: string;
    our_price: number | null;
    their_price: number | null;
    winner_side: "us" | "them" | "other";
  }[];
}

export interface WonTop {
  pid: string;
  name: string;
  price: number;
  group: string;
}

export interface WonPortfolio {
  total: { count: number; value: number };
  groups: Record<"bid" | "specific" | "other", { count: number; value: number }>;
  top_overall: WonTop | null;
  top_bid: WonTop | null;
  top_nonbid: WonTop | null;
  proc: "all" | "bid" | "specific" | "other";
  jobs: { pid: string; name: string; price: number; proc_type: string; group: string; discount: number | null }[];
}

export interface AreaPortfolio {
  label_count: number;
  jobs: CompanyJob[];
}

export interface CompanyDetail {
  profile: CompanyProfile;
  h2h: HeadToHead | null;
  won: WonPortfolio | null;
  area: AreaPortfolio | null;
  area_label: string;
}

export async function getCompanyDetail(
  lineUserId: string,
  tin: string,
  opts: { proc?: string; areaIds?: string; areaLabel?: string } = {},
): Promise<CompanyDetail | null> {
  if (!lineUserId || !tin) return null;
  const qs = new URLSearchParams({ line_user_id: lineUserId, tin });
  if (opts.proc) qs.set("proc", opts.proc);
  if (opts.areaIds) qs.set("area_ids", opts.areaIds);
  if (opts.areaLabel) qs.set("area_label", opts.areaLabel);
  const res = await fetch(`${BMS_API_URL}/api/portal/company-detail?${qs.toString()}`, {
    headers: { "X-BMS-Secret": BMS_SECRET },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`engine GET company-detail failed: ${res.status}`);
  const data = (await res.json()) as { ok: boolean; data?: CompanyDetail };
  return data.ok && data.data ? data.data : null;
}
