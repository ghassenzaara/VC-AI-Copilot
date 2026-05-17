---
marp: true
theme: default
paginate: true
---

# Vista
### Where promising ideas meet the right capital.

**IBM BOB Hackathon Submission**
Built on IBM WatsonX

---

## The obvious problem everyone solves

Every hackathon team this year is building the same thing:

> **A coding assistant.**
> Help developers ship faster. Help them debug faster. Help them write boilerplate faster.

We knew that. We chose to dig deeper.

**What if "shipping faster" isn't the bottleneck anymore?**

---

## The real bottleneck

With AI coding assistants, ideas ship in days, not months.
What's missing is **the investment that lets those ideas survive**.

Most promising startups never see the light of day —
not because the idea was bad,
not because the team couldn't build it,
but because **no investor found them in time to believe in them.**

---

## Why investors miss the good ideas

VCs are drowning in deal flow.

They use **Granola** for call transcripts.
**Affinity** for their CRM.
**Slack** for team debates.
**Gmail** for founder threads.

Each platform helps. **None of them talk to each other.**

So partners spend their day **coordinating tools** instead of evaluating companies.
Promising startups slip through the cracks. Investment doesn't reach them. The idea dies.

---

## The chain reaction we want to fix

```
More tool sprawl for VCs
    ↓
Fewer ideas evaluated properly
    ↓
Fewer startups funded
    ↓
Developers stop building
    ↓
Money becomes the blocker again
```

**Reverse it, and AI coding tools actually matter.**

---

## Meet Vista

**A B2B intelligence layer for venture capital firms.**

Vista unifies every signal a VC already collects —
calls, emails, CRM notes, Slack debates —
and turns them into a **living, queryable knowledge graph**
of every founder, company, and conversation in their pipeline.

So no promising startup gets forgotten.
So every founder gets a fair shot at funding.
So developers keep building.

---

## What Vista does

1. **Aggregates** every data source a VC already uses (Granola, Affinity, Gmail, Slack)
2. **Filters** noise from relevance with an LLM relevance pass
3. **Extracts** structured signals — team, traction, sector, momentum, verdict
4. **Stores** everything in a per-user knowledge graph (Neo4j) + relational store (PostgreSQL + pgvector)
5. **Clusters** companies into market maps grouped by *problem space*, not by technology
6. **Surfaces** the deals you'd otherwise forget — with momentum signals, last-touch reminders, and team debates in one view

---

## Key features

- **Unified dashboard** — KPIs, funnel, momentum split, top deals
- **Startup deep-dives** — every interaction, extraction, and team debate per company
- **Market maps** — interactive cluster visualization with LLM-generated names based on the *problem domain*
- **One-click regenerate** — re-cluster the entire portfolio as new companies arrive
- **Chatbot** — natural-language queries over your firm's knowledge graph
- **Integrations hub** — connect Granola, Affinity, Slack, Gmail in clicks
- **Full multi-tenant isolation** — every VC firm's data is cryptographically separated

---

## Technology stack

| Layer | Stack |
|---|---|
| **Frontend** | Next.js 14 (App Router) · React 18 · TypeScript · Tailwind CSS · Framer Motion |
| **Auth** | Clerk (multi-tenant) · PyJWT + JWKS verification |
| **Backend** | FastAPI · Pydantic v2 · Async + threadpool offload |
| **LLM** | **IBM WatsonX** — Llama 3.3 70B (Pro tier for extraction & naming, Flash tier for filtering) |
| **Databases** | PostgreSQL 16 + pgvector · Neo4j 5.15 (graph + APOC) |
| **ML** | scikit-learn KMeans · HDBSCAN · silhouette scoring · cosine similarity |
| **Infra** | Docker Compose · SSE streaming for long-running jobs |
| **Integrations** | Granola API · Affinity API · Gmail OAuth · Slack OAuth |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Next.js Frontend (Clerk Auth)                              │
│  Dashboard · Startups · Market Maps · Chatbot · Integrations│
└────────────────────────┬────────────────────────────────────┘
                         │ Bearer JWT
                         ▼
┌─────────────────────────────────────────────────────────────┐
│  FastAPI Backend                                            │
│  Verify JWT (JWKS) → Provision User → Route                 │
└──┬──────────────────────────────────────────────────────┬───┘
   │                                                      │
   ▼                                                      ▼
┌──────────────────────┐                    ┌─────────────────────────┐
│  Pipeline            │                    │  Per-User Storage       │
│  ┌────────────────┐  │                    │                         │
│  │ Aggregate      │◄─┼─── Granola         │  PostgreSQL + pgvector  │
│  │ Filter (LLM)   │  │    Affinity        │  ▪ structured records   │
│  │ Extract (LLM)  │──┼─── Gmail           │  ▪ embeddings           │
│  │ Embed          │  │    Slack           │  ▪ clusters / metadata  │
│  │ Cluster        │  │                    │                         │
│  │ Name (LLM)     │──┼──► IBM WatsonX     │  Neo4j 5.15             │
│  └────────────────┘  │    (Llama 3.3 70B) │  ▪ :User → :OWNS → *    │
└──────────────────────┘                    │  ▪ :Company, :Person,   │
                                            │    :Interaction,        │
                                            │    :Cluster, :Sector    │
                                            └─────────────────────────┘
```

---

## The pipeline (per company)

```
Granola │ Affinity │ Gmail │ Slack
              │
              ▼
       Aggregate per company
              │
              ▼
   Filter (WatsonX Flash) — keep only relevant interactions
              │
              ▼
   Extract (WatsonX Pro) — structured schema: team, traction, sector...
              │
              ▼
   Store in PostgreSQL (relational) + Neo4j (graph)
              │
              ▼
   Generate embedding (pgvector)
              │
              ▼
   Compute similarity edges (cosine)
              │
              ▼
   K-Means cluster on embeddings
              │
              ▼
   LLM-name clusters by *problem domain*, not by tech
```

---

## Multi-tenant data isolation

Every VC firm sees only their own portfolio. Enforced at every layer:

- **PostgreSQL** — `owner_clerk_id` column on every domain table, composite UNIQUE constraints `(owner_clerk_id, ...)`, FK chain rooted in `users(clerk_id)` with `ON DELETE CASCADE`
- **Neo4j** — every node carries `clerk_id`; `:User` anchor nodes via `[:OWNS]` edges; composite uniqueness `(clerk_id, id)` on every label
- **API** — every authenticated route depends on `get_current_user_provisioned`; every Cypher `MATCH` and every SQL `WHERE` includes `clerk_id`
- **Auth** — Clerk-issued JWT verified against JWKS with key caching; lazy user provisioning on first request — no webhooks needed

A user **cannot** see another user's data even if they craft a request with another user's company ID. The filter makes the row invisible.

---

## AI / ML highlights

- **Two-tier LLM strategy** — Llama 3.3 70B Flash for cheap-and-fast filtering, Pro for high-fidelity extraction and naming
- **Embeddings** stored in pgvector for sub-millisecond similarity lookup
- **Auto-K KMeans** — silhouette-scored search across `k ∈ [3, √n]` picks the optimal cluster count automatically
- **Problem-domain cluster naming** — the LLM prompt explicitly excludes tech terms ("AI", "LLM", "Agent"). Every modern startup uses AI; what makes a cluster meaningful is *the problem they solve*, not their toolchain.
- **Idempotent regenerate** — wipe + recluster + rename runs in seconds and refreshes the UI without a full-page reload

---

## What makes Vista different

| Existing tools | Vista |
|---|---|
| Each platform is a silo | One unified knowledge graph |
| Manual tagging & lists | Automatic LLM extraction |
| Sector tags from a dropdown | Embedding-based market maps |
| Static dashboards | Re-cluster on demand as the portfolio grows |
| Single-tenant or shared workspace | Strict per-firm cryptographic isolation |
| Vendor lock-in | Pluggable data sources, open architecture |

---

## Live demo flow

1. **Sign in with Clerk** — the firm's workspace is provisioned lazily
2. **Run the pipeline** — SSE-streamed progress across 4 sources, per-company filter → extract → store → embed
3. **Dashboard** — see KPIs, funnel, momentum at a glance
4. **Market Maps** — interactive cluster canvas, click a bubble to inspect the companies inside
5. **Regenerate** — wipe + recompute + rename in seconds, smooth UI swap
6. **Drill into a startup** — every interaction, signal, debate, and decision in one timeline
7. **Sign in as a second user** — see zero overlap. Strict isolation, no leakage.

---

## What's next

**Short term**
- Live data source webhooks (Granola, Affinity push instead of pull)
- Daily auto-refresh of clusters (same smooth regenerate flow, just on a schedule)
- Slack & Gmail OAuth fully wired (UI ready today)
- Email digest of "deals you might be forgetting"

**Medium term**
- Multi-user per firm (team workspaces with role-based access)
- Founder-side surface — let founders see (and correct) how a VC sees them
- Cross-firm benchmark mode (privacy-preserving, opt-in)

---

## Why Vista, why now

AI made building cheap.
Capital allocation is now the bottleneck.

If every promising idea found its right investor in days instead of months,
we'd unlock a generation of founders who today give up before they start.

**Vista is the connective tissue that closes that gap.**

---

## Built with IBM BOB

Vista's backend was bootstrapped end-to-end with **IBM BOB** across four working sessions (May 15–16, 2026):

- **Planned the entire system** — translated the architecture brief into a step-by-step `IMPLEMENTATION_PLAN.md` covering data model, ingestion, LLM stages, storage, and API surface
- **Implemented the first version of the backend** — FastAPI app, Postgres + Neo4j clients, all four data-source connectors (Granola, Affinity, Gmail, Slack), LLM relevance filter & extraction engine, storage orchestrator, pipeline coordinator, similarity & clustering services
- **Reviewed the codebase** for security and clarity across multiple audit rounds (auth, Pydantic v2 migration, timestamp normalization, architectural cleanup)
- **Wrote and reviewed the documentation** — `README.md`, architecture notes, and the operational runbook

BOB turned a single planning prompt into a working multi-service backend in hours, not weeks.

---

## Built on IBM WatsonX

Every LLM call in Vista — relevance filtering, structured extraction, cluster naming —
runs on **IBM WatsonX** with **Llama 3.3 70B**.

Two tiers (Flash + Pro) give us cost-effective scale on filter passes
and high-fidelity output on extraction and naming.

**Thank you.**

Questions?
