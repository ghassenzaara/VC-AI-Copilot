import Link from "next/link";
import type { StartupSummary } from "@/lib/types";
import { MomentumBadge, PipelinePill, Tag, VerdictBadge } from "./badges";
import { relativeTime, initials } from "@/lib/utils";
import { ArrowUpRight } from "lucide-react";

export function StartupCard({ s }: { s: StartupSummary }) {
  return (
    <Link
      href={`/startups/${s.id}`}
      className="card p-5 hover:shadow-elev transition group block"
    >
      <div className="flex items-start gap-3">
        <div className="h-10 w-10 rounded-xl bg-bg-subtle border border-line flex items-center justify-center text-sm font-semibold text-ink">
          {initials(s.name)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <div className="font-semibold text-ink truncate">{s.name}</div>
            <ArrowUpRight
              size={14}
              className="text-ink-faint opacity-0 group-hover:opacity-100 transition"
            />
          </div>
          <div className="text-xs text-ink-muted">{s.sector}</div>
        </div>
        <VerdictBadge verdict={s.verdict} />
      </div>

      <p className="mt-3 text-sm text-ink-muted line-clamp-2 min-h-[2.5em]">
        {s.one_liner}
      </p>

      <div className="mt-4 flex items-center gap-1.5 flex-wrap">
        <PipelinePill stage={s.pipeline_stage} />
        <MomentumBadge momentum={s.momentum} />
        <Tag>{s.stage}</Tag>
      </div>

      <div className="mt-4 pt-4 border-t border-line flex items-center justify-between text-xs">
        <div className="text-ink-muted">
          Owner <span className="text-ink">{s.owner}</span>
        </div>
        <div className="text-ink-faint">
          Last touch · {relativeTime(s.last_touch_at)}
        </div>
      </div>
    </Link>
  );
}
