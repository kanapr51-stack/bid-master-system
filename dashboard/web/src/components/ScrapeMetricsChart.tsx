"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ScrapeMetricsChartProps {
  data: {
    date: string;
    raw: number;
    filtered: number;
    new: number;
    cloudflare: number;
    timeouts: number;
  }[];
}

export function ScrapeMetricsChart({ data }: ScrapeMetricsChartProps) {
  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={data} margin={{ top: 10, right: 24, bottom: 10, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="date"
          tickFormatter={(v) => v.slice(5)}
          stroke="#94a3b8"
          fontSize={12}
        />
        <YAxis
          yAxisId="left"
          stroke="#94a3b8"
          fontSize={12}
          label={{ value: "รายการ", angle: -90, position: "insideLeft", fontSize: 11, fill: "#64748b" }}
        />
        <YAxis
          yAxisId="right"
          orientation="right"
          stroke="#ef4444"
          fontSize={12}
          label={{ value: "CF/Timeout", angle: 90, position: "insideRight", fontSize: 11, fill: "#ef4444" }}
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
        />
        <Legend wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        <Bar yAxisId="left" dataKey="raw" fill="#3b82f6" name="Raw" fillOpacity={0.6} />
        <Bar yAxisId="left" dataKey="filtered" fill="#10b981" name="Filtered" fillOpacity={0.8} />
        <Bar yAxisId="left" dataKey="new" fill="#a78bfa" name="New" />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="cloudflare"
          stroke="#ef4444"
          strokeWidth={2}
          dot={{ r: 3 }}
          name="Cloudflare"
        />
        <Line
          yAxisId="right"
          type="monotone"
          dataKey="timeouts"
          stroke="#f59e0b"
          strokeWidth={2}
          strokeDasharray="4 4"
          dot={{ r: 3 }}
          name="Timeouts"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
