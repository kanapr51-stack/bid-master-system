import { Snapshot } from "@/lib/snapshot";
import { formatDuration } from "@/lib/utils";
import {
  ArrowDown,
  ArrowUp,
  Briefcase,
  Calendar,
  CheckCircle2,
  Clock,
  GitCommit,
  Inbox,
  Minus,
  Search,
  Shield,
  ShieldAlert,
  Trophy,
  Zap,
  type LucideIcon,
} from "lucide-react";

interface WhatChangedTodayProps {
  snapshot: Snapshot;
}

type ChangeItem = {
  icon: LucideIcon;
  iconColor: string;
  iconBg: string;
  category: string;
  title: string;
  detail?: string;
  delta?: { value: string; trend: "up" | "down" | "flat"; polarity: "good" | "bad" };
  timestamp?: string;
};

function deltaPercent(
  current: number,
  previous: number | null | undefined,
  polarity: "good" | "bad" = "good"
): ChangeItem["delta"] | undefined {
  if (previous == null || previous === 0) return undefined;
  const delta = ((current - previous) / previous) * 100;
  const sign = delta >= 0 ? "+" : "";
  const trend = Math.abs(delta) < 1 ? "flat" : delta > 0 ? "up" : "down";
  return { value: `${sign}${delta.toFixed(0)}%`, trend, polarity };
}

export function WhatChangedToday({ snapshot }: WhatChangedTodayProps) {
  const today = new Date().toISOString().slice(0, 10);
  const todayDaily = snapshot.daily[today];
  const yesterdayKey = Object.keys(snapshot.daily)
    .sort()
    .filter((d) => d < today)
    .pop();
  const yesterday = yesterdayKey ? snapshot.daily[yesterdayKey] : null;

  const changes: ChangeItem[] = [];

  // ── System / Pipeline ─────────────────────────────────
  if (todayDaily) {
    // Pipeline time
    changes.push({
      icon: Clock,
      iconColor: "text-blue-600 dark:text-blue-400",
      iconBg: "bg-blue-50 dark:bg-blue-950/40",
      category: "ระบบ",
      title: `Pipeline รัน ${todayDaily.pipeline_runs} ครั้ง`,
      detail: `รวม ${formatDuration(todayDaily.total_pipeline_sec)} (เฉลี่ย ${formatDuration(
        todayDaily.total_pipeline_sec / Math.max(1, todayDaily.pipeline_runs)
      )}/รอบ)`,
      delta: yesterday
        ? deltaPercent(
            todayDaily.total_pipeline_sec,
            yesterday.total_pipeline_sec,
            "bad"
          )
        : undefined,
    });

    // Scraped raw items
    if (todayDaily.total_raw_scraped > 0) {
      changes.push({
        icon: Search,
        iconColor: "text-indigo-600 dark:text-indigo-400",
        iconBg: "bg-indigo-50 dark:bg-indigo-950/40",
        category: "ดึงข้อมูล",
        title: `Scrape ดึง ${todayDaily.total_raw_scraped.toLocaleString()} รายการ`,
        detail: `กรองแล้วเหลือ ${todayDaily.total_filtered.toLocaleString()} (${(
          (todayDaily.total_filtered / todayDaily.total_raw_scraped) *
          100
        ).toFixed(1)}%)`,
        delta: yesterday
          ? deltaPercent(
              todayDaily.total_raw_scraped,
              yesterday.total_raw_scraped,
              "good"
            )
          : undefined,
      });
    }

    // New jobs
    changes.push({
      icon: todayDaily.total_new_jobs > 0 ? Inbox : Minus,
      iconColor:
        todayDaily.total_new_jobs > 0
          ? "text-emerald-600 dark:text-emerald-400"
          : "text-slate-400 dark:text-slate-500",
      iconBg:
        todayDaily.total_new_jobs > 0
          ? "bg-emerald-50 dark:bg-emerald-950/40"
          : "bg-slate-100 dark:bg-slate-800",
      category: "ข้อมูลใหม่",
      title:
        todayDaily.total_new_jobs > 0
          ? `พบงานใหม่ ${todayDaily.total_new_jobs} ตัว`
          : "ไม่มีงานใหม่วันนี้",
      detail:
        todayDaily.total_new_jobs === 0
          ? "ทุกงาน scrape ได้ตรงกับ seen_ids cache (ปกติ — เพราะหน้าซ้ำกันเยอะ)"
          : "ถูก dedupe และเขียนลง all_jobs แล้ว",
      delta: yesterday
        ? deltaPercent(
            todayDaily.total_new_jobs,
            yesterday.total_new_jobs,
            "good"
          )
        : undefined,
    });

    // Cloudflare hits
    if (todayDaily.cloudflare_hits > 0 || todayDaily.search_timeouts > 0) {
      const severity =
        todayDaily.cloudflare_hits > 200
          ? "อันตราย"
          : todayDaily.cloudflare_hits > 50
          ? "ระวัง"
          : "ปกติ";
      changes.push({
        icon: todayDaily.cloudflare_hits > 50 ? ShieldAlert : Shield,
        iconColor:
          todayDaily.cloudflare_hits > 200
            ? "text-rose-600 dark:text-rose-400"
            : todayDaily.cloudflare_hits > 50
            ? "text-amber-600 dark:text-amber-400"
            : "text-emerald-600 dark:text-emerald-400",
        iconBg:
          todayDaily.cloudflare_hits > 200
            ? "bg-rose-50 dark:bg-rose-950/40"
            : todayDaily.cloudflare_hits > 50
            ? "bg-amber-50 dark:bg-amber-950/40"
            : "bg-emerald-50 dark:bg-emerald-950/40",
        category: "Cloudflare",
        title: `${todayDaily.cloudflare_hits} hits (${severity})`,
        detail: `Search timeouts ${todayDaily.search_timeouts} ครั้ง · ${
          todayDaily.cloudflare_hits < 50
            ? "อยู่ในเกณฑ์ดี"
            : "อาจกระทบ scrape — ดู /scrape page"
        }`,
        delta: yesterday
          ? deltaPercent(
              todayDaily.cloudflare_hits,
              yesterday.cloudflare_hits,
              "bad"
            )
          : undefined,
      });
    }
  } else {
    changes.push({
      icon: Calendar,
      iconColor: "text-slate-400",
      iconBg: "bg-slate-100 dark:bg-slate-800",
      category: "ระบบ",
      title: "Pipeline ยังไม่รันวันนี้",
      detail: "รอตาราง 06:00 หรือรันด้วยมือผ่าน run_pipeline_collect.bat",
    });
  }

  // ── Classifier snapshot ────────────────────────────────
  const cls = todayDaily?.classifier_latest;
  if (cls) {
    const activePipeline =
      (cls.active_bidding ?? 0) + (cls.tor_review ?? 0) + (cls.pending_award ?? 0);
    const yCls = yesterday?.classifier_latest;
    const yActive = yCls
      ? (yCls.active_bidding ?? 0) + (yCls.tor_review ?? 0) + (yCls.pending_award ?? 0)
      : null;

    changes.push({
      icon: Briefcase,
      iconColor: "text-violet-600 dark:text-violet-400",
      iconBg: "bg-violet-50 dark:bg-violet-950/40",
      category: "Active Pipeline",
      title: `${activePipeline} งานในระบบ`,
      detail: `🔵 ${cls.active_bidding ?? 0} active · 🟢 ${cls.tor_review ?? 0} tor · 🟡 ${cls.pending_award ?? 0} pending`,
      delta: yActive != null ? deltaPercent(activePipeline, yActive, "good") : undefined,
    });

    // Awarded change
    if (yCls && (cls.awarded_jobs ?? 0) !== (yCls.awarded_jobs ?? 0)) {
      const diff = (cls.awarded_jobs ?? 0) - (yCls.awarded_jobs ?? 0);
      changes.push({
        icon: Trophy,
        iconColor: "text-amber-600 dark:text-amber-400",
        iconBg: "bg-amber-50 dark:bg-amber-950/40",
        category: "ประกาศผู้ชนะ",
        title: `${diff > 0 ? "+" : ""}${diff} งานประกาศใหม่`,
        detail: `รวมทั้งหมด ${cls.awarded_jobs} งานในชีต awarded_jobs`,
      });
    }

    // Cancelled change
    if (yCls && (cls.cancelled_jobs ?? 0) !== (yCls.cancelled_jobs ?? 0)) {
      const diff = (cls.cancelled_jobs ?? 0) - (yCls.cancelled_jobs ?? 0);
      changes.push({
        icon: Shield,
        iconColor: "text-rose-600 dark:text-rose-400",
        iconBg: "bg-rose-50 dark:bg-rose-950/40",
        category: "ยกเลิก",
        title: `${diff > 0 ? "+" : ""}${diff} งานถูกยกเลิก`,
        detail: `รวมทั้งหมด ${cls.cancelled_jobs} งานในชีต cancelled_jobs`,
      });
    }
  }

  // ── Today's commits (inflection events) ───────────────
  const todayCommits = snapshot.commits.filter((c) => c.date.slice(0, 10) === today);
  if (todayCommits.length > 0) {
    changes.push({
      icon: GitCommit,
      iconColor: "text-fuchsia-600 dark:text-fuchsia-400",
      iconBg: "bg-fuchsia-50 dark:bg-fuchsia-950/40",
      category: "Code",
      title: `${todayCommits.length} commits วันนี้`,
      detail: todayCommits
        .slice(0, 3)
        .map((c) => `\`${c.hash}\` ${c.subject.slice(0, 50)}`)
        .join(" · "),
    });
  }

  // ── LINE / Discord notify ─────────────────────────────
  if (snapshot.runs.length > 0) {
    const latestRun = snapshot.runs
      .filter((r) => r.date === today)
      .sort((a, b) => (a.last_modified || "").localeCompare(b.last_modified || ""))
      .pop();
    if (latestRun) {
      const lineSent = latestRun.line_notify_success ?? 0;
      const discordSent = latestRun.discord_notify_success ?? 0;
      if (lineSent > 0 || discordSent > 0) {
        changes.push({
          icon: CheckCircle2,
          iconColor: "text-emerald-600 dark:text-emerald-400",
          iconBg: "bg-emerald-50 dark:bg-emerald-950/40",
          category: "Notify",
          title: `ส่ง notification สำเร็จ`,
          detail: `LINE ${lineSent} part · Discord ${discordSent} msg`,
        });
      }
    }
  }

  // ── Winners cache (always shown) ──────────────────────
  if (snapshot.winners.total_winners) {
    changes.push({
      icon: Zap,
      iconColor: "text-cyan-600 dark:text-cyan-400",
      iconBg: "bg-cyan-50 dark:bg-cyan-950/40",
      category: "Cache",
      title: `Winners cache: ${snapshot.winners.total_winners.toLocaleString()} รายการ`,
      detail: `${snapshot.winners.unique_tins?.toLocaleString() ?? "?"} TINs unique · ${
        snapshot.winners.unique_jobs?.toLocaleString() ?? "?"
      } งาน unique`,
    });
  }

  return (
    <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            วันนี้มีอะไรเปลี่ยนแปลง
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
            กิจกรรมและ metrics เปรียบเทียบกับเมื่อวาน
          </p>
        </div>
        <span className="text-xs text-slate-500 dark:text-slate-400 px-2 py-1 rounded bg-slate-100 dark:bg-slate-800 font-mono">
          {today}
        </span>
      </div>

      <ul className="space-y-3">
        {changes.length === 0 ? (
          <li className="text-sm text-slate-500 dark:text-slate-400 italic py-8 text-center">
            ยังไม่มีการเปลี่ยนแปลงวันนี้ — pipeline ยังไม่รันรอบเช้า
          </li>
        ) : (
          changes.map((c, i) => {
            const Icon = c.icon;
            const trendColor =
              c.delta?.trend === "flat"
                ? "text-slate-500"
                : c.delta?.polarity === "good"
                ? c.delta?.trend === "up"
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-rose-600 dark:text-rose-400"
                : c.delta?.trend === "up"
                ? "text-rose-600 dark:text-rose-400"
                : "text-emerald-600 dark:text-emerald-400";
            const TrendIcon =
              c.delta?.trend === "up"
                ? ArrowUp
                : c.delta?.trend === "down"
                ? ArrowDown
                : Minus;
            return (
              <li
                key={i}
                className="flex items-start gap-3 pb-3 border-b border-slate-100 dark:border-slate-800 last:border-0 last:pb-0"
              >
                <div className={`${c.iconBg} rounded-lg p-2 shrink-0`}>
                  <Icon className={`size-4 ${c.iconColor}`} strokeWidth={2.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[10px] uppercase tracking-wider font-medium text-slate-500 dark:text-slate-400">
                      {c.category}
                    </span>
                    {c.delta && (
                      <span
                        className={`inline-flex items-center gap-0.5 text-[10px] font-semibold ${trendColor}`}
                      >
                        <TrendIcon className="size-3" strokeWidth={3} />
                        {c.delta.value}
                      </span>
                    )}
                  </div>
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                    {c.title}
                  </p>
                  {c.detail && (
                    <p className="text-xs text-slate-600 dark:text-slate-400 mt-0.5 leading-relaxed">
                      {c.detail}
                    </p>
                  )}
                </div>
              </li>
            );
          })
        )}
      </ul>
    </section>
  );
}
