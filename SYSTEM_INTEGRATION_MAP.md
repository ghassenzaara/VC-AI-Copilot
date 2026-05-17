# VC Intelligence System Integration Map

Complete architecture and data flow documentation showing how all components connect.

## 📊 System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES LAYER                              │
├─────────────────────────────────────────────────────────────────────────┤
│  Granola API  │  Affinity CRM  │  Gmail API  │  Slack API               │
└────────┬──────────────┬──────────────┬──────────────┬────────────────────┘
         │              │              │              │
         └──────────────┴──────────────┴──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │   INGESTION LAYER           │
         │  - Base Connectors          │
         │  - Pydantic Models          │
         │  - Data Aggregator          │
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │   LLM PROCESSING LAYER      │
         │  - Relevance Filter         │
         │  - Extraction Engine        │
         │  - Cluster Namer            │
         │  - WatsonX Client           │
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │   PIPELINE LAYER            │
         │  - Coordinator              │
         │  - Company Processor        │
         │  - Similarity Computer      │
         │  - Market Map Clusterer     │
         │  - Geocoding Service        │
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │   STORAGE LAYER             │
         │  - Storage Orchestrator     │
         │  - Neo4j Writer             │
         │  - PostgreSQL Writer        │
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │   DATABASE LAYER            │
         │  Neo4j (Graph)  PostgreSQL  │
         │  - Companies    - Embeddings│
         │  - People       - Transcripts│
         │  - Interactions - Metadata  │
         │  - Clusters     - Clusters  │
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │   API LAYER (FastAPI)       │
         │  - Health endpoints         │
         │  - Pipeline endpoints       │
         │  - Similarity endpoints     │
         │  - Clustering endpoints     │
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────┐
         │   FRONTEND (Next.js)        │
         │  - Dashboard                │
         │  - Market Maps              │
         │  - Company Details          │
         └─────────────────────────────┘
```

## 🔄 Complete Data Flow

### 1. Company Processing Pipeline

```
User Request → FastAPI → PipelineCoordinator
                              ↓
                    ┌─────────▼─────────┐
                    │  DataAggregator   │
                    │  Fetches from:    │
                    │  - Granola        │
                    │  - Affinity       │
                    │  - Gmail          │
                    │  - Slack          │
                    └─────────┬─────────┘
                              ↓
                    ┌─────────▼─────────┐
                    │ CompanyProcessor  │
                    │ Orchestrates:     │
                    └─────────┬─────────┘
                              ↓
                    ┌─────────▼─────────┐
                    │ RelevanceFilter   │
                    │ (Granite 4.0 H)   │
                    │ Filters non-deal  │
                    └─────────┬─────────┘
                              ↓
                    ┌─────────▼─────────┐
                    │ ExtractionEngine  │
                    │ (Llama 3.3 70B)   │
                    │ Extracts intel    │
                    └─────────┬─────────┘
                              ↓
                    ┌─────────▼─────────┐
                    │StorageOrchestrator│
                    └─────────┬─────────┘
                              ↓
                    ┌─────────▼─────────┐
                    │   Neo4j Writer    │
                    │ Creates:          │
                    │ - Company node    │
                    │ - Person nodes    │
                    │ - Interaction nodes│
                    │ - Relationships   │
                    │ Returns: company_id│
                    └─────────┬─────────┘
                              ↓
                    ┌─────────▼─────────┐
                    │ PostgreSQL Writer │
                    │ Stores:           │
                    │ - Transcripts     │
                    │ - Metadata        │
                    │ - Debates         │
                    │ - Decisions       │
                    └─────────┬─────────┘
                              ↓
                    ┌─────────▼─────────┐
                    │SimilarityComputer │
                    │ Generates:        │
                    │ - Embedding (768d)│
                    │ Stores in:        │
                    │ - PostgreSQL      │
                    └─────────┬─────────┘
                              ↓
                    ┌─────────▼─────────┐
                    │ GeocodingService  │
                    │ Updates Neo4j:    │
                    │ - lat/lng coords  │
                    └───────────────────┘
```

### 2. Clustering Pipeline

```
Trigger (Manual/Scheduled)
         ↓
┌────────▼────────┐
│MarketMapClusterer│
│ Initialized with:│
│ - PostgresClient│
│ - Neo4jClient   │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 1. Fetch        │
│    Embeddings   │
│    FROM:        │
│    company_     │
│    embeddings   │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 2. Run          │
│    Clustering   │
│    Algorithm:   │
│    - K-means OR │
│    - HDBSCAN    │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 3. Store        │
│    Clusters     │
│    PostgreSQL:  │
│    - market_    │
│      clusters   │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 4. Store        │
│    Assignments  │
│    PostgreSQL:  │
│    - company_   │
│      cluster_   │
│      assignments│
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 5. Compute      │
│    Metadata     │
│    PostgreSQL:  │
│    - cluster_   │
│      metadata   │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 6. Create       │
│    Neo4j        │
│    - Cluster    │
│      nodes      │
│    - BELONGS_TO_│
│      CLUSTER    │
│      edges      │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ ClusterNamer    │
│ Initialized with:│
│ - WatsonXClient│
│ - PostgresClient│
│ - Neo4jClient   │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 1. Fetch        │
│    Unnamed      │
│    Clusters     │
│    FROM:        │
│    market_      │
│    clusters +   │
│    metadata     │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 2. Generate     │
│    Names        │
│    LLM:         │
│    - Llama 3.3  │
│      70B        │
│    - Analyzes   │
│      sectors,   │
│      stages,    │
│      tags       │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ 3. Store Names  │
│    PostgreSQL:  │
│    - market_    │
│      clusters   │
│      .name      │
│    Neo4j:       │
│    - Cluster    │
│      .name      │
└─────────────────┘
```

### 3. Frontend Data Flow

```
User Opens /market-maps
         ↓
┌────────▼────────┐
│ React Component │
│ useEffect()     │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ fetch()         │
│ GET /market-map │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ FastAPI Handler │
│ get_market_map()│
└────────┬────────┘
         ↓
┌────────▼────────┐
│ Query PostgreSQL│
│ SELECT clusters │
│ + metadata      │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ For Each Cluster│
│ Query Neo4j:    │
│ MATCH (c:Company)│
│ -[:BELONGS_TO_  │
│   CLUSTER]->    │
│   (cl:Cluster)  │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ Return JSON     │
│ {               │
│   clusters: [   │
│     {           │
│       id,       │
│       name,     │
│       companies │
│     }           │
│   ]             │
│ }               │
└────────┬────────┘
         ↓
┌────────▼────────┐
│ Frontend        │
│ - Generates     │
│   layout        │
│ - Renders       │
│   clusters      │
│ - Shows         │
│   companies     │
└─────────────────┘
```

## 🗄️ Database Schema Integration

### PostgreSQL Tables

**Core Pipeline Tables:**
```sql
company_embeddings (768-dim vectors)
  ↓ referenced by
company_cluster_assignments
  ↓ references
market_clusters
  ↓ referenced by
cluster_metadata
```

**Content Tables:**
```sql
interaction_content (transcripts, summaries)
extraction_metadata (LLM confidence, warnings)
team_debates (for/against arguments)
decision_records (verdict, rationale)
company_snapshots (headcount, funding)
company_news (headlines, URLs)
company_signals (hiring, funding events)
```

### Neo4j Graph Schema

**Nodes:**
```cypher
(:Company {id, name, sector, stage, verdict, momentum})
(:Person {id, name, email, role})
(:VCPartner {id, name})
(:Interaction {id, type, occurred_at})
(:Sector {name})
(:Tag {name})
(:Cluster {id, cluster_number, name, description})
```

**Relationships:**
```cypher
(Company)-[:SIMILAR_TO {score}]->(Company)
(Company)-[:BELONGS_TO_CLUSTER]->(Cluster)
(Company)-[:HAS_CONTACT]->(Person)
(Company)-[:IN_SECTOR]->(Sector)
(Company)-[:TAGGED_WITH]->(Tag)
(Person)-[:FOUNDER_OF]->(Company)
(VCPartner)-[:OWNS]->(Company)
(VCPartner)-[:PARTICIPATED_IN]->(Interaction)
(Interaction)-[:ABOUT]->(Company)
```

## 🔗 Key Integration Points

### 1. Company ID Propagation
```
Neo4j (generates UUID) 
  → company_id 
  → PostgreSQL (foreign key)
  → company_embeddings.company_id
  → company_cluster_assignments.company_id
```

### 2. Embedding Flow
```
CompanyProcessor
  → SimilarityComputer.generate_company_embedding()
  → WatsonXClient.embed_content()
  → PostgresClient.insert_company_embedding()
  → company_embeddings table
```

### 3. Clustering Flow
```
MarketMapClusterer.compute_clusters()
  → Fetch from company_embeddings
  → Run K-means/HDBSCAN
  → Store in market_clusters
  → Store in company_cluster_assignments
  → Store in cluster_metadata
  → Create Neo4j Cluster nodes
  → Create BELONGS_TO_CLUSTER edges
```

### 4. Cluster Naming Flow
```
ClusterNamer.name_all_clusters()
  → Fetch from market_clusters + cluster_metadata
  → WatsonXClient.generate_json() (Llama 3.3 70B)
  → Update market_clusters.name (PostgreSQL)
  → Update Cluster.name (Neo4j)
```

### 5. API to Frontend Flow
```
Frontend fetch()
  → FastAPI endpoint
  → PostgreSQL query (clusters + metadata)
  → Neo4j query (companies per cluster)
  → JSON response
  → Frontend state update
  → UI render
```

## 🔧 Component Dependencies

### PipelineCoordinator Dependencies
```python
- DataAggregator
  - GranolaConnector
  - AffinityConnector
  - GmailConnector
  - SlackConnector
- WatsonXClient (flash + pro)
- RelevanceFilter
- ExtractionEngine
- PostgresClient
- Neo4jClient
- StorageOrchestrator
- GeocodingService
- SimilarityComputer
- CompanyProcessor
```

### MarketMapClusterer Dependencies
```python
- PostgresClient (fetch embeddings, store clusters)
- Neo4jClient (create nodes, relationships)
- numpy, sklearn, hdbscan (algorithms)
```

### ClusterNamer Dependencies
```python
- WatsonXClient (LLM for naming)
- PostgresClient (fetch metadata, store names)
- Neo4jClient (update cluster names)
```

### FastAPI Dependencies
```python
- PipelineCoordinator (global instance)
- SimilarityComputer (global instance)
- PostgresClient (via get_postgres_connection)
- Neo4jClient (via get_neo4j_driver)
```

## 📝 Configuration Flow

```
.env file
  ↓
src/config.py (Settings class)
  ↓
get_settings() (singleton)
  ↓
Used by:
  - PipelineCoordinator.__init__()
  - WatsonXClient.__init__()
  - get_postgres_connection()
  - get_neo4j_driver()
  - Connector classes
```

## 🚀 Execution Flows

### Full Pipeline Execution
```bash
# 1. Start services
docker-compose up -d

# 2. Run pipeline (Python)
from src.pipeline.coordinator import PipelineCoordinator
pipeline = PipelineCoordinator()
results = pipeline.process_all_companies()

# 3. Compute similarities
from src.pipeline.similarity import SimilarityComputer
similarity = SimilarityComputer(postgres, neo4j, watsonx)
similarity.compute_all_similarities()

# 4. Run clustering
from src.pipeline.clustering import MarketMapClusterer
clusterer = MarketMapClusterer(postgres, neo4j)
stats = clusterer.compute_clusters()

# 5. Generate cluster names
from src.llm.cluster_namer import ClusterNamer
namer = ClusterNamer(watsonx, postgres, neo4j)
namer.name_all_clusters()

# 6. Start API
uvicorn src.api.main:app --reload

# 7. View in frontend
# Navigate to http://localhost:3000/market-maps
```

### API-Driven Execution
```bash
# Start API
uvicorn src.api.main:app --reload

# Process companies
curl -X POST http://localhost:8000/pipeline/process-companies

# Compute similarities
curl -X POST http://localhost:8000/similarity/compute-all

# View market map
curl http://localhost:8000/market-map

# Frontend automatically fetches from API
```

## 🔍 Data Consistency Rules

1. **Company ID is Source of Truth**
   - Generated in Neo4j
   - Used as foreign key in PostgreSQL
   - Never modified after creation

2. **Embeddings Before Clustering**
   - All companies must have embeddings
   - Embeddings stored in PostgreSQL
   - Clustering reads from company_embeddings

3. **Cluster Assignments are Exclusive**
   - Each company belongs to exactly one cluster
   - Enforced by UNIQUE constraint on company_id
   - Re-clustering overwrites previous assignments

4. **Names Synced Across Databases**
   - Cluster names stored in both PostgreSQL and Neo4j
   - ClusterNamer updates both atomically
   - PostgreSQL is source of truth for metadata

5. **Rollback on Failure**
   - If PostgreSQL write fails, Neo4j is rolled back
   - Prevents orphaned nodes
   - Maintains referential integrity

## 🎯 Critical Integration Points

### ✅ Properly Integrated
- [x] Company processing → Storage
- [x] Storage → Embedding generation
- [x] Embeddings → Clustering
- [x] Clustering → Database storage
- [x] Cluster naming → Both databases
- [x] API → Database queries
- [x] Frontend → API endpoints

### 🔄 Integration Verification Checklist
- [ ] Run full pipeline end-to-end
- [ ] Verify embeddings are generated
- [ ] Run clustering algorithm
- [ ] Generate cluster names
- [ ] Check PostgreSQL tables populated
- [ ] Check Neo4j graph created
- [ ] Test API endpoints
- [ ] Verify frontend displays data

---

**Last Updated:** May 2026  
**Maintained By:** Bob AI Assistant