import { cn } from "@/lib/utils";
import { TrendingUp, TrendingDown, Minus, LucideIcon } from "lucide-react";

interface KpiCardProps {
  label: string;
  value: string | number;
  subtitle?: string;
  delta?: {
    value: string;
    trend: "up" | "down" | "flat";
  };
  /** "good" trend: up=green / down=red; "bad" trend: up=red / down=green (e.g. Cloudflare hits) */
  trendPolarity?: "good" | "bad";
  icon?: LucideIcon;
  accent?: "blue" | "green" | "yellow" | "red" | "purple" | "gray";
}

const accentClasses = {
  blue: "border-blue-200 dark:border-blue-900 bg-blue-50/30 dark:bg-blue-950/20",
  green: "border-emerald-200 dark:border-emerald-900 bg-emerald-50/30 dark:bg-emerald-950/20",
  yellow: "border-amber-200 dark:border-amber-900 bg-amber-50/30 dark:bg-amber-950/20",
  red: "border-rose-200 dark:border-rose-900 bg-rose-50/30 dark:bg-rose-950/20",
  purple: "border-violet-200 dark:border-violet-900 bg-violet-50/30 dark:bg-violet-950/20",
  gray: "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900",
};

const accentIcon = {
  blue: "text-blue-600 dark:text-blue-400",
  green: "text-emerald-600 dark:text-emerald-400",
  yellow: "text-amber-600 dark:text-amber-400",
  red: "text-rose-600 dark:text-rose-400",
  purple: "text-violet-600 dark:text-violet-400",
  gray: "text-slate-600 dark:text-slate-400",
};

export function KpiCard({
  label,
  value,
  subtitle,
  delta,
  trendPolarity = "good",
  icon: Icon,
  accent = "gray",
}: KpiCardProps) {
  const trendColor =
    delta?.trend === "flat"
      ? "text-slate-500"
      : trendPolarity === "good"
      ? delta?.trend === "up"
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-rose-600 dark:text-rose-400"
      : delta?.trend === "up"
      ? "text-rose-600 dark:text-rose-400"
      : "text-emerald-600 dark:text-emerald-400";

  const TrendIcon =
    delta?.trend === "up"
      ? TrendingUp
      : delta?.trend === "down"
      ? TrendingDown
      : Minus;

  return (
    <div
      className={cn(
        "rounded-xl border p-5 shadow-sm transition-all hover:shadow-md",
        accentClasses[accent]
      )}
    >
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-slate-600 dark:text-slate-400">
            {label}
          </p>
          <p className="mt-2 text-3xl font-bold tabular-nums text-slate-900 dark:text-slate-100">
            {value}
          </p>
          {subtitle && (
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {subtitle}
            </p>
          )}
        </div>
        {Icon && (
          <div className={cn("rounded-lg p-2", accentIcon[accent])}>
            <Icon className="size-5" strokeWidth={2} />
          </div>
        )}
      </div>
      {delta && (
        <div className={cn("mt-3 flex items-center gap-1 text-sm font-medium", trendColor)}>
          <TrendIcon className="size-4" strokeWidth={2.5} />
          <span>{delta.value}</span>
          <span className="text-slate-500 dark:text-slate-400 ml-1">vs. เมื่อวาน</span>
        </div>
      )}
    </div>
  );
}
