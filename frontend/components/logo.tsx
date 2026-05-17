import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="relative h-7 w-7 rounded-xl bg-ink flex items-center justify-center">
        <div className="absolute h-3 w-3 rounded-full bg-accent-green" />
        <div className="absolute h-2 w-2 rounded-full bg-white right-1.5 bottom-1.5" />
      </div>
      <span className="text-[15px] font-semibold tracking-tight text-ink">
        Vista
      </span>
    </div>
  );
}
