import { cn } from "@/lib/utils";
import type {
  Momentum,
  PipelineStage,
  Stage,
  Verdict,
  Sentiment,
} from "@/lib/types";
import { ArrowUpRight, Minus, ArrowDownRight, Skull } from "lucide-react";

export function StagePill({ stage }: { stage: Stage }) {
  return (
    <span className="pill bg-bg-subtle border border-line text-ink-muted">
      {stage}
    </span>
  );
}

export function PipelinePill({ stage }: { stage: PipelineStage }) {
  const palette: Record<PipelineStage, string> = {
    Tracking: "bg-line/60 text-ink-muted",
    "First call": "bg-accent-blue/60 text-accent-blueInk",
    Diligence: "bg-accent-amber/40 text-accent-amberInk",
    "IC review": "bg-accent-amber/70 text-accent-amberInk",
    Decision: "bg-ink text-white",
  };
  return <span className={cn("pill", palette[stage])}>{stage}</span>;
}

export function MomentumBadge({ momentum }: { momentum: Momentum }) {
  const config: Record<
    Momentum,
    { label: string; cls: string; Icon: typeof ArrowUpRight }
  > = {
    accelerating: {
      label: "Accelerating",
      cls: "bg-accent-green/60 text-accent-greenInk",
      Icon: ArrowUpRight,
    },
    stable: {
      label: "Stable",
      cls: "bg-bg-subtle border border-line text-ink-muted",
      Icon: Minus,
    },
    stalling: {
      label: "Stalling",
      cls: "bg-accent-amber/40 text-accent-amberInk",
      Icon: ArrowDownRight,
    },
    dead: {
      label: "Dead",
      cls: "bg-accent-red/40 text-accent-redInk",
      Icon: Skull,
    },
  };
  const { label, cls, Icon } = config[momentum];
  return (
    <span className={cn("pill", cls)}>
      <Icon size={12} strokeWidth={2.5} />
      {label}
    </span>
  );
}

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const config: Record<Verdict, string> = {
    tracking: "bg-bg-subtle border border-line text-ink-muted",
    diligence: "bg-accent-amber/40 text-accent-amberInk",
    invested: "bg-accent-green/60 text-accent-greenInk",
    passed: "bg-accent-red/40 text-accent-redInk",
  };
  return (
    <span className={cn("pill capitalize", config[verdict])}>{verdict}</span>
  );
}

export function SentimentDot({ sentiment }: { sentiment: Sentiment }) {
  const color: Record<Sentiment, string> = {
    positive: "bg-accent-greenInk",
    neutral: "bg-ink-faint",
    negative: "bg-accent-redInk",
  };
  return (
    <span
      className={cn("inline-block h-1.5 w-1.5 rounded-full", color[sentiment])}
    />
  );
}

export function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="pill bg-bg-subtle border border-line text-ink-muted">
      {children}
    </span>
  );
}
