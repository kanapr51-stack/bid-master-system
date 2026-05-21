/**
 * bid-history.ts — Server-side DB queries for bid_history and competitor_profiles
 * Uses @neondatabase/serverless to query Neon PostgreSQL directly from Next.js
 */
import { neon } from '@neondatabase/serverless';

function getDb() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error('DATABASE_URL not set');
  return neon(url);
}

// ── Types ─────────────────────────────────────────────────────────────────────

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
}

export interface RecentJobRow {
  job_id: string;
  title: string;
  department: string;
  province: string;
  publish_date: string;
  is_winner: boolean;
  price_proposal: string;
  price_agree: string;
}

export interface CompetitorProfileResult {
  profile: CompetitorProfile;
  recent_jobs: RecentJobRow[];
}

// ── Queries ───────────────────────────────────────────────────────────────────

export async function queryJobBidders(jobId: string): Promise<JobBiddersResult | { error: string }> {
  const db = getDb();
  const [jobRows, bidderRows] = await Promise.all([
    db`SELECT job_id, title, department, budget, deadline, province
       FROM all_jobs WHERE job_id = ${jobId}`,
    db`SELECT bidder_name, bidder_tin, price_proposal, price_agree,
              is_winner, is_sme, is_joint_venture, jv_partners, result_flag, consider_desc
       FROM bid_history
       WHERE job_id = ${jobId}
       ORDER BY is_winner DESC, price_agree`,
  ]);

  if (!jobRows.length) return { error: 'not_found' };
  return {
    job: jobRows[0] as JobInfo,
    bidders: bidderRows as BidderRow[],
    total: bidderRows.length,
  };
}

export async function queryCompetitorProfile(tin: string): Promise<CompetitorProfileResult | { error: string }> {
  const db = getDb();
  const [profileRows, recentRows] = await Promise.all([
    db`SELECT bidder_tin, company_name, total_bids, total_wins, win_rate_pct,
              is_sme, has_jv, first_seen, last_seen, provinces, proc_types, avg_discount_pct
       FROM competitor_profiles WHERE bidder_tin = ${tin}`,
    db`SELECT bh.job_id, aj.title, aj.department, aj.province, aj.publish_date,
              bh.is_winner, bh.price_proposal, bh.price_agree
       FROM bid_history bh
       JOIN all_jobs aj ON aj.job_id = bh.job_id
       WHERE bh.bidder_tin = ${tin}
       ORDER BY aj.publish_date DESC
       LIMIT 20`,
  ]);

  if (!profileRows.length) return { error: 'not_found' };
  const p = profileRows[0] as CompetitorProfile;
  p.provinces = Array.isArray(p.provinces) ? p.provinces : [];
  p.proc_types = Array.isArray(p.proc_types) ? p.proc_types : [];
  return {
    profile: p,
    recent_jobs: recentRows as RecentJobRow[],
  };
}

export async function searchCompetitors(query: string): Promise<CompetitorProfile[]> {
  const db = getDb();
  const rows = await db`
    SELECT bidder_tin, company_name, total_bids, total_wins, win_rate_pct,
           is_sme, provinces, first_seen, last_seen
    FROM competitor_profiles
    WHERE company_name ILIKE ${'%' + query + '%'}
    ORDER BY total_bids DESC
    LIMIT 20
  `;
  return rows.map(r => {
    const d = r as CompetitorProfile;
    d.provinces = Array.isArray(d.provinces) ? d.provinces : [];
    d.proc_types = Array.isArray(d.proc_types) ? d.proc_types : [];
    return d;
  });
}
