"use client";

/**
 * Hidden operator console for running the full extraction pipeline against
 * mock_data.json. Not linked from anywhere in the app — reach it directly
 * via /op-x7k9m2-pipeline-runner.
 *
 * Backend contract: POST /admin/run-mock-pipeline with optional
 * X-Admin-Token header; response is text/event-stream with `step`,
 * `substep`, `company`, `error`, and `done` events.
 */

import { useCallback, useMemo, useRef, useState } from "react";

type StreamEvent =
  | { event: "step"; data: Record<string, unknown> }
  | { event: "substep"; data: Record<string, unknown> }
  | { event: "company"; data: Record<string, unknown> }
  | { event: "error"; data: Record<string, unknown> }
  | { event: "done"; data: Record<string, unknown> }
  | { event: "log"; data: Record<string, unknown> };

type LogLine = {
  id: number;
  ts: string;
  event: StreamEvent["event"];
  payload: Record<string, unknown>;
};

const API_BASE =
  (typeof window !== "undefined" &&
    (process.env.NEXT_PUBLIC_API_URL as string | undefined)) ||
  "http://localhost:8000";

function nowStamp() {
  return new Date().toLocaleTimeString([], { hour12: false });
}

function parseSseChunk(buffer: string): {
  events: StreamEvent[];
  remainder: string;
} {
  const events: StreamEvent[] = [];
  let remainder = buffer;
  while (true) {
    const sep = remainder.indexOf("\n\n");
    if (sep === -1) break;
    const frame = remainder.slice(0, sep);
    remainder = remainder.slice(sep + 2);

    let event: StreamEvent["event"] = "log";
    let data: Record<string, unknown> = {};
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim() as StreamEvent["event"];
      } else if (line.startsWith("data:")) {
        const raw = line.slice(5).trim();
        try {
          data = JSON.parse(raw);
        } catch {
          data = { raw };
        }
      }
    }
    events.push({ event, data } as StreamEvent);
  }
  return { events, remainder };
}

export default function PipelineRunnerPage() {
  const [token, setToken] = useState("");
  const [clerkId, setClerkId] = useState("");
  const [running, setRunning] = useState(false);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [pingState, setPingState] = useState<{
    status: "idle" | "checking" | "ok" | "fail";
    detail?: string;
  }>({ status: "idle" });
  const abortRef = useRef<AbortController | null>(null);
  const idRef = useRef(0);

  const testConnection = useCallback(async () => {
    setPingState({ status: "checking" });
    try {
      const res = await fetch(`${API_BASE}/admin/ping`, {
        method: "GET",
        headers: token ? { "X-Admin-Token": token } : {},
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setPingState({
          status: "fail",
          detail: `HTTP ${res.status}: ${JSON.stringify(body)}`,
        });
      } else {
        setPingState({
          status: "ok",
          detail: `Backend reachable. token_required=${body.token_required}`,
        });
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setPingState({
        status: "fail",
        detail: `Could not reach ${API_BASE} — ${msg}. Is uvicorn running on port 8000?`,
      });
    }
  }, [token]);

  const appendLogs = useCallback((events: StreamEvent[]) => {
    if (!events.length) return;
    setLogs((prev) => {
      const next = [...prev];
      for (const e of events) {
        idRef.current += 1;
        next.push({
          id: idRef.current,
          ts: nowStamp(),
          event: e.event,
          payload: e.data,
        });
      }
      return next;
    });
  }, []);

  const reset = useCallback(() => {
    setLogs([]);
    setSummary(null);
    setErrorMsg(null);
    idRef.current = 0;
  }, []);

  const [wiping, setWiping] = useState(false);
  const wipe = useCallback(async () => {
    if (running || wiping) return;
    const ok = window.confirm(
      "Wipe ALL data from PostgreSQL and Neo4j? Schema is preserved; only the contents are deleted. This cannot be undone.",
    );
    if (!ok) return;
    setWiping(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/admin/wipe-databases`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "X-Admin-Token": token } : {}),
        },
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${JSON.stringify(body)}`);
      }
      reset();
      idRef.current += 1;
      setLogs([
        {
          id: idRef.current,
          ts: nowStamp(),
          event: "step",
          payload: { step: "wipe", status: "done", ...body },
        },
      ]);
    } catch (e: unknown) {
      setErrorMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setWiping(false);
    }
  }, [running, wiping, token, reset]);

  const run = useCallback(async () => {
    if (running) return;
    if (!clerkId.trim()) {
      setErrorMsg("clerk_id is required — paste the target user's Clerk ID first.");
      return;
    }
    reset();
    setRunning(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch(`${API_BASE}/admin/run-mock-pipeline`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "X-Admin-Token": token } : {}),
        },
        body: JSON.stringify({ clerk_id: clerkId.trim() }),
        signal: controller.signal,
      });

      if (!res.ok || !res.body) {
        const txt = await res.text().catch(() => "");
        throw new Error(
          `HTTP ${res.status} ${res.statusText}${txt ? ` — ${txt}` : ""}`,
        );
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { events, remainder } = parseSseChunk(buffer);
        buffer = remainder;
        appendLogs(events);
        const doneEvent = events.find((e) => e.event === "done");
        if (doneEvent) {
          setSummary(doneEvent.data);
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      // "Failed to fetch" / "NetworkError" all mean the backend is unreachable.
      const looksLikeNetwork =
        /failed to fetch|networkerror|load failed|err_connection/i.test(msg);
      setErrorMsg(
        looksLikeNetwork
          ? `Could not reach ${API_BASE}. The FastAPI backend is probably not running. Start it with:\n\n  .\\.venv\\Scripts\\Activate.ps1\n  uvicorn src.api.main:app --reload --port 8000\n\n(original error: ${msg})`
          : msg,
      );
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }, [running, token, clerkId, appendLogs, reset]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const stats = useMemo(() => {
    let processed = 0;
    let failed = 0;
    let lastStep: string | null = null;
    for (const line of logs) {
      if (line.event === "company") {
        const status = line.payload.status as string | undefined;
        if (status === "done") processed += 1;
        if (status === "failed" || status === "skipped") failed += 1;
      } else if (line.event === "step") {
        lastStep = (line.payload.step as string | null) ?? lastStep;
      }
    }
    return { processed, failed, lastStep };
  }, [logs]);

  // Live "now processing" indicator — derived from the latest `company` /
  // `substep` events so the operator can see exactly which company (and which
  // phase of it) is in flight right now.
  const current = useMemo(() => {
    let index = 0;
    let total = 0;
    let company = "";
    let phase = "";
    let companyStatus: "running" | "done" | "failed" | "skipped" | null = null;
    let lastGlobalStep: string | null = null;
    let lastGlobalStatus: string | null = null;

    for (const line of logs) {
      const p = line.payload;
      if (line.event === "company") {
        const status = p.status as string | undefined;
        if (status === "starting") {
          index = (p.index as number) ?? index;
          total = (p.total as number) ?? total;
          company = (p.company as string) ?? company;
          phase = "filter";
          companyStatus = "running";
        } else if (
          status === "done" ||
          status === "failed" ||
          status === "skipped"
        ) {
          if ((p.company as string) === company) {
            companyStatus = status as "done" | "failed" | "skipped";
          }
        }
      } else if (line.event === "substep") {
        if ((p.company as string) === company) {
          phase = (p.phase as string) ?? phase;
        }
      } else if (line.event === "step") {
        lastGlobalStep = (p.step as string | null) ?? lastGlobalStep;
        lastGlobalStatus = (p.status as string | null) ?? lastGlobalStatus;
      }
    }
    return {
      index,
      total,
      company,
      phase,
      companyStatus,
      lastGlobalStep,
      lastGlobalStatus,
    };
  }, [logs]);

  const progressPct =
    current.total > 0
      ? Math.min(100, Math.round((current.index / current.total) * 100))
      : 0;

  return (
    <main className="min-h-screen bg-bg-base text-ink">
      <div className="mx-auto max-w-5xl px-6 py-10">
        <header className="mb-8">
          <p className="text-xs uppercase tracking-wide text-ink-muted">
            internal • not linked
          </p>
          <h1 className="mt-1 text-2xl font-semibold">
            Pipeline Operator Console
          </h1>
          <p className="mt-2 text-sm text-ink-muted">
            Runs the full extraction pipeline against
            <code className="mx-1 rounded bg-bg-subtle px-1.5 py-0.5 text-xs">
              mock_data.json
            </code>
            : relevance filter → extraction → similarity → clustering. All
            results land in PostgreSQL (embeddings) and Neo4j (graph).
          </p>
        </header>

        <section className="card p-5 mb-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex-1">
              <label className="block text-xs font-medium text-ink-muted mb-1">
                Admin token (X-Admin-Token header)
              </label>
              <input
                type="password"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                placeholder="Leave empty if backend has no token set"
                disabled={running}
                className="w-full rounded-xl border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink/30"
              />
            </div>
            <div className="flex-1">
              <label className="block text-xs font-medium text-ink-muted mb-1">
                Target user clerk_id
              </label>
              <input
                type="text"
                value={clerkId}
                onChange={(e) => setClerkId(e.target.value)}
                placeholder="user_xxxxxxxxxxxxxxxxxxxxxxxxx"
                disabled={running}
                className="w-full rounded-xl border border-line bg-white px-3 py-2 text-sm outline-none focus:border-ink/30 font-mono"
              />
            </div>
            <div className="flex gap-2">
              {!running ? (
                <button
                  onClick={run}
                  className="btn-primary disabled:opacity-50"
                  disabled={running}
                >
                  Run pipeline
                </button>
              ) : (
                <button onClick={stop} className="btn-outline">
                  Stop
                </button>
              )}
              <button
                onClick={reset}
                className="btn-ghost"
                disabled={running}
              >
                Clear
              </button>
              <button
                onClick={testConnection}
                className="btn-ghost"
                disabled={running || pingState.status === "checking"}
              >
                {pingState.status === "checking"
                  ? "Testing…"
                  : "Test connection"}
              </button>
              <button
                onClick={wipe}
                className="btn-ghost text-accent-redInk hover:text-accent-redInk"
                disabled={running || wiping}
                title="Truncate Postgres + delete every Neo4j node"
              >
                {wiping ? "Wiping…" : "Wipe DBs"}
              </button>
            </div>
          </div>
          <p className="mt-3 text-xs text-ink-faint">
            API: <code>{API_BASE}/admin/run-mock-pipeline</code>
          </p>
          {pingState.status !== "idle" && (
            <p
              className={`mt-2 text-xs ${
                pingState.status === "ok"
                  ? "text-accent-greenInk"
                  : pingState.status === "fail"
                  ? "text-accent-redInk"
                  : "text-ink-muted"
              }`}
            >
              {pingState.status === "ok" && "✓ "}
              {pingState.status === "fail" && "✗ "}
              {pingState.detail}
            </p>
          )}
        </section>

        <section className="grid grid-cols-2 gap-4 mb-6 sm:grid-cols-4">
          <Stat
            label="Progress"
            value={
              current.total > 0
                ? `${current.index} / ${current.total}`
                : "—"
            }
          />
          <Stat label="Companies done" value={stats.processed} />
          <Stat label="Failed / skipped" value={stats.failed} />
          <Stat label="Current step" value={stats.lastStep ?? "—"} />
        </section>

        {(running || logs.length > 0) && (
          <section className="card p-5 mb-6">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <p className="text-xs uppercase tracking-wide text-ink-muted">
                  {current.companyStatus === "done"
                    ? "Last processed"
                    : current.companyStatus === "failed" ||
                      current.companyStatus === "skipped"
                    ? `Last (${current.companyStatus})`
                    : current.company
                    ? "Now processing"
                    : current.lastGlobalStep
                    ? "Pipeline stage"
                    : "Starting…"}
                </p>
                <p className="mt-1 text-lg font-semibold truncate">
                  {current.company ||
                    (current.lastGlobalStep
                      ? prettyStep(current.lastGlobalStep)
                      : "Connecting to backend…")}
                </p>
                <p className="mt-1 text-xs text-ink-muted">
                  {current.companyStatus === "running" && current.phase
                    ? `Phase: ${current.phase}`
                    : current.lastGlobalStep
                    ? `Global step: ${current.lastGlobalStep}${
                        current.lastGlobalStatus
                          ? ` (${current.lastGlobalStatus})`
                          : ""
                      }`
                    : "Awaiting first event from server"}
                </p>
              </div>
              <div className="text-right shrink-0">
                <p className="text-2xl font-semibold tabular-nums">
                  {current.total > 0
                    ? `${current.index}/${current.total}`
                    : "—"}
                </p>
                <p className="text-xs text-ink-faint">{progressPct}%</p>
              </div>
            </div>

            <div className="mt-4 h-2 w-full overflow-hidden rounded-full bg-bg-subtle">
              <div
                className={`h-full transition-all duration-300 ${
                  current.companyStatus === "failed"
                    ? "bg-accent-redInk"
                    : "bg-ink"
                }`}
                style={{ width: `${progressPct}%` }}
              />
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {PHASES.map((ph) => (
                <PhasePill
                  key={ph}
                  phase={ph}
                  active={current.phase === ph && current.companyStatus === "running"}
                />
              ))}
            </div>
          </section>
        )}

        {errorMsg && (
          <div className="mb-4 rounded-xl border border-accent-red bg-accent-red/20 px-4 py-3 text-sm text-accent-redInk">
            {errorMsg}
          </div>
        )}

        {summary && (
          <section className="card p-5 mb-6">
            <h2 className="text-sm font-medium mb-2">Run summary</h2>
            <pre className="text-xs whitespace-pre-wrap text-ink-muted">
              {JSON.stringify(summary, null, 2)}
            </pre>
          </section>
        )}

        <section className="card p-0 overflow-hidden">
          <div className="px-5 py-3 border-b border-line flex items-center justify-between">
            <h2 className="text-sm font-medium">Event stream</h2>
            <span className="text-xs text-ink-faint">
              {logs.length} events
            </span>
          </div>
          <div className="max-h-[60vh] overflow-y-auto font-mono text-xs">
            {logs.length === 0 ? (
              <div className="px-5 py-8 text-center text-ink-faint">
                Idle — click <span className="font-semibold">Run pipeline</span>{" "}
                to begin.
              </div>
            ) : (
              <ul className="divide-y divide-line/60">
                {logs.map((line) => (
                  <li key={line.id} className="px-5 py-2 flex gap-3">
                    <span className="text-ink-faint shrink-0">{line.ts}</span>
                    <EventBadge type={line.event} />
                    <span className="text-ink-muted truncate flex-1">
                      {summarizePayload(line.event, line.payload)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}

// Per-company phases emitted by the backend `substep` events (admin.py).
const PHASES = ["filter", "extract", "store", "embed", "geocode"] as const;

function prettyStep(step: string): string {
  const map: Record<string, string> = {
    boot: "Starting pipeline…",
    load_mock: "Loading mock_data.json…",
    per_company: "Per-company processing complete",
    similarity: "Computing cross-company similarities…",
    clustering: "Clustering companies in embedding space…",
    naming: "Naming clusters via LLM…",
  };
  return map[step] ?? step;
}

function PhasePill({
  phase,
  active,
}: {
  phase: (typeof PHASES)[number];
  active: boolean;
}) {
  return (
    <span
      className={`rounded-full px-2.5 py-1 text-[10px] uppercase tracking-wider transition ${
        active
          ? "bg-ink text-white"
          : "bg-bg-subtle text-ink-faint border border-line"
      }`}
    >
      {phase}
    </span>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card p-4">
      <p className="text-xs text-ink-muted">{label}</p>
      <p className="mt-1 text-xl font-semibold">{value}</p>
    </div>
  );
}

function EventBadge({ type }: { type: StreamEvent["event"] }) {
  const map: Record<StreamEvent["event"], string> = {
    step: "bg-accent-blue/30 text-accent-blueInk",
    substep: "bg-bg-subtle text-ink-muted",
    company: "bg-accent-green/40 text-accent-greenInk",
    error: "bg-accent-red/30 text-accent-redInk",
    done: "bg-ink text-white",
    log: "bg-bg-subtle text-ink-muted",
  };
  return (
    <span
      className={`shrink-0 rounded-md px-1.5 py-0.5 text-[10px] uppercase tracking-wider ${map[type]}`}
    >
      {type}
    </span>
  );
}

function summarizePayload(
  event: StreamEvent["event"],
  payload: Record<string, unknown>,
): string {
  switch (event) {
    case "step": {
      const step = payload.step as string | undefined;
      const status = payload.status as string | undefined;
      const extras = Object.entries(payload)
        .filter(([k]) => !["step", "status"].includes(k))
        .map(([k, v]) => `${k}=${formatValue(v)}`)
        .join(" ");
      return [step, status, extras].filter(Boolean).join(" • ");
    }
    case "substep": {
      const company = payload.company as string | undefined;
      const phase = payload.phase as string | undefined;
      const status = payload.status as string | undefined;
      const extras = Object.entries(payload)
        .filter(([k]) => !["company", "phase", "status"].includes(k))
        .map(([k, v]) => `${k}=${formatValue(v)}`)
        .join(" ");
      return [company && `[${company}]`, phase, status, extras]
        .filter(Boolean)
        .join(" ");
    }
    case "company": {
      const company = payload.company as string | undefined;
      const status = payload.status as string | undefined;
      const extras = Object.entries(payload)
        .filter(([k]) => !["company", "status"].includes(k))
        .map(([k, v]) => `${k}=${formatValue(v)}`)
        .join(" ");
      return [company && `[${company}]`, status, extras]
        .filter(Boolean)
        .join(" ");
    }
    case "error":
      return (payload.message as string | undefined) ?? JSON.stringify(payload);
    case "done":
      return Object.entries(payload)
        .map(([k, v]) => `${k}=${formatValue(v)}`)
        .join(" ");
    default:
      return JSON.stringify(payload);
  }
}

function formatValue(v: unknown): string {
  if (v == null) return "—";
  if (Array.isArray(v)) return `[${v.length}]`;
  if (typeof v === "object") return JSON.stringify(v);
  if (typeof v === "number") return v.toLocaleString();
  return String(v);
}
