# VC Intelligence Knowledge Graph Platform

A production-grade VC deal intelligence platform that combines Neo4j knowledge graphs, PostgreSQL data warehouse, and Google Gemini 2.5 LLM for intelligent data extraction and analysis.

## 🏗️ Architecture

```
Data Sources → Ingestion Layer → LLM Processing → Hybrid Storage → FastAPI
(Granola,      (Connectors)      (Gemini 2.5)     (Neo4j +        (REST API)
 Affinity,                                          PostgreSQL)
 Gmail,
 Slack)
```

## 🚀 Features

- **Multi-Source Data Ingestion**: Granola, Affinity CRM, Gmail, Slack
- **LLM-Powered Intelligence**: Gemini 2.5 for relevance filtering and structured extraction
- **Hybrid Database Architecture**: 
  - Neo4j for relationship graphs
  - PostgreSQL with pgvector for embeddings and heavy data
- **Semantic Search**: Vector similarity search for company matching
- **Knowledge Graph**: Rich entity relationships (companies, people, interactions, sectors)

## 📋 Prerequisites

- Docker & Docker Compose
- Python 3.11+
- API Keys:
  - Google Gemini API
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
│   │   ├── base.py         # Base connector interface
│   │   ├── granola.py      # Granola API connector
│   │   ├── affinity.py     # Affinity CRM connector
│   │   ├── gmail.py        # Gmail API connector
│   │   └── slack.py        # Slack API connector
│   │
│   ├── llm/                # LLM processing
│   │   ├── gemini_client.py      # Gemini API wrapper
│   │   ├── relevance_filter.py   # Filter non-deal interactions
│   │   ├── extraction_engine.py  # Extract structured data
│   │   └── prompts/              # Prompt templates
│   │
│   ├── database/           # Database layer
│   │   ├── postgres.py           # PostgreSQL client
│   │   ├── neo4j_client.py       # Neo4j client
│   │   ├── migrations/           # SQL migrations
│   │   └── cypher/               # Cypher queries
│   │
│   ├── storage/            # Storage orchestration
│   │   ├── orchestrator.py       # Main storage coordinator
│   │   ├── neo4j_writer.py       # Neo4j write operations
│   │   ├── postgres_writer.py    # PostgreSQL write operations
│   │   └── geocoding.py          # Location geocoding
│   │
│   ├── pipeline/           # Pipeline orchestration
│   │   ├── orchestrator.py       # Main pipeline coordinator
│   │   ├── processor.py          # Single company processor
│   │   └── similarity.py         # Similarity computation
│   │
│   ├── api/                # FastAPI routes
│   │   └── routes.py
│   │
│   ├── config.py           # Configuration management
│   └── main.py             # FastAPI entry point
│
├── tests/                  # Test suite
├── data/                   # Mock data
├── docker-compose.yml      # Docker services
├── Dockerfile              # Application container
├── requirements.txt        # Python dependencies
└── .env.example            # Environment template
```

## 🗄️ Database Schemas

### PostgreSQL Tables

**Core Tables:**
- `interaction_content`: Full transcripts, summaries, topics, quotes, metrics
- `company_embeddings`: Vector embeddings (1536-dim) for similarity search
- `extraction_metadata`: LLM extraction metadata
- `team_debates`: Internal team discussions
- `decision_records`: Investment decisions (verdict, rationale, check size, valuation)

**Company Now Tables:**
- `company_snapshots`: Point-in-time company data (headcount, funding, domain)
- `company_news`: Latest news articles about companies
- `company_signals`: Detected signals (hiring, funding, product launches)

### Neo4j Graph Schema

**Nodes:**
- `Company`: Startups and companies
- `Person`: Founders and contacts
- `VCPartner`: VC team members
- `Interaction`: Meetings, emails, messages
- `Sector`: Industry sectors
- `Tag`: Custom tags

**Relationships:**
- `SIMILAR_TO`: Company similarity (with score)
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

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_ingestion.py

# Run with coverage
pytest --cov=src tests/
```

## 📊 API Endpoints (Coming Soon)

- `POST /ingest`: Trigger data ingestion
- `GET /companies/{id}`: Get company details
- `GET /companies/{id}/similar`: Find similar companies
- `GET /companies/{id}/interactions`: Get company interactions
- `POST /search`: Semantic search across companies

## 🔧 Configuration

Key environment variables in `.env`:

```bash
# LLM
GEMINI_API_KEY=your_key_here

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

## 📈 Development Status

### ✅ Completed
- [x] Project structure and Docker setup
- [x] Database schemas (PostgreSQL + Neo4j)
- [x] Database connection modules
- [x] Base connector interface

### 🚧 In Progress
- [ ] Data source connectors (Granola, Affinity, Gmail, Slack)
- [ ] LLM integration (Gemini 2.5)
- [ ] Storage layer
- [ ] Pipeline orchestration
- [ ] FastAPI endpoints

### 📅 Planned
- [ ] RAG chatbot
- [ ] Company evolution tracking
- [ ] Market map clustering
- [ ] Frontend dashboard

## 🤝 Contributing

1. Follow the existing code structure
2. Add tests for new features
3. Update documentation
4. Follow PEP 8 style guide

## 📝 License

[Your License Here]

## 🔗 References

- [Implementation Plan](IMPLEMENTATION_PLAN.md)
- [Data Formats](data-forms.md)
- [Extraction Output Format](extraction_output_format.json)
- [Prompt Templates](prompt_extraction_engine.md)

---

Built with ❤️ for VC intelligence