"use client";

import Link from "next/link";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  Tooltip,
} from "recharts";
import { KpiCard } from "@/components/kpi-card";
import {
  MomentumBadge,
  PipelinePill,
  VerdictBadge,
} from "@/components/badges";
import {
  startups,
  recentActivity,
  pipelineTrend,
  ALL_PIPELINE_STAGES,
} from "@/lib/mock-data";
import { relativeTime } from "@/lib/utils";
import { ChevronDown } from "lucide-react";

export default function DashboardPage() {
  const totalDeals = startups.length;
  const invested = startups.filter((s) => s.verdict === "invested").length;
  const accelerating = startups.filter(
    (s) => s.momentum === "accelerating",
  ).length;
  const needsFollowUp = startups.filter(
    (s) => s.pipeline_stage !== "Decision",
  ).length;

  // Pipeline funnel counts
  const funnel = ALL_PIPELINE_STAGES.map((stage) => ({
    stage,
    count: startups.filter((s) => s.pipeline_stage === stage).length,
  }));
  const funnelMax = Math.max(...funnel.map((f) => f.count), 1);

  // Momentum split
  const momentumSplit: Array<{
    label: string;
    count: number;
    color: string;
  }> = [
    {
      label: "Accelerating",
      count: startups.filter((s) => s.momentum === "accelerating").length,
      color: "bg-accent-green",
    },
    {
      label: "Stable",
      count: startups.filter((s) => s.momentum === "stable").length,
      color: "bg-ink/70",
    },
    {
      label: "Stalling",
      count: startups.filter((s) => s.momentum === "stalling").length,
      color: "bg-accent-amber",
    },
    {
      label: "Dead",
      count: startups.filter((s) => s.momentum === "dead").length,
      color: "bg-accent-red",
    },
  ];
  const momentumTotal = momentumSplit.reduce((a, b) => a + b.count, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs text-ink-muted">Overview</div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">
            Dashboard
          </h1>
        </div>
        <button className="btn-outline">
          Last 30 days <ChevronDown size={14} />
        </button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Total deals tracked"
          value={String(totalDeals)}
          delta={{ value: "+12%", positive: true }}
          hint="vs. previous period"
        />
        <KpiCard
          label="Invested this period"
          value={String(invested)}
          delta={{ value: "+1", positive: true }}
          hint="1 closed, 0 pending"
        />
        <KpiCard
          label="Accelerating"
          value={String(accelerating)}
          delta={{ value: "+25%", positive: true }}
          hint="of tracked deals"
        />
        <KpiCard
          label="Needs follow-up"
          value={String(needsFollowUp)}
          delta={{ value: "-8%", positive: false }}
          hint="open next-steps"
        />
      </div>

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Pipeline trend chart */}
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs text-ink-muted">Pipeline growth</div>
              <div className="mt-1 flex items-baseline gap-2">
                <div className="text-2xl font-semibold tracking-tight">
                  {totalDeals} deals
                </div>
                <span className="pill bg-accent-green/60 text-accent-greenInk">
                  ↑ 12%
                </span>
              </div>
            </div>
            <div className="text-xs text-ink-faint">Last 6 months</div>
          </div>

          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={pipelineTrend}
                margin={{ top: 10, right: 0, left: 0, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0A0A0A" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#0A0A0A" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="month"
                  stroke="#9CA3AF"
                  fontSize={11}
                  tickLine={false}
                  axisLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "#fff",
                    border: "1px solid #E7E7E2",
                    borderRadius: 12,
                    fontSize: 12,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="#0A0A0A"
                  strokeWidth={2}
                  fill="url(#g1)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Momentum split */}
        <div className="card p-5">
          <div className="text-xs text-ink-muted">Deal momentum</div>
          <div className="mt-1 text-2xl font-semibold tracking-tight">
            {momentumTotal}
            <span className="text-sm text-ink-muted font-normal ml-1">
              active
            </span>
          </div>

          {/* Stacked bar */}
          <div className="mt-5 flex h-2.5 w-full rounded-full overflow-hidden">
            {momentumSplit.map((m) => (
              <div
                key={m.label}
                className={m.color}
                style={{
                  width: `${(m.count / Math.max(momentumTotal, 1)) * 100}%`,
                }}
              />
            ))}
          </div>

          <div className="mt-5 space-y-2.5">
            {momentumSplit.map((m) => (
              <div
                key={m.label}
                className="flex items-center justify-between text-sm"
              >
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${m.color}`} />
                  <span className="text-ink">{m.label}</span>
                </div>
                <span className="text-ink-muted">{m.count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Pipeline funnel + activity */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Funnel */}
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs text-ink-muted">Pipeline funnel</div>
              <div className="mt-1 text-lg font-semibold">
                Deals by stage
              </div>
            </div>
          </div>
          <div className="mt-5 space-y-3">
            {funnel.map((f) => (
              <div key={f.stage} className="grid grid-cols-[120px_1fr_40px] items-center gap-3">
                <div className="text-sm text-ink-muted">{f.stage}</div>
                <div className="h-7 bg-bg-subtle rounded-full overflow-hidden">
                  <div
                    className="h-full bg-ink/85 rounded-full transition-all"
                    style={{ width: `${(f.count / funnelMax) * 100}%` }}
                  />
                </div>
                <div className="text-sm text-ink font-semibold text-right">
                  {f.count}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Recent activity */}
        <div className="card p-5">
          <div className="flex items-center justify-between">
            <div className="text-xs text-ink-muted">Recent activity</div>
            <Link
              href="/startups"
              className="text-xs text-ink-muted hover:text-ink"
            >
              View all →
            </Link>
          </div>
          <div className="mt-4 space-y-3">
            {recentActivity.map((a) => (
              <Link
                key={a.id}
                href={`/startups/${a.companyId}`}
                className="block group"
              >
                <div className="flex items-start gap-3">
                  <div className="h-2 w-2 rounded-full bg-accent-greenInk mt-2" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-ink group-hover:underline">
                      {a.company}
                    </div>
                    <div className="text-xs text-ink-muted truncate">
                      {a.text}
                    </div>
                  </div>
                  <div className="text-[11px] text-ink-faint shrink-0">
                    {relativeTime(a.at)}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Top deals table */}
      <div className="card overflow-hidden">
        <div className="px-5 py-4 flex items-center justify-between border-b border-line">
          <div>
            <div className="text-xs text-ink-muted">Active deals</div>
            <div className="text-lg font-semibold mt-0.5">Top of pipeline</div>
          </div>
          <Link
            href="/startups"
            className="text-xs text-ink-muted hover:text-ink"
          >
            View all →
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted border-b border-line">
                <th className="px-5 py-3 font-medium">Company</th>
                <th className="px-3 py-3 font-medium">Sector</th>
                <th className="px-3 py-3 font-medium">Stage</th>
                <th className="px-3 py-3 font-medium">Momentum</th>
                <th className="px-3 py-3 font-medium">Verdict</th>
                <th className="px-3 py-3 font-medium">Owner</th>
                <th className="px-5 py-3 font-medium text-right">Last touch</th>
              </tr>
            </thead>
            <tbody>
              {startups.slice(0, 6).map((s) => (
                <tr
                  key={s.id}
                  className="border-b border-line last:border-0 hover:bg-bg-subtle transition"
                >
                  <td className="px-5 py-3">
                    <Link
                      href={`/startups/${s.id}`}
                      className="font-medium text-ink hover:underline"
                    >
                      {s.name}
                    </Link>
                  </td>
                  <td className="px-3 py-3 text-ink-muted">{s.sector}</td>
                  <td className="px-3 py-3">
                    <PipelinePill stage={s.pipeline_stage} />
                  </td>
                  <td className="px-3 py-3">
                    <MomentumBadge momentum={s.momentum} />
                  </td>
                  <td className="px-3 py-3">
                    <VerdictBadge verdict={s.verdict} />
                  </td>
                  <td className="px-3 py-3 text-ink-muted">{s.owner}</td>
                  <td className="px-5 py-3 text-right text-ink-faint text-xs">
                    {relativeTime(s.last_touch_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
