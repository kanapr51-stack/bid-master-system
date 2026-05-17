import { readSnapshot } from "@/lib/snapshot";
import { formatNumber, formatDuration } from "@/lib/utils";
import { HeaderBar } from "@/components/HeaderBar";
import { KpiCard } from "@/components/KpiCard";
import { ScrapeMetricsChart } from "@/components/ScrapeMetricsChart";
import { KeywordBreakdown } from "@/components/KeywordBreakdown";
import { RssCatalogCard } from "@/components/RssCatalogCard";
import { CatalogBrowser } from "@/components/CatalogBrowser";
import { Search, ShieldAlert, Clock, Inbox } from "lucide-react";

export const dynamic = "force-dynamic";

export default async function ScrapePage() {
  const snapshot = await readSnapshot();
  const dailyDates = Object.keys(snapshot.daily).sort();

  // Daily series
  const series = dailyDates.map((d) => ({
    date: d,
    raw: snapshot.daily[d].total_raw_scraped || 0,
    filtered: snapshot.daily[d].total_filtered || 0,
    new: snapshot.daily[d].total_new_jobs || 0,
    cloudflare: snapshot.daily[d].cloudflare_hits || 0,
    timeouts: snapshot.daily[d].search_timeouts || 0,
  }));

  const today = dailyDates[dailyDates.length - 1];
  const yest = dailyDates[dailyDates.length - 2];
  const todayD = today ? snapshot.daily[today] : null;
  const yestD = yest ? snapshot.daily[yest] : null;

  // Latest run for keyword breakdown
  const latestRun = [...snapshot.runs]
    .sort((a, b) => (a.last_modified || "").localeCompare(b.last_modified || ""))
    .reverse()
    .find((r) => Array.isArray(r.scrape_keywords) && r.scrape_keywords.length > 0);

  const totalRaw = series.reduce((s, x) => s + x.raw, 0);
  const totalFiltered = series.reduce((s, x) => s + x.filtered, 0);
  const totalNew = series.reduce((s, x) => s + x.new, 0);
  const totalCloudflare = series.reduce((s, x) => s + x.cloudflare, 0);

  const filterRate = totalRaw > 0 ? (totalFiltered / totalRaw) * 100 : 0;
  const newRate = totalFiltered > 0 ? (totalNew / totalFiltered) * 100 : 0;

  return (
    <>
      <HeaderBar generatedAt={snapshot.generated_at} />
      <main className="max-w-7xl mx-auto px-6 py-8 space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
            🕷️ Scrape Monitor
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            สถิติการดึงข้อมูลจาก eGP รวม Cloudflare/timeout · 7 วันย้อนหลัง
          </p>
        </div>

        <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard
            label="Raw items (7d)"
            value={formatNumber(totalRaw)}
            subtitle={`เฉลี่ย ${formatNumber(Math.round(totalRaw / Math.max(1, dailyDates.length)))} /วัน`}
            icon={Search}
            accent="blue"
          />
          <KpiCard
            label="Filtered"
            value={formatNumber(totalFiltered)}
            subtitle={`${filterRate.toFixed(1)}% ของ raw`}
            icon={Inbox}
            accent="green"
          />
          <KpiCard
            label="New jobs"
            value={formatNumber(totalNew)}
            subtitle={`${newRate.toFixed(1)}% ของ filtered`}
            icon={Clock}
            accent="purple"
          />
          <KpiCard
            label="Cloudflare hits"
            value={formatNumber(totalCloudflare)}
            subtitle={
              todayD
                ? `วันนี้ ${todayD.cloudflare_hits} · ${todayD.search_timeouts} timeouts`
                : undefined
            }
            icon={ShieldAlert}
            accent={totalCloudflare > 300 ? "red" : totalCloudflare > 100 ? "yellow" : "green"}
          />
        </section>

        {snapshot.rss_catalog && (
          <RssCatalogCard rss={snapshot.rss_catalog} />
        )}

        {snapshot.rss_catalog?.all_depts && (
          <CatalogBrowser depts={snapshot.rss_catalog.all_depts} />
        )}

        <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
          <div className="mb-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
              Scrape Funnel (รายวัน)
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Raw → Filtered → New · เส้นแดง overlay = Cloudflare hits
            </p>
          </div>
          <ScrapeMetricsChart data={series} />
        </section>

        {latestRun && latestRun.scrape_keywords && (
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                  Keyword Breakdown (รอบล่าสุด)
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  {latestRun.filename} · {latestRun.last_modified?.slice(0, 19)}
                </p>
              </div>
              <span className="text-xs text-slate-500 dark:text-slate-400">
                {latestRun.scrape_keywords.length} keywords · {formatDuration(latestRun.total_duration_sec || 0)}
              </span>
            </div>
            <KeywordBreakdown items={latestRun.scrape_keywords} />
          </section>
        )}

        {yestD && todayD && (
          <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">
              Day-over-Day Delta
            </h2>
            <div className="overflow-x-auto -mx-6 px-6">
            <table className="w-full text-sm min-w-[480px]">
              <thead className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
                <tr className="border-b border-slate-200 dark:border-slate-800">
                  <th className="text-left py-2">Metric</th>
                  <th className="text-right py-2">เมื่อวาน</th>
                  <th className="text-right py-2">วันนี้</th>
                  <th className="text-right py-2">Δ</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { label: "Raw scraped", a: yestD.total_raw_scraped, b: todayD.total_raw_scraped, polarity: "good" as const },
                  { label: "Filtered", a: yestD.total_filtered, b: todayD.total_filtered, polarity: "good" as const },
                  { label: "New jobs", a: yestD.total_new_jobs, b: todayD.total_new_jobs, polarity: "good" as const },
                  { label: "Cloudflare hits", a: yestD.cloudflare_hits, b: todayD.cloudflare_hits, polarity: "bad" as const },
                  { label: "Search timeouts", a: yestD.search_timeouts, b: todayD.search_timeouts, polarity: "bad" as const },
                ].map((r) => {
                  const diff = r.b - r.a;
                  const better =
                    r.polarity === "good" ? diff > 0 : diff < 0;
                  const worse = r.polarity === "good" ? diff < 0 : diff > 0;
                  return (
                    <tr key={r.label} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="py-2 text-slate-700 dark:text-slate-300">{r.label}</td>
                      <td className="py-2 text-right tabular-nums text-slate-500">{r.a.toLocaleString()}</td>
                      <td className="py-2 text-right tabular-nums font-medium text-slate-900 dark:text-slate-100">{r.b.toLocaleString()}</td>
                      <td
                        className={
                          "py-2 text-right tabular-nums font-medium " +
                          (better
                            ? "text-emerald-600 dark:text-emerald-400"
                            : worse
                            ? "text-rose-600 dark:text-rose-400"
                            : "text-slate-500")
                        }
                      >
                        {diff > 0 ? "+" : ""}
                        {diff.toLocaleString()}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            </div>
          </section>
        )}
      </main>
    </>
  );
}
