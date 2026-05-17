import { KeywordResult } from "@/lib/snapshot";

interface KeywordBreakdownProps {
  items: KeywordResult[];
}

export function KeywordBreakdown({ items }: KeywordBreakdownProps) {
  const sorted = [...items].sort((a, b) => b.raw_items - a.raw_items);
  const maxRaw = Math.max(1, ...sorted.map((i) => i.raw_items));

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">
          <tr className="border-b border-slate-200 dark:border-slate-800">
            <th className="text-left py-2 pl-1">Keyword</th>
            <th className="text-right py-2">Raw</th>
            <th className="text-right py-2">Filtered</th>
            <th className="text-right py-2">Province skip</th>
            <th className="text-right py-2">New</th>
            <th className="text-left py-2 pl-4 w-1/3">Volume</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((k) => {
            const widthPct = (k.raw_items / maxRaw) * 100;
            return (
              <tr
                key={k.keyword}
                className="border-b border-slate-100 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40"
              >
                <td className="py-2 pl-1 font-medium text-slate-900 dark:text-slate-100">
                  {k.keyword}
                </td>
                <td className="py-2 text-right tabular-nums text-slate-700 dark:text-slate-300">
                  {k.raw_items.toLocaleString()}
                </td>
                <td className="py-2 text-right tabular-nums text-emerald-600 dark:text-emerald-400">
                  {k.filtered.toLocaleString()}
                </td>
                <td className="py-2 text-right tabular-nums text-slate-500">
                  {k.province_skipped.toLocaleString()}
                </td>
                <td className="py-2 text-right tabular-nums font-semibold text-violet-600 dark:text-violet-400">
                  {k.new.toLocaleString()}
                </td>
                <td className="py-2 pl-4">
                  <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500"
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
