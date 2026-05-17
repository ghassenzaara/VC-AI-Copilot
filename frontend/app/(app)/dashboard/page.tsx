"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  Tooltip,
} from "recharts";
import { Loader2, ChevronDown } from "lucide-react";
import { KpiCard } from "@/components/kpi-card";
import {
  MomentumBadge,
  PipelinePill,
  VerdictBadge,
} from "@/components/badges";
import { ALL_PIPELINE_STAGES } from "@/lib/constants";
import { type DashboardSummary } from "@/lib/api";
import { useApi } from "@/lib/use-api";
import { relativeTime } from "@/lib/utils";

const MOMENTUM_COLOR: Record<string, string> = {
  accelerating: "bg-accent-green",
  stable: "bg-ink/70",
  stalling: "bg-accent-amber",
  dead: "bg-accent-red",
};
const MOMENTUM_LABEL: Record<string, string> = {
  accelerating: "Accelerating",
  stable: "Stable",
  stalling: "Stalling",
  dead: "Dead",
};

export default function DashboardPage() {
  const api = useApi();
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!api.isReady) return;
    let cancelled = false;
    setLoading(true);
    api
      .fetchDashboardSummary()
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[60vh]">
        <Loader2 className="w-8 h-8 animate-spin text-ink-muted" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-8 text-center">
        <h3 className="text-lg font-semibold text-ink mb-2">
          Couldn&apos;t load dashboard
        </h3>
        <p className="text-sm text-ink-muted">{error}</p>
        <p className="text-xs text-ink-faint mt-4">
          Check that the backend is reachable.
        </p>
      </div>
    );
  }

  if (!data || data.kpis.total_deals === 0) {
    return <EmptyDashboard />;
  }

  const { kpis, funnel, momentum_split, pipeline_trend, recent_activity, top_deals } = data;
  const funnelMax = Math.max(...funnel.map((f) => f.count), 1);
  const momentumTotal = momentum_split.reduce((a, b) => a + b.count, 0);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs text-ink-muted">Overview</div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Dashboard</h1>
        </div>
        <button className="btn-outline">
          Last 30 days <ChevronDown size={14} />
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Total deals tracked" value={String(kpis.total_deals)} hint="across all sources" />
        <KpiCard label="Invested this period" value={String(kpis.invested)} hint="closed deals" />
        <KpiCard label="Accelerating" value={String(kpis.accelerating)} hint="of tracked deals" />
        <KpiCard label="Needs follow-up" value={String(kpis.needs_followup)} hint="open next-steps" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-5 lg:col-span-2">
          <div className="flex items-start justify-between">
            <div>
              <div className="text-xs text-ink-muted">Pipeline growth</div>
              <div className="mt-1 flex items-baseline gap-2">
                <div className="text-2xl font-semibold tracking-tight">{kpis.total_deals} deals</div>
              </div>
            </div>
            <div className="text-xs text-ink-faint">Last 6 months</div>
          </div>
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={pipeline_trend} margin={{ top: 10, right: 0, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="g1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#0A0A0A" stopOpacity={0.18} />
                    <stop offset="100%" stopColor="#0A0A0A" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="month" stroke="#9CA3AF" fontSize={11} tickLine={false} axisLine={false} />
                <Tooltip
                  contentStyle={{ background: "#fff", border: "1px solid #E7E7E2", borderRadius: 12, fontSize: 12 }}
                />
                <Area type="monotone" dataKey="value" stroke="#0A0A0A" strokeWidth={2} fill="url(#g1)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card p-5">
          <div className="text-xs text-ink-muted">Deal momentum</div>
          <div className="mt-1 text-2xl font-semibold tracking-tight">
            {momentumTotal}
            <span className="text-sm text-ink-muted font-normal ml-1">active</span>
          </div>
          <div className="mt-5 flex h-2.5 w-full rounded-full overflow-hidden">
            {momentum_split.map((m) => (
              <div
                key={m.label}
                className={MOMENTUM_COLOR[m.label] ?? "bg-ink/30"}
                style={{ width: `${(m.count / Math.max(momentumTotal, 1)) * 100}%` }}
              />
            ))}
          </div>
          <div className="mt-5 space-y-2.5">
            {momentum_split.map((m) => (
              <div key={m.label} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 rounded-full ${MOMENTUM_COLOR[m.label] ?? "bg-ink/30"}`} />
                  <span className="text-ink">{MOMENTUM_LABEL[m.label] ?? m.label}</span>
                </div>
                <span className="text-ink-muted">{m.count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="card p-5 lg:col-span-2">
          <div className="text-xs text-ink-muted">Pipeline funnel</div>
          <div className="mt-1 text-lg font-semibold">Deals by stage</div>
          <div className="mt-5 space-y-3">
            {ALL_PIPELINE_STAGES.map((stage) => {
              const count = funnel.find((f) => f.stage === stage)?.count ?? 0;
              return (
                <div key={stage} className="grid grid-cols-[120px_1fr_40px] items-center gap-3">
                  <div className="text-sm text-ink-muted">{stage}</div>
                  <div className="h-7 bg-bg-subtle rounded-full overflow-hidden">
                    <div
                      className="h-full bg-ink/85 rounded-full transition-all"
                      style={{ width: `${(count / funnelMax) * 100}%` }}
                    />
                  </div>
                  <div className="text-sm text-ink font-semibold text-right">{count}</div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="card p-5">
          <div className="flex items-center justify-between">
            <div className="text-xs text-ink-muted">Recent activity</div>
            <Link href="/startups" className="text-xs text-ink-muted hover:text-ink">View all →</Link>
          </div>
          <div className="mt-4 space-y-3">
            {recent_activity.length === 0 ? (
              <p className="text-sm text-ink-faint">No recent activity.</p>
            ) : (
              recent_activity.map((a) => (
                <Link key={a.id} href={`/startups/${a.companyId}`} className="block group">
                  <div className="flex items-start gap-3">
                    <div className="h-2 w-2 rounded-full bg-accent-greenInk mt-2" />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm text-ink group-hover:underline">{a.company}</div>
                      <div className="text-xs text-ink-muted truncate">{a.text}</div>
                    </div>
                    <div className="text-[11px] text-ink-faint shrink-0">{a.at ? relativeTime(a.at) : ""}</div>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="px-5 py-4 flex items-center justify-between border-b border-line">
          <div>
            <div className="text-xs text-ink-muted">Active deals</div>
            <div className="text-lg font-semibold mt-0.5">Top of pipeline</div>
          </div>
          <Link href="/startups" className="text-xs text-ink-muted hover:text-ink">View all →</Link>
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
              {top_deals.map((s) => (
                <tr key={s.id} className="border-b border-line last:border-0 hover:bg-bg-subtle transition">
                  <td className="px-5 py-3">
                    <Link href={`/startups/${s.id}`} className="font-medium text-ink hover:underline">
                      {s.name}
                    </Link>
                  </td>
                  <td className="px-3 py-3 text-ink-muted">{s.sector}</td>
                  <td className="px-3 py-3"><PipelinePill stage={s.pipeline_stage} /></td>
                  <td className="px-3 py-3"><MomentumBadge momentum={s.momentum} /></td>
                  <td className="px-3 py-3"><VerdictBadge verdict={s.verdict} /></td>
                  <td className="px-3 py-3 text-ink-muted">{s.owner}</td>
                  <td className="px-5 py-3 text-right text-ink-faint text-xs">
                    {s.last_touch_at ? relativeTime(s.last_touch_at) : "—"}
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

function EmptyDashboard() {
  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs text-ink-muted">Overview</div>
        <h1 className="mt-1 text-3xl font-semibold tracking-tight">Dashboard</h1>
      </div>
      <div className="card p-12 text-center">
        <h3 className="text-lg font-semibold text-ink mb-2">No deals yet</h3>
        <p className="text-sm text-ink-muted max-w-md mx-auto">
          Once the extraction pipeline runs, your companies, pipeline stages, and
          recent activity will appear here.
        </p>
      </div>
    </div>
  );
}
