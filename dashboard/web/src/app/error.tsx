"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorPage({ error, reset }: ErrorPageProps) {
  useEffect(() => {
    console.error("[dashboard] page error:", error);
  }, [error]);

  return (
    <main className="min-h-screen flex items-center justify-center px-6 py-12 bg-slate-50 dark:bg-slate-950">
      <div className="max-w-lg w-full rounded-xl border border-rose-200 dark:border-rose-900 bg-white dark:bg-slate-900 p-8 shadow-sm">
        <div className="flex items-start gap-4">
          <div className="rounded-lg bg-rose-50 dark:bg-rose-950/40 p-3 shrink-0">
            <AlertTriangle
              className="size-6 text-rose-600 dark:text-rose-400"
              strokeWidth={2}
            />
          </div>
          <div className="flex-1 min-w-0">
            <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
              เกิดข้อผิดพลาดในการโหลดหน้า
            </h1>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
              อาจเป็นเพราะ snapshot.json ยังไม่ถูก generate หรือ Vercel Blob เข้าถึงไม่ได้
            </p>
            {error.digest && (
              <p className="mt-3 text-xs text-slate-500 dark:text-slate-500 font-mono bg-slate-50 dark:bg-slate-800 rounded px-2 py-1 inline-block">
                error digest: {error.digest}
              </p>
            )}
            {error.message && (
              <details className="mt-3">
                <summary className="text-xs text-slate-500 dark:text-slate-400 cursor-pointer hover:text-slate-700 dark:hover:text-slate-300">
                  รายละเอียดสำหรับ debug
                </summary>
                <pre className="mt-2 text-xs text-slate-600 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded p-3 overflow-x-auto whitespace-pre-wrap break-all">
                  {error.message}
                </pre>
              </details>
            )}
            <div className="mt-6 flex gap-2">
              <button
                onClick={reset}
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-lg transition"
              >
                <RefreshCw className="size-4" strokeWidth={2.5} />
                ลองใหม่
              </button>
              <a
                href="/"
                className="inline-flex items-center px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-sm font-medium rounded-lg transition"
              >
                กลับหน้าแรก
              </a>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
