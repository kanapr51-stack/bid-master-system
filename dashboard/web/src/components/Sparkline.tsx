"use client";

import { Line, LineChart, ResponsiveContainer, Tooltip } from "recharts";

interface SparklineProps {
  data: { date: string; value: number }[];
  color?: string;
  height?: number;
}

export function Sparkline({ data, color = "#3b82f6", height = 60 }: SparklineProps) {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-xs text-slate-400"
        style={{ height }}
      >
        ไม่มีข้อมูล
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 4, right: 4, left: 4, bottom: 4 }}>
        <Line
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(15, 23, 42, 0.95)",
            border: "none",
            borderRadius: 6,
            color: "white",
            fontSize: 12,
          }}
          labelStyle={{ color: "rgba(255,255,255,0.7)" }}
          formatter={(value) => {
            const v = typeof value === "number" ? value : Number(value);
            return [v.toLocaleString(), "ค่า"];
          }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
