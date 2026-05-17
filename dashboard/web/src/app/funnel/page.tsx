import { readSnapshot } from "@/lib/snapshot";
import { HeaderBar } from "@/components/HeaderBar";
import { FunnelDiagram } from "@/components/FunnelDiagram";

export const dynamic = "force-dynamic";

export default async function FunnelPage() {
  const snapshot = await readSnapshot();
  const dailyDates = Object.keys(snapshot.daily).sort();

  // Sum across last 7 days
  const totals = dailyDates.reduce(
    (acc, d) => {
      const x = snapshot.daily[d];
      acc.raw += x.total_raw_scraped || 0;
      acc.filtered += x.total_filtered || 0;
      acc.new += x.total_new_jobs || 0;
      return acc;
    },
    { raw: 0, filtered: 0, new: 0 }
  );

  // Today only (last day in series)
  const todayKey = dailyDates[dailyDates.length - 1];
  const todayD = todayKey ? snapshot.daily[todayKey] : null;
  const todayCls = todayD?.classifier_latest || {};

  const todayClassified =
    (todayCls.pre_tor || 0) +
    (todayCls.tor_review || 0) +
    (todayCls.active_bidding || 0) +
    (todayCls.pending_award || 0) +
    (todayCls.awarded_jobs || 0) +
    (todayCls.cancelled_jobs || 0);
  const todayActionable =
    (todayCls.active_bidding || 0) +
    (todayCls.tor_review || 0) +
    (todayCls.pending_award || 0);

  const funnel7d = [
    { label: "Raw scraped", value: totals.raw, color: "#3b82f6", description: "ดึงดิบจาก eGP search" },
    { label: "Filtered (keyword + ภาค)", value: totals.filtered, color: "#10b981", description: "ผ่าน keyword + เป้าหมายภูมิภาค" },
    { label: "New jobs", value: totals.new, color: "#a78bfa", description: "ไม่ซ้ำกับ seen_ids" },
  ];

  const funnelToday = [
    { label: "Raw scraped (วันนี้)", value: todayD?.total_raw_scraped || 0, color: "#3b82f6", description: "" },
    { label: "Filtered", value: todayD?.total_filtered || 0, color: "#10b981", description: "" },
    { label: "New jobs", value: todayD?.total_new_jobs || 0, color: "#a78bfa", description: "" },
    { label: "Classified (ทั้ง sheet)", value: todayClassified, color: "#64748b", description: "all_jobs ที่ผ่าน classifier" },
    { label: "Actionable (active+tor+pending)", value: todayActionable, color: "#f59e0b", description: "งานที่ยังต้องจับตา" },
  ];

  return (
    <>
      <HeaderBar generatedAt={snapshot.generated_at} />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            🪣 Funnel Analysis
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            ดูประสิทธิภาพ pipeline จาก raw scrape → actionable งาน
          </p>
        </div>

        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              7-Day Funnel (รวม)
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              สะท้อนประสิทธิภาพการกรอง keyword + dedupe ในรอบสัปดาห์
            </p>
          </div>
          <FunnelDiagram stages={funnel7d} />
        </section>

        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="mb-6">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Today Funnel (จากดิบไป actionable)
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              ขั้นล่างวัดจาก classifier latest — ไม่ใช่จำนวนงานใหม่วันนี้
            </p>
          </div>
          <FunnelDiagram stages={funnelToday} />
        </section>

        <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
            <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Filter rate (7d)
            </p>
            <p className="mt-2 text-3xl font-bold text-slate-900 dark:text-slate-100">
              {totals.raw > 0 ? ((totals.filtered / totals.raw) * 100).toFixed(1) : "—"}%
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {totals.filtered.toLocaleString()} / {totals.raw.toLocaleString()}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
            <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
              New rate (จาก filtered)
            </p>
            <p className="mt-2 text-3xl font-bold text-slate-900 dark:text-slate-100">
              {totals.filtered > 0 ? ((totals.new / totals.filtered) * 100).toFixed(1) : "—"}%
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {totals.new.toLocaleString()} / {totals.filtered.toLocaleString()}
            </p>
          </div>
          <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
            <p className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Actionable share
            </p>
            <p className="mt-2 text-3xl font-bold text-slate-900 dark:text-slate-100">
              {todayClassified > 0
                ? ((todayActionable / todayClassified) * 100).toFixed(1)
                : "—"}
              %
            </p>
            <p className="text-xs text-slate-500 mt-1">
              {todayActionable.toLocaleString()} / {todayClassified.toLocaleString()}
            </p>
          </div>
        </section>
      </main>
    </>
  );
}
