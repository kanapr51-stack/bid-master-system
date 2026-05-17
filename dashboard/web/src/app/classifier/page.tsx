import { readSnapshot } from "@/lib/snapshot";
import { HeaderBar } from "@/components/HeaderBar";
import { KpiCard } from "@/components/KpiCard";
import { LifecycleStackChart } from "@/components/LifecycleStackChart";
import { ClassifierTrendChart } from "@/components/ClassifierTrendChart";
import {
  Briefcase,
  FileText,
  Hourglass,
  Trophy,
  X,
  Layers,
} from "lucide-react";

export const dynamic = "force-dynamic";

const LIFECYCLE_KEYS = [
  "pre_tor",
  "tor_review",
  "active_bidding",
  "pending_award",
  "awarded_jobs",
  "cancelled_jobs",
] as const;

const LABELS: Record<(typeof LIFECYCLE_KEYS)[number], string> = {
  pre_tor: "Pre-TOR",
  tor_review: "TOR Review",
  active_bidding: "Active Bidding",
  pending_award: "Pending Award",
  awarded_jobs: "Awarded",
  cancelled_jobs: "Cancelled",
};

const SEMANTICS: Record<(typeof LIFECYCLE_KEYS)[number], string> = {
  pre_tor: "ขั้นวางแผน (early radar)",
  tor_review: "รับฟังคำวิจารณ์",
  active_bidding: "ยื่นซองได้ตอนนี้",
  pending_award: "รอประกาศผู้ชนะ",
  awarded_jobs: "รู้ผู้ชนะแล้ว",
  cancelled_jobs: "ยกเลิก",
};

export default async function ClassifierPage() {
  const snapshot = await readSnapshot();
  const dailyDates = Object.keys(snapshot.daily).sort();

  const lifecycleSeries = dailyDates.map((d) => {
    const cls = snapshot.daily[d].classifier_latest || {};
    return {
      date: d,
      pre_tor: cls.pre_tor || 0,
      tor_review: cls.tor_review || 0,
      active_bidding: cls.active_bidding || 0,
      pending_award: cls.pending_award || 0,
      awarded_jobs: cls.awarded_jobs || 0,
      cancelled_jobs: cls.cancelled_jobs || 0,
    };
  });

  const todayKey = dailyDates[dailyDates.length - 1];
  const yestKey = dailyDates[dailyDates.length - 2];
  const today = todayKey ? snapshot.daily[todayKey].classifier_latest || {} : {};
  const yest = yestKey ? snapshot.daily[yestKey].classifier_latest || {} : {};

  return (
    <>
      <HeaderBar generatedAt={snapshot.generated_at} />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            🗂️ Classifier Lifecycle
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            การจัดประเภทงานตาม stepId · 6 sheets · เก็บสถานะล่าสุดของแต่ละวัน
          </p>
        </div>

        <section className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {LIFECYCLE_KEYS.map((k) => {
            const v = today[k] || 0;
            const yv = yest[k] || 0;
            const diff = v - yv;
            return (
              <KpiCard
                key={k}
                label={LABELS[k]}
                value={v.toLocaleString()}
                subtitle={SEMANTICS[k]}
                delta={
                  diff === 0
                    ? undefined
                    : {
                        value: `${diff > 0 ? "+" : ""}${diff}`,
                        trend: diff > 0 ? "up" : "down",
                      }
                }
                trendPolarity={k === "cancelled_jobs" ? "bad" : "good"}
                icon={
                  k === "pre_tor"
                    ? Layers
                    : k === "tor_review"
                    ? FileText
                    : k === "active_bidding"
                    ? Briefcase
                    : k === "pending_award"
                    ? Hourglass
                    : k === "awarded_jobs"
                    ? Trophy
                    : X
                }
                accent={
                  k === "active_bidding"
                    ? "blue"
                    : k === "tor_review"
                    ? "green"
                    : k === "pending_award"
                    ? "yellow"
                    : k === "awarded_jobs"
                    ? "gray"
                    : k === "cancelled_jobs"
                    ? "red"
                    : "purple"
                }
              />
            );
          })}
        </section>

        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Lifecycle Stack (รายวัน)
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              ดูการกระจายของงานในแต่ละ stage ตามเวลา
            </p>
          </div>
          <LifecycleStackChart data={lifecycleSeries} />
        </section>

        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Active Pipeline (ไม่รวม awarded/cancelled)
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              งานที่ยังไม่จบ — Pre-TOR + TOR + Active + Pending
            </p>
          </div>
          <ClassifierTrendChart data={lifecycleSeries} />
        </section>

        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">
            Sheet vs. Classifier (วันนี้)
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
            เปรียบเทียบจำนวนใน Google Sheet กับผลการ classify ครั้งสุดท้าย
          </p>
          <div className="overflow-x-auto -mx-6 px-6">
          <table className="w-full text-sm min-w-[480px]">
            <thead className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <th className="text-left py-2">Sheet</th>
                <th className="text-right py-2">Classifier</th>
                <th className="text-right py-2">Sheet snapshot</th>
                <th className="text-right py-2">Δ</th>
              </tr>
            </thead>
            <tbody>
              {LIFECYCLE_KEYS.map((k) => {
                const cl = today[k] || 0;
                const sh = snapshot.sheet_snapshot[k];
                const diff = sh != null ? cl - sh : null;
                return (
                  <tr key={k} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-medium text-slate-700 dark:text-slate-300">
                      {LABELS[k]}
                    </td>
                    <td className="py-2 text-right tabular-nums text-slate-900 dark:text-slate-100">
                      {cl.toLocaleString()}
                    </td>
                    <td className="py-2 text-right tabular-nums text-slate-500">
                      {sh != null ? sh.toLocaleString() : "—"}
                    </td>
                    <td
                      className={
                        "py-2 text-right tabular-nums font-medium " +
                        (diff == null
                          ? "text-slate-400"
                          : diff === 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-amber-600 dark:text-amber-400")
                      }
                    >
                      {diff == null ? "—" : diff === 0 ? "✓" : diff > 0 ? `+${diff}` : diff}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          </div>
        </section>
      </main>
    </>
  );
}
