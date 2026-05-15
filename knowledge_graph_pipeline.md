# Knowledge Graph Pipeline Spec — Component 3

## Architecture Decision

The entire pipeline runs inside a **Python FastAPI backend** with direct API integrations.
All LLM calls go through **Google Gemini 2.5 API** using direct API key authentication.
The pipeline is triggered by API endpoints or scheduled jobs.
Data is stored in a **hybrid database architecture**: Neo4j (knowledge graph) + PostgreSQL (data warehouse with pgvector).

---

## LLM API

- **Provider:** Google Gemini API (direct integration)
- **Model for LLM calls:** `gemini-2.5-flash` or `gemini-2.5-pro`
- **Model for embeddings:** `text-embedding-004` (Google's latest embedding model)
- **Authentication:** Direct API key via `GEMINI_API_KEY` environment variable

All calls use the Google Generative AI Python SDK:
```python
import google.generativeai as genai

genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# For text generation
model = genai.GenerativeModel('gemini-2.5-flash')
response = model.generate_content(prompt)
result = response.text

# For embeddings
result = genai.embed_content(
    model="models/text-embedding-004",
    content=text,
    task_type="retrieval_document"
)
embedding = result['embedding']
```

---

## Pipeline Functions

### 1. `process_company` (core function)
Processes a single company through the full pipeline:
ingest → filter → extract → geocode → embed → store in Neo4j + PostgreSQL.

**Input:** Company data from data sources (Granola, Affinity, Gmail, Slack)

**Steps:**

**Step 1 — Data Ingestion**
- Fetch data from all 4 sources for the company
- Transform to unified company object format (see `data-forms.md`)
- Combine all interactions from different sources

**Step 2 — Relevance Filter**
- For each interaction, call Gemini 2.5 with prompt from `prompt_relevance_filter.md`
- Replace `{{INTERACTION}}` with JSON-stringified interaction
- Parse response as JSON: `{"relevant": bool, "reason": "string"}`
- Strip markdown code fences before parsing
- Keep only interactions where `relevant: true`
- Default to `relevant: true` on parse failure

**Step 3 — Extraction**
- Call Gemini 2.5 with prompt from `prompt_extraction_engine.md`
- Replace `{{COMPANY_DATA}}` with filtered company JSON
- Replace `{{CURRENT_DATETIME}}` with current ISO 8601 datetime
- Replace `{{MODEL_NAME}}` with `gemini-2.5-flash` or `gemini-2.5-pro`
- Parse response as JSON matching `extraction_output_format.json`
- Strip markdown code fences before parsing
- Retry once with "return only valid JSON" instruction on parse failure

**Step 4 — Geocode Location**
- Input: `extracted.company.location` (e.g., "Amsterdam, Netherlands")
- Call Nominatim API: `https://nominatim.openstreetmap.org/search?q={location}&format=json&limit=1`
- Set User-Agent header to `vc-intelligence-app`
- Extract `lat` and `lon` from first result
- Set to null on failure (don't crash)

**Step 5 — Generate Embedding**
- Build text from: company name, sector, stage, one_liner, key_strengths, key_concerns, tags, deal_momentum, summaries from first 5 interactions
- Call Gemini embeddings API with model `text-embedding-004`
- Return embedding vector (768 dimensions for text-embedding-004)

**Step 6 — Store in Databases**
- **Neo4j:** Create nodes (Company, Person, VCPartner, Interaction, Sector, Tag) and relationships
- **PostgreSQL:** Insert interaction_content, company_embeddings, extraction_metadata, team_debates, decision_records
- Use transaction to ensure atomicity
- Return inserted company id

**Output:** `{"success": true, "id": "uuid", "name": "company name"}` or `{"success": false, "error": "message"}`

---

### 2. `compute_similarities` (post-processing function)
Computes similarity relationships between all companies using vector embeddings.

**Steps:**
- Fetch all companies from PostgreSQL: `SELECT company_id, embedding FROM company_embeddings`
- For each company, compute cosine similarity with all others
- Select top 3 most similar companies (excluding self)
- Store relationships in Neo4j: `(Company)-[:SIMILAR_TO {score: float}]->(Company)`
- Also update PostgreSQL `similar_to` JSONB array if needed

**Output:** `{"success": true, "relationships_created": 45}`

---

### 3. `reset_pipeline` (utility function)
Clears all data from both databases for clean re-runs.

**Steps:**
- Neo4j: `MATCH (n) DETACH DELETE n` (delete all nodes and relationships)
- PostgreSQL: Truncate all tables with CASCADE
- Return success status

**Output:** `{"success": true}`

---

## API Endpoints

The FastAPI backend exposes these endpoints:

```python
POST /api/pipeline/process-company
Body: {"company_id": "string", "sources": ["granola", "affinity", "gmail", "slack"]}

POST /api/pipeline/compute-similarities

POST /api/pipeline/reset

POST /api/pipeline/run-full
# Processes all companies and computes similarities
```

---

## Mock Data Location

For testing, `mock_data.json` is stored in the project's `data/` directory.
The pipeline reads it directly from the filesystem during development.
In production, data comes from live API integrations.

---

## Error Handling Rules

- Filter parse failure → default to relevant, continue
- Extraction parse failure → retry once, then skip company and return error
- Geocoding failure → set lat/lng to null, continue — world map skips null points
- Supabase insert failure → return error for that company, continue with next
- Similarity failure for one company → log and continue, not critical for demo

---

## Environment Variables

Required environment variables for the Python backend:

```bash
# LLM API
GEMINI_API_KEY=your_gemini_api_key_here

# Data Source APIs
GRANOLA_API_KEY=your_granola_api_key
AFFINITY_API_KEY=your_affinity_api_key
GMAIL_CREDENTIALS=path_to_gmail_oauth_credentials.json
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token

# Databases
POSTGRES_URL=postgresql://vcuser:vcpass@localhost:5432/vc_intelligence
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=vcpassword
```
