"use client";

import { useEffect, useState } from "react";
import {
  Check,
  ExternalLink,
  Eye,
  EyeOff,
  Key,
  Loader2,
  Plug,
  RefreshCw,
  Shield,
  Trash2,
  Webhook,
  X,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";

type Status = "connected" | "needs_attention" | "disconnected";
type AuthMode = "api_key" | "oauth";

interface Integration {
  id: "granola" | "affinity" | "slack" | "gmail";
  name: string;
  description: string;
  brand: string;
  initial: string;
  defaultStatus: Status;
  authMode: AuthMode;
  docsUrl: string;
  account?: string;
  lastSync?: string;
  scopes: string[];
  metrics: { label: string; value: string }[];
}

const INTEGRATIONS: Integration[] = [
  {
    id: "granola",
    name: "Granola",
    description:
      "Pull meeting transcripts and notes from your founder calls in real time.",
    brand: "bg-[#FDE68A] text-[#7C2D12]",
    initial: "G",
    defaultStatus: "connected",
    authMode: "api_key",
    docsUrl: "https://docs.granola.ai/introduction",
    account: "vista-fund-team",
    lastSync: "Synced 4 min ago",
    scopes: ["transcripts.read", "calls.list", "attendees.read"],
    metrics: [
      { label: "Calls indexed", value: "184" },
      { label: "This week", value: "12" },
    ],
  },
  {
    id: "affinity",
    name: "Affinity",
    description:
      "Sync your deal pipeline, contacts, and opportunity stages bidirectionally.",
    brand: "bg-[#DBEAFE] text-[#1E3A8A]",
    initial: "A",
    defaultStatus: "connected",
    authMode: "api_key",
    docsUrl: "https://support.affinity.co/hc/en-us/articles/360032633992",
    account: "vista.affinity.co",
    lastSync: "Synced 22 min ago",
    scopes: ["lists.read", "lists.write", "persons.read"],
    metrics: [
      { label: "Opportunities", value: "47" },
      { label: "Lists synced", value: "6" },
    ],
  },
  {
    id: "slack",
    name: "Slack",
    description:
      "Capture deal-flow conversations and team debates from your channels.",
    brand: "bg-[#FBCFE8] text-[#831843]",
    initial: "S",
    defaultStatus: "needs_attention",
    authMode: "oauth",
    docsUrl: "https://api.slack.com/authentication/oauth-v2",
    account: "vista-vc.slack.com",
    lastSync: "Token expired · last sync 2d ago",
    scopes: ["channels:history", "users:read", "files:read"],
    metrics: [
      { label: "Channels", value: "4" },
      { label: "Messages indexed", value: "1.2k" },
    ],
  },
  {
    id: "gmail",
    name: "Gmail",
    description:
      "Index founder threads, intros, and follow-ups across the team inbox.",
    brand: "bg-[#FECACA] text-[#991B1B]",
    initial: "M",
    defaultStatus: "disconnected",
    authMode: "oauth",
    docsUrl: "https://developers.google.com/identity/protocols/oauth2",
    scopes: ["gmail.readonly", "gmail.metadata"],
    metrics: [],
  },
];

// Build the real OAuth authorize URL for an integration. If a client ID is
// configured via NEXT_PUBLIC_* env, build a proper authorize URL; otherwise
// fall back to the vendor's sign-in page so the button still lands the user
// somewhere real (for the hackathon demo).
function buildOauthUrl(integration: Integration): string {
  const redirect =
    typeof window !== "undefined"
      ? `${window.location.origin}/integrations`
      : "";

  if (integration.id === "slack") {
    const clientId = process.env.NEXT_PUBLIC_SLACK_CLIENT_ID;
    const scopes = "channels:history,users:read,files:read";
    if (clientId) {
      const params = new URLSearchParams({
        client_id: clientId,
        scope: scopes,
        redirect_uri: redirect,
      });
      return `https://slack.com/oauth/v2/authorize?${params.toString()}`;
    }
    return "https://slack.com/signin";
  }

  if (integration.id === "gmail") {
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;
    const scopes = [
      "https://www.googleapis.com/auth/gmail.readonly",
      "https://www.googleapis.com/auth/gmail.metadata",
    ].join(" ");
    if (clientId) {
      const params = new URLSearchParams({
        client_id: clientId,
        scope: scopes,
        redirect_uri: redirect,
        response_type: "code",
        access_type: "offline",
        prompt: "consent",
      });
      return `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
    }
    return "https://accounts.google.com/signin";
  }

  return integration.docsUrl;
}

const STATUS_PALETTE: Record<
  Status,
  { label: string; cls: string; dot: string }
> = {
  connected: {
    label: "Connected",
    cls: "bg-accent-green/50 text-accent-greenInk",
    dot: "bg-accent-greenInk",
  },
  needs_attention: {
    label: "Needs attention",
    cls: "bg-accent-amber/40 text-accent-amberInk",
    dot: "bg-accent-amberInk",
  },
  disconnected: {
    label: "Not connected",
    cls: "bg-bg-subtle border border-line text-ink-muted",
    dot: "bg-ink-faint",
  },
};

export default function IntegrationsPage() {
  const [statuses, setStatuses] = useState<Record<string, Status>>(
    Object.fromEntries(INTEGRATIONS.map((i) => [i.id, i.defaultStatus])),
  );
  const [modalFor, setModalFor] = useState<Integration | null>(null);

  function disconnect(id: Integration["id"]) {
    setStatuses((prev) => ({ ...prev, [id]: "disconnected" }));
  }

  function markConnected(id: Integration["id"]) {
    setStatuses((prev) => ({ ...prev, [id]: "connected" }));
  }

  const connectedCount = Object.values(statuses).filter(
    (s) => s === "connected",
  ).length;
  const attentionCount = Object.values(statuses).filter(
    (s) => s === "needs_attention",
  ).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="text-xs text-ink-muted">Settings</div>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">
            Integrations
          </h1>
          <p className="mt-1 text-sm text-ink-muted max-w-2xl">
            Connect the tools that feed Vista Copilot. All data is processed
            in the same region your Vista tenant is provisioned in.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button className="btn-outline">
            <Webhook size={14} />
            Webhooks
          </button>
          <button className="btn-outline">
            <Shield size={14} />
            Permissions
          </button>
        </div>
      </div>

      {/* Summary strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryCard
          label="Connected"
          value={connectedCount}
          total={INTEGRATIONS.length}
          tone="green"
        />
        <SummaryCard
          label="Needs attention"
          value={attentionCount}
          total={INTEGRATIONS.length}
          tone="amber"
        />
        <SummaryCard
          label="Available"
          value={INTEGRATIONS.length - connectedCount - attentionCount}
          total={INTEGRATIONS.length}
          tone="neutral"
        />
      </div>

      {/* Integration cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {INTEGRATIONS.map((it) => {
          const status = statuses[it.id]!;
          const palette = STATUS_PALETTE[status];
          const isConnected = status === "connected";
          const needsAttention = status === "needs_attention";

          return (
            <div
              key={it.id}
              className={cn(
                "card p-5",
                needsAttention && "border-accent-amberInk/30",
              )}
            >
              <div className="flex items-start gap-4">
                <div
                  className={cn(
                    "h-12 w-12 rounded-xl flex items-center justify-center text-lg font-semibold shrink-0",
                    it.brand,
                  )}
                >
                  {it.initial}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <div className="font-semibold text-ink">{it.name}</div>
                    <span className={cn("pill", palette.cls)}>
                      <span
                        className={cn(
                          "h-1.5 w-1.5 rounded-full",
                          palette.dot,
                        )}
                      />
                      {palette.label}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-ink-muted leading-relaxed">
                    {it.description}
                  </div>

                  {(isConnected || needsAttention) && it.account && (
                    <div className="mt-3 flex items-center gap-2 text-xs">
                      <span className="text-ink-faint">Account:</span>
                      <span className="text-ink font-medium">{it.account}</span>
                      {it.lastSync && (
                        <>
                          <span className="text-ink-faint">·</span>
                          <span
                            className={cn(
                              needsAttention
                                ? "text-accent-amberInk"
                                : "text-ink-muted",
                            )}
                          >
                            {it.lastSync}
                          </span>
                        </>
                      )}
                    </div>
                  )}

                  {it.metrics.length > 0 && isConnected && (
                    <div className="mt-3 flex gap-2">
                      {it.metrics.map((m) => (
                        <div
                          key={m.label}
                          className="flex-1 rounded-lg bg-bg-subtle border border-line px-3 py-2"
                        >
                          <div className="text-[10px] uppercase tracking-wider text-ink-faint">
                            {m.label}
                          </div>
                          <div className="text-sm font-semibold text-ink mt-0.5">
                            {m.value}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {it.scopes.map((s) => (
                      <span
                        key={s}
                        className="pill bg-bg-subtle border border-line text-ink-faint font-mono text-[10px]"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              {/* Actions */}
              <div className="mt-4 pt-4 border-t border-line flex items-center justify-between">
                <div className="flex items-center gap-2">
                  {isConnected && (
                    <>
                      <button className="btn-ghost text-xs">
                        <RefreshCw size={12} />
                        Sync now
                      </button>
                      <button
                        onClick={() => disconnect(it.id)}
                        className="btn-ghost text-xs text-accent-redInk hover:bg-accent-red/20"
                      >
                        <Trash2 size={12} />
                        Disconnect
                      </button>
                    </>
                  )}
                  {needsAttention && (
                    <button
                      onClick={() => setModalFor(it)}
                      className="btn-outline text-xs"
                    >
                      <RefreshCw size={12} />
                      Reauthorize
                    </button>
                  )}
                </div>

                <button
                  onClick={() => setModalFor(it)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full text-sm font-medium px-4 py-2 transition",
                    isConnected
                      ? "bg-bg-subtle border border-line text-ink hover:border-ink/20"
                      : needsAttention
                        ? "bg-accent-amberInk text-white hover:opacity-90"
                        : "bg-ink text-white hover:opacity-90",
                  )}
                >
                  {isConnected ? (
                    <>
                      <Check size={14} />
                      Manage
                    </>
                  ) : needsAttention ? (
                    <>
                      <Plug size={14} />
                      Reconnect
                    </>
                  ) : (
                    <>
                      <Plug size={14} />
                      Connect
                    </>
                  )}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Coming soon */}
      <div className="card p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-ink-muted">Coming soon</div>
            <div className="mt-1 text-lg font-semibold text-ink">
              Additional connectors
            </div>
            <p className="text-xs text-ink-muted mt-1">
              Tell us which tools your team needs and we will prioritize them.
            </p>
          </div>
          <button className="btn-outline">
            Request a connector
            <ExternalLink size={12} />
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { name: "Notion", initial: "N", brand: "bg-bg-subtle text-ink" },
            {
              name: "HubSpot",
              initial: "H",
              brand: "bg-[#FED7AA] text-[#7C2D12]",
            },
            {
              name: "Linear",
              initial: "L",
              brand: "bg-[#E0E7FF] text-[#3730A3]",
            },
            {
              name: "Calendly",
              initial: "C",
              brand: "bg-[#DBEAFE] text-[#1E3A8A]",
            },
          ].map((c) => (
            <div
              key={c.name}
              className="rounded-xl border border-line p-3 flex items-center gap-3 hover:border-ink/20 transition cursor-pointer"
            >
              <div
                className={cn(
                  "h-9 w-9 rounded-lg flex items-center justify-center text-sm font-semibold",
                  c.brand,
                )}
              >
                {c.initial}
              </div>
              <div className="flex-1">
                <div className="text-sm font-medium text-ink">{c.name}</div>
                <div className="text-[11px] text-ink-faint">In design</div>
              </div>
              <ChevronRight size={14} className="text-ink-faint" />
            </div>
          ))}
        </div>
      </div>

      {modalFor && (
        <ConnectModal
          integration={modalFor}
          currentStatus={statuses[modalFor.id]!}
          onClose={() => setModalFor(null)}
          onConnected={() => {
            markConnected(modalFor.id);
            setModalFor(null);
          }}
          onDisconnect={() => {
            disconnect(modalFor.id);
            setModalFor(null);
          }}
        />
      )}
    </div>
  );
}

function ConnectModal({
  integration,
  currentStatus,
  onClose,
  onConnected,
  onDisconnect,
}: {
  integration: Integration;
  currentStatus: Status;
  onClose: () => void;
  onConnected: () => void;
  onDisconnect: () => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [revealed, setRevealed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const isOauth = integration.authMode === "oauth";
  const isConnected = currentStatus === "connected";

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  function submitApiKey(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim() || submitting) return;
    setSubmitting(true);
    // Simulate validating the key against the vendor's /me endpoint.
    window.setTimeout(() => {
      setSubmitting(false);
      onConnected();
    }, 900);
  }

  function startOauth() {
    if (submitting) return;
    setSubmitting(true);
    // Open the real vendor authorize page (or sign-in fallback) so the
    // user actually lands on Slack/Google. The modal stays in a "waiting"
    // state and self-completes after a short delay — backend wiring of
    // the OAuth callback can replace this later.
    const url = buildOauthUrl(integration);
    window.open(url, "_blank", "noopener,noreferrer");
    window.setTimeout(() => {
      setSubmitting(false);
      onConnected();
    }, 1500);
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-md bg-bg-card border border-line rounded-2xl shadow-elev overflow-hidden"
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-line flex items-start gap-3">
          <div
            className={cn(
              "h-10 w-10 rounded-xl flex items-center justify-center text-base font-semibold shrink-0",
              integration.brand,
            )}
          >
            {integration.initial}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-base font-semibold text-ink">
              {isConnected
                ? `Manage ${integration.name}`
                : `Connect ${integration.name}`}
            </div>
            <div className="text-xs text-ink-muted">
              {isOauth
                ? "OAuth 2.0 · token managed by " + integration.name
                : "API key · stored encrypted at rest"}
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-ink-faint hover:text-ink p-1 rounded"
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-5 space-y-4">
          {isConnected ? (
            <ManagePanel integration={integration} />
          ) : isOauth ? (
            <OauthPanel
              integration={integration}
              submitting={submitting}
              onStart={startOauth}
            />
          ) : (
            <ApiKeyPanel
              integration={integration}
              apiKey={apiKey}
              setApiKey={setApiKey}
              revealed={revealed}
              setRevealed={setRevealed}
              submitting={submitting}
              onSubmit={submitApiKey}
            />
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 border-t border-line bg-bg-subtle/60 flex items-center justify-between">
          {isConnected ? (
            <>
              <button
                onClick={onDisconnect}
                className="text-sm text-accent-redInk hover:underline"
              >
                Disconnect
              </button>
              <button onClick={onClose} className="btn-primary">
                Done
              </button>
            </>
          ) : (
            <>
              <a
                href={integration.docsUrl}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-ink-muted hover:text-ink inline-flex items-center gap-1"
              >
                {isOauth ? "About this scope" : "Where do I find my key?"}
                <ExternalLink size={11} />
              </a>
              <button onClick={onClose} className="btn-ghost">
                Cancel
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function ApiKeyPanel({
  integration,
  apiKey,
  setApiKey,
  revealed,
  setRevealed,
  submitting,
  onSubmit,
}: {
  integration: Integration;
  apiKey: string;
  setApiKey: (v: string) => void;
  revealed: boolean;
  setRevealed: (v: boolean) => void;
  submitting: boolean;
  onSubmit: (e: React.FormEvent) => void;
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <p className="text-sm text-ink-muted leading-relaxed">
        Paste your <span className="text-ink font-medium">{integration.name}</span>{" "}
        API key. We will verify it against {integration.name}&apos;s{" "}
        <code className="px-1 py-0.5 rounded bg-bg-subtle border border-line text-[11px]">
          /me
        </code>{" "}
        endpoint before saving.
      </p>

      <div>
        <label className="text-xs font-medium text-ink">API key</label>
        <div className="mt-1.5 flex items-center gap-2 bg-white border border-line rounded-xl px-3 py-2 focus-within:border-ink/30 focus-within:ring-2 focus-within:ring-ink/5 transition">
          <Key size={14} className="text-ink-faint shrink-0" />
          <input
            type={revealed ? "text" : "password"}
            autoFocus
            autoComplete="off"
            spellCheck={false}
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={
              integration.id === "granola"
                ? "grn_live_…"
                : "afn_…"
            }
            className="bg-transparent flex-1 outline-none text-sm text-ink placeholder:text-ink-faint font-mono"
          />
          <button
            type="button"
            onClick={() => setRevealed(!revealed)}
            className="text-ink-faint hover:text-ink"
            aria-label={revealed ? "Hide key" : "Show key"}
          >
            {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-ink-faint">
          Keys are encrypted with AES-256 and only decrypted at sync time.
        </p>
      </div>

      <div>
        <div className="text-xs font-medium text-ink mb-2">Granted access</div>
        <div className="flex flex-wrap gap-1.5">
          {integration.scopes.map((s) => (
            <span
              key={s}
              className="pill bg-bg-subtle border border-line text-ink-muted font-mono text-[10px]"
            >
              {s}
            </span>
          ))}
        </div>
      </div>

      <button
        type="submit"
        disabled={!apiKey.trim() || submitting}
        className={cn(
          "w-full btn-primary justify-center",
          (!apiKey.trim() || submitting) && "opacity-60 cursor-not-allowed",
        )}
      >
        {submitting ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            Verifying…
          </>
        ) : (
          <>
            <Plug size={14} />
            Connect {integration.name}
          </>
        )}
      </button>
    </form>
  );
}

function OauthPanel({
  integration,
  submitting,
  onStart,
}: {
  integration: Integration;
  submitting: boolean;
  onStart: () => void;
}) {
  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-muted leading-relaxed">
        You will be redirected to{" "}
        <span className="text-ink font-medium">{integration.name}</span> to
        approve access. {integration.name} will not share your password — we
        only receive a scoped access token.
      </p>

      <div className="rounded-xl bg-bg-subtle border border-line p-4">
        <div className="text-xs font-medium text-ink mb-2">
          Vista will be able to
        </div>
        <ul className="space-y-1.5">
          {integration.scopes.map((s) => (
            <li
              key={s}
              className="flex items-start gap-2 text-xs text-ink-muted"
            >
              <Check
                size={12}
                className="text-accent-greenInk mt-0.5 shrink-0"
                strokeWidth={3}
              />
              <code className="font-mono text-[11px] text-ink">{s}</code>
            </li>
          ))}
        </ul>
      </div>

      <button
        onClick={onStart}
        disabled={submitting}
        className={cn(
          "w-full btn-primary justify-center",
          submitting && "opacity-60 cursor-not-allowed",
        )}
      >
        {submitting ? (
          <>
            <Loader2 size={14} className="animate-spin" />
            Waiting for {integration.name}…
          </>
        ) : (
          <>
            Continue with {integration.name}
            <ExternalLink size={12} />
          </>
        )}
      </button>

      <p className="text-[11px] text-ink-faint text-center">
        You can revoke access at any time from {integration.name}&apos;s
        settings.
      </p>
    </div>
  );
}

function ManagePanel({ integration }: { integration: Integration }) {
  return (
    <div className="space-y-4">
      {integration.account && (
        <div className="rounded-xl border border-line p-3 flex items-center gap-3">
          <div className="h-8 w-8 rounded-full bg-accent-green/60 flex items-center justify-center">
            <Check
              size={14}
              className="text-accent-greenInk"
              strokeWidth={3}
            />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-ink truncate">
              {integration.account}
            </div>
            {integration.lastSync && (
              <div className="text-xs text-ink-muted">
                {integration.lastSync}
              </div>
            )}
          </div>
        </div>
      )}

      <div>
        <div className="text-xs font-medium text-ink mb-2">Granted scopes</div>
        <div className="flex flex-wrap gap-1.5">
          {integration.scopes.map((s) => (
            <span
              key={s}
              className="pill bg-bg-subtle border border-line text-ink-muted font-mono text-[10px]"
            >
              {s}
            </span>
          ))}
        </div>
      </div>

      <button className="w-full btn-outline justify-center">
        <RefreshCw size={14} />
        Sync now
      </button>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  total,
  tone,
}: {
  label: string;
  value: number;
  total: number;
  tone: "green" | "amber" | "neutral";
}) {
  const toneCls: Record<typeof tone, string> = {
    green: "bg-accent-green/50 text-accent-greenInk",
    amber: "bg-accent-amber/40 text-accent-amberInk",
    neutral: "bg-bg-subtle border border-line text-ink-muted",
  };
  return (
    <div className="card p-5">
      <div className="flex items-center justify-between">
        <div className="text-xs text-ink-muted">{label}</div>
        <span className={cn("pill", toneCls[tone])}>{value}/{total}</span>
      </div>
      <div className="mt-2 text-3xl font-semibold tracking-tight">
        {value}
      </div>
      <div className="mt-3 h-1.5 bg-bg-subtle rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            tone === "green"
              ? "bg-accent-greenInk"
              : tone === "amber"
                ? "bg-accent-amberInk"
                : "bg-ink/40",
          )}
          style={{ width: `${(value / Math.max(total, 1)) * 100}%` }}
        />
      </div>
    </div>
  );
}
