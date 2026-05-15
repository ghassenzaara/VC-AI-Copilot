# VC Intelligence Knowledge Graph - Implementation Plan

## Project Overview

Building a production-grade VC deal intelligence platform with:
- **Backend:** Python FastAPI
- **LLM:** Google Gemini 2.5 API (direct integration)
- **Databases:** Neo4j (graph) + PostgreSQL (data warehouse) hybrid architecture
- **Data Sources:** Granola, Affinity CRM, Gmail, Slack
- **Deployment:** Docker Compose

---

## Architecture Overview

```mermaid
flowchart TD
    A1[Granola<br/>Meeting Notes] --> B[Data Ingestion Layer]
    A2[Affinity CRM<br/>Companies & Deals] --> B
    A3[Gmail<br/>Email Threads] --> B
    A4[Slack<br/>Internal Discussions] --> B
    
    B --> C[LLM Relevance Filter<br/>Gemini 2.5]
    C --> D[LLM Extraction Engine<br/>Gemini 2.5]
    D --> E[Data Router]
    E --> F[Neo4j<br/>Knowledge Graph]
    E --> G[PostgreSQL<br/>Data Warehouse + pgvector]
    F <--> H[FastAPI Backend]
    G <--> H
    H --> I[REST API Endpoints]
```

---

## Phase 1: Data Ingestion Layer

### 1.1 Overview

The ingestion layer fetches raw data from 4 sources and transforms it into a unified company object format. Each connector must follow the exact data formats specified in [`data-forms.md`](data-forms.md).

**Critical Reference:** All connectors MUST implement the data structures defined in [`data-forms.md`](data-forms.md):
- Granola format: lines 3-41
- Affinity format: lines 47-124
- Gmail format: lines 128-155
- Slack format: lines 161-200

### 1.2 Data Source Connectors

**Granola API Connector**
- **Endpoint:** Granola API for meeting notes
- **Authentication:** API key (`GRANOLA_API_KEY`)
- **Data Format:** See [`data-forms.md`](data-forms.md) lines 3-41
- **Key Fields to Extract:**
  - `id`, `title`, `owner`, `created_at`
  - `calendar_event` (scheduled times, organizer)
  - `attendees` (name, email)
  - `summary_text`
  - `transcript` (speaker, text, timestamps)
- **Output:** Standardized interaction objects with `source: "granola"`

**Affinity CRM Connector**
- **Endpoint:** Affinity REST API
- **Authentication:** API key (`AFFINITY_API_KEY`)
- **Data Format:** See [`data-forms.md`](data-forms.md) lines 47-124
- **6 Objects to Fetch:**
  1. Organization (id, name, domain, person_ids, opportunity_ids, interaction_dates)
  2. Person (id, first_name, last_name, primary_email, organization_ids)
  3. Opportunity (id, name, organization_ids, person_ids, list_entries)
  4. Field Values (sector, stage, MRR, location, verdict, owner, next follow-up)
  5. Notes (id, content, created_at, person_ids)
  6. Interactions (last_event_date, next_event_date)
- **Output:** Company object with all 6 objects combined + interaction objects from notes

**Gmail API Connector**
- **Endpoint:** Gmail API v1
- **Authentication:** OAuth 2.0 (`GMAIL_CREDENTIALS`)
- **Data Format:** See [`data-forms.md`](data-forms.md) lines 128-155
- **Key Fields to Extract:**
  - `id`, `threadId`, `internalDate`
  - Headers: From, To, Subject, Date
  - Body: Extract from `payload.parts` with `mimeType: "text/plain"`
  - `snippet` for preview
- **Output:** Email interaction objects with `source: "gmail"`

**Slack API Connector**
- **Endpoint:** Slack Web API
- **Authentication:** Bot token (`SLACK_BOT_TOKEN`)
- **Data Format:** See [`data-forms.md`](data-forms.md) lines 161-200
- **3 Objects to Fetch:**
  1. Message (ts, user, text, thread_ts, reply_count, reactions)
  2. Channel (id, name, is_private)
  3. User (id, real_name, profile.email, profile.title)
- **Key Note:** Resolve user IDs to real names (see line 200 in data-forms.md)
- **Output:** Slack message interaction objects with `source: "slack"`

### 1.3 Implementation Structure

```
src/
├── ingestion/
│   ├── __init__.py
│   ├── base.py              # Base connector interface
│   ├── models.py            # Pydantic models matching data-forms.md
│   ├── granola.py           # Granola connector
│   ├── affinity.py          # Affinity CRM connector (handles 6 objects)
│   ├── gmail.py             # Gmail connector
│   ├── slack.py             # Slack connector (resolves user IDs)
│   └── aggregator.py        # Combines all sources into unified company object
```

### 1.4 Data Validation

Each connector must validate against the exact formats in [`data-forms.md`](data-forms.md):
- Use Pydantic models to enforce structure
- Handle missing optional fields gracefully
- Log warnings for unexpected formats
- Never crash on malformed data

---

## Phase 2: LLM Relevance Filter

### 2.1 Gemini 2.5 Integration

**Purpose:** Filter out non-deal-related interactions before expensive extraction

**Input:** Raw interaction object (JSON)

**Process:**
1. Load prompt template from [`prompt_relevance_filter.md`](prompt_relevance_filter.md)
2. Replace `{{INTERACTION}}` with JSON-stringified interaction
3. Call Gemini 2.5 API with prompt
4. Parse JSON response: `{"relevant": bool, "reason": string}`
5. Strip markdown code fences if present
6. Default to `relevant: true` on parse failure

**Output:** Boolean decision + reason

**Implementation:**
```
src/
├── llm/
│   ├── __init__.py
│   ├── gemini_client.py     # Gemini API wrapper
│   ├── relevance_filter.py  # Relevance filter logic
│   └── prompts/
│       └── relevance_filter.txt  # Loaded from .md file
```

**API Configuration:**
- Model: `gemini-2.5-flash` or `gemini-2.5-pro`
- Temperature: 0.1 (deterministic)
- Max tokens: 100 (short response)
- API Key: Environment variable `GEMINI_API_KEY`

---

## Phase 3: LLM Extraction Engine

### 3.1 Structured Data Extraction

**Purpose:** Extract structured intelligence from filtered interactions

**Input:** Filtered company object with all relevant interactions

**Process:**
1. Load prompt template from [`prompt_extraction_engine.md`](prompt_extraction_engine.md)
2. Replace template variables:
   - `{{COMPANY_DATA}}` → JSON-stringified company object
   - `{{CURRENT_DATETIME}}` → ISO 8601 timestamp
   - `{{MODEL_NAME}}` → `gemini-2.5-flash` or `gemini-2.5-pro`
3. Call Gemini 2.5 API with prompt
4. Parse JSON response matching [`extraction_output_format.json`](extraction_output_format.json)
5. Strip markdown code fences
6. Retry once with "return only valid JSON" instruction on parse failure
7. Validate against Pydantic schema

**Output:** Structured extraction object

**Implementation:**
```
src/
├── llm/
│   ├── extraction_engine.py  # Extraction logic
│   ├── schemas.py            # Pydantic models for extraction output
│   └── prompts/
│       └── extraction_engine.txt  # Loaded from .md file
```

**API Configuration:**
- Model: `gemini-2.5-pro` (better for complex extraction)
- Temperature: 0.2 (slightly creative for synthesis)
- Max tokens: 4096 (long structured output)
- Response format: JSON mode if available

---

## Phase 4: Database Layer

### 4.1 PostgreSQL Schema (Data Warehouse)

**Tables:**

```sql
-- Full interaction transcripts and content
CREATE TABLE interaction_content (
    id UUID PRIMARY KEY,
    neo4j_interaction_id TEXT NOT NULL,
    full_transcript TEXT,
    summary TEXT,
    takeaways JSONB,
    quotes JSONB,
    metrics_mentioned JSONB,
    topics JSONB,  -- NEW: Array of topic strings
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Vector embeddings for semantic search
CREATE TABLE company_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id TEXT NOT NULL,  -- References Neo4j company
    embedding VECTOR(1536),
    embedding_text TEXT,
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Extraction metadata
CREATE TABLE extraction_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id TEXT NOT NULL,
    model_used TEXT,
    confidence FLOAT,
    warnings JSONB,
    extracted_at TIMESTAMPTZ DEFAULT NOW()
);

-- Team debates (internal discussions)
CREATE TABLE team_debates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id TEXT NOT NULL,
    detected BOOLEAN,
    for_arguments JSONB,
    against_arguments JSONB,
    open_questions JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Decision records (UPDATED with missing fields)
CREATE TABLE decision_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id TEXT NOT NULL,
    verdict TEXT,  -- NEW: tracking | diligence | invested | passed
    rationale TEXT,
    conditions JSONB,
    check_size TEXT,  -- NEW: Investment check size
    valuation TEXT,   -- NEW: Company valuation
    decided_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- NEW: Company snapshots (company_now data)
CREATE TABLE company_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id TEXT NOT NULL,
    domain TEXT,
    headcount INT,
    open_roles INT,
    funding JSONB,  -- {last_round_stage, last_round_amount_usd, total_raised_usd}
    fetched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- NEW: Company news articles
CREATE TABLE company_news (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id TEXT NOT NULL,
    headline TEXT NOT NULL,
    url TEXT,
    published_at DATE,
    source TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- NEW: Company signals (hiring, funding, product launches)
CREATE TABLE company_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id TEXT NOT NULL,
    label TEXT NOT NULL,
    detected_at DATE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_company_embeddings_company_id ON company_embeddings(company_id);
CREATE INDEX idx_interaction_content_neo4j_id ON interaction_content(neo4j_interaction_id);
CREATE INDEX idx_extraction_metadata_company_id ON extraction_metadata(company_id);
CREATE INDEX idx_company_snapshots_company_id ON company_snapshots(company_id);
CREATE INDEX idx_company_news_company_id ON company_news(company_id);
CREATE INDEX idx_company_signals_company_id ON company_signals(company_id);
CREATE INDEX idx_decision_records_verdict ON decision_records(verdict);

-- Vector index for similarity search
CREATE INDEX ON company_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Implementation:**
```
src/
├── database/
│   ├── __init__.py
│   ├── postgres.py          # PostgreSQL connection & queries
│   ├── migrations/
│   │   └── 001_initial_schema.sql  # Complete schema (165 lines)
│   └── models.py            # SQLAlchemy models
```

---

### 4.2 Neo4j Schema (Knowledge Graph)

**Node Labels:**

```cypher
// Company node
CREATE CONSTRAINT company_id IF NOT EXISTS
FOR (c:Company) REQUIRE c.id IS UNIQUE;

CREATE INDEX company_name IF NOT EXISTS
FOR (c:Company) ON (c.name);

// Person node
CREATE CONSTRAINT person_id IF NOT EXISTS
FOR (p:Person) REQUIRE p.id IS UNIQUE;

// VCPartner node
CREATE CONSTRAINT vc_partner_id IF NOT EXISTS
FOR (v:VCPartner) REQUIRE v.id IS UNIQUE;

// Interaction node
CREATE CONSTRAINT interaction_id IF NOT EXISTS
FOR (i:Interaction) REQUIRE i.id IS UNIQUE;

// Sector node
CREATE CONSTRAINT sector_name IF NOT EXISTS
FOR (s:Sector) REQUIRE s.name IS UNIQUE;

// Tag node
CREATE CONSTRAINT tag_name IF NOT EXISTS
FOR (t:Tag) REQUIRE t.name IS UNIQUE;
```

**Relationship Types:**

```cypher
// Company relationships
(:Company)-[:SIMILAR_TO {score: float}]->(:Company)
(:Company)-[:HAS_CONTACT]->(:Person)
(:Company)-[:IN_SECTOR]->(:Sector)
(:Company)-[:TAGGED_WITH]->(:Tag)
(:Company)-[:COMPETED_WITH]->(:Company)

// Person relationships
(:Person)-[:FOUNDER_OF]->(:Company)
(:Person)-[:WORKS_AT]->(:Company)

// VC Partner relationships
(:VCPartner)-[:OWNS]->(:Company)
(:VCPartner)-[:PARTICIPATED_IN]->(:Interaction)

// Interaction relationships
(:Interaction)-[:ABOUT]->(:Company)
(:Interaction)-[:INVOLVES]->(:Person)
(:Interaction)-[:INVOLVES]->(:VCPartner)
```

**Node Properties:**

```cypher
// Company
{
  id: string,
  name: string,
  one_liner: string,
  sector: string,
  stage: string,
  verdict: string,
  pipeline_stage: string,
  owner: string,
  deal_momentum: string,
  location_city: string,
  location_country: string,
  lat: float,
  lng: float,
  website: string,
  first_met_at: date,
  last_touch_at: datetime,
  next_step: string,
  check_size: string,
  valuation: string,
  decided_at: datetime
}

// Person
{
  id: string,
  name: string,
  email: string,
  role: string,
  is_primary: boolean,
  phone: string,
  linkedin: string,
  twitter: string,
  notes: string
}

// Interaction
{
  id: string,
  type: string,
  title: string,
  subtitle: string,
  occurred_at: datetime,
  duration_minutes: int,
  channel: string,
  sentiment: string
}
```

**Implementation:**
```
src/
├── database/
│   ├── neo4j_client.py      # Neo4j connection & queries
│   ├── graph_models.py      # Graph data models
│   └── cypher/
│       ├── schema.cypher    # Schema creation
│       └── queries.cypher   # Common queries
```

---

## Phase 5: Data Storage Layer

### 5.1 Storage Orchestrator

**Purpose:** Route extracted data to appropriate databases

**Process:**
1. Receive extraction output from LLM
2. Generate embedding for company (using Gemini embeddings API)
3. Geocode location using Nominatim
4. Split data:
   - **Neo4j:** Entities and relationships
   - **PostgreSQL:** Heavy data and embeddings
5. Execute writes in transaction
6. Return success/failure status

**Neo4j Write Operations:**
```python
# Create Company node
# Create Person nodes
# Create VCPartner nodes
# Create Interaction nodes
# Create Sector node
# Create Tag nodes
# Create all relationships
```

**PostgreSQL Write Operations:**
```python
# Insert interaction_content records
# Insert company_embeddings record
# Insert extraction_metadata record
# Insert team_debates record
# Insert decision_records record
```

**Implementation:**
```
src/
├── storage/
│   ├── __init__.py
│   ├── orchestrator.py      # Main storage coordinator
│   ├── neo4j_writer.py      # Neo4j write operations
│   ├── postgres_writer.py   # PostgreSQL write operations
│   └── geocoding.py         # Nominatim geocoding service
```

---

## Phase 6: Pipeline Orchestrator

### 6.1 End-to-End Pipeline

**Purpose:** Coordinate all components for complete data processing

**Flow:**
```
1. Fetch data from source (Granola/Affinity/Gmail/Slack)
2. For each company:
   a. For each interaction:
      - Run relevance filter
      - Keep only relevant interactions
   b. Run extraction engine on filtered company data
   c. Generate embedding
   d. Geocode location
   e. Store in Neo4j + PostgreSQL
3. Compute similarity relationships (after all companies processed)
4. Return processing summary
```

**Implementation:**
```
src/
├── pipeline/
│   ├── __init__.py
│   ├── orchestrator.py      # Main pipeline coordinator
│   ├── processor.py         # Single company processor
│   └── similarity.py        # Similarity computation
```

---

## Project Structure

```
vc-intelligence/
├── docker-compose.yml
├── .env.example
├── requirements.txt
├── README.md
├── IMPLEMENTATION_PLAN.md
│
├── src/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Configuration management
│   │
│   ├── ingestion/           # Phase 1: Data source connectors
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── granola.py
│   │   ├── affinity.py
│   │   ├── gmail.py
│   │   ├── slack.py
│   │   └── models.py
│   │
│   ├── llm/                 # Phase 2 & 3: LLM processing
│   │   ├── __init__.py
│   │   ├── gemini_client.py
│   │   ├── relevance_filter.py
│   │   ├── extraction_engine.py
│   │   ├── schemas.py
│   │   └── prompts/
│   │       ├── relevance_filter.txt
│   │       └── extraction_engine.txt
│   │
│   ├── database/            # Phase 4: Database layer
│   │   ├── __init__.py
│   │   ├── postgres.py
│   │   ├── neo4j_client.py
│   │   ├── models.py
│   │   ├── graph_models.py
│   │   ├── migrations/
│   │   │   └── 001_initial_schema.sql
│   │   └── cypher/
│   │       ├── schema.cypher
│   │       └── queries.cypher
│   │
│   ├── storage/             # Phase 5: Storage layer
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   ├── neo4j_writer.py
│   │   ├── postgres_writer.py
│   │   └── geocoding.py
│   │
│   ├── pipeline/            # Phase 6: Pipeline orchestrator
│   │   ├── __init__.py
│   │   ├── orchestrator.py
│   │   ├── processor.py
│   │   └── similarity.py
│   │
│   └── api/                 # FastAPI routes (future)
│       ├── __init__.py
│       └── routes.py
│
├── tests/
│   ├── __init__.py
│   ├── test_ingestion.py
│   ├── test_llm.py
│   ├── test_storage.py
│   └── test_pipeline.py
│
└── data/
    └── mock_data.json       # Test data
```

---

## Docker Compose Configuration

```yaml
version: '3.8'

services:
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: vc_intelligence
      POSTGRES_USER: vcuser
      POSTGRES_PASSWORD: vcpass
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./src/database/migrations:/docker-entrypoint-initdb.d

  neo4j:
    image: neo4j:5.15
    environment:
      NEO4J_AUTH: neo4j/vcpassword
      NEO4J_PLUGINS: '["apoc"]'
    ports:
      - "7474:7474"  # HTTP
      - "7687:7687"  # Bolt
    volumes:
      - neo4j_data:/data
      - ./src/database/cypher:/import

  api:
    build: .
    environment:
      POSTGRES_URL: postgresql://vcuser:vcpass@postgres:5432/vc_intelligence
      NEO4J_URI: bolt://neo4j:7687
      NEO4J_USER: neo4j
      NEO4J_PASSWORD: vcpassword
      GEMINI_API_KEY: ${GEMINI_API_KEY}
      GRANOLA_API_KEY: ${GRANOLA_API_KEY}
      AFFINITY_API_KEY: ${AFFINITY_API_KEY}
      GMAIL_CREDENTIALS: ${GMAIL_CREDENTIALS}
      SLACK_BOT_TOKEN: ${SLACK_BOT_TOKEN}
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - neo4j
    volumes:
      - ./src:/app/src

volumes:
  postgres_data:
  neo4j_data:
```

---

## Environment Variables

```bash
# .env file
GEMINI_API_KEY=your_gemini_api_key_here
GRANOLA_API_KEY=your_granola_api_key
AFFINITY_API_KEY=your_affinity_api_key
GMAIL_CREDENTIALS=path_to_gmail_oauth_credentials.json
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token

POSTGRES_URL=postgresql://vcuser:vcpass@localhost:5432/vc_intelligence
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=vcpassword
```

---

## Dependencies (requirements.txt)

```txt
# FastAPI
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0

# Database
psycopg2-binary==2.9.9
sqlalchemy==2.0.25
pgvector==0.2.4
neo4j==5.16.0

# LLM
google-generativeai==0.3.2

# Data source APIs
requests==2.31.0
google-auth==2.27.0
google-auth-oauthlib==1.2.0
google-api-python-client==2.116.0
slack-sdk==3.26.2

# Utilities
python-dotenv==1.0.0
httpx==0.26.0
tenacity==8.2.3

# Testing
pytest==7.4.4
pytest-asyncio==0.23.3
```

---

## Implementation Order

### Week 1: Foundation
1. ✅ Create project structure
2. ✅ Set up Docker Compose
3. ✅ Configure databases (PostgreSQL + Neo4j)
4. ✅ Implement Gemini API client

### Week 2: Data Ingestion
5. ✅ Build base connector interface
6. ✅ Implement Granola connector
7. ✅ Implement Affinity connector
8. ✅ Implement Gmail connector
9. ✅ Implement Slack connector

### Week 3: LLM Processing
10. ✅ Implement relevance filter
11. ✅ Implement extraction engine
12. ✅ Add retry logic and error handling
13. ✅ Test with mock data

### Week 4: Storage Layer
14. ✅ Implement PostgreSQL writer
15. ✅ Implement Neo4j writer
16. ✅ Build storage orchestrator
17. ✅ Add geocoding service

### Week 5: Pipeline & Testing
18. ✅ Build pipeline orchestrator
19. ✅ Implement similarity computation
20. ✅ End-to-end testing
21. ✅ Performance optimization

---

## Success Criteria

- [ ] Successfully ingest data from all 4 sources
- [ ] Relevance filter achieves >90% accuracy
- [ ] Extraction engine produces valid structured output
- [ ] Data correctly stored in both databases
- [ ] Graph queries execute in <100ms
- [ ] Vector similarity search works correctly
- [ ] Pipeline processes 15 companies in <5 minutes
- [ ] All tests pass

---

## Next Steps

After completing this implementation:
1. Build FastAPI REST endpoints
2. Implement RAG chatbot
3. Add company evolution tracking
4. Build market map clustering
5. Create frontend dashboard
6. Deploy to production

---

## Notes

- Use existing prompt files: `prompt_relevance_filter.md` and `prompt_extraction_engine.md`
- Follow extraction output format: `extraction_output_format.json`
- Reference data formats: `data-forms.md`
- Mock data rules: `mock-data-rules.md`