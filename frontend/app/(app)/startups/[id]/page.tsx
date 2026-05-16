"use client";

import { notFound, useParams } from "next/navigation";
import Link from "next/link";
import {
  ArrowLeft,
  Globe,
  MapPin,
  Calendar,
  Mail,
  ExternalLink,
  Sparkles,
  AlertTriangle,
  MessageSquare,
  Video,
  Hash,
  Building2,
  Users,
  Quote as QuoteIcon,
} from "lucide-react";
import { neuralEdge, startups } from "@/lib/mock-data";
import {
  MomentumBadge,
  PipelinePill,
  SentimentDot,
  Tag,
  VerdictBadge,
} from "@/components/badges";
import { formatDate, initials, relativeTime } from "@/lib/utils";
import type {
  InteractionType,
  ExtractionOutput,
} from "@/lib/types";

const interactionIcon: Record<InteractionType, typeof Video> = {
  intro_meeting: Video,
  deep_dive: Video,
  demo: Video,
  reference_call: Video,
  email: Mail,
  slack_message: Hash,
  memo: MessageSquare,
  ic_review: Building2,
  other: MessageSquare,
};

export default function StartupDetailPage() {
  const params = useParams<{ id: string }>();
  const summary = startups.find((s) => s.id === params.id);
  if (!summary) notFound();

  // Only NeuralEdge has full data in mock; others render a "thin" view.
  const data: ExtractionOutput | null =
    params.id === "neuraledge" ? neuralEdge : null;

  return (
    <div className="space-y-6">
      {/* Back */}
      <Link
        href="/startups"
        className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
      >
        <ArrowLeft size={14} /> Back to startups
      </Link>

      {/* Header */}
      <div className="card p-6">
        <div className="flex items-start gap-5">
          <div className="h-16 w-16 rounded-2xl bg-bg-subtle border border-line flex items-center justify-center text-xl font-semibold text-ink">
            {initials(summary.name)}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-2xl font-semibold tracking-tight">
                {summary.name}
              </h1>
              <VerdictBadge verdict={summary.verdict} />
              <MomentumBadge momentum={summary.momentum} />
            </div>
            <p className="mt-2 text-sm text-ink-muted">{summary.one_liner}</p>

            <div className="mt-4 flex items-center gap-5 flex-wrap text-xs text-ink-muted">
              <div className="flex items-center gap-1.5">
                <Building2 size={13} /> {summary.sector}
              </div>
              {data?.company.location && (
                <div className="flex items-center gap-1.5">
                  <MapPin size={13} /> {data.company.location}
                </div>
              )}
              {data?.company.website && (
                <a
                  href={data.company.website}
                  className="flex items-center gap-1.5 hover:text-ink"
                  target="_blank"
                  rel="noreferrer"
                >
                  <Globe size={13} /> {data.company.website.replace("https://", "")}
                  <ExternalLink size={11} />
                </a>
              )}
              {data?.company.first_met_at && (
                <div className="flex items-center gap-1.5">
                  <Calendar size={13} /> First met{" "}
                  {formatDate(data.company.first_met_at)}
                </div>
              )}
            </div>

            <div className="mt-4 flex items-center gap-1.5 flex-wrap">
              <Tag>{summary.stage}</Tag>
              <PipelinePill stage={summary.pipeline_stage} />
              {summary.tags.map((t) => (
                <Tag key={t}>{t}</Tag>
              ))}
            </div>
          </div>

          <div className="text-right">
            <div className="text-xs text-ink-muted">Owner</div>
            <div className="text-sm font-medium mt-0.5">{summary.owner}</div>
            <div className="mt-3 text-xs text-ink-muted">Last touch</div>
            <div className="text-sm mt-0.5">
              {relativeTime(summary.last_touch_at)}
            </div>
          </div>
        </div>
      </div>

      {/* Two-column main */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          {/* Strengths & concerns */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="card p-5">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Sparkles size={14} className="text-accent-greenInk" />
                Key strengths
              </div>
              {data ? (
                <ul className="mt-4 space-y-2.5">
                  {data.company.key_strengths.map((s, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-accent-greenInk" />
                      <span className="text-sm text-ink">{s}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyHint text="No strengths extracted yet" />
              )}
            </div>
            <div className="card p-5">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <AlertTriangle size={14} className="text-accent-redInk" />
                Key concerns
              </div>
              {data ? (
                <ul className="mt-4 space-y-2.5">
                  {data.company.key_concerns.map((c, i) => (
                    <li key={i} className="flex items-start gap-2.5">
                      <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-accent-redInk" />
                      <span className="text-sm text-ink">{c}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyHint text="No concerns flagged" />
              )}
            </div>
          </div>

          {/* Interaction timeline */}
          <div className="card p-5">
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">Interaction timeline</div>
              <div className="text-xs text-ink-muted">
                {data?.interactions.length ?? 0} total
              </div>
            </div>

            {data ? (
              <div className="mt-5 space-y-4">
                {[...data.interactions]
                  .sort(
                    (a, b) =>
                      new Date(b.occurred_at).getTime() -
                      new Date(a.occurred_at).getTime(),
                  )
                  .map((interaction) => {
                    const Icon = interactionIcon[interaction.type];
                    return (
                      <div
                        key={interaction.id}
                        className="flex gap-4 pb-4 border-b border-line last:border-0"
                      >
                        <div className="flex flex-col items-center pt-1">
                          <div className="h-8 w-8 rounded-full bg-bg-subtle border border-line flex items-center justify-center">
                            <Icon size={14} className="text-ink-muted" />
                          </div>
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <div className="font-medium text-sm text-ink">
                              {interaction.title}
                            </div>
                            <SentimentDot sentiment={interaction.sentiment} />
                            <div className="text-xs text-ink-faint">
                              {formatDate(interaction.occurred_at)}
                            </div>
                          </div>
                          {interaction.subtitle && (
                            <div className="text-xs text-ink-muted mt-0.5">
                              {interaction.subtitle}
                            </div>
                          )}
                          <p className="mt-2.5 text-sm text-ink-muted leading-relaxed">
                            {interaction.what_happened.summary}
                          </p>

                          {interaction.what_happened.takeaways.length > 0 && (
                            <ul className="mt-3 space-y-1.5">
                              {interaction.what_happened.takeaways.map(
                                (t, i) => (
                                  <li
                                    key={i}
                                    className="flex items-start gap-2 text-sm"
                                  >
                                    <span className="mt-1.5 h-1 w-1 rounded-full bg-ink-faint" />
                                    <span className="text-ink">{t}</span>
                                  </li>
                                ),
                              )}
                            </ul>
                          )}

                          {interaction.what_happened.metrics_mentioned.length >
                            0 && (
                            <div className="mt-3 flex items-center gap-2 flex-wrap">
                              {interaction.what_happened.metrics_mentioned.map(
                                (m, i) => (
                                  <span
                                    key={i}
                                    className="pill bg-bg-subtle border border-line text-ink"
                                  >
                                    <span className="text-ink-muted mr-1">
                                      {m.label}
                                    </span>
                                    {m.value}
                                  </span>
                                ),
                              )}
                            </div>
                          )}

                          {interaction.what_happened.quotes.length > 0 && (
                            <div className="mt-3 card-subtle p-3 border-l-2 border-l-ink/30">
                              <QuoteIcon
                                size={12}
                                className="text-ink-faint mb-1"
                              />
                              {interaction.what_happened.quotes.map((q, i) => (
                                <div key={i} className="text-sm">
                                  <span className="italic text-ink">
                                    “{q.text}”
                                  </span>
                                  <span className="text-xs text-ink-muted ml-2">
                                    — {q.speaker}
                                  </span>
                                </div>
                              ))}
                            </div>
                          )}

                          <div className="mt-3 flex items-center gap-1.5 flex-wrap">
                            {interaction.participants.map((p) => (
                              <span
                                key={p}
                                className="text-[11px] text-ink-muted bg-bg-subtle border border-line rounded-full px-2 py-0.5"
                              >
                                {p}
                              </span>
                            ))}
                          </div>
                        </div>
                      </div>
                    );
                  })}
              </div>
            ) : (
              <EmptyHint text="No interactions logged yet" />
            )}
          </div>

          {/* Team debate */}
          {data?.team_debate.detected && (
            <div className="card p-5">
              <div className="text-sm font-semibold">Team debate</div>
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-ink-muted mb-3">
                    Arguments for
                  </div>
                  <div className="space-y-3">
                    {data.team_debate.for_arguments.map((a, i) => (
                      <ArgumentCard key={i} argument={a} positive />
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-ink-muted mb-3">
                    Arguments against
                  </div>
                  <div className="space-y-3">
                    {data.team_debate.against_arguments.map((a, i) => (
                      <ArgumentCard key={i} argument={a} positive={false} />
                    ))}
                  </div>
                </div>
              </div>
              {data.team_debate.open_questions.length > 0 && (
                <div className="mt-5 pt-5 border-t border-line">
                  <div className="text-xs text-ink-muted mb-3">
                    Open questions
                  </div>
                  <ul className="space-y-2">
                    {data.team_debate.open_questions.map((q, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm">
                        <span className="mt-2 h-1 w-1 rounded-full bg-ink-faint" />
                        <span className="text-ink">{q}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right column */}
        <div className="space-y-4">
          {/* Deal status */}
          <div className="card p-5">
            <div className="text-sm font-semibold">Deal status</div>
            <dl className="mt-4 space-y-3 text-sm">
              <Detail
                label="Pipeline"
                value={<PipelinePill stage={summary.pipeline_stage} />}
              />
              <Detail
                label="Verdict"
                value={<VerdictBadge verdict={summary.verdict} />}
              />
              <Detail
                label="Owner"
                value={<span className="text-ink">{summary.owner}</span>}
              />
              {data?.deal_status.next_step && (
                <Detail
                  label="Next step"
                  value={
                    <span className="text-ink">{data.deal_status.next_step}</span>
                  }
                />
              )}
              <Detail
                label="Last touch"
                value={
                  <span className="text-ink-muted">
                    {formatDate(summary.last_touch_at)}
                  </span>
                }
              />
            </dl>
          </div>

          {/* Decision record */}
          {data && data.decision_record.verdict !== "tracking" && (
            <div className="card p-5">
              <div className="text-sm font-semibold">Decision record</div>
              <dl className="mt-4 space-y-3 text-sm">
                {data.decision_record.check_size && (
                  <Detail
                    label="Check size"
                    value={
                      <span className="text-ink font-medium">
                        {data.decision_record.check_size}
                      </span>
                    }
                  />
                )}
                {data.decision_record.valuation && (
                  <Detail
                    label="Valuation"
                    value={
                      <span className="text-ink font-medium">
                        {data.decision_record.valuation}
                      </span>
                    }
                  />
                )}
                {data.decision_record.decided_at && (
                  <Detail
                    label="Decided"
                    value={
                      <span className="text-ink-muted">
                        {formatDate(data.decision_record.decided_at)}
                      </span>
                    }
                  />
                )}
              </dl>
              {data.decision_record.rationale && (
                <p className="mt-4 pt-4 border-t border-line text-sm text-ink-muted leading-relaxed">
                  {data.decision_record.rationale}
                </p>
              )}
            </div>
          )}

          {/* Contacts */}
          {data && data.contacts.length > 0 && (
            <div className="card p-5">
              <div className="flex items-center gap-2 text-sm font-semibold">
                <Users size={14} className="text-ink-muted" />
                Contacts
              </div>
              <div className="mt-4 space-y-3">
                {data.contacts.map((c, i) => (
                  <div key={i} className="flex items-start gap-3">
                    <div className="h-9 w-9 rounded-full bg-bg-subtle border border-line flex items-center justify-center text-xs font-semibold">
                      {initials(c.name)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <div className="text-sm font-medium">{c.name}</div>
                        {c.is_primary && (
                          <span className="pill bg-ink text-white">
                            Primary
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-ink-muted">{c.role}</div>
                      {c.email && (
                        <div className="text-xs text-ink-faint mt-0.5 truncate">
                          {c.email}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Company now */}
          {data?.company_now.headcount && (
            <div className="card p-5">
              <div className="text-sm font-semibold">Company now</div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <NowStat label="Headcount" value={data.company_now.headcount} />
                <NowStat
                  label="Open roles"
                  value={data.company_now.open_roles ?? 0}
                />
              </div>
              {data.company_now.signals.length > 0 && (
                <div className="mt-4 pt-4 border-t border-line">
                  <div className="text-xs text-ink-muted mb-2">
                    Recent signals
                  </div>
                  <ul className="space-y-1.5">
                    {data.company_now.signals.map((s, i) => (
                      <li key={i} className="text-xs text-ink">
                        · {s.label}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Detail({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-xs text-ink-muted">{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function NowStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl bg-bg-subtle border border-line p-3">
      <div className="text-xs text-ink-muted">{label}</div>
      <div className="text-lg font-semibold mt-1">{value}</div>
    </div>
  );
}

function ArgumentCard({
  argument,
  positive,
}: {
  argument: { argument: string; supporter: string | null; evidence: string | null };
  positive: boolean;
}) {
  return (
    <div
      className={`rounded-xl border p-3 ${
        positive
          ? "border-accent-green/40 bg-accent-green/10"
          : "border-accent-red/40 bg-accent-red/10"
      }`}
    >
      <div className="text-sm text-ink">{argument.argument}</div>
      {argument.supporter && (
        <div className="mt-2 text-xs text-ink-muted">
          — {argument.supporter}
        </div>
      )}
    </div>
  );
}

function EmptyHint({ text }: { text: string }) {
  return (
    <div className="mt-4 text-xs text-ink-faint italic">{text}</div>
  );
}
