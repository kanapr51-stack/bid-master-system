import { Snapshot } from "@/lib/snapshot";
import { GitCommit } from "lucide-react";

interface CommitTimelineProps {
  snapshot: Snapshot;
  limit?: number;
}

export function CommitTimeline({ snapshot, limit = 8 }: CommitTimelineProps) {
  const commits = snapshot.commits.slice(0, limit);

  return (
    <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          จุดเปลี่ยน (Inflection Points)
        </h2>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {commits.length} commits ล่าสุด
        </span>
      </div>
      <ul className="space-y-4 relative">
        {/* vertical line */}
        <div className="absolute left-[7px] top-2 bottom-2 w-px bg-slate-200 dark:bg-slate-800" />
        {commits.map((c) => {
          const isToday = c.date.slice(0, 10) === new Date().toISOString().slice(0, 10);
          return (
            <li key={c.hash} className="flex gap-4 relative pl-1">
              <div className="relative shrink-0">
                <div
                  className={
                    isToday
                      ? "size-4 rounded-full bg-blue-600 ring-4 ring-blue-100 dark:ring-blue-950 relative z-10"
                      : "size-4 rounded-full bg-slate-300 dark:bg-slate-700 ring-4 ring-white dark:ring-slate-900 relative z-10"
                  }
                />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                  <code className="font-mono font-medium text-slate-700 dark:text-slate-300">
                    {c.hash}
                  </code>
                  <span>·</span>
                  <span>
                    {new Date(c.date).toLocaleString("th-TH", {
                      day: "numeric",
                      month: "short",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  {isToday && (
                    <span className="ml-1 px-2 py-0.5 rounded-full bg-blue-100 dark:bg-blue-950 text-blue-700 dark:text-blue-300 text-[10px] font-medium">
                      วันนี้
                    </span>
                  )}
                </div>
                <p className="mt-1 text-sm text-slate-800 dark:text-slate-200">
                  {c.subject}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
