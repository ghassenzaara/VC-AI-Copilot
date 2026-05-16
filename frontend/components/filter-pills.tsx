"use client";

import { cn } from "@/lib/utils";

interface FilterPillsProps<T extends string> {
  label?: string;
  options: readonly T[];
  active: T | "all";
  onChange: (value: T | "all") => void;
  capitalize?: boolean;
}

export function FilterPills<T extends string>({
  label,
  options,
  active,
  onChange,
  capitalize,
}: FilterPillsProps<T>) {
  return (
    <div className="flex items-center gap-2 flex-wrap">
      {label && (
        <span className="text-xs text-ink-muted shrink-0 mr-1">{label}</span>
      )}
      <button
        onClick={() => onChange("all")}
        className={cn(
          "pill border transition",
          active === "all"
            ? "bg-ink text-white border-ink"
            : "bg-bg-card border-line text-ink-muted hover:text-ink",
        )}
      >
        All
      </button>
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={cn(
            "pill border transition",
            capitalize && "capitalize",
            active === opt
              ? "bg-ink text-white border-ink"
              : "bg-bg-card border-line text-ink-muted hover:text-ink",
          )}
        >
          {opt}
        </button>
      ))}
    </div>
  );
}
