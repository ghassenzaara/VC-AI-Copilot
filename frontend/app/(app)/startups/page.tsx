"use client";

import { useMemo, useState } from "react";
import { Search, LayoutGrid, List, ChevronDown } from "lucide-react";
import { StartupCard } from "@/components/startup-card";
import { FilterPills } from "@/components/filter-pills";
import {
  MomentumBadge,
  PipelinePill,
  Tag,
  VerdictBadge,
} from "@/components/badges";
import {
  startups,
  ALL_MOMENTUMS,
  ALL_PIPELINE_STAGES,
  ALL_VERDICTS,
  ALL_STAGES,
} from "@/lib/mock-data";
import type {
  Momentum,
  PipelineStage,
  Stage,
  Verdict,
} from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";
import Link from "next/link";

type View = "grid" | "list";

export default function StartupsPage() {
  const [view, setView] = useState<View>("grid");
  const [query, setQuery] = useState("");
  const [pipelineFilter, setPipelineFilter] = useState<PipelineStage | "all">(
    "all",
  );
  const [momentumFilter, setMomentumFilter] = useState<Momentum | "all">("all");
  const [verdictFilter, setVerdictFilter] = useState<Verdict | "all">("all");
  const [stageFilter, setStageFilter] = useState<Stage | "all">("all");

  const filtered = useMemo(() => {
    return startups.filter((s) => {
      if (
        query &&
        !s.name.toLowerCase().includes(query.toLowerCase()) &&
        !s.one_liner.toLowerCase().includes(query.toLowerCase()) &&
        !s.sector.toLowerCase().includes(query.toLowerCase())
      )
        return false;
      if (pipelineFilter !== "all" && s.pipeline_stage !== pipelineFilter)
        return false;
      if (momentumFilter !== "all" && s.momentum !== momentumFilter)
        return false;
      if (verdictFilter !== "all" && s.verdict !== verdictFilter) return false;
      if (stageFilter !== "all" && s.stage !== stageFilter) return false;
      return true;
    });
  }, [query, pipelineFilter, momentumFilter, verdictFilter, stageFilter]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs text-ink-muted">Portfolio</div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">
            Startups
            <span className="ml-3 text-ink-muted font-normal text-xl">
              {filtered.length}
            </span>
          </h1>
        </div>

        <div className="flex items-center gap-2">
          <button className="btn-outline">
            Sort by Last touch <ChevronDown size={14} />
          </button>
          <div className="inline-flex bg-bg-card border border-line rounded-full p-1">
            <button
              onClick={() => setView("grid")}
              className={cn(
                "p-1.5 rounded-full transition",
                view === "grid"
                  ? "bg-ink text-white"
                  : "text-ink-muted hover:text-ink",
              )}
              aria-label="Grid view"
            >
              <LayoutGrid size={14} />
            </button>
            <button
              onClick={() => setView("list")}
              className={cn(
                "p-1.5 rounded-full transition",
                view === "list"
                  ? "bg-ink text-white"
                  : "text-ink-muted hover:text-ink",
              )}
              aria-label="List view"
            >
              <List size={14} />
            </button>
          </div>
        </div>
      </div>

      {/* Search + filters */}
      <div className="card p-4 space-y-4">
        <div className="flex items-center gap-2 bg-bg-subtle border border-line rounded-full px-4 py-2">
          <Search size={16} className="text-ink-faint" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search by name, sector, or description…"
            className="bg-transparent flex-1 outline-none text-sm text-ink placeholder:text-ink-faint"
          />
          {query && (
            <button
              onClick={() => setQuery("")}
              className="text-xs text-ink-muted hover:text-ink"
            >
              Clear
            </button>
          )}
        </div>

        <div className="space-y-2.5">
          <FilterPills
            label="Pipeline"
            options={ALL_PIPELINE_STAGES}
            active={pipelineFilter}
            onChange={setPipelineFilter}
          />
          <FilterPills
            label="Momentum"
            options={ALL_MOMENTUMS}
            active={momentumFilter}
            onChange={setMomentumFilter}
            capitalize
          />
          <FilterPills
            label="Verdict"
            options={ALL_VERDICTS}
            active={verdictFilter}
            onChange={setVerdictFilter}
            capitalize
          />
          <FilterPills
            label="Stage"
            options={ALL_STAGES}
            active={stageFilter}
            onChange={setStageFilter}
          />
        </div>
      </div>

      {/* Results */}
      {filtered.length === 0 ? (
        <div className="card p-12 text-center">
          <div className="text-ink-muted">No startups match your filters.</div>
          <button
            onClick={() => {
              setQuery("");
              setPipelineFilter("all");
              setMomentumFilter("all");
              setVerdictFilter("all");
              setStageFilter("all");
            }}
            className="mt-3 btn-ghost"
          >
            Reset filters
          </button>
        </div>
      ) : view === "grid" ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((s) => (
            <StartupCard key={s.id} s={s} />
          ))}
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-muted border-b border-line">
                <th className="px-5 py-3 font-medium">Company</th>
                <th className="px-3 py-3 font-medium">Sector</th>
                <th className="px-3 py-3 font-medium">Stage</th>
                <th className="px-3 py-3 font-medium">Pipeline</th>
                <th className="px-3 py-3 font-medium">Momentum</th>
                <th className="px-3 py-3 font-medium">Verdict</th>
                <th className="px-3 py-3 font-medium">Owner</th>
                <th className="px-5 py-3 font-medium text-right">Last touch</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
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
                    <div className="text-xs text-ink-muted truncate max-w-[260px]">
                      {s.one_liner}
                    </div>
                  </td>
                  <td className="px-3 py-3 text-ink-muted">{s.sector}</td>
                  <td className="px-3 py-3">
                    <Tag>{s.stage}</Tag>
                  </td>
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
      )}
    </div>
  );
}
