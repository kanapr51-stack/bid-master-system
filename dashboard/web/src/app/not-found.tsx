import Link from "next/link";
import { Compass } from "lucide-react";

export default function NotFound() {
  return (
    <main className="min-h-screen flex items-center justify-center px-6 py-12 bg-slate-50 dark:bg-slate-950">
      <div className="max-w-lg w-full rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-sm text-center">
        <div className="inline-flex rounded-full bg-blue-50 dark:bg-blue-950/40 p-4 mb-4">
          <Compass className="size-8 text-blue-600 dark:text-blue-400" strokeWidth={2} />
        </div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          ไม่พบหน้านี้
        </h1>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
          URL ที่คุณเข้าอาจสะกดผิด หรือหน้านี้ถูกย้าย
        </p>
        <div className="mt-6 flex justify-center gap-2">
          <Link
            href="/"
            className="inline-flex items-center px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition"
          >
            กลับหน้าแรก
          </Link>
        </div>
        <div className="mt-6 grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
          {[
            { href: "/scrape", label: "Scrape" },
            { href: "/classifier", label: "Classifier" },
            { href: "/funnel", label: "Funnel" },
            { href: "/timeline", label: "Timeline" },
            { href: "/history", label: "History" },
          ].map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="px-3 py-2 bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 rounded-md transition"
            >
              {item.label}
            </Link>
          ))}
        </div>
      </div>
    </main>
  );
}
