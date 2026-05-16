"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth, useSignIn, useSignUp } from "@clerk/nextjs";
import { Logo } from "@/components/logo";
import { Eye, EyeOff, ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

type Mode = "login" | "register";
type Step = "form" | "verify-email" | "verify-client-trust";

function extractClerkError(err: any): string {
  if (!err) return "Something went wrong.";
  const first = err?.errors?.[0] ?? err;
  return (
    first?.longMessage ??
    first?.message ??
    err?.message ??
    "Something went wrong."
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { isLoaded: clerkReady } = useAuth();
  const { signIn } = useSignIn();
  const { signUp } = useSignUp();

  const [mode, setMode] = useState<Mode>("login");
  const [step, setStep] = useState<Step>("form");
  const [showPass, setShowPass] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");

  useEffect(() => {
    console.log("[auth] clerk init", {
      clerkReady,
      hasSignIn: !!signIn,
      hasSignUp: !!signUp,
      publishableKey: !!process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
    });
  }, [clerkReady, signIn, signUp]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!clerkReady || !signIn || !signUp) {
      setError("Authentication is still loading. Please try again in a moment.");
      return;
    }
    setError(null);
    setSubmitting(true);

    try {
      if (mode === "login") {
        const { error: signInError } = await signIn.password({
          identifier: email,
          password,
        });
        if (signInError) {
          setError(extractClerkError(signInError));
          return;
        }

        if (signIn.status === "complete") {
          await signIn.finalize();
          router.push("/dashboard");
          return;
        }

        if (signIn.status === "needs_client_trust") {
          const { error: sendError } = await signIn.emailCode.sendCode();
          if (sendError) {
            setError(extractClerkError(sendError));
            return;
          }
          setStep("verify-client-trust");
          return;
        }

        console.warn("[auth] unhandled sign-in status", signIn.status);
        setError(`Sign-in needs an extra step (${signIn.status}).`);
      } else {
        const [firstName, ...rest] = name.trim().split(" ");
        const lastName = rest.join(" ");
        const { error: createError } = await signUp.create({
          emailAddress: email,
          password,
          firstName: firstName || undefined,
          lastName: lastName || undefined,
        });
        if (createError) {
          setError(extractClerkError(createError));
          return;
        }
        const { error: sendError } =
          await signUp.verifications.sendEmailCode();
        if (sendError) {
          setError(extractClerkError(sendError));
          return;
        }
        setStep("verify-email");
      }
    } catch (err: any) {
      console.error("[auth] submit failed", err);
      setError(extractClerkError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerifyEmail(e: React.FormEvent) {
    e.preventDefault();
    if (!signUp) return;
    setError(null);
    setSubmitting(true);
    try {
      const { error: verifyError } =
        await signUp.verifications.verifyEmailCode({ code });
      if (verifyError) {
        setError(extractClerkError(verifyError));
        return;
      }
      if (signUp.status === "complete") {
        await signUp.finalize();
        router.push("/onboarding");
      } else if (signUp.status === "missing_requirements") {
        console.warn("[auth] sign-up missing fields", {
          missingFields: signUp.missingFields,
          unverifiedFields: signUp.unverifiedFields,
          requiredFields: signUp.requiredFields,
        });
        const missing = (signUp.missingFields ?? []).join(", ");
        setError(
          missing
            ? `Your Clerk app requires: ${missing}. Disable these in Clerk Dashboard → User & Authentication, or collect them in the form.`
            : "Sign-up needs more information that this form doesn't collect.",
        );
      } else {
        setError(`Sign-up needs an extra step (${signUp.status}).`);
      }
    } catch (err: any) {
      console.error("[auth] verify failed", err);
      setError(extractClerkError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVerifyClientTrust(e: React.FormEvent) {
    e.preventDefault();
    if (!signIn) return;
    setError(null);
    setSubmitting(true);
    try {
      const { error: verifyError } = await signIn.emailCode.verifyCode({
        code,
      });
      if (verifyError) {
        setError(extractClerkError(verifyError));
        return;
      }
      if (signIn.status === "complete") {
        await signIn.finalize();
        router.push("/dashboard");
      } else {
        setError(`Sign-in needs an extra step (${signIn.status}).`);
      }
    } catch (err: any) {
      console.error("[auth] client trust verify failed", err);
      setError(extractClerkError(err));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGoogle() {
    if (!clerkReady || !signIn) {
      setError("Authentication is still loading. Please try again in a moment.");
      return;
    }
    setError(null);
    try {
      const callbackUrl = `${window.location.origin}/sso-callback`;
      await signIn.sso({
        strategy: "oauth_google",
        redirectUrl: callbackUrl,
        redirectCallbackUrl: callbackUrl,
      });
    } catch (err: any) {
      console.error("[auth] google oauth failed", err);
      setError(extractClerkError(err));
    }
  }

  const onVerifySubmit =
    step === "verify-email" ? handleVerifyEmail : handleVerifyClientTrust;
  const verifyTitle =
    step === "verify-email" ? "Check your email" : "One more step";
  const verifySubtitle =
    step === "verify-email"
      ? `We sent a verification code to ${email}.`
      : `New device detected. We sent a verification code to ${email}.`;


  return (
    <div className="min-h-screen flex">
      {/* Left side — form */}
      <div className="flex-1 flex flex-col">
        <div className="px-8 pt-6">
          <Logo />
        </div>

        <div className="flex-1 flex items-center justify-center px-8">
          <div className="w-full max-w-sm">
            <h1 className="text-3xl font-semibold tracking-tight text-ink">
              {step !== "form"
                ? verifyTitle
                : mode === "login"
                  ? "Welcome back"
                  : "Create your account"}
            </h1>
            <p className="mt-2 text-sm text-ink-muted">
              {step !== "form"
                ? verifySubtitle
                : mode === "login"
                  ? "Sign in to access your deal intelligence."
                  : "Start tracking your portfolio in minutes."}
            </p>

            {step === "form" && (
              <div className="mt-7 inline-flex bg-bg-card border border-line rounded-full p-1">
                <button
                  onClick={() => {
                    setMode("login");
                    setError(null);
                  }}
                  className={cn(
                    "px-4 py-1.5 text-sm rounded-full transition",
                    mode === "login"
                      ? "bg-ink text-white"
                      : "text-ink-muted hover:text-ink",
                  )}
                >
                  Sign in
                </button>
                <button
                  onClick={() => {
                    setMode("register");
                    setError(null);
                  }}
                  className={cn(
                    "px-4 py-1.5 text-sm rounded-full transition",
                    mode === "register"
                      ? "bg-ink text-white"
                      : "text-ink-muted hover:text-ink",
                  )}
                >
                  Sign up
                </button>
              </div>
            )}

            {step !== "form" ? (
              <form className="mt-6 space-y-4" onSubmit={onVerifySubmit}>
                <div>
                  <label className="text-xs text-ink-muted">
                    Verification code
                  </label>
                  <input
                    className="input mt-1.5 tracking-widest text-center"
                    placeholder="123456"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    inputMode="numeric"
                    autoFocus
                    required
                  />
                </div>

                {error && (
                  <p className="text-xs text-red-500" role="alert">
                    {error}
                  </p>
                )}

                <button
                  type="submit"
                  className="btn-primary w-full py-2.5"
                  disabled={submitting}
                >
                  {submitting ? "Verifying…" : "Verify"}
                  <ArrowRight size={14} />
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setStep("form");
                    setCode("");
                    setError(null);
                  }}
                  className="text-xs text-ink-muted hover:text-ink underline-offset-4 hover:underline"
                >
                  Back
                </button>
              </form>
            ) : (
              <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
                {mode === "register" && (
                  <div>
                    <label className="text-xs text-ink-muted">Full name</label>
                    <input
                      className="input mt-1.5"
                      placeholder="Ghassen Zaara"
                      autoComplete="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                    />
                  </div>
                )}

                <div>
                  <label className="text-xs text-ink-muted">Email</label>
                  <input
                    className="input mt-1.5"
                    placeholder="you@firm.vc"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label className="text-xs text-ink-muted">Password</label>
                  <div className="relative mt-1.5">
                    <input
                      className="input pr-10"
                      placeholder="••••••••"
                      type={showPass ? "text" : "password"}
                      autoComplete={
                        mode === "register" ? "new-password" : "current-password"
                      }
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                    />
                    <button
                      type="button"
                      onClick={() => setShowPass((p) => !p)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-faint hover:text-ink"
                      aria-label="Toggle password visibility"
                    >
                      {showPass ? <EyeOff size={16} /> : <Eye size={16} />}
                    </button>
                  </div>
                  {mode === "register" && (
                    <p className="mt-1.5 text-[11px] text-ink-faint">
                      8+ characters with a number and a symbol.
                    </p>
                  )}
                </div>

                {mode === "login" && (
                  <div className="flex items-center justify-between text-xs">
                    <label className="flex items-center gap-2 text-ink-muted">
                      <input
                        type="checkbox"
                        className="rounded border-line accent-ink"
                      />
                      Remember me
                    </label>
                    <Link
                      href="#"
                      className="text-ink-muted hover:text-ink underline-offset-4 hover:underline"
                    >
                      Forgot password?
                    </Link>
                  </div>
                )}

                {error && (
                  <p className="text-xs text-red-500" role="alert">
                    {error}
                  </p>
                )}

                {/* Required by Clerk for bot protection on sign-up */}
                <div id="clerk-captcha" className="min-h-[1px]" />

                <button
                  type="submit"
                  className="btn-primary w-full py-2.5"
                  disabled={submitting || !clerkReady}
                >
                  {!clerkReady
                    ? "Loading…"
                    : submitting
                      ? mode === "login"
                        ? "Signing in…"
                        : "Creating account…"
                      : mode === "login"
                        ? "Sign in"
                        : "Create account"}
                  <ArrowRight size={14} />
                </button>

                <div className="relative my-5">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-line" />
                  </div>
                  <div className="relative flex justify-center">
                    <span className="bg-bg-base px-3 text-[11px] uppercase tracking-wider text-ink-faint">
                      or continue with
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleGoogle}
                  disabled={!clerkReady}
                  className="btn-outline w-full py-2.5"
                >
                  <GoogleIcon /> Google
                </button>
              </form>
            )}

            <p className="mt-8 text-xs text-ink-faint text-center">
              By continuing you agree to our Terms & Privacy Policy.
            </p>
          </div>
        </div>
      </div>

      {/* Right side — visual */}
      <div className="hidden lg:flex flex-1 bg-bg-card border-l border-line items-center justify-center p-12 relative overflow-hidden">
        <div className="absolute inset-0 dot-bg opacity-50" />
        <div className="relative max-w-md">
          <div className="card p-6 shadow-elev">
            <div className="text-xs text-ink-muted">Pipeline this quarter</div>
            <div className="mt-2 flex items-baseline gap-2">
              <div className="text-3xl font-semibold tracking-tight">32</div>
              <span className="pill bg-accent-green/60 text-accent-greenInk">
                +18%
              </span>
            </div>
            <div className="mt-4 grid grid-cols-5 gap-1.5 h-16 items-end">
              {[40, 65, 30, 80, 55].map((h, i) => (
                <div
                  key={i}
                  className="rounded-md bg-ink/80"
                  style={{ height: `${h}%` }}
                />
              ))}
            </div>
          </div>

          <div className="card p-5 mt-4 shadow-elev">
            <div className="flex items-center gap-3">
              <div className="h-9 w-9 rounded-xl bg-bg-subtle border border-line flex items-center justify-center text-xs font-semibold">
                NE
              </div>
              <div className="flex-1">
                <div className="font-medium text-sm">NeuralEdge</div>
                <div className="text-xs text-ink-muted">
                  AI-powered GPU orchestration
                </div>
              </div>
              <span className="pill bg-accent-green/60 text-accent-greenInk">
                Invested
              </span>
            </div>
          </div>

          <p className="mt-10 text-sm text-ink-muted leading-relaxed">
            “Every meeting, email, and Slack thread distilled into one
            structured deal profile. That&apos;s our edge.”
          </p>
          <p className="mt-2 text-xs text-ink-faint">— Clara, Partner</p>
        </div>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#FFC107"
        d="M43.6 20.5H42V20H24v8h11.3c-1.6 4.7-6.1 8-11.3 8-6.6 0-12-5.4-12-12s5.4-12 12-12c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.2-.1-2.3-.4-3.5z"
      />
      <path
        fill="#FF3D00"
        d="M6.3 14.7l6.6 4.8C14.6 16 18.9 13 24 13c3 0 5.8 1.1 7.9 3l5.7-5.7C34 6.1 29.3 4 24 4 16.3 4 9.7 8.4 6.3 14.7z"
      />
      <path
        fill="#4CAF50"
        d="M24 44c5.2 0 9.9-2 13.4-5.2l-6.2-5.2C29.2 35 26.7 36 24 36c-5.2 0-9.6-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z"
      />
      <path
        fill="#1976D2"
        d="M43.6 20.5H42V20H24v8h11.3c-.8 2.3-2.2 4.3-4.1 5.6l6.2 5.2C40.9 35.9 44 30.4 44 24c0-1.2-.1-2.3-.4-3.5z"
      />
    </svg>
  );
}
