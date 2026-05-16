import { cn } from "@/lib/utils";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";

interface KpiCardProps {
  label: string;
  value: string;
  delta?: { value: string; positive?: boolean } | null;
  hint?: string;
  className?: string;
  children?: React.ReactNode;
}

export function KpiCard({
  label,
  value,
  delta,
  hint,
  className,
  children,
}: KpiCardProps) {
  return (
    <div className={cn("card p-5", className)}>
      <div className="text-xs text-ink-muted">{label}</div>
      <div className="mt-2 flex items-baseline gap-2">
        <div className="text-2xl font-semibold tracking-tight text-ink">
          {value}
        </div>
        {delta && (
          <span
            className={cn(
              "pill",
              delta.positive
                ? "bg-accent-green/60 text-accent-greenInk"
                : "bg-accent-red/40 text-accent-redInk",
            )}
          >
            {delta.positive ? (
              <ArrowUpRight size={12} strokeWidth={2.5} />
            ) : (
              <ArrowDownRight size={12} strokeWidth={2.5} />
            )}
            {delta.value}
          </span>
        )}
      </div>
      {hint && <div className="mt-1 text-xs text-ink-faint">{hint}</div>}
      {children}
    </div>
  );
}
