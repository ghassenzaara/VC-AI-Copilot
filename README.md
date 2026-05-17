# VC Intelligence Knowledge Graph Platform

A production-grade VC deal intelligence platform that combines Neo4j knowledge graphs, PostgreSQL data warehouse, and IBM WatsonX LLMs for intelligent data extraction and analysis.

## 🏗️ Architecture

```
Data Sources → Ingestion Layer → LLM Processing → Hybrid Storage → FastAPI
(Granola,      (Connectors)      (IBM WatsonX)    (Neo4j +        (REST API)
 Affinity,                       Llama 3.3 70B     PostgreSQL)
 Gmail,                          Granite 4.0 Small
 Slack)
```

### System Flow

1. **Data Ingestion**: Fetch and aggregate data from multiple sources
2. **Relevance Filtering**: LLM filters out non-deal-related interactions (Granite 4.0 H Small)
3. **Intelligence Extraction**: LLM extracts structured data (Llama 3.3 70B Instruct)
4. **Geocoding**: Convert locations to coordinates (Nominatim API)
5. **Embedding Generation**: Create semantic vectors for similarity search (Granite Embedding 278M)
6. **Hybrid Storage**: Write to Neo4j (graph) and PostgreSQL (data + vectors)
7. **Similarity Computation**: Calculate company relationships based on embeddings
8. **Market Map Clustering** (optional): Group companies into clusters with LLM-generated names

## 🚀 Features

- **Multi-Source Data Ingestion**: Granola, Affinity CRM, Gmail, Slack
- **LLM-Powered Intelligence**: IBM WatsonX for relevance filtering and structured extraction
  - `meta-llama/llama-3-3-70b-instruct` — complex deal intelligence extraction
  - `ibm/granite-4-h-small` — lightweight interaction relevance filtering
  - `ibm/granite-embedding-278m-multilingual` — multilingual semantic embeddings (768-dim)
- **RAG AI Agent**: Intelligent chatbot with multi-modal capabilities
  - Query Neo4j knowledge graph and PostgreSQL database for context
  - Process PDFs and images (OCR + vision analysis)
  - Web scraping for external data enrichment
  - Conversation memory with isolated chat histories
  - Source citation and reference tracking
  - Streaming responses for real-time interaction
- **Hybrid Database Architecture**:
  - Neo4j for relationship graphs and entity connections
  - PostgreSQL with pgvector for embeddings, transcripts, and analytics
- **Semantic Search**: Vector similarity search for company matching (cosine similarity)
- **Market Map Clustering**: AI-powered company grouping with LLM-generated cluster names
  - K-means and HDBSCAN clustering algorithms
  - Automatic optimal cluster detection using silhouette scores
  - LLM-generated descriptive names based on sector, stage, and company characteristics
- **Knowledge Graph**: Rich entity relationships (companies, people, interactions, sectors, tags, clusters)
- **Robust Error Handling**: Graceful degradation with detailed logging and warnings
- **Schema Validation**: Pydantic models ensure data integrity throughout the pipeline

## 📋 Prerequisites

- Docker & Docker Compose
- Python 3.11+
- API Keys:
  - IBM Cloud API key (for WatsonX)
  - IBM WatsonX Project ID
  - Granola API
  - Affinity CRM API
  - Gmail OAuth credentials
  - Slack Bot Token

## 🛠️ Installation

### 1. Clone and Setup

```bash
git clone <repository-url>
cd vc-intelligence
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Start Services with Docker

```bash
docker-compose up -d
```

This will start:
- PostgreSQL with pgvector (port 5432)
- Neo4j (ports 7474, 7687)
- FastAPI application (port 8000)

### 4. Install Python Dependencies (for local development)

```bash
pip install -r requirements.txt
```

## 📁 Project Structure

```
vc-intelligence/
├── src/
│   ├── ingestion/          # Data source connectors
│   │   ├── base.py         # Base connector interface with validation
│   │   ├── models.py       # Pydantic models for all data sources
│   │   ├── aggregator.py   # Aggregates data by company
│   │   ├── granola.py      # Granola API connector
│   │   ├── affinity.py     # Affinity CRM connector
│   │   ├── gmail.py        # Gmail API connector
│   │   ├── slack.py        # Slack API connector
│   │   └── utils.py        # Shared utilities
│   │
│   ├── llm/                # LLM processing
│   │   ├── watsonx_client.py     # IBM WatsonX API wrapper
│   │   ├── relevance_filter.py   # Filter non-deal interactions
│   │   ├── extraction_engine.py  # Extract structured data
│   │   ├── cluster_namer.py      # LLM-powered cluster naming
│   │   ├── schemas.py            # Pydantic schemas for extraction output
│   │   └── prompts/              # Prompt templates
│   │       ├── extraction_engine.txt
│   │       ├── relevance_filter.txt
│   │       └── cluster_naming.txt
│   │
│   ├── database/           # Database layer
│   │   ├── postgres.py           # PostgreSQL client
│   │   ├── neo4j_client.py       # Neo4j client
│   │   ├── migrations/           # SQL migrations
│   │   │   └── schema.sql        # PostgreSQL schema (includes clustering tables)
│   │   └── cypher/               # Cypher queries
│   │       ├── schema.cypher     # Neo4j constraints & indexes (includes Cluster node)
│   │       └── queries.cypher    # Common queries
│   │
│   ├── storage/            # Storage orchestration
│   │   ├── orchestrator.py       # Main storage coordinator
│   │   ├── neo4j_writer.py       # Neo4j write operations
│   │   └── postgres_writer.py    # PostgreSQL write operations
│   │
│   ├── pipeline/           # Pipeline orchestration
│   │   ├── coordinator.py        # Main pipeline coordinator
│   │   ├── company_processor.py  # Single company processor
│   │   ├── similarity.py         # Similarity computation
│   │   ├── clustering.py         # Market map clustering (K-means, HDBSCAN)
│   │   └── geocoding.py          # Location geocoding (Nominatim)
│   │
│   ├── api/                # FastAPI application
│   │   └── main.py         # API endpoints
│   │
│   └── config.py           # Configuration management
│
├── frontend/               # Next.js frontend (in development)
│   ├── app/                # Next.js 15 app directory
│   ├── components/         # React components
│   └── lib/                # Utilities and types
│
├── tests/                  # Test suite
├── data/                   # Mock data for testing
├── bob_sessions/           # Development session logs
├── docker-compose.yml      # Docker services configuration
├── Dockerfile              # Application container
├── requirements.txt        # Python dependencies
├── test_pipeline.py        # Pipeline smoke test
├── mock_data.json          # Mock data for testing
├── .env.example            # Environment template
└── README.md               # This file
```

## 🗄️ Database Schemas

### PostgreSQL Tables

**Core Tables:**
- `interaction_content`: Full transcripts, summaries, topics, quotes, metrics
- `company_embeddings`: Vector embeddings (768-dim) for similarity search
- `extraction_metadata`: LLM extraction metadata
- `team_debates`: Internal team discussions
- `decision_records`: Investment decisions (verdict, rationale, check size, valuation)

**Company Now Tables:**
- `company_snapshots`: Point-in-time company data (headcount, funding, domain)
- `company_news`: Latest news articles about companies
- `company_signals`: Detected signals (hiring, funding, product launches)

**Market Map Clustering Tables:**
- `market_clusters`: Cluster definitions with LLM-generated names and centroids
- `company_cluster_assignments`: Company-to-cluster mappings with distance metrics
- `cluster_metadata`: Aggregated cluster characteristics (sectors, stages, tags, sample companies)

### Neo4j Graph Schema

**Nodes:**
- `Company`: Startups and companies
- `Person`: Founders and contacts
- `VCPartner`: VC team members
- `Interaction`: Meetings, emails, messages
- `Sector`: Industry sectors
- `Tag`: Custom tags
- `Cluster`: Market map clusters with LLM-generated names

**Relationships:**
- `SIMILAR_TO`: Company similarity (with score)
- `BELONGS_TO_CLUSTER`: Company-Cluster assignment
- `HAS_CONTACT`: Company-Person connections
- `FOUNDER_OF`: Person-Company founding relationship
- `OWNS`: VCPartner-Company ownership
- `PARTICIPATED_IN`: VCPartner-Interaction participation
- `ABOUT`: Interaction-Company association
- `IN_SECTOR`: Company-Sector classification
- `TAGGED_WITH`: Company-Tag associations

## 🔄 Data Pipeline

1. **Ingestion**: Fetch data from sources (Granola, Affinity, Gmail, Slack)
2. **Relevance Filter**: LLM filters out non-deal-related interactions
3. **Extraction**: LLM extracts structured intelligence
4. **Embedding**: Generate vector embeddings for semantic search
5. **Geocoding**: Convert locations to coordinates
6. **Storage**: Write to Neo4j (graph) and PostgreSQL (data + vectors)
7. **Similarity**: Compute company similarity relationships

## 🧪 Testing

### Quick Pipeline Test

Test the complete pipeline with mock data (no database required):

```bash
python test_pipeline.py
```

This smoke test:
1. Loads mock data from `mock_data.json`
2. Runs relevance filtering (Granite 4.0 H Small)
3. Runs extraction (Llama 3.3 70B Instruct)
4. Validates output against schemas
5. Saves results to `test_output.json`

### Unit Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_ingestion.py

# Run with coverage
pytest --cov=src tests/
```

### Manual Testing

```bash
# Test individual components
python -m src.ingestion.granola
python -m src.llm.relevance_filter
python -m src.llm.extraction_engine
```

## 📊 API Endpoints

### Health & Status
- `GET /` - Root endpoint with API info
- `GET /health` - Health check with component status
- `GET /status` - Detailed pipeline status

### Pipeline Operations
- `POST /pipeline/process-company` - Process a single company
  ```json
  {
    "company_domain": "example.com",
    "limit_per_source": 100
  }
  ```
- `POST /pipeline/process-companies` - Process multiple companies
  ```json
  {
    "company_domains": ["example.com", "startup.io"],
    "limit_per_source": 100
  }
  ```

### Similarity Operations
- `POST /similarity/compute` - Compute similarities for a company
  ```json
  {
    "company_id": "uuid",
    "threshold": 0.75,
    "limit": 10
  }
  ```
- `POST /similarity/compute-all` - Compute similarities for all companies

### Clustering Operations
- `GET /market-map` - Get complete market map with all clusters and companies
- `GET /market-map/cluster/{cluster_id}` - Get detailed cluster information

### Geocoding
- `GET /geocode?location=Amsterdam,%20Netherlands` - Geocode a location

### Query Endpoints (Planned)
- `GET /companies/{company_id}` - Get company details
- `GET /companies` - List companies with filters

## 🔧 Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
# IBM WatsonX
IBM_API_KEY=your_ibm_cloud_api_key
IBM_PROJECT_ID=your_watsonx_project_id
IBM_URL=https://us-south.ml.cloud.ibm.com   # change region if needed

# Data Sources
GRANOLA_API_KEY=your_key
AFFINITY_API_KEY=your_key
GMAIL_CREDENTIALS=path/to/credentials.json
SLACK_BOT_TOKEN=xoxb-your-token

# Databases
POSTGRES_URL=postgresql://vcuser:vcpass@localhost:5432/vc_intelligence
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=vcpassword
```

**Getting IBM credentials:**
1. Create an [IBM Cloud](https://cloud.ibm.com) account
2. Provision a WatsonX.ai instance and note your Project ID
3. Generate an API key from **Manage → Access (IAM) → API keys**

## 📈 Development Status

### ✅ Completed (Backend)
- [x] Project structure and Docker setup
- [x] Database schemas (PostgreSQL + Neo4j)
- [x] Database connection modules with health checks
- [x] Base connector interface with validation
- [x] Pydantic models for all data sources
- [x] Data source connectors (Granola, Affinity, Gmail, Slack)
- [x] Data aggregator (groups interactions by company)
- [x] IBM WatsonX LLM integration
  - [x] Llama 3.3 70B Instruct (extraction)
  - [x] Granite 4.0 H Small (relevance filtering)
  - [x] Granite Embedding 278M (semantic search)
- [x] Relevance filter with error handling
- [x] Extraction engine with schema validation
- [x] Comprehensive Pydantic schemas matching extraction output
- [x] Storage layer (Neo4j + PostgreSQL writers)
- [x] Storage orchestrator with rollback on failure
- [x] Pipeline coordinator and company processor
- [x] Similarity computation with vector embeddings
- [x] Geocoding service (Nominatim API)
- [x] Market map clustering implementation
  - [x] K-means and HDBSCAN algorithms
  - [x] Automatic optimal cluster detection
  - [x] LLM-powered cluster naming
  - [x] Database schema (PostgreSQL + Neo4j)
  - [x] API endpoints (GET /market-map, GET /market-map/cluster/{id})
  - [x] Frontend integration with real clustering data
- [x] FastAPI endpoints (health, pipeline, similarity, geocoding, clustering)
- [x] Pipeline smoke test (`test_pipeline.py`)

### 🚧 In Progress
- [ ] Frontend dashboard (Next.js 15 + Clerk auth)
  - [x] Basic UI components
  - [x] Authentication flow
  - [x] Market map visualization (connected to real data)
  - [ ] Dashboard views
  - [ ] Company detail pages
  - [ ] Search and filtering

### 📅 Planned
- [ ] Clustering compute endpoints (POST /clustering/compute, POST /clustering/name-clusters)
- [ ] Query endpoints (GET companies, interactions, etc.)
- [ ] RAG AI Agent for deal intelligence
  - [ ] Vector search service for knowledge retrieval
  - [ ] PDF processing with text extraction
  - [ ] Image processing with OCR and vision analysis
  - [ ] Web scraping service for external data enrichment
  - [ ] RAG query engine combining Neo4j and PostgreSQL context
  - [ ] Conversation memory and history management
  - [ ] Chatbot API endpoint with streaming responses
  - [ ] File upload handling in backend
  - [ ] Frontend chatbot integration
  - [ ] Source citation and reference tracking
- [ ] Company evolution tracking over time
- [ ] Advanced analytics and insights
- [ ] Webhook integrations for real-time updates

## 🔧 Key Technical Details

### LLM Configuration
- **Flash Model** (Granite 4.0 H Small): Fast relevance filtering, temperature 0.1
- **Pro Model** (Llama 3.3 70B Instruct): Complex extraction, temperature 0.2, max tokens 16384
- **Embedding Model** (Granite 278M): 768-dimensional vectors for semantic search

### Database Design
- **Neo4j**: Stores graph relationships (companies, people, interactions, sectors, tags)
- **PostgreSQL**: Stores heavy data (transcripts, embeddings, metadata, decisions)
- **Hybrid Approach**: Company ID generated in Neo4j, used as foreign key in PostgreSQL

### Error Handling
- Relevance filter errors default to "relevant" (fail-open to avoid data loss)
- Extraction errors are logged with detailed warnings
- Storage failures trigger Neo4j rollback to maintain consistency
- Schema validation with Pydantic catches data drift

### Performance Optimizations
- Batch processing for multiple companies
- Vector index (IVFFlat) for fast similarity search
- Connection pooling for database clients
- Async operations in FastAPI endpoints

## 🤝 Contributing

1. Follow the existing code structure
2. Add tests for new features
3. Update documentation
4. Follow PEP 8 style guide
5. Use Pydantic models for data validation
6. Add type hints to all functions
7. Log errors with appropriate severity levels

## 📝 License

MIT License - See LICENSE file for details

## 🔗 References

### Documentation
- [Implementation Plan](IMPLEMENTATION_PLAN.md) - Detailed implementation roadmap
- [RAG AI Agent Implementation](RAG_AI_AGENT_IMPLEMENTATION.md) - Complete RAG system architecture and implementation guide
- [Security Audit](SECURITY_AUDIT.md) - Comprehensive security analysis and recommendations
- [Market Map Clustering Plan](MARKET_MAP_CLUSTERING_PLAN.md) - Clustering feature specification
- [System Integration Map](SYSTEM_INTEGRATION_MAP.md) - Complete architecture and data flow
- [Clustering Usage Guide](CLUSTERING_USAGE_GUIDE.md) - Step-by-step clustering tutorial
- [Data Formats](data-forms.md) - Data source format specifications
- [Extraction Output Format](extraction_output_format.json) - LLM output schema
- [Knowledge Graph Pipeline](knowledge_graph_pipeline.md) - Pipeline architecture
- [Mock Data Rules](mock-data-rules.md) - Mock data generation guidelines

### Key Files
- [Extraction Prompt](src/llm/prompts/extraction_engine.txt) - LLM extraction prompt
- [Relevance Filter Prompt](src/llm/prompts/relevance_filter.txt) - LLM filter prompt
- [Cluster Naming Prompt](src/llm/prompts/cluster_naming.txt) - LLM cluster naming prompt
- [PostgreSQL Schema](src/database/migrations/schema.sql) - Database schema (includes clustering tables)
- [Neo4j Schema](src/database/cypher/schema.cypher) - Graph schema (includes Cluster node)
- [Clustering Implementation](src/pipeline/clustering.py) - Market map clustering algorithms
- [Cluster Namer](src/llm/cluster_namer.py) - LLM-powered cluster naming
- [Pipeline Test](test_pipeline.py) - Smoke test for the complete pipeline

### External APIs
- [IBM WatsonX](https://www.ibm.com/watsonx) - LLM and embedding models
- [Granola API](https://granola.so) - Meeting notes
- [Affinity CRM](https://www.affinity.co) - Deal pipeline
- [Gmail API](https://developers.google.com/gmail/api) - Email data
- [Slack API](https://api.slack.com) - Internal discussions
- [Nominatim](https://nominatim.org) - Geocoding service

---

**Built with ❤️ for VC intelligence**

*Last updated: May 2026*