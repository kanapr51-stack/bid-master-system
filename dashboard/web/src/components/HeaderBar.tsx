"use client";

import { usePathname } from "next/navigation";
import Link from "next/link";
import { formatThaiDate } from "@/lib/utils";
import { Activity, Bell } from "lucide-react";

interface HeaderBarProps {
  generatedAt: string;
}

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/scrape", label: "Scrape" },
  { href: "/classifier", label: "Classifier" },
  { href: "/funnel", label: "Funnel" },
  { href: "/timeline", label: "Timeline" },
  { href: "/history", label: "History" },
];

export function HeaderBar({ generatedAt }: HeaderBarProps) {
  const pathname = usePathname();
  return (
    <header className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 sticky top-0 z-10">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-blue-600 p-2">
            <Activity className="size-5 text-white" strokeWidth={2.5} />
          </div>
          <div>
            <h1 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Bid Master Dashboard
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              ระบบมอนิเตอร์ pipeline งานประมูล eGP
            </p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-xs text-slate-500 dark:text-slate-400">อัปเดตล่าสุด</p>
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">
              {new Date(generatedAt).toLocaleTimeString("th-TH", {
                hour: "2-digit",
                minute: "2-digit",
              })}{" "}
              · {formatThaiDate(generatedAt)}
            </p>
          </div>
          <div className="relative">
            <Bell className="size-5 text-slate-400" />
            <span className="absolute -top-1 -right-1 size-2 rounded-full bg-emerald-500" />
          </div>
        </div>
      </div>
      <nav className="border-t border-slate-200 dark:border-slate-800">
        <div className="max-w-7xl mx-auto px-6 flex gap-1 overflow-x-auto">
          {NAV_ITEMS.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={
                  active
                    ? "px-4 py-3 text-sm font-medium border-b-2 border-blue-600 text-blue-600 dark:text-blue-400 whitespace-nowrap"
                    : "px-4 py-3 text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100 whitespace-nowrap"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
