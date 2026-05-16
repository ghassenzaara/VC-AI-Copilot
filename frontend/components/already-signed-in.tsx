"use client";

import { useRouter } from "next/navigation";
import { useClerk, useUser } from "@clerk/nextjs";
import { ArrowRight } from "lucide-react";
import { Logo } from "./logo";

export function AlreadySignedIn() {
  const router = useRouter();
  const { signOut } = useClerk();
  const { user } = useUser();

  const firstName = user?.firstName ?? null;
  const greeting = firstName ? `Welcome back, ${firstName}` : "Welcome back";

  return (
    <div className="min-h-screen flex">
      <div className="flex-1 flex flex-col">
        <div className="px-8 pt-6">
          <Logo />
        </div>
        <div className="flex-1 flex items-center justify-center px-8">
          <div className="w-full max-w-sm">
            <div className="h-12 w-12 rounded-2xl bg-accent-green/60 flex items-center justify-center text-accent-greenInk mb-6">
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M20 6L9 17l-5-5" />
              </svg>
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-ink">
              {greeting}
            </h1>
            <p className="mt-2 text-sm text-ink-muted">
              You&apos;re already signed in. Continue to your dashboard or sign
              out to use a different account.
            </p>

            <div className="mt-7 space-y-2">
              <button
                type="button"
                onClick={() => router.push("/dashboard")}
                className="btn-primary w-full py-2.5"
              >
                Continue to dashboard
                <ArrowRight size={14} />
              </button>
              <button
                type="button"
                onClick={async () => {
                  await signOut();
                  router.push("/login");
                }}
                className="btn-outline w-full py-2.5"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="hidden lg:flex flex-1 bg-bg-card border-l border-line items-center justify-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 dot-bg opacity-50" />
        <div className="relative max-w-md">
          <p className="text-sm text-ink-muted leading-relaxed">
            “Every meeting, email, and Slack thread distilled into one
            structured deal profile. That&apos;s our edge.”
          </p>
          <p className="mt-2 text-xs text-ink-faint">— Clara, Partner</p>
        </div>
      </div>
    </div>
  );
}
