"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";

interface LifecycleStackChartProps {
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

const COLORS = {
  pre_tor: "#a78bfa",
  tor_review: "#34d399",
  active_bidding: "#3b82f6",
  pending_award: "#fbbf24",
  awarded_jobs: "#64748b",
  cancelled_jobs: "#f87171",
};

const LABELS = {
  pre_tor: "Pre-TOR",
  tor_review: "TOR Review",
  active_bidding: "Active Bidding",
  pending_award: "Pending Award",
  awarded_jobs: "Awarded",
  cancelled_jobs: "Cancelled",
};

export function LifecycleStackChart({ data }: LifecycleStackChartProps) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={data} margin={{ top: 10, right: 24, bottom: 10, left: 0 }}>
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
        <Legend
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
          formatter={(value) => LABELS[value as keyof typeof LABELS] || value}
        />
        {(Object.keys(COLORS) as Array<keyof typeof COLORS>).map((key) => (
          <Area
            key={key}
            type="monotone"
            dataKey={key}
            stackId="1"
            stroke={COLORS[key]}
            fill={COLORS[key]}
            fillOpacity={0.7}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  );
}
