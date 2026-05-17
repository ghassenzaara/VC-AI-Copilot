// Typed fetch helpers for every backend endpoint the UI uses.
// Every call requires a Clerk session token, which the backend verifies
// against its JWKS to scope reads/writes to the calling user.

import type {
  ExtractionOutput,
  MarketMapResponse,
  StartupSummary,
  PipelineStage,
  Momentum,
  Verdict,
} from "./types";

export const API_BASE =
  (typeof window !== "undefined" &&
    (process.env.NEXT_PUBLIC_API_URL as string | undefined)) ||
  "http://localhost:8000";

async function authedGetJSON<T>(path: string, token: string): Promise<T> {
  if (!token) {
    throw new Error("Missing Clerk session token");
  }
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} ${body}`);
  }
  return res.json() as Promise<T>;
}

async function authedPostJSON<T>(
  path: string,
  token: string,
  body?: unknown,
): Promise<T> {
  if (!token) {
    throw new Error("Missing Clerk session token");
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const respBody = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} ${res.statusText} ${respBody}`);
  }
  return res.json() as Promise<T>;
}

// ---- Companies ----

export function fetchCompanies(token: string): Promise<StartupSummary[]> {
  return authedGetJSON<StartupSummary[]>("/companies", token);
}

export function fetchCompanyFull(
  id: string,
  token: string
): Promise<ExtractionOutput> {
  return authedGetJSON<ExtractionOutput>(
    `/companies/${encodeURIComponent(id)}/full`,
    token
  );
}

// ---- Market map ----

export function fetchMarketMap(token: string): Promise<MarketMapResponse> {
  return authedGetJSON<MarketMapResponse>("/market-map", token);
}

export interface RegenerateMarketMapResponse {
  status: "ok";
  clustering: {
    n_clusters: number;
    n_companies: number;
    n_noise: number;
    silhouette_score: number;
    cluster_sizes: Record<string, number>;
  };
  naming: { named: number; total: number };
}

export function regenerateMarketMap(
  token: string,
): Promise<RegenerateMarketMapResponse> {
  return authedPostJSON<RegenerateMarketMapResponse>(
    "/market-map/regenerate",
    token,
  );
}

// ---- Dashboard ----

export interface DashboardSummary {
  kpis: {
    total_deals: number;
    invested: number;
    accelerating: number;
    needs_followup: number;
  };
  funnel: { stage: PipelineStage; count: number }[];
  momentum_split: { label: Momentum; count: number }[];
  pipeline_trend: { month: string; value: number }[];
  recent_activity: {
    id: string;
    companyId: string;
    company: string;
    text: string;
    at: string;
  }[];
  top_deals: {
    id: string;
    name: string;
    sector: string;
    pipeline_stage: PipelineStage;
    momentum: Momentum;
    verdict: Verdict;
    owner: string;
    last_touch_at: string;
  }[];
}

export function fetchDashboardSummary(
  token: string
): Promise<DashboardSummary> {
  return authedGetJSON<DashboardSummary>("/dashboard/summary", token);
}
