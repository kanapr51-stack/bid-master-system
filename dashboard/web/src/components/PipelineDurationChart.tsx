"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
} from "recharts";

interface PipelineDurationChartProps {
  data: { date: string; minutes: number; cloudflare: number }[];
  inflections?: { date: string; label: string }[];
}

export function PipelineDurationChart({ data, inflections = [] }: PipelineDurationChartProps) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 10, right: 24, bottom: 10, left: 0 }}>
        <defs>
          <linearGradient id="durGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.4} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="date"
          tickFormatter={(v) => v.slice(5)}
          stroke="#94a3b8"
          fontSize={12}
        />
        <YAxis
          stroke="#94a3b8"
          fontSize={12}
          label={{ value: "นาที", angle: -90, position: "insideLeft", fontSize: 12, fill: "#64748b" }}
        />
        <Tooltip
          contentStyle={{
            background: "rgba(15, 23, 42, 0.95)",
            border: "none",
            borderRadius: 8,
            color: "white",
            fontSize: 12,
          }}
          labelStyle={{ color: "rgba(255,255,255,0.7)" }}
          formatter={(value, name) => {
            const v = typeof value === "number" ? value : Number(value);
            if (name === "minutes") return [`${v.toFixed(1)} นาที`, "เวลา pipeline"];
            return [String(v), "Cloudflare hits"];
          }}
        />
        {inflections.map((inf) => (
          <ReferenceLine
            key={`${inf.date}-${inf.label}`}
            x={inf.date}
            stroke="#ef4444"
            strokeDasharray="3 3"
            label={{
              value: inf.label,
              position: "top",
              fontSize: 10,
              fill: "#ef4444",
            }}
          />
        ))}
        <Area
          type="monotone"
          dataKey="minutes"
          stroke="#3b82f6"
          strokeWidth={2}
          fill="url(#durGradient)"
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
