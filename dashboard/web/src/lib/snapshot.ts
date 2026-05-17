import path from "node:path";
import { readFile } from "node:fs/promises";

export interface ClassifierCounts {
  pre_tor?: number;
  tor_review?: number;
  active_bidding?: number;
  pending_award?: number;
  awarded_jobs?: number;
  cancelled_jobs?: number;
}

export interface KeywordResult {
  keyword: string;
  raw_items: number;
  filtered: number;
  province_skipped: number;
  new: number;
}

export interface PipelineRun {
  date: string;
  filename: string;
  phase: string;
  file_size: number;
  last_modified: string;
  pipeline_durations_sec?: number[];
  total_duration_sec?: number;
  scrape_keywords?: KeywordResult[];
  total_raw?: number;
  total_filtered?: number;
  total_new?: number;
  cloudflare_hits?: number;
  search_timeouts?: number;
  classifier?: ClassifierCounts;
  all_jobs_count?: number;
  line_notify_success?: number;
  discord_notify_success?: number;
}

export interface DailyAggregate {
  date: string;
  total_pipeline_sec: number;
  pipeline_runs: number;
  total_raw_scraped: number;
  total_filtered: number;
  total_new_jobs: number;
  cloudflare_hits: number;
  search_timeouts: number;
  classifier_latest: ClassifierCounts | null;
  phases: string[];
}

export interface Commit {
  hash: string;
  date: string;
  subject: string;
}

export interface InflectionPoint {
  hash: string;
  date: string;
  subject: string;
  before_metrics: DailyAggregate | null;
  current_metrics: DailyAggregate | null;
  after_metrics: DailyAggregate | null;
}

export interface SheetSnapshot {
  fetched_at: string;
  pre_tor?: number | null;
  tor_review?: number | null;
  active_bidding?: number | null;
  pending_award?: number | null;
  awarded_jobs?: number | null;
  cancelled_jobs?: number | null;
  all_jobs?: number | null;
}

export interface KPIs {
  pipeline_duration_today: number;
  pipeline_duration_yesterday: number | null;
  active_jobs: number;
  tor_jobs: number;
  pending_jobs: number;
  awarded_jobs: number;
  cancelled_jobs: number;
  all_jobs_count: number;
  cloudflare_hits_today: number;
  total_winners: number;
}

export interface WinnerStats {
  total_winners?: number;
  unique_tins?: number;
  unique_jobs?: number;
  last_modified?: string;
}

export interface Snapshot {
  generated_at: string;
  version: number;
  kpis: KPIs;
  daily: Record<string, DailyAggregate>;
  runs: PipelineRun[];
  sheet_snapshot: SheetSnapshot;
  winners: WinnerStats;
  commits: Commit[];
  inflections: InflectionPoint[];
}

/**
 * Read snapshot.json from the public/ folder.
 * Server-side only (uses fs).
 */
export async function readSnapshot(): Promise<Snapshot> {
  const publicPath = path.join(process.cwd(), "public", "snapshot.json");
  const text = await readFile(publicPath, "utf-8");
  return JSON.parse(text) as Snapshot;
}
