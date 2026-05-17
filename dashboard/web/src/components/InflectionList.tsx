import type { InflectionPoint } from "@/lib/snapshot";
import { ArrowDown, ArrowUp, GitCommit, Minus } from "lucide-react";

interface InflectionListProps {
  inflections: InflectionPoint[];
}

interface MetricRow {
  label: string;
  key: "total_pipeline_sec" | "total_new_jobs" | "cloudflare_hits" | "search_timeouts" | "total_raw_scraped";
  polarity: "good" | "bad";
  format?: (v: number) => string;
}

const METRICS: MetricRow[] = [
  { label: "Pipeline", key: "total_pipeline_sec", polarity: "bad", format: (v) => `${(v / 60).toFixed(1)} นาที` },
  { label: "Raw", key: "total_raw_scraped", polarity: "good" },
  { label: "New", key: "total_new_jobs", polarity: "good" },
  { label: "Cloudflare", key: "cloudflare_hits", polarity: "bad" },
  { label: "Timeouts", key: "search_timeouts", polarity: "bad" },
];

function formatDelta(
  before: number | null | undefined,
  current: number | null | undefined
) {
  if (before == null || current == null) return null;
  const diff = current - before;
  if (diff === 0) return { value: "0", trend: "flat" as const };
  const sign = diff > 0 ? "+" : "";
  return {
    value: `${sign}${diff.toLocaleString(undefined, {
      maximumFractionDigits: 1,
    })}`,
    trend: diff > 0 ? ("up" as const) : ("down" as const),
  };
}

export function InflectionList({ inflections }: InflectionListProps) {
  if (inflections.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 text-center text-sm text-slate-500">
        ยังไม่มี inflection points
      </div>
    );
  }

  return (
    <ol className="space-y-4">
      {inflections.map((inf) => {
        const bf = inf.before_metrics;
        const cu = inf.current_metrics;
        return (
          <li
            key={inf.hash}
            className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 shadow-sm hover:shadow-md transition"
          >
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-fuchsia-50 dark:bg-fuchsia-950/40 p-2 shrink-0">
                <GitCommit className="size-4 text-fuchsia-600 dark:text-fuchsia-400" strokeWidth={2.5} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <code className="font-mono font-semibold text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">
                    {inf.hash}
                  </code>
                  <span className="text-slate-500">·</span>
                  <span className="text-slate-500 tabular-nums">
                    {new Date(inf.date).toLocaleString("th-TH", {
                      year: "numeric",
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
                <p className="mt-1 text-sm font-medium text-slate-900 dark:text-slate-100">
                  {inf.subject}
                </p>

                {bf && cu && (
                  <div className="mt-3 grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
                    {METRICS.map((m) => {
                      const a = bf[m.key] as number | undefined;
                      const b = cu[m.key] as number | undefined;
                      const delta = formatDelta(a, b);
                      const trendIcon =
                        delta?.trend === "up" ? ArrowUp : delta?.trend === "down" ? ArrowDown : Minus;
                      const TrendIcon = trendIcon;
                      const better =
                        m.polarity === "good"
                          ? delta?.trend === "up"
                          : delta?.trend === "down";
                      const worse =
                        m.polarity === "good"
                          ? delta?.trend === "down"
                          : delta?.trend === "up";
                      const color =
                        delta?.trend === "flat" || delta == null
                          ? "text-slate-500"
                          : better
                          ? "text-emerald-600 dark:text-emerald-400"
                          : worse
                          ? "text-rose-600 dark:text-rose-400"
                          : "text-slate-500";

                      return (
                        <div
                          key={m.key}
                          className="rounded-md bg-slate-50 dark:bg-slate-800/50 px-2 py-1.5"
                        >
                          <p className="text-[10px] uppercase tracking-wide text-slate-500">
                            {m.label}
                          </p>
                          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 tabular-nums">
                            {m.format
                              ? m.format(b ?? 0)
                              : (b ?? 0).toLocaleString()}
                          </p>
                          {delta && (
                            <p className={`text-[10px] font-semibold flex items-center gap-0.5 ${color}`}>
                              <TrendIcon className="size-3" strokeWidth={3} />
                              {m.format ? m.format(Math.abs((b ?? 0) - (a ?? 0))) : delta.value}
                            </p>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}

                {(!bf || !cu) && (
                  <p className="mt-2 text-xs text-slate-500 italic">
                    ไม่มี metrics ก่อน/หลังที่จะเปรียบเทียบ (commit อยู่นอกช่วงเวลาที่บันทึก)
                  </p>
                )}
              </div>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
