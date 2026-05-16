// Types mirroring src/llm/schemas.py (ExtractionOutput).
// Keep field names in sync with the Pydantic models — these will be
// returned verbatim by the backend API.

export type Stage =
  | "Pre-seed"
  | "Seed"
  | "Series A"
  | "Series B"
  | "Series C+"
  | "Growth";

export type Momentum = "accelerating" | "stable" | "stalling" | "dead";

export type PipelineStage =
  | "Tracking"
  | "First call"
  | "Diligence"
  | "IC review"
  | "Decision";

export type Verdict = "tracking" | "diligence" | "invested" | "passed";

export type ContactRole =
  | "Founder"
  | "CEO"
  | "CTO"
  | "COO"
  | "Investor"
  | "Operator"
  | "Other";

export type InteractionType =
  | "intro_meeting"
  | "deep_dive"
  | "demo"
  | "reference_call"
  | "email"
  | "slack_message"
  | "memo"
  | "ic_review"
  | "other";

export type Channel =
  | "video"
  | "in_person"
  | "phone"
  | "email"
  | "slack"
  | "other";

export type Sentiment = "positive" | "neutral" | "negative";

export type MetricLabel =
  | "ARR"
  | "MRR"
  | "customers"
  | "burn"
  | "runway"
  | "growth_rate"
  | "margin"
  | "headcount"
  | "other";

export interface CompanySource {
  types: ("granola" | "affinity" | "slack" | "gmail")[];
  external_id?: string | null;
}

export interface Company {
  id: string | null;
  name: string;
  one_liner: string | null;
  sector: string | null;
  stage: Stage | null;
  location: string | null;
  website: string | null;
  tags: string[];
  first_met_at: string | null;
  key_strengths: string[];
  key_concerns: string[];
  deal_momentum: Momentum | null;
  source: CompanySource | null;
}

export interface DealStatus {
  pipeline_stage: PipelineStage;
  last_touch_at: string;
  next_step: string | null;
  owner: string | null;
}

export interface Contact {
  name: string;
  role: ContactRole;
  is_primary: boolean;
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  twitter: string | null;
  notes: string | null;
}

export interface MetricMention {
  label: MetricLabel;
  value: string;
  as_of: string | null;
}

export interface Quote {
  speaker: string;
  text: string;
}

export interface WhatHappened {
  summary: string;
  takeaways: string[];
  topics: string[];
  metrics_mentioned: MetricMention[];
  quotes: Quote[];
}

export interface InteractionSource {
  type: "granola" | "affinity" | "slack" | "gmail";
  url: string | null;
  external_id: string | null;
}

export interface Interaction {
  id: string;
  type: InteractionType;
  title: string;
  subtitle: string | null;
  occurred_at: string;
  duration_minutes: number | null;
  channel: Channel;
  sentiment: Sentiment;
  participants: string[];
  source: InteractionSource | null;
  what_happened: WhatHappened;
}

export interface Argument {
  argument: string;
  supporter: string | null;
  evidence: string | null;
}

export interface TeamDebate {
  detected: boolean;
  for_arguments: Argument[];
  against_arguments: Argument[];
  open_questions: string[];
}

export interface DecisionRecord {
  verdict: Verdict;
  decided_at: string | null;
  rationale: string | null;
  conditions: string[];
  check_size: string | null;
  valuation: string | null;
}

export interface Funding {
  last_round_stage: string | null;
  last_round_amount_usd: number | null;
  total_raised_usd: number | null;
}

export interface NewsItem {
  headline: string;
  url: string;
  published_at: string;
  source: string;
}

export interface Signal {
  label: string;
  detected_at: string;
}

export interface CompanyNow {
  domain: string | null;
  fetched_at: string | null;
  headcount: number | null;
  open_roles: number | null;
  funding: Funding;
  latest_news: NewsItem[];
  signals: Signal[];
}

export interface ExtractionMeta {
  model: string;
  extracted_at: string;
  confidence: number;
  warnings: string[];
}

export interface ExtractionOutput {
  company: Company;
  deal_status: DealStatus;
  contacts: Contact[];
  interactions: Interaction[];
  team_debate: TeamDebate;
  decision_record: DecisionRecord;
  company_now: CompanyNow;
  extraction_meta: ExtractionMeta;
}

// Lightweight type used for the startups list view.
export interface StartupSummary {
  id: string;
  name: string;
  one_liner: string;
  sector: string;
  stage: Stage;
  pipeline_stage: PipelineStage;
  momentum: Momentum;
  verdict: Verdict;
  last_touch_at: string;
  owner: string;
  tags: string[];
}
