import type { ExtractionOutput, StartupSummary } from "./types";

// One full ExtractionOutput, mirroring test_output.json exactly.
// Used by the startup detail page.
export const neuralEdge: ExtractionOutput = {
  company: {
    id: "neuraledge",
    name: "NeuralEdge",
    one_liner:
      "AI-powered GPU orchestration for European ML teams",
    sector: "AI Infrastructure",
    stage: "Series A",
    location: "Amsterdam, Netherlands",
    website: "https://neuraledge.ai",
    tags: ["B2B", "SaaS", "Cloud Computing", "AI", "Machine Learning"],
    first_met_at: "2025-09-03",
    key_strengths: [
      "Strong technical team",
      "Unique cross-cloud routing intelligence",
      "Impressive cost savings for customers",
    ],
    key_concerns: [
      "Potential complexity in multi-region failover",
      "Dependence on cloud providers' spot instance pricing",
    ],
    deal_momentum: "stable",
    source: { types: ["granola", "slack", "gmail"], external_id: null },
  },
  deal_status: {
    pipeline_stage: "Decision",
    last_touch_at: "2025-11-20T10:00:00Z",
    next_step: "Schedule first board meeting",
    owner: "Clara Hoffmann",
  },
  contacts: [
    {
      name: "Tomás Reyes",
      role: "Founder",
      is_primary: true,
      email: "tomas@neuraledge.ai",
      phone: null,
      linkedin: null,
      twitter: null,
      notes: "Ex-founding engineer at a YC-backed MLOps startup",
    },
    {
      name: "Priya Nair",
      role: "CTO",
      is_primary: false,
      email: "priya@neuraledge.ai",
      phone: null,
      linkedin: null,
      twitter: null,
      notes: "Previously led infrastructure at Booking.com",
    },
  ],
  interactions: [
    {
      id: "not_neuraledge_001",
      type: "intro_meeting",
      title: "NeuralEdge — First Intro Call",
      subtitle: "45 min · video call",
      occurred_at: "2025-09-03T10:00:00Z",
      duration_minutes: 45,
      channel: "video",
      sentiment: "positive",
      participants: ["Clara Hoffmann", "Tomás Reyes", "Priya Nair"],
      source: {
        type: "granola",
        url: null,
        external_id: "not_neuraledge_001",
      },
      what_happened: {
        summary:
          "First call with NeuralEdge discussing their product, traction, and competitive moat.",
        takeaways: [
          "NeuralEdge has a unique cross-cloud routing intelligence.",
          "They claim 40% cost reduction for ML training workloads.",
          "Currently at €185K MRR, growing 18% MoM.",
        ],
        topics: ["traction", "team", "competitive moat"],
        metrics_mentioned: [
          { label: "MRR", value: "€185K", as_of: "2025-09-03" },
          { label: "growth_rate", value: "18%", as_of: "2025-09-03" },
        ],
        quotes: [
          {
            speaker: "Tomás Reyes",
            text: "We save our median customer 38% on their cloud bill from day one.",
          },
        ],
      },
    },
    {
      id: "not_neuraledge_002",
      type: "deep_dive",
      title: "Technical Deep Dive with Marcus",
      subtitle: "60 min · video call",
      occurred_at: "2025-09-10T14:00:00Z",
      duration_minutes: 60,
      channel: "video",
      sentiment: "positive",
      participants: ["Marcus Weber", "Priya Nair"],
      source: {
        type: "granola",
        url: null,
        external_id: "not_neuraledge_002",
      },
      what_happened: {
        summary:
          "Technical session with Priya discussing NeuralEdge's routing algorithm and failure handling.",
        takeaways: [
          "Multi-armed bandit approach with Thompson sampling.",
          "Failure recovery has a 90-second guarantee.",
        ],
        topics: ["technical architecture", "failure handling"],
        metrics_mentioned: [],
        quotes: [],
      },
    },
    {
      id: "msg_neuraledge_001",
      type: "email",
      title: "Follow-up Materials",
      subtitle: "Email from Tomás",
      occurred_at: "2025-09-04T09:00:00Z",
      duration_minutes: null,
      channel: "email",
      sentiment: "positive",
      participants: ["Clara Hoffmann", "Tomás Reyes"],
      source: {
        type: "gmail",
        url: null,
        external_id: "msg_neuraledge_001",
      },
      what_happened: {
        summary:
          "Tomás sent follow-up materials and granted Marcus access to their API docs.",
        takeaways: [
          "NeuralEdge closed Zalando as a customer.",
          "They are in conversations with two other European VCs.",
        ],
        topics: ["traction", "deal context"],
        metrics_mentioned: [
          { label: "customers", value: "24", as_of: "2025-09-04" },
        ],
        quotes: [],
      },
    },
    {
      id: "slack_neuraledge_003",
      type: "slack_message",
      title: "IC Memo",
      subtitle: "Slack · investments channel",
      occurred_at: "2025-09-15T11:00:00Z",
      duration_minutes: null,
      channel: "slack",
      sentiment: "positive",
      participants: ["Clara Hoffmann"],
      source: {
        type: "slack",
        url: null,
        external_id: "slack_neuraledge_003",
      },
      what_happened: {
        summary: "Clara shared the NeuralEdge IC memo with the team.",
        takeaways: [
          "NeuralEdge is asking for €8M at a €40M pre-money valuation.",
          "Yellow is targeting €3M of the round.",
        ],
        topics: ["deal context", "valuation"],
        metrics_mentioned: [],
        quotes: [],
      },
    },
    {
      id: "msg_neuraledge_003",
      type: "email",
      title: "Closing Confirmed",
      subtitle: "Email from Tomás",
      occurred_at: "2025-10-28T09:00:00Z",
      duration_minutes: null,
      channel: "email",
      sentiment: "positive",
      participants: ["Clara Hoffmann", "Tomás Reyes"],
      source: {
        type: "gmail",
        url: null,
        external_id: "msg_neuraledge_003",
      },
      what_happened: {
        summary: "Tomás confirmed the closing of the investment round.",
        takeaways: [
          "All documents signed.",
          "Wires from Yellow and Project A received.",
        ],
        topics: ["deal closure"],
        metrics_mentioned: [],
        quotes: [],
      },
    },
    {
      id: "slack_neuraledge_004",
      type: "slack_message",
      title: "Public Announcement",
      subtitle: "Slack · portfolio channel",
      occurred_at: "2025-11-20T10:00:00Z",
      duration_minutes: null,
      channel: "slack",
      sentiment: "positive",
      participants: ["Clara Hoffmann"],
      source: {
        type: "slack",
        url: null,
        external_id: "slack_neuraledge_004",
      },
      what_happened: {
        summary: "NeuralEdge announced their Series A publicly.",
        takeaways: [
          "TechCrunch picked up the story.",
          "December MRR tracking at €210K.",
        ],
        topics: ["public announcement", "traction"],
        metrics_mentioned: [
          { label: "MRR", value: "€210K", as_of: "2025-12-01" },
        ],
        quotes: [],
      },
    },
  ],
  team_debate: {
    detected: true,
    for_arguments: [
      {
        argument: "Cross-cloud routing IP is genuinely defensible.",
        supporter: "Marcus Weber",
        evidence: "Reviewed architecture diagrams + customer testimonials.",
      },
      {
        argument: "Customer growth trajectory is strong.",
        supporter: "Clara Hoffmann",
        evidence: "24 paying customers, 18% MoM revenue growth.",
      },
    ],
    against_arguments: [
      {
        argument: "Risk of cloud providers cutting spot pricing.",
        supporter: "Ahmed Zaara",
        evidence: "Spot prices dropped 30% last year on AWS.",
      },
    ],
    open_questions: [
      "What is the long-term defensibility if hyperscalers ship comparable routing?",
      "Do we need a US foothold before Series B?",
    ],
  },
  decision_record: {
    verdict: "invested",
    decided_at: "2025-10-28T00:00:00Z",
    rationale:
      "Strong technical team, unique cross-cloud routing intelligence, and impressive cost savings for customers.",
    conditions: [],
    check_size: "€3M",
    valuation: "€40M",
  },
  company_now: {
    domain: "neuraledge.ai",
    fetched_at: "2025-11-25T08:00:00Z",
    headcount: 28,
    open_roles: 6,
    funding: {
      last_round_stage: "Series A",
      last_round_amount_usd: 8_700_000,
      total_raised_usd: 10_200_000,
    },
    latest_news: [
      {
        headline: "NeuralEdge raises $9M Series A led by Yellow",
        url: "https://techcrunch.com/neuraledge-series-a",
        published_at: "2025-11-21",
        source: "TechCrunch",
      },
    ],
    signals: [
      { label: "Hiring 6 engineers", detected_at: "2025-11-22" },
      { label: "Zalando case study published", detected_at: "2025-11-18" },
    ],
  },
  extraction_meta: {
    model: "meta-llama/llama-3-3-70b-instruct",
    extracted_at: "2026-05-16T10:12:38.644994Z",
    confidence: 0.9,
    warnings: [],
  },
};

// Lightweight summaries for the list / dashboard views.
export const startups: StartupSummary[] = [
  {
    id: "neuraledge",
    name: "NeuralEdge",
    one_liner: "AI-powered GPU orchestration for European ML teams",
    sector: "AI Infrastructure",
    stage: "Series A",
    pipeline_stage: "Decision",
    momentum: "stable",
    verdict: "invested",
    last_touch_at: "2025-11-20T10:00:00Z",
    owner: "Clara Hoffmann",
    tags: ["B2B", "SaaS", "AI", "Cloud"],
  },
  {
    id: "luminary-health",
    name: "Luminary Health",
    one_liner: "Remote cardiac monitoring for European primary care clinics",
    sector: "Digital Health",
    stage: "Seed",
    pipeline_stage: "Diligence",
    momentum: "accelerating",
    verdict: "diligence",
    last_touch_at: "2025-12-08T14:00:00Z",
    owner: "Marcus Weber",
    tags: ["Healthcare", "B2B", "Hardware"],
  },
  {
    id: "quantumledger",
    name: "QuantumLedger",
    one_liner: "Privacy-preserving compliance audits for fintech",
    sector: "FinTech",
    stage: "Pre-seed",
    pipeline_stage: "First call",
    momentum: "stable",
    verdict: "tracking",
    last_touch_at: "2025-12-15T11:30:00Z",
    owner: "Ahmed Zaara",
    tags: ["FinTech", "Compliance", "B2B"],
  },
  {
    id: "fleetmind",
    name: "FleetMind",
    one_liner: "AI-driven route optimization for European logistics fleets",
    sector: "Mobility",
    stage: "Series A",
    pipeline_stage: "IC review",
    momentum: "accelerating",
    verdict: "diligence",
    last_touch_at: "2025-12-20T09:00:00Z",
    owner: "Clara Hoffmann",
    tags: ["B2B", "Logistics", "AI"],
  },
  {
    id: "polardb",
    name: "PolarDB",
    one_liner: "Real-time analytical database for streaming pipelines",
    sector: "Developer Tools",
    stage: "Seed",
    pipeline_stage: "Tracking",
    momentum: "stalling",
    verdict: "tracking",
    last_touch_at: "2025-10-02T15:30:00Z",
    owner: "Marcus Weber",
    tags: ["Developer Tools", "Database", "B2B"],
  },
  {
    id: "aeronova",
    name: "AeroNova",
    one_liner: "Carbon-neutral cargo drones for last-mile rural delivery",
    sector: "Climate",
    stage: "Seed",
    pipeline_stage: "Decision",
    momentum: "dead",
    verdict: "passed",
    last_touch_at: "2025-09-12T16:00:00Z",
    owner: "Ahmed Zaara",
    tags: ["Climate", "Hardware", "Mobility"],
  },
  {
    id: "synthlab",
    name: "SynthLab",
    one_liner: "Synthetic data generation for healthcare ML training",
    sector: "AI Infrastructure",
    stage: "Pre-seed",
    pipeline_stage: "First call",
    momentum: "accelerating",
    verdict: "tracking",
    last_touch_at: "2025-12-22T13:00:00Z",
    owner: "Clara Hoffmann",
    tags: ["Healthcare", "AI", "Privacy"],
  },
  {
    id: "graphwise",
    name: "GraphWise",
    one_liner: "Knowledge-graph copilot for enterprise sales teams",
    sector: "Enterprise SaaS",
    stage: "Seed",
    pipeline_stage: "Diligence",
    momentum: "stable",
    verdict: "diligence",
    last_touch_at: "2025-12-18T10:00:00Z",
    owner: "Marcus Weber",
    tags: ["Enterprise", "AI", "B2B"],
  },
];

export const ALL_STAGES = [
  "Pre-seed",
  "Seed",
  "Series A",
  "Series B",
  "Series C+",
  "Growth",
] as const;

export const ALL_SECTORS = Array.from(
  new Set(startups.map((s) => s.sector)),
).sort();

export const ALL_MOMENTUMS = [
  "accelerating",
  "stable",
  "stalling",
  "dead",
] as const;

export const ALL_VERDICTS = [
  "tracking",
  "diligence",
  "invested",
  "passed",
] as const;

export const ALL_PIPELINE_STAGES = [
  "Tracking",
  "First call",
  "Diligence",
  "IC review",
  "Decision",
] as const;

// Activity feed for the dashboard — pulled from recent interactions across companies.
export const recentActivity = [
  {
    id: "a1",
    company: "NeuralEdge",
    companyId: "neuraledge",
    text: "Public announcement on Slack",
    at: "2025-11-20T10:00:00Z",
    type: "slack_message" as const,
  },
  {
    id: "a2",
    company: "FleetMind",
    companyId: "fleetmind",
    text: "IC review scheduled",
    at: "2025-12-20T09:00:00Z",
    type: "ic_review" as const,
  },
  {
    id: "a3",
    company: "SynthLab",
    companyId: "synthlab",
    text: "First intro call completed",
    at: "2025-12-22T13:00:00Z",
    type: "intro_meeting" as const,
  },
  {
    id: "a4",
    company: "Luminary Health",
    companyId: "luminary-health",
    text: "Reference call with chief cardiologist",
    at: "2025-12-08T14:00:00Z",
    type: "reference_call" as const,
  },
  {
    id: "a5",
    company: "GraphWise",
    companyId: "graphwise",
    text: "Diligence memo shared",
    at: "2025-12-18T10:00:00Z",
    type: "memo" as const,
  },
];

// Lightweight chart series for the dashboard "Pipeline Trend" sparkline.
export const pipelineTrend = [
  { month: "Jul", value: 8 },
  { month: "Aug", value: 12 },
  { month: "Sep", value: 18 },
  { month: "Oct", value: 22 },
  { month: "Nov", value: 25 },
  { month: "Dec", value: 32 },
];
