import { readSnapshot } from "@/lib/snapshot";
import { formatDuration, formatPercentDelta, formatNumber } from "@/lib/utils";
import { HeaderBar } from "@/components/HeaderBar";
import { KpiCard } from "@/components/KpiCard";
import { Sparkline } from "@/components/Sparkline";
import { WhatChangedToday } from "@/components/WhatChangedToday";
import { CommitTimeline } from "@/components/CommitTimeline";
import { PipelineDurationChart } from "@/components/PipelineDurationChart";
import { LifecycleStackChart } from "@/components/LifecycleStackChart";
import {
  Clock,
  Briefcase,
  FileText,
  Hourglass,
  Trophy,
  ShieldAlert,
} from "lucide-react";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const snapshot = await readSnapshot();
  const { kpis } = snapshot;

  // Build chart series from daily aggregates
  const dailyDates = Object.keys(snapshot.daily).sort();
  const pipelineSeries = dailyDates.map((d) => ({
    date: d,
    minutes: (snapshot.daily[d].total_pipeline_sec || 0) / 60,
    cloudflare: snapshot.daily[d].cloudflare_hits || 0,
  }));

  const cloudflareSparkline = dailyDates.slice(-7).map((d) => ({
    date: d,
    value: snapshot.daily[d].cloudflare_hits || 0,
  }));

  const newJobsSparkline = dailyDates.slice(-7).map((d) => ({
    date: d,
    value: snapshot.daily[d].total_new_jobs || 0,
  }));

  const pipelineDurSparkline = dailyDates.slice(-7).map((d) => ({
    date: d,
    value: (snapshot.daily[d].total_pipeline_sec || 0) / 60,
  }));

  // Lifecycle stack data
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

  // Inflection markers (commits today / yesterday)
  const recentCommits = snapshot.commits
    .filter((c) => {
      const d = new Date(c.date);
      const cutoff = Date.now() - 7 * 24 * 60 * 60 * 1000;
      return d.getTime() > cutoff;
    })
    .slice(0, 5)
    .map((c) => ({
      date: c.date.slice(0, 10),
      label: c.hash,
    }));

  return (
    <>
      <HeaderBar generatedAt={snapshot.generated_at} />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        {/* TL;DR */}
        <section className="rounded-2xl bg-gradient-to-br from-blue-600 to-blue-700 text-white p-6 shadow-lg">
          <p className="text-blue-100 text-xs uppercase tracking-wider font-medium">
            สรุปวันนี้
          </p>
          <h2 className="mt-2 text-2xl font-bold">
            ระบบทำงานปกติ — มี{" "}
            <span className="text-blue-100">{kpis.active_jobs} งาน</span>{" "}
            ใน active bidding และส่ง LINE notify เรียบร้อย
          </h2>
          <p className="mt-2 text-blue-100 text-sm">
            Pipeline เช้านี้ใช้เวลา{" "}
            <strong className="text-white">
              {formatDuration(kpis.pipeline_duration_today)}
            </strong>{" "}
            · Cloudflare hits{" "}
            <strong className="text-white">{kpis.cloudflare_hits_today}</strong>{" "}
            ครั้ง · มี winners cache รวม{" "}
            <strong className="text-white">{kpis.total_winners}</strong> รายการ
          </p>
        </section>

        {/* KPI Grid — 6 cards */}
        <section>
          <h2 className="text-lg font-semibold mb-4 text-slate-900 dark:text-slate-100">
            ตัวชี้วัดหลัก
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="space-y-2">
              <KpiCard
                label="เวลา Pipeline วันนี้"
                value={formatDuration(kpis.pipeline_duration_today)}
                subtitle={
                  kpis.pipeline_duration_yesterday
                    ? `เมื่อวาน: ${formatDuration(kpis.pipeline_duration_yesterday)}`
                    : undefined
                }
                delta={
                  kpis.pipeline_duration_yesterday
                    ? formatPercentDelta(
                        kpis.pipeline_duration_today,
                        kpis.pipeline_duration_yesterday
                      )
                    : undefined
                }
                trendPolarity="bad"
                icon={Clock}
                accent="blue"
              />
              <div className="rounded-xl border border-blue-200 dark:border-blue-900 bg-white dark:bg-slate-900 p-2">
                <Sparkline data={pipelineDurSparkline} color="#3b82f6" height={40} />
              </div>
            </div>

            <KpiCard
              label="Active Jobs"
              value={kpis.active_jobs}
              subtitle="ยื่นซองได้ตอนนี้"
              icon={Briefcase}
              accent="blue"
            />

            <KpiCard
              label="TOR Review"
              value={kpis.tor_jobs}
              subtitle="รับฟังคำวิจารณ์"
              icon={FileText}
              accent="green"
            />

            <KpiCard
              label="Pending Award"
              value={kpis.pending_jobs}
              subtitle="รอประกาศผู้ชนะ"
              icon={Hourglass}
              accent="yellow"
            />

            <KpiCard
              label="Awarded"
              value={formatNumber(kpis.awarded_jobs)}
              subtitle={`รวม winners ${formatNumber(kpis.total_winners)} รายการ`}
              icon={Trophy}
              accent="gray"
            />

            <div className="space-y-2">
              <KpiCard
                label="Cloudflare Hits"
                value={kpis.cloudflare_hits_today}
                subtitle="เจอบล็อก/timeout วันนี้"
                trendPolarity="bad"
                icon={ShieldAlert}
                accent={kpis.cloudflare_hits_today > 100 ? "red" : "yellow"}
              />
              <div className="rounded-xl border border-rose-200 dark:border-rose-900 bg-white dark:bg-slate-900 p-2">
                <Sparkline data={cloudflareSparkline} color="#ef4444" height={40} />
              </div>
            </div>
          </div>
        </section>

        {/* Pipeline Duration Chart */}
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                เวลา Pipeline ตามวัน
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                หน่วย: นาที · ยิ่งต่ำยิ่งดี · เส้นประแดง = commit ที่มี impact
              </p>
            </div>
          </div>
          <PipelineDurationChart data={pipelineSeries} inflections={recentCommits} />
        </section>

        {/* What Changed + Commit Timeline (side by side) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <WhatChangedToday snapshot={snapshot} />
          <CommitTimeline snapshot={snapshot} limit={8} />
        </div>

        {/* Lifecycle Stack */}
        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                Lifecycle Distribution
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                จำนวนงานในแต่ละ stage ตามวัน
              </p>
            </div>
          </div>
          <LifecycleStackChart data={lifecycleSeries} />
        </section>

        {/* Footer note */}
        <footer className="pt-8 pb-12 text-center text-xs text-slate-500 dark:text-slate-400">
          <p>
            Bid Master Dashboard · MVP{" "}
            <span className="text-slate-400">v0.1</span> · Generated:{" "}
            {new Date(snapshot.generated_at).toLocaleString("th-TH")}
          </p>
          <p className="mt-1">
            หน้าอื่นๆ (Scrape / Classifier / Funnel / Timeline / History) — กำลังพัฒนา
          </p>
        </footer>
      </main>
    </>
  );
}
