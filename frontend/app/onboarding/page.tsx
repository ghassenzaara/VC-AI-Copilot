"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import { Logo } from "@/components/logo";
import { Check, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface Integration {
  id: "granola" | "affinity" | "slack" | "gmail";
  name: string;
  description: string;
  brand: string; // tailwind bg class for the brand square
  initial: string;
}

const INTEGRATIONS: Integration[] = [
  {
    id: "granola",
    name: "Granola",
    description:
      "Pull meeting transcripts and notes from your founder calls.",
    brand: "bg-[#FDE68A] text-[#7C2D12]",
    initial: "G",
  },
  {
    id: "affinity",
    name: "Affinity",
    description: "Sync your deal pipeline, contacts, and opportunity stages.",
    brand: "bg-[#DBEAFE] text-[#1E3A8A]",
    initial: "A",
  },
  {
    id: "slack",
    name: "Slack",
    description: "Capture deal-flow conversations from your team channels.",
    brand: "bg-[#FBCFE8] text-[#831843]",
    initial: "S",
  },
  {
    id: "gmail",
    name: "Gmail",
    description: "Index founder threads, intros, and follow-ups automatically.",
    brand: "bg-[#FECACA] text-[#991B1B]",
    initial: "M",
  },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { user } = useUser();
  const [connected, setConnected] = useState<Set<string>>(new Set());

  const firstName = user?.firstName ?? null;

  function toggleConnect(id: string) {
    setConnected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div className="min-h-screen flex flex-col">
      <div className="px-8 pt-6 flex items-center justify-between">
        <Logo />
        <Link href="/dashboard" className="text-sm text-ink-muted hover:text-ink">
          Skip for now →
        </Link>
      </div>

      <div className="flex-1 flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-3xl">
          <div className="text-center">
            <div className="inline-flex pill bg-bg-card border border-line text-ink-muted">
              Step 1 of 1
            </div>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight text-ink">
              {firstName
                ? `Welcome, ${firstName}. Connect your data sources`
                : "Connect your data sources"}
            </h1>
            <p className="mt-2 text-sm text-ink-muted max-w-md mx-auto">
              We pull interactions from these tools and synthesize them into
              structured deal intelligence. You can configure these later.
            </p>
          </div>

          <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 gap-4">
            {INTEGRATIONS.map((it) => {
              const isConnected = connected.has(it.id);
              return (
                <div
                  key={it.id}
                  className={cn(
                    "card p-5 transition",
                    isConnected && "border-ink/30 shadow-elev",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={cn(
                        "h-11 w-11 rounded-xl flex items-center justify-center text-base font-semibold",
                        it.brand,
                      )}
                    >
                      {it.initial}
                    </div>
                    <div className="flex-1">
                      <div className="font-semibold text-ink">{it.name}</div>
                      <div className="mt-0.5 text-xs text-ink-muted leading-relaxed">
                        {it.description}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => toggleConnect(it.id)}
                    className={cn(
                      "mt-4 w-full py-2 rounded-full text-sm font-medium transition",
                      isConnected
                        ? "bg-accent-green/60 text-accent-greenInk hover:bg-accent-green/70"
                        : "bg-ink text-white hover:opacity-90",
                    )}
                  >
                    {isConnected ? (
                      <span className="inline-flex items-center gap-2">
                        <Check size={14} strokeWidth={3} />
                        Connected
                      </span>
                    ) : (
                      "Connect"
                    )}
                  </button>
                </div>
              );
            })}
          </div>

          <div className="mt-10 flex items-center justify-between">
            <Link href="/dashboard" className="btn-ghost">
              Skip for now
            </Link>
            <button
              onClick={() => router.push("/dashboard")}
              className="btn-primary"
            >
              Continue to dashboard <ArrowRight size={14} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
