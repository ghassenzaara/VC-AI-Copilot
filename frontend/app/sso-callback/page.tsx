"use client";

import { AuthenticateWithRedirectCallback } from "@clerk/nextjs";

export default function SSOCallback() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-sm text-ink-muted">Signing you in…</div>
      <AuthenticateWithRedirectCallback
        signInForceRedirectUrl="/dashboard"
        signUpForceRedirectUrl="/onboarding"
      />
    </div>
  );
}
