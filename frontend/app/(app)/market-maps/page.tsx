"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Network,
  Maximize2,
  Filter,
  Sparkles,
  Layers,
  Info,
} from "lucide-react";
import { startups } from "@/lib/mock-data";
import { MomentumBadge, VerdictBadge } from "@/components/badges";
import { cn, relativeTime } from "@/lib/utils";
import type { StartupSummary } from "@/lib/types";

interface Cluster {
  id: string;
  label: string;
  hint: string;
  color: string;
  startups: StartupSummary[];
  // Position on the canvas in % (0–100). Hand-tuned for a pleasing layout.
  x: number;
  y: number;
}

// Group startups by their sector. We hand-place clusters on a 2D canvas
// to mimic a force-directed layout — once the Neo4j backend is wired up
// the positions can be computed from embedding similarity instead.
function buildClusters(): Cluster[] {
  const layout: Record<
    string,
    { hint: string; color: string; x: number; y: number }
  > = {
    "AI Infrastructure": {
      hint: "ML platforms, GPU orchestration, synthetic data",
      color: "bg-accent-green/40 border-accent-greenInk/30",
      x: 28,
      y: 32,
    },
    "Digital Health": {
      hint: "Remote care, diagnostics, clinical workflow",
      color: "bg-accent-blue/40 border-accent-blueInk/30",
      x: 72,
      y: 28,
    },
    FinTech: {
      hint: "Compliance, payments, embedded finance",
      color: "bg-accent-amber/40 border-accent-amberInk/30",
      x: 78,
      y: 64,
    },
    Mobility: {
      hint: "Logistics, routing, autonomous fleets",
      color: "bg-ink/10 border-ink/20",
      x: 50,
      y: 70,
    },
    "Developer Tools": {
      hint: "Databases, observability, build tooling",
      color: "bg-accent-red/30 border-accent-redInk/30",
      x: 22,
      y: 70,
    },
    Climate: {
      hint: "Carbon removal, energy, sustainable hardware",
      color: "bg-accent-green/30 border-accent-greenInk/20",
      x: 60,
      y: 18,
    },
    "Enterprise SaaS": {
      hint: "Vertical SaaS, sales tooling, knowledge work",
      color: "bg-accent-blue/30 border-accent-blueInk/20",
      x: 14,
      y: 50,
    },
  };

  const bySector = new Map<string, StartupSummary[]>();
  for (const s of startups) {
    const list = bySector.get(s.sector) ?? [];
    list.push(s);
    bySector.set(s.sector, list);
  }

  return Array.from(bySector.entries()).map(([sector, list]) => {
    const cfg = layout[sector] ?? {
      hint: "",
      color: "bg-bg-subtle border-line",
      x: 50,
      y: 50,
    };
    return {
      id: sector,
      label: sector,
      hint: cfg.hint,
      color: cfg.color,
      startups: list,
      x: cfg.x,
      y: cfg.y,
    };
  });
}

export default function MarketMapsPage() {
  const clusters = useMemo(() => buildClusters(), []);
  const [selected, setSelected] = useState<Cluster | null>(clusters[0] ?? null);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs text-ink-muted">Discovery</div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">
            Market Maps
          </h1>
          <p className="mt-1 text-sm text-ink-muted max-w-2xl">
            Clusters generated from interaction embeddings and shared market
            signals. Click a cluster to inspect the startups inside it.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button className="btn-outline">
            <Filter size={14} />
            Filter
          </button>
          <button className="btn-outline">
            <Layers size={14} />
            By sector
          </button>
          <button className="btn-primary">
            <Sparkles size={14} />
            Regenerate
          </button>
        </div>
      </div>

      {/* Canvas + side panel */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-4">
        {/* Canvas */}
        <div className="card relative overflow-hidden dot-bg h-[560px]">
          <div className="absolute inset-0 bg-gradient-to-b from-bg-card/60 to-transparent pointer-events-none" />

          {/* SVG connectors between adjacent clusters */}
          <svg
            className="absolute inset-0 w-full h-full pointer-events-none"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
          >
            {clusters.flatMap((c, i) =>
              clusters.slice(i + 1).map((other) => {
                const dx = c.x - other.x;
                const dy = c.y - other.y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                // Only connect nearby clusters to keep the canvas readable.
                if (dist > 38) return null;
                return (
                  <line
                    key={`${c.id}-${other.id}`}
                    x1={c.x}
                    y1={c.y}
                    x2={other.x}
                    y2={other.y}
                    stroke="#0A0A0A"
                    strokeOpacity={0.08}
                    strokeWidth={0.2}
                    strokeDasharray="0.8 0.8"
                  />
                );
              }),
            )}
          </svg>

          {clusters.map((c) => {
            const size = Math.min(170, 70 + c.startups.length * 22);
            const isSelected = selected?.id === c.id;
            return (
              <motion.button
                key={c.id}
                onClick={() => setSelected(c)}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{
                  type: "spring",
                  stiffness: 200,
                  damping: 22,
                  delay: 0.05 * clusters.indexOf(c),
                }}
                whileHover={{ scale: 1.04 }}
                className={cn(
                  "absolute rounded-full border-2 flex flex-col items-center justify-center text-center px-4 transition shadow-card",
                  c.color,
                  isSelected && "ring-4 ring-ink/20",
                )}
                style={{
                  width: size,
                  height: size,
                  left: `calc(${c.x}% - ${size / 2}px)`,
                  top: `calc(${c.y}% - ${size / 2}px)`,
                }}
              >
                <div className="text-[11px] uppercase tracking-wider text-ink/70">
                  Cluster
                </div>
                <div className="text-sm font-semibold text-ink leading-tight mt-0.5">
                  {c.label}
                </div>
                <div className="mt-1 pill bg-white/80 text-ink-muted text-[10px]">
                  {c.startups.length}{" "}
                  {c.startups.length === 1 ? "deal" : "deals"}
                </div>
              </motion.button>
            );
          })}

          {/* Legend */}
          <div className="absolute bottom-4 left-4 bg-bg-card/95 backdrop-blur border border-line rounded-xl p-3 shadow-card text-xs">
            <div className="flex items-center gap-2 text-ink-muted">
              <Network size={12} />
              <span className="font-medium text-ink">
                {clusters.length} clusters
              </span>
              <span>·</span>
              <span>{startups.length} startups mapped</span>
            </div>
            <div className="text-[11px] text-ink-faint mt-1">
              Edge = shared sector or thematic overlap.
            </div>
          </div>

          <button
            className="absolute top-4 right-4 btn-outline"
            aria-label="Expand"
          >
            <Maximize2 size={14} />
          </button>
        </div>

        {/* Side panel — cluster details */}
        <div className="card p-5 flex flex-col">
          {selected ? (
            <>
              <div className="flex items-start justify-between">
                <div>
                  <div className="text-xs text-ink-muted">Selected cluster</div>
                  <div className="mt-1 text-xl font-semibold text-ink">
                    {selected.label}
                  </div>
                </div>
                <div
                  className={cn(
                    "h-9 w-9 rounded-xl border-2",
                    selected.color,
                  )}
                />
              </div>

              {selected.hint && (
                <p className="mt-2 text-xs text-ink-muted leading-relaxed">
                  {selected.hint}
                </p>
              )}

              <div className="mt-4 grid grid-cols-3 gap-2">
                <Stat label="Deals" value={String(selected.startups.length)} />
                <Stat
                  label="Accelerating"
                  value={String(
                    selected.startups.filter((s) => s.momentum === "accelerating")
                      .length,
                  )}
                />
                <Stat
                  label="Invested"
                  value={String(
                    selected.startups.filter((s) => s.verdict === "invested")
                      .length,
                  )}
                />
              </div>

              <div className="mt-5 text-[10px] uppercase tracking-wider text-ink-faint">
                Startups
              </div>
              <div className="mt-2 space-y-2 overflow-y-auto flex-1">
                {selected.startups.map((s) => (
                  <Link
                    key={s.id}
                    href={`/startups/${s.id}`}
                    className="block p-3 rounded-xl border border-line hover:border-ink/20 hover:bg-bg-subtle transition group"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-medium text-ink group-hover:underline truncate">
                        {s.name}
                      </div>
                      <span className="text-[11px] text-ink-faint shrink-0">
                        {relativeTime(s.last_touch_at)}
                      </span>
                    </div>
                    <div className="text-xs text-ink-muted mt-0.5 truncate">
                      {s.one_liner}
                    </div>
                    <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                      <MomentumBadge momentum={s.momentum} />
                      <VerdictBadge verdict={s.verdict} />
                    </div>
                  </Link>
                ))}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-sm text-ink-muted">
              Select a cluster on the canvas to inspect it.
            </div>
          )}
        </div>
      </div>

      {/* Hint */}
      <div className="card-subtle p-4 flex items-start gap-3 text-sm">
        <Info size={16} className="text-ink-muted mt-0.5 shrink-0" />
        <div className="text-ink-muted">
          <span className="text-ink font-medium">Heads up.</span> The map
          currently lays out clusters by sector. Once the Neo4j backend is
          wired up, positions will come from interaction-graph embeddings so
          edges reflect actual thematic overlap, not just shared labels.
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-bg-subtle border border-line p-2.5">
      <div className="text-[10px] uppercase tracking-wider text-ink-faint">
        {label}
      </div>
      <div className="mt-0.5 text-lg font-semibold text-ink">{value}</div>
    </div>
  );
}
