"use client";

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface ClassifierTrendChartProps {
  data: {
    date: string;
    pre_tor: number;
    tor_review: number;
    active_bidding: number;
    pending_award: number;
    awarded_jobs: number;
    cancelled_jobs: number;
  }[];
}

export function ClassifierTrendChart({ data }: ClassifierTrendChartProps) {
  const enriched = data.map((d) => ({
    date: d.date,
    active_total: d.pre_tor + d.tor_review + d.active_bidding + d.pending_award,
    active_bidding: d.active_bidding,
    tor_review: d.tor_review,
    pending_award: d.pending_award,
  }));

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={enriched} margin={{ top: 10, right: 24, bottom: 10, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
        <XAxis
          dataKey="date"
          tickFormatter={(v) => v.slice(5)}
          stroke="#94a3b8"
          fontSize={12}
        />
        <YAxis stroke="#94a3b8" fontSize={12} />
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
        <Line
          type="monotone"
          dataKey="active_total"
          stroke="#0f172a"
          strokeWidth={2.5}
          dot={{ r: 4 }}
          name="Active total"
        />
        <Line
          type="monotone"
          dataKey="active_bidding"
          stroke="#3b82f6"
          strokeWidth={1.5}
          dot={{ r: 3 }}
          name="Active"
        />
        <Line
          type="monotone"
          dataKey="tor_review"
          stroke="#10b981"
          strokeWidth={1.5}
          dot={{ r: 3 }}
          name="TOR"
        />
        <Line
          type="monotone"
          dataKey="pending_award"
          stroke="#f59e0b"
          strokeWidth={1.5}
          dot={{ r: 3 }}
          name="Pending"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
