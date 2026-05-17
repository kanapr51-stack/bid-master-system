interface FunnelStage {
  label: string;
  value: number;
  color: string;
  description?: string;
}

interface FunnelDiagramProps {
  stages: FunnelStage[];
}

export function FunnelDiagram({ stages }: FunnelDiagramProps) {
  const max = Math.max(1, ...stages.map((s) => s.value));

  return (
    <ol className="space-y-2">
      {stages.map((stage, i) => {
        const widthPct = (stage.value / max) * 100;
        const prev = i > 0 ? stages[i - 1] : null;
        const dropFromPrev =
          prev && prev.value > 0
            ? ((stage.value / prev.value) * 100).toFixed(1)
            : null;
        return (
          <li key={stage.label} className="space-y-1">
            <div className="flex items-baseline justify-between text-sm">
              <span className="font-medium text-slate-800 dark:text-slate-200">
                {stage.label}
              </span>
              <div className="flex items-baseline gap-3">
                <span className="text-base font-bold tabular-nums text-slate-900 dark:text-slate-100">
                  {stage.value.toLocaleString()}
                </span>
                {dropFromPrev != null && (
                  <span className="text-xs text-slate-500 dark:text-slate-400 tabular-nums">
                    ({dropFromPrev}% เหลือจากชั้นบน)
                  </span>
                )}
              </div>
            </div>
            <div className="h-10 bg-slate-100 dark:bg-slate-800 rounded-md overflow-hidden">
              <div
                className="h-full transition-all flex items-center justify-end px-3"
                style={{
                  width: `${Math.max(2, widthPct)}%`,
                  background: `linear-gradient(90deg, ${stage.color}99, ${stage.color})`,
                }}
              />
            </div>
            {stage.description && (
              <p className="text-xs text-slate-500 dark:text-slate-400 pl-1">
                {stage.description}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}
