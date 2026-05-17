import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(0)} วินาที`;
  const min = seconds / 60;
  if (min < 60) return `${min.toFixed(1)} นาที`;
  const hr = min / 60;
  return `${hr.toFixed(1)} ชั่วโมง`;
}

export function formatNumber(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toString();
}

export function formatPercentDelta(
  current: number,
  previous: number | null
): { value: string; trend: "up" | "down" | "flat" } {
  if (previous == null || previous === 0) return { value: "—", trend: "flat" };
  const delta = ((current - previous) / previous) * 100;
  const sign = delta >= 0 ? "+" : "";
  return {
    value: `${sign}${delta.toFixed(1)}%`,
    trend: delta > 1 ? "up" : delta < -1 ? "down" : "flat",
  };
}

export function formatThaiDate(iso: string): string {
  const d = new Date(iso);
  const months = [
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
  ];
  return `${d.getDate()} ${months[d.getMonth()]} ${d.getFullYear() + 543}`;
}
