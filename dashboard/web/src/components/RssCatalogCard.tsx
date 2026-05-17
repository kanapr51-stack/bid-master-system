"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Radio, Database, Inbox, Activity } from "lucide-react";
import type { RssCatalog } from "@/lib/snapshot";

interface Props {
  rss: RssCatalog;
}

export function RssCatalogCard({ rss }: Props) {
  const total = rss.total_depts ?? 0;
  const active = rss.active_depts ?? 0;
  const empty = rss.empty_depts ?? 0;
  const coverage = rss.coverage_pct ?? 0;
  const activePct = rss.active_pct ?? 0;
  const queue = rss.queue_size ?? 0;
  const totalItems = rss.total_items ?? 0;
  const history = rss.history ?? [];

  // Format for chart — show shorter time labels
  const chartData = history.map((h) => ({
    time: h.at.slice(11, 16),
    fullTime: h.at,
    catalog: h.catalog_size,
    items: h.total_items,
  }));

  // Growth rate (last 2 points)
  let growthRate = 0;
  if (history.length >= 2) {
    const last = history[history.length - 1].catalog_size;
    const prev = history[history.length - 2].catalog_size;
    growthRate = last - prev;
  }

  return (
    <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
      <div className="flex flex-wrap items-start justify-between mb-5 gap-2">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Radio className="size-5 text-blue-600 dark:text-blue-400" />
            RSS Catalog Tracker
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            หน่วยงานที่ค้นพบผ่าน RSS feeds · เป้าหมาย 9,999 deptIds
          </p>
        </div>
        <span className="px-2.5 py-1 rounded-md bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 text-xs font-medium">
          ทุก 30 นาที auto-grow
        </span>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Metric
          icon={Database}
          label="Total catalog"
          value={total.toLocaleString()}
          subtitle={`${coverage.toFixed(1)}% ของ 9,999`}
          color="blue"
        />
        <Metric
          icon={Activity}
          label="Active depts"
          value={active.toLocaleString()}
          subtitle={`${activePct.toFixed(1)}% มี items`}
          color="green"
        />
        <Metric
          icon={Inbox}
          label="Queue pending"
          value={queue.toLocaleString()}
          subtitle="รอ ingest → all_jobs"
          color="yellow"
        />
        <Metric
          icon={Radio}
          label="D0 items / รอบ"
          value={totalItems.toLocaleString()}
          subtitle="active_bidding ปัจจุบัน"
          color="purple"
        />
      </div>

      {/* Coverage progress bar */}
      <div className="mb-6">
        <div className="flex items-baseline justify-between text-xs mb-1.5">
          <span className="text-slate-600 dark:text-slate-400">Coverage progress</span>
          <span className="font-semibold text-slate-800 dark:text-slate-200 tabular-nums">
            {total.toLocaleString()} / 9,999 · {coverage.toFixed(2)}%
          </span>
        </div>
        <div className="h-3 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-blue-500 to-blue-600 transition-all"
            style={{ width: `${Math.min(100, coverage)}%` }}
          />
        </div>
        {coverage < 100 && (
          <p className="text-[11px] text-slate-500 dark:text-slate-500 mt-1.5">
            เหลือ {(9999 - total).toLocaleString()} deptIds · ที่ rate ปัจจุบัน ({growthRate > 0 ? `+${growthRate}/รอบ` : "—"}) → คาดเสร็จ {growthRate > 0 ? Math.ceil((9999 - total) / growthRate / 2) : "—"} ชม.
          </p>
        )}
      </div>

      {/* Growth chart */}
      {chartData.length > 1 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3">
            อัตราการเพิ่มขึ้น (catalog size ตามเวลา · {chartData.length} รอบล่าสุด)
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
              <defs>
                <linearGradient id="catalogGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="time" stroke="#94a3b8" fontSize={11} />
              <YAxis stroke="#94a3b8" fontSize={11} />
              <Tooltip
                contentStyle={{
                  background: "rgba(15, 23, 42, 0.95)",
                  border: "none",
                  borderRadius: 8,
                  color: "white",
                  fontSize: 12,
                }}
                labelStyle={{ color: "rgba(255,255,255,0.7)" }}
                labelFormatter={(_, payload) =>
                  payload?.[0]?.payload?.fullTime ?? ""
                }
              />
              <Area
                type="monotone"
                dataKey="catalog"
                stroke="#3b82f6"
                strokeWidth={2}
                fill="url(#catalogGrad)"
                name="Catalog size"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Top depts */}
      {rss.top_depts && rss.top_depts.length > 0 && (
        <div className="mt-6">
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3">
            Top 10 active depts (ตอนนี้มี D0 announcements)
          </h3>
          <div className="overflow-x-auto -mx-6 px-6">
            <table className="w-full text-sm min-w-[480px]">
              <thead className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="text-left py-2">DeptId</th>
                  <th className="text-right py-2">Items</th>
                  <th className="text-left py-2 pl-4">ตัวอย่าง title</th>
                </tr>
              </thead>
              <tbody>
                {rss.top_depts.map((d) => (
                  <tr
                    key={d.dept_id}
                    className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  >
                    <td className="py-2 font-mono font-medium text-slate-700 dark:text-slate-300">
                      {d.dept_id}
                    </td>
                    <td className="py-2 text-right tabular-nums font-semibold text-blue-600 dark:text-blue-400">
                      {d.item_count}
                    </td>
                    <td className="py-2 pl-4 text-xs text-slate-600 dark:text-slate-400">
                      {d.sample_title || "(no title)"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}

interface MetricProps {
  icon: typeof Database;
  label: string;
  value: string;
  subtitle: string;
  color: "blue" | "green" | "yellow" | "purple";
}

function Metric({ icon: Icon, label, value, subtitle, color }: MetricProps) {
  const colorClasses = {
    blue: "border-blue-200 dark:border-blue-900 bg-blue-50/30 dark:bg-blue-950/20 text-blue-600 dark:text-blue-400",
    green: "border-emerald-200 dark:border-emerald-900 bg-emerald-50/30 dark:bg-emerald-950/20 text-emerald-600 dark:text-emerald-400",
    yellow: "border-amber-200 dark:border-amber-900 bg-amber-50/30 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400",
    purple: "border-violet-200 dark:border-violet-900 bg-violet-50/30 dark:bg-violet-950/20 text-violet-600 dark:text-violet-400",
  };
  return (
    <div className={`rounded-lg border p-3 ${colorClasses[color]}`}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-[10px] uppercase tracking-wide text-slate-600 dark:text-slate-400 font-medium">
            {label}
          </p>
          <p className="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
            {value}
          </p>
          <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
            {subtitle}
          </p>
        </div>
        <Icon className="size-4 shrink-0" strokeWidth={2.5} />
      </div>
    </div>
  );
}
