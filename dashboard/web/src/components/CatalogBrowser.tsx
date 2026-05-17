"use client";

import { useMemo, useState } from "react";
import { Search, Filter, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import type { RssCatalogDept } from "@/lib/snapshot";

interface Props {
  depts: RssCatalogDept[];
}

type FilterMode = "all" | "active" | "empty";

const PAGE_SIZE = 50;

export function CatalogBrowser({ depts }: Props) {
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterMode>("active");
  const [sortBy, setSortBy] = useState<"items" | "id">("items");
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState(false);

  const filtered = useMemo(() => {
    let result = depts;
    if (filter === "active") result = result.filter((d) => d.item_count > 0);
    if (filter === "empty") result = result.filter((d) => d.item_count === 0);

    const q = search.trim().toLowerCase();
    if (q) {
      result = result.filter(
        (d) =>
          d.dept_id.toLowerCase().includes(q) ||
          (d.dept_name ?? "").toLowerCase().includes(q) ||
          d.sample_title.toLowerCase().includes(q),
      );
    }

    return [...result].sort((a, b) => {
      if (sortBy === "items") return b.item_count - a.item_count;
      return a.dept_id.localeCompare(b.dept_id);
    });
  }, [depts, search, filter, sortBy]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visiblePage = Math.min(page, totalPages - 1);
  const pageStart = visiblePage * PAGE_SIZE;
  const pageDepts = filtered.slice(pageStart, pageStart + PAGE_SIZE);

  const filterChip = (mode: FilterMode, label: string, count: number) => {
    const active = filter === mode;
    return (
      <button
        key={mode}
        onClick={() => {
          setFilter(mode);
          setPage(0);
        }}
        className={
          "px-3 py-1 text-xs font-medium rounded-md transition " +
          (active
            ? "bg-blue-600 text-white"
            : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700")
        }
      >
        {label} <span className="opacity-70">({count.toLocaleString()})</span>
      </button>
    );
  };

  const counts = {
    all: depts.length,
    active: depts.filter((d) => d.item_count > 0).length,
    empty: depts.filter((d) => d.item_count === 0).length,
  };

  return (
    <section className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <Filter className="size-5 text-blue-600 dark:text-blue-400" />
            Catalog Browser
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            ค้นหา deptId หรือ keyword ใน title · {depts.length.toLocaleString()} entries ทั้งหมด
          </p>
        </div>
        <button
          onClick={() => setExpanded((e) => !e)}
          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/40 hover:bg-blue-100 dark:hover:bg-blue-950/60 rounded-md transition"
        >
          {expanded ? (
            <>
              ซ่อน <ChevronUp className="size-3" />
            </>
          ) : (
            <>
              เปิดดูทั้งหมด <ChevronDown className="size-3" />
            </>
          )}
        </button>
      </div>

      {expanded && (
        <>
          {/* Search + Filters */}
          <div className="space-y-3 mb-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-slate-400" />
              <input
                type="search"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(0);
                }}
                placeholder="ค้นหา deptId / ชื่อหน่วยงาน / keyword ใน title (เช่น 0703, กรมชลประทาน, นครพนม)"
                className="w-full pl-10 pr-3 py-2 text-sm bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-slate-900 dark:text-slate-100"
              />
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap gap-1.5">
                {filterChip("active", "Active", counts.active)}
                {filterChip("empty", "Empty", counts.empty)}
                {filterChip("all", "All", counts.all)}
              </div>

              <div className="flex items-center gap-2 text-xs">
                <span className="text-slate-500 dark:text-slate-400">Sort:</span>
                <select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as "items" | "id")}
                  className="bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded px-2 py-1 text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  <option value="items">Item count (desc)</option>
                  <option value="id">DeptId (asc)</option>
                </select>
              </div>
            </div>
          </div>

          {/* Result count */}
          <div className="text-xs text-slate-500 dark:text-slate-400 mb-3 flex items-center justify-between">
            <span>
              พบ <span className="font-semibold text-slate-700 dark:text-slate-300">{filtered.length.toLocaleString()}</span>{" "}
              entries{search ? ` ตรงกับ "${search}"` : ""}
            </span>
            {totalPages > 1 && (
              <span className="tabular-nums">
                หน้า {visiblePage + 1} / {totalPages}
              </span>
            )}
          </div>

          {/* Table */}
          {filtered.length === 0 ? (
            <div className="py-12 text-center text-sm text-slate-500 dark:text-slate-400 italic">
              ไม่พบ entries ที่ตรงกับเงื่อนไข
            </div>
          ) : (
            <div className="overflow-x-auto -mx-6 px-6">
              <table className="w-full text-sm min-w-[720px]">
                <thead className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400 sticky top-0">
                  <tr className="border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                    <th className="text-left py-2 w-16">DeptId</th>
                    <th className="text-left py-2 pl-3 min-w-[200px]">ชื่อหน่วยงาน</th>
                    <th className="text-right py-2 w-14">Items</th>
                    <th className="text-left py-2 w-20">pubDate</th>
                    <th className="text-left py-2 pl-4 min-w-[260px]">ตัวอย่าง title</th>
                    <th className="text-right py-2 w-10"></th>
                  </tr>
                </thead>
                <tbody>
                  {pageDepts.map((d) => {
                    const rssUrl = `https://process.gprocurement.go.th/EPROCRssFeedWeb/egpannouncerss.xml?deptId=${d.dept_id}`;
                    return (
                      <tr
                        key={d.dept_id}
                        className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                      >
                        <td className="py-2 font-mono font-medium text-slate-700 dark:text-slate-300">
                          {d.dept_id}
                        </td>
                        <td className="py-2 pl-3 text-sm">
                          {d.dept_name ? (
                            <span className="font-medium text-slate-900 dark:text-slate-100">
                              {d.dept_name}
                            </span>
                          ) : (
                            <span className="text-slate-400 italic text-xs">(ยังไม่ได้ enrich)</span>
                          )}
                        </td>
                        <td className="py-2 text-right tabular-nums">
                          {d.item_count > 0 ? (
                            <span className="font-semibold text-blue-600 dark:text-blue-400">
                              {d.item_count}
                            </span>
                          ) : (
                            <span className="text-slate-400">0</span>
                          )}
                        </td>
                        <td className="py-2 tabular-nums text-xs text-slate-500">
                          {d.pub_date || "—"}
                        </td>
                        <td className="py-2 pl-4 text-xs text-slate-600 dark:text-slate-400">
                          {d.sample_title || (
                            <span className="text-slate-400 italic">(no items)</span>
                          )}
                        </td>
                        <td className="py-2 text-right">
                          <a
                            href={rssUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center justify-center text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition"
                            title="เปิด RSS feed ของ dept นี้"
                          >
                            <ExternalLink className="size-3.5" />
                          </a>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={visiblePage === 0}
                className="px-3 py-1.5 text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-200 dark:hover:bg-slate-700 transition"
              >
                ← ก่อนหน้า
              </button>
              <span className="text-xs text-slate-500 dark:text-slate-400 tabular-nums px-2">
                {visiblePage + 1} / {totalPages}
              </span>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={visiblePage >= totalPages - 1}
                className="px-3 py-1.5 text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-md disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-200 dark:hover:bg-slate-700 transition"
              >
                ถัดไป →
              </button>
            </div>
          )}
        </>
      )}
    </section>
  );
}
