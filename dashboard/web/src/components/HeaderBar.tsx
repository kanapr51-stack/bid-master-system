import { formatThaiDate } from "@/lib/utils";
import { Activity, Bell } from "lucide-react";

interface HeaderBarProps {
  generatedAt: string;
}

export function HeaderBar({ generatedAt }: HeaderBarProps) {
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
        <div className="max-w-7xl mx-auto px-6 flex gap-1">
          {[
            { href: "/", label: "Overview", active: true },
            { href: "/scrape", label: "Scrape", active: false },
            { href: "/classifier", label: "Classifier", active: false },
            { href: "/funnel", label: "Funnel", active: false },
            { href: "/timeline", label: "Timeline", active: false },
            { href: "/history", label: "History", active: false },
          ].map((item) => (
            <a
              key={item.href}
              href={item.href}
              className={
                item.active
                  ? "px-4 py-3 text-sm font-medium border-b-2 border-blue-600 text-blue-600 dark:text-blue-400"
                  : "px-4 py-3 text-sm font-medium text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-100"
              }
            >
              {item.label}
            </a>
          ))}
        </div>
      </nav>
    </header>
  );
}
