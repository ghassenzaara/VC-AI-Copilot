// Pure enum arrays mirroring the backend Pydantic Literals.
// No company data lives here — that comes from the API.

export const ALL_STAGES = [
  "Pre-seed",
  "Seed",
  "Series A",
  "Series B",
  "Series C+",
  "Growth",
] as const;

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
