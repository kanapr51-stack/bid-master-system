import { readSnapshot } from "@/lib/snapshot";
import { formatDuration } from "@/lib/utils";
import { HeaderBar } from "@/components/HeaderBar";
import { CheckCircle2, AlertCircle, Clock, Inbox, Shield } from "lucide-react";

export const dynamic = "force-dynamic";

function phaseBadge(phase: string) {
  const map: Record<string, { label: string; cls: string }> = {
    full: { label: "Full", cls: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300" },
    collect: { label: "Collect", cls: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
    notify: { label: "Notify", cls: "bg-fuchsia-100 text-fuchsia-700 dark:bg-fuchsia-950 dark:text-fuchsia-300" },
    refresh: { label: "Refresh", cls: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
    classify: { label: "Classify", cls: "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300" },
  };
  const item = map[phase] || { label: phase || "?", cls: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300" };
  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium ${item.cls}`}>
      {item.label}
    </span>
  );
}

export default async function HistoryPage() {
  const snapshot = await readSnapshot();
  const runs = [...snapshot.runs].sort(
    (a, b) => (b.last_modified || "").localeCompare(a.last_modified || "")
  );

  // Aggregate by day for headers
  const byDay = new Map<string, typeof runs>();
  for (const r of runs) {
    const k = r.date.slice(0, 10);
    if (!byDay.has(k)) byDay.set(k, []);
    byDay.get(k)!.push(r);
  }
  const days = Array.from(byDay.keys()).sort().reverse();

  return (
    <>
      <HeaderBar generatedAt={snapshot.generated_at} />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            🗄️ Pipeline Run History
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            ประวัติทุกรอบ pipeline ที่รัน — ดูจุดที่ scrape/notify มีปัญหา
          </p>
        </div>

        <div className="text-xs text-slate-500 dark:text-slate-400">
          📂 {runs.length} runs · {days.length} วัน
        </div>

        <div className="space-y-6">
          {days.map((day) => {
            const dayRuns = byDay.get(day)!;
            const dayD = snapshot.daily[day];
            return (
              <section
                key={day}
                className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden"
              >
                <header className="bg-slate-50 dark:bg-slate-800/50 px-5 py-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                  <div className="font-semibold text-slate-900 dark:text-slate-100 tabular-nums">
                    {day}
                  </div>
                  {dayD && (
                    <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400 tabular-nums">
                      <span className="flex items-center gap-1">
                        <Clock className="size-3" />
                        {formatDuration(dayD.total_pipeline_sec)}
                      </span>
                      <span className="flex items-center gap-1">
                        <Inbox className="size-3" />
                        {dayD.total_new_jobs} new
                      </span>
                      <span className="flex items-center gap-1">
                        <Shield className="size-3" />
                        {dayD.cloudflare_hits} CF
                      </span>
                    </div>
                  )}
                </header>
                <table className="w-full text-sm">
                  <thead className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                    <tr className="border-b border-slate-100 dark:border-slate-800">
                      <th className="text-left px-5 py-2">Time</th>
                      <th className="text-left py-2">Phase</th>
                      <th className="text-left py-2">File</th>
                      <th className="text-right py-2">Duration</th>
                      <th className="text-right py-2">Raw</th>
                      <th className="text-right py-2">Filtered</th>
                      <th className="text-right py-2">New</th>
                      <th className="text-right py-2">CF</th>
                      <th className="text-right px-5 py-2">Notify</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dayRuns.map((r) => {
                      const notifyTotal = (r.line_notify_success || 0) + (r.discord_notify_success || 0);
                      return (
                        <tr
                          key={r.filename}
                          className="border-b border-slate-100 dark:border-slate-800 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                        >
                          <td className="px-5 py-2 tabular-nums text-slate-700 dark:text-slate-300">
                            {r.last_modified?.slice(11, 16) || "—"}
                          </td>
                          <td className="py-2">{phaseBadge(r.phase)}</td>
                          <td className="py-2 text-xs font-mono text-slate-500">
                            {r.filename}
                          </td>
                          <td className="py-2 text-right tabular-nums text-slate-700 dark:text-slate-300">
                            {formatDuration(r.total_duration_sec || 0)}
                          </td>
                          <td className="py-2 text-right tabular-nums text-slate-500">
                            {(r.total_raw || 0).toLocaleString()}
                          </td>
                          <td className="py-2 text-right tabular-nums text-slate-500">
                            {(r.total_filtered || 0).toLocaleString()}
                          </td>
                          <td className="py-2 text-right tabular-nums font-semibold text-violet-600 dark:text-violet-400">
                            {(r.total_new || 0).toLocaleString()}
                          </td>
                          <td
                            className={
                              "py-2 text-right tabular-nums " +
                              ((r.cloudflare_hits || 0) > 50
                                ? "text-rose-600 dark:text-rose-400 font-semibold"
                                : "text-slate-500")
                            }
                          >
                            {(r.cloudflare_hits || 0).toLocaleString()}
                          </td>
                          <td className="px-5 py-2 text-right">
                            {notifyTotal > 0 ? (
                              <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400 text-xs font-medium">
                                <CheckCircle2 className="size-3" />
                                {notifyTotal}
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-slate-400 text-xs">
                                <AlertCircle className="size-3" />
                                0
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </section>
            );
          })}
        </div>
      </main>
    </>
  );
}
