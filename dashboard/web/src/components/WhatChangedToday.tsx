import { Snapshot } from "@/lib/snapshot";
import { ArrowRight, Plus, RefreshCw, Trophy } from "lucide-react";

interface WhatChangedTodayProps {
  snapshot: Snapshot;
}

export function WhatChangedToday({ snapshot }: WhatChangedTodayProps) {
  const today = new Date().toISOString().slice(0, 10);
  const todayDaily = snapshot.daily[today];
  const yesterdayKey = Object.keys(snapshot.daily)
    .sort()
    .filter((d) => d < today)
    .pop();
  const yesterday = yesterdayKey ? snapshot.daily[yesterdayKey] : null;

  const changes: { icon: typeof Plus; label: string; color: string }[] = [];

  if (todayDaily) {
    if (todayDaily.total_new_jobs > 0) {
      changes.push({
        icon: Plus,
        label: `พบงานใหม่ ${todayDaily.total_new_jobs} ตัว`,
        color: "text-emerald-600 dark:text-emerald-400",
      });
    }

    if (todayDaily.cloudflare_hits > 0) {
      const cmp = yesterday?.cloudflare_hits ?? 0;
      const verdict =
        todayDaily.cloudflare_hits > cmp ? "เพิ่มขึ้น" : "ลดลง";
      changes.push({
        icon: RefreshCw,
        label: `Cloudflare hits ${todayDaily.cloudflare_hits} ครั้ง (${verdict})`,
        color:
          todayDaily.cloudflare_hits > cmp
            ? "text-rose-600 dark:text-rose-400"
            : "text-amber-600 dark:text-amber-400",
      });
    }

    const cls = todayDaily.classifier_latest;
    if (cls) {
      const total =
        (cls.active_bidding ?? 0) +
        (cls.tor_review ?? 0) +
        (cls.pending_award ?? 0);
      changes.push({
        icon: ArrowRight,
        label: `Active pipeline: ${total} งาน (active ${cls.active_bidding ?? 0} + tor ${cls.tor_review ?? 0} + pending ${cls.pending_award ?? 0})`,
        color: "text-blue-600 dark:text-blue-400",
      });
    }
  }

  if (snapshot.winners.total_winners) {
    changes.push({
      icon: Trophy,
      label: `Winners cache: ${snapshot.winners.total_winners} รายการ`,
      color: "text-violet-600 dark:text-violet-400",
    });
  }

  return (
    <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          วันนี้มีอะไรเปลี่ยนแปลง
        </h2>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          {today}
        </span>
      </div>
      <ul className="space-y-3">
        {changes.length === 0 ? (
          <li className="text-sm text-slate-500 dark:text-slate-400 italic">
            ยังไม่มีการเปลี่ยนแปลงวันนี้ — pipeline ยังไม่รันรอบเช้า
          </li>
        ) : (
          changes.map((c, i) => {
            const Icon = c.icon;
            return (
              <li key={i} className="flex items-start gap-3 text-sm">
                <Icon className={`size-4 mt-0.5 shrink-0 ${c.color}`} strokeWidth={2.5} />
                <span className="text-slate-700 dark:text-slate-300">{c.label}</span>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
