"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Network,
  Maximize2,
  Filter,
  Sparkles,
  Layers,
  Info,
  Loader2,
} from "lucide-react";
import { MomentumBadge, VerdictBadge } from "@/components/badges";
import { useApi } from "@/lib/use-api";
import { cn, relativeTime } from "@/lib/utils";
import type { MarketCluster, MarketMapResponse, ClusterCompany } from "@/lib/types";

interface ClusterWithLayout extends MarketCluster {
  x: number;
  y: number;
  color: string;
}

// Color palette for clusters
const CLUSTER_COLORS = [
  "bg-accent-green/40 border-accent-greenInk/30",
  "bg-accent-blue/40 border-accent-blueInk/30",
  "bg-accent-amber/40 border-accent-amberInk/30",
  "bg-ink/10 border-ink/20",
  "bg-accent-red/30 border-accent-redInk/30",
  "bg-accent-green/30 border-accent-greenInk/20",
  "bg-accent-blue/30 border-accent-blueInk/20",
  "bg-accent-amber/30 border-accent-amberInk/20",
];

// Generate layout positions for clusters in a circular/organic pattern
function generateClusterLayout(clusters: MarketCluster[]): ClusterWithLayout[] {
  const n = clusters.length;
  const radius = 35; // Distance from center
  const centerX = 50;
  const centerY = 50;

  return clusters.map((cluster, i) => {
    // Distribute clusters in a circle with some randomness
    const angle = (i / n) * 2 * Math.PI;
    const jitter = (Math.random() - 0.5) * 10; // Add some organic variation
    
    const x = centerX + radius * Math.cos(angle) + jitter;
    const y = centerY + radius * Math.sin(angle) + jitter;
    
    return {
      ...cluster,
      x: Math.max(15, Math.min(85, x)), // Keep within bounds
      y: Math.max(15, Math.min(85, y)),
      color: CLUSTER_COLORS[i % CLUSTER_COLORS.length],
    };
  });
}

export default function MarketMapsPage() {
  const api = useApi();
  const [data, setData] = useState<MarketMapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ClusterWithLayout | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [regenError, setRegenError] = useState<string | null>(null);

  // `silent=true` skips the full-page spinner so the existing canvas stays
  // visible while we refetch in the background (used by regenerate and any
  // future auto-refresh). Initial mount uses silent=false so the user sees
  // the loading state instead of an empty card.
  const loadMap = useCallback(
    async ({ silent = false }: { silent?: boolean } = {}) => {
      if (!api.isReady) return;
      if (!silent) setLoading(true);
      try {
        const mapData = await api.fetchMarketMap();
        setData(mapData);
        setError(null);
      } catch (err) {
        console.error("Failed to fetch market map:", err);
        setError(err instanceof Error ? err.message : "Failed to load market map");
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [api],
  );

  useEffect(() => {
    void loadMap();
  }, [loadMap]);

  const handleRegenerate = useCallback(async () => {
    if (!api.isReady || regenerating) return;
    setRegenerating(true);
    setRegenError(null);
    try {
      await api.regenerateMarketMap();
      // Refetch silently — the button spinner already communicates the work.
      // The auto-select effect below handles swapping `selected` once the
      // previously-selected cluster id is no longer in the new data.
      await loadMap({ silent: true });
    } catch (err) {
      console.error("Failed to regenerate market map:", err);
      setRegenError(
        err instanceof Error ? err.message : "Failed to regenerate clusters",
      );
    } finally {
      setRegenerating(false);
    }
  }, [api, regenerating, loadMap]);

  const clustersWithLayout = useMemo(() => {
    if (!data?.clusters) return [];
    const layout = generateClusterLayout(data.clusters);
    return layout;
  }, [data]);

  // Auto-select first cluster when data loads, OR re-point the selection
  // after a regenerate (cluster ids change so the previous selection becomes
  // stale). If the selected id still exists in the new data, keep it but
  // swap to the refreshed cluster object so the side panel re-renders.
  useEffect(() => {
    if (clustersWithLayout.length === 0) return;
    if (!selected) {
      setSelected(clustersWithLayout[0]);
      return;
    }
    const match = clustersWithLayout.find((c) => c.id === selected.id);
    if (!match) {
      setSelected(clustersWithLayout[0]);
    } else if (match !== selected) {
      setSelected(match);
    }
  }, [clustersWithLayout, selected]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-[600px]">
        <div className="text-center">
          <Loader2 className="w-8 h-8 animate-spin text-ink-muted mx-auto" />
          <p className="mt-4 text-sm text-ink-muted">Loading market map...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card p-8 text-center">
        <div className="text-ink-muted mb-4">⚠️</div>
        <h3 className="text-lg font-semibold text-ink mb-2">Failed to Load Market Map</h3>
        <p className="text-sm text-ink-muted mb-4">{error}</p>
        <button 
          onClick={() => window.location.reload()} 
          className="btn-primary"
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data || clustersWithLayout.length === 0) {
    return (
      <div className="card p-8 text-center">
        <div className="text-ink-muted mb-4">📊</div>
        <h3 className="text-lg font-semibold text-ink mb-2">No Clusters Yet</h3>
        <p className="text-sm text-ink-muted mb-4">
          Run the clustering algorithm to generate market map clusters.
        </p>
        <button
          onClick={handleRegenerate}
          disabled={regenerating}
          className={cn("btn-primary", regenerating && "opacity-60 cursor-not-allowed")}
        >
          {regenerating ? (
            <>
              <Loader2 size={14} className="animate-spin" />
              Generating…
            </>
          ) : (
            <>
              <Sparkles size={14} />
              Generate Clusters
            </>
          )}
        </button>
        {regenError && (
          <p className="mt-3 text-xs text-accent-redInk">{regenError}</p>
        )}
      </div>
    );
  }

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
            AI-generated clusters from company embeddings and LLM analysis.
            Click a cluster to inspect the companies inside it.
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
          <button
            onClick={handleRegenerate}
            disabled={regenerating}
            className={cn(
              "btn-primary",
              regenerating && "opacity-60 cursor-not-allowed",
            )}
            title="Wipe existing clusters and re-run clustering + naming"
          >
            {regenerating ? (
              <>
                <Loader2 size={14} className="animate-spin" />
                Regenerating…
              </>
            ) : (
              <>
                <Sparkles size={14} />
                Regenerate
              </>
            )}
          </button>
        </div>
      </div>

      {regenError && (
        <div className="card-subtle p-3 text-sm text-accent-redInk">
          {regenError}
        </div>
      )}

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
            {clustersWithLayout.flatMap((c, i) =>
              clustersWithLayout.slice(i + 1).map((other) => {
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

          {clustersWithLayout.map((c) => {
            const size = Math.min(170, 70 + c.company_count * 22);
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
                  delay: 0.05 * clustersWithLayout.indexOf(c),
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
                <div className="text-sm font-semibold text-ink leading-tight">
                  {c.name || "Unnamed cluster"}
                </div>
                <div className="mt-1 pill bg-white/80 text-ink-muted text-[10px]">
                  {c.company_count}{" "}
                  {c.company_count === 1 ? "company" : "companies"}
                </div>
              </motion.button>
            );
          })}

          {/* Legend */}
          <div className="absolute bottom-4 left-4 bg-bg-card/95 backdrop-blur border border-line rounded-xl p-3 shadow-card text-xs">
            <div className="flex items-center gap-2 text-ink-muted">
              <Network size={12} />
              <span className="font-medium text-ink">
                {clustersWithLayout.length} clusters
              </span>
              <span>·</span>
              <span>{data.total_companies} companies mapped</span>
            </div>
            <div className="text-[11px] text-ink-faint mt-1">
              Generated from embedding similarity.
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
                    {selected.name || "Unnamed cluster"}
                  </div>
                </div>
                <div
                  className={cn(
                    "h-9 w-9 rounded-xl border-2",
                    selected.color,
                  )}
                />
              </div>

              {selected.description && (
                <p className="mt-2 text-xs text-ink-muted leading-relaxed">
                  {selected.description}
                </p>
              )}

              {/* Cluster metadata */}
              {((selected.common_sectors?.length ?? 0) > 0 ||
                (selected.common_stages?.length ?? 0) > 0) && (
                <div className="mt-3 space-y-2">
                  {(selected.common_sectors?.length ?? 0) > 0 && (
                    <div className="text-xs">
                      <span className="text-ink-faint">Sectors:</span>{" "}
                      <span className="text-ink">{selected.common_sectors.join(", ")}</span>
                    </div>
                  )}
                  {(selected.common_stages?.length ?? 0) > 0 && (
                    <div className="text-xs">
                      <span className="text-ink-faint">Stages:</span>{" "}
                      <span className="text-ink">{selected.common_stages.join(", ")}</span>
                    </div>
                  )}
                </div>
              )}

              <div className="mt-4 grid grid-cols-3 gap-2">
                <Stat label="Companies" value={String(selected.company_count)} />
                <Stat
                  label="Accelerating"
                  value={String(
                    selected.companies.filter((s) => s.momentum === "accelerating")
                      .length,
                  )}
                />
                <Stat
                  label="Invested"
                  value={String(
                    selected.companies.filter((s) => s.verdict === "invested")
                      .length,
                  )}
                />
              </div>

              <div className="mt-5 text-[10px] uppercase tracking-wider text-ink-faint">
                Companies
              </div>
              <div className="mt-2 space-y-2 overflow-y-auto flex-1">
                {selected.companies.map((s) => (
                  <Link
                    key={s.id}
                    href={`/startups/${s.id}`}
                    className="block p-3 rounded-xl border border-line hover:border-ink/20 hover:bg-bg-subtle transition group"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="font-medium text-ink group-hover:underline truncate">
                        {s.name}
                      </div>
                      {s.last_touch_at && (
                        <span className="text-[11px] text-ink-faint shrink-0">
                          {relativeTime(s.last_touch_at)}
                        </span>
                      )}
                    </div>
                    {s.one_liner && (
                      <div className="text-xs text-ink-muted mt-0.5 truncate">
                        {s.one_liner}
                      </div>
                    )}
                    <div className="mt-2 flex items-center gap-1.5 flex-wrap">
                      {s.momentum && <MomentumBadge momentum={s.momentum} />}
                      {s.verdict && <VerdictBadge verdict={s.verdict} />}
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

      {/* Info banner */}
      <div className="card-subtle p-4 flex items-start gap-3 text-sm">
        <Info size={16} className="text-ink-muted mt-0.5 shrink-0" />
        <div className="text-ink-muted">
          <span className="text-ink font-medium">Real-time clustering.</span> This
          market map is generated from company embeddings using K-means or HDBSCAN
          algorithms. Cluster names are generated by LLM analysis of company
          characteristics. Click "Regenerate" to recompute clusters.
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

// Made with Bob
