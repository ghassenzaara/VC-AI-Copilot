# Market Map Clustering - Complete Usage Guide

Step-by-step guide to run the complete clustering pipeline and view results in the frontend.

## 📋 Prerequisites

1. **Services Running**
   ```bash
   docker-compose up -d
   ```
   This starts:
   - PostgreSQL (port 5432)
   - Neo4j (ports 7474, 7687)

2. **Environment Variables**
   ```bash
   # Copy and configure
   cp .env.example .env
   
   # Required variables:
   IBM_API_KEY=your_ibm_cloud_api_key
   IBM_PROJECT_ID=your_watsonx_project_id
   IBM_URL=https://us-south.ml.cloud.ibm.com
   POSTGRES_URL=postgresql://vcuser:vcpass@localhost:5432/vc_intelligence
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=vcpassword
   ```

3. **Python Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## 🚀 Step-by-Step Execution

### Step 1: Process Companies (Generate Data)

First, you need companies with embeddings in the database.

**Option A: Process All Companies**
```python
from src.pipeline.coordinator import PipelineCoordinator

# Initialize pipeline
pipeline = PipelineCoordinator()

# Process all companies from data sources
results = pipeline.process_all_companies(limit_per_source=100)

print(f"Processed {len(results)} companies")
```

**Option B: Process Specific Companies**
```python
from src.pipeline.coordinator import PipelineCoordinator

pipeline = PipelineCoordinator()

# Process specific domains
results = pipeline.process_company_list(
    company_domains=["example.com", "startup.io"],
    limit_per_source=100
)
```

**Option C: Use Test Data**
```bash
# Run the pipeline smoke test
python test_pipeline.py
```

**What This Does:**
1. Fetches data from sources (Granola, Affinity, Gmail, Slack)
2. Filters for relevance (Granite 4.0 H Small)
3. Extracts intelligence (Llama 3.3 70B)
4. Stores to Neo4j (creates Company nodes)
5. Stores to PostgreSQL (transcripts, metadata)
6. Generates embeddings (Granite Embedding 278M, 768-dim)
7. Computes similarities (cosine similarity)

**Expected Output:**
```
INFO - Processing 1/5: Example Corp
INFO - Step 2/4: Filtering interactions for Example Corp
INFO - Filtered to 8 relevant interactions
INFO - Step 3/4: Extracting intelligence for Example Corp
INFO - Extracted intelligence (confidence: 0.92)
INFO - Step 4/4: Storing to databases for Example Corp
INFO - Stored to databases (company_id: abc-123-def)
INFO - Generated embedding for company abc-123-def
INFO - Pipeline complete: 5/5 companies processed successfully
```

### Step 2: Verify Embeddings

Check that embeddings were generated:

```python
from src.database.postgres import get_postgres_connection

postgres = get_postgres_connection()

# Check embedding count
query = "SELECT COUNT(*) as count FROM company_embeddings"
result = postgres.execute_query(query, fetch=True)
print(f"Total embeddings: {result[0]['count']}")

# View sample
query = """
    SELECT company_id, 
           LEFT(embedding_text, 100) as text_preview,
           generated_at
    FROM company_embeddings
    ORDER BY generated_at DESC
    LIMIT 5
"""
embeddings = postgres.execute_query(query, fetch=True)
for emb in embeddings:
    print(f"Company: {emb['company_id']}")
    print(f"Text: {emb['text_preview']}...")
    print(f"Generated: {emb['generated_at']}\n")
```

**Expected Output:**
```
Total embeddings: 5
Company: abc-123-def
Text: NeuralEdge is an AI-powered GPU orchestration platform for European ML teams. Sector: AI Infra...
Generated: 2026-05-16 19:30:00
```

### Step 3: Run Clustering Algorithm

Now cluster the companies based on their embeddings:

```python
from src.database.postgres import get_postgres_connection
from src.database.neo4j_client import get_neo4j_driver
from src.pipeline.clustering import MarketMapClusterer

# Initialize clients
postgres = get_postgres_connection()
neo4j = get_neo4j_driver()

# Initialize clusterer
clusterer = MarketMapClusterer(
    postgres_client=postgres,
    neo4j_client=neo4j,
    algorithm="kmeans",  # or "hdbscan"
    n_clusters=None  # Auto-detect optimal number
)

# Run clustering
stats = clusterer.compute_clusters()

print(f"Clustering complete!")
print(f"Clusters: {stats['n_clusters']}")
print(f"Companies: {stats['n_companies']}")
print(f"Silhouette score: {stats['silhouette_score']:.3f}")
print(f"Cluster sizes: {stats['cluster_sizes']}")
```

**Expected Output:**
```
INFO - Starting market map clustering...
INFO - Clustering 5 companies...
INFO - Determined optimal clusters: 3
INFO - Storing cluster definitions...
INFO - Storing company assignments...
INFO - Computing cluster metadata...
INFO - Creating Neo4j cluster relationships...
INFO - Clustering complete: 3 clusters, silhouette score: 0.782

Clustering complete!
Clusters: 3
Companies: 5
Silhouette score: 0.782
Cluster sizes: {0: 2, 1: 2, 2: 1}
```

**What This Does:**
1. Fetches all embeddings from `company_embeddings`
2. Runs clustering algorithm (K-means or HDBSCAN)
3. Stores cluster definitions in `market_clusters`
4. Stores assignments in `company_cluster_assignments`
5. Computes metadata in `cluster_metadata`
6. Creates `Cluster` nodes in Neo4j
7. Creates `BELONGS_TO_CLUSTER` relationships

### Step 4: Generate Cluster Names

Use LLM to generate meaningful names for clusters:

```python
from src.database.postgres import get_postgres_connection
from src.database.neo4j_client import get_neo4j_driver
from src.llm.watsonx_client import WatsonXClient
from src.llm.cluster_namer import ClusterNamer

# Initialize clients
postgres = get_postgres_connection()
neo4j = get_neo4j_driver()
watsonx = WatsonXClient(model="pro")  # Uses Llama 3.3 70B

# Initialize namer
namer = ClusterNamer(
    watsonx_client=watsonx,
    postgres_client=postgres,
    neo4j_client=neo4j
)

# Generate names
result = namer.name_all_clusters()

print(f"Named {result['named']} out of {result['total']} clusters")
```

**Expected Output:**
```
INFO - Starting cluster naming...
INFO - Naming 3 clusters...
INFO - Cluster 0: Enterprise AI Infrastructure
INFO - Cluster 1: Digital Health & Diagnostics
INFO - Cluster 2: Climate Tech Hardware

Named 3 out of 3 clusters
```

**What This Does:**
1. Fetches unnamed clusters with metadata
2. For each cluster, builds prompt with:
   - Common sectors, stages, tags
   - Sample companies
3. Calls LLM (Llama 3.3 70B) to generate name + description
4. Updates `market_clusters.name` in PostgreSQL
5. Updates `Cluster.name` in Neo4j

### Step 5: Verify Clustering Results

Check the database to see the results:

```python
from src.database.postgres import get_postgres_connection

postgres = get_postgres_connection()

# View clusters
query = """
    SELECT 
        mc.cluster_number,
        mc.name,
        mc.description,
        mc.company_count,
        cm.common_sectors,
        cm.common_stages
    FROM market_clusters mc
    LEFT JOIN cluster_metadata cm ON cm.cluster_id = mc.id
    ORDER BY mc.cluster_number
"""
clusters = postgres.execute_query(query, fetch=True)

for cluster in clusters:
    print(f"\n{'='*60}")
    print(f"Cluster {cluster['cluster_number']}: {cluster['name']}")
    print(f"Description: {cluster['description']}")
    print(f"Companies: {cluster['company_count']}")
    print(f"Sectors: {cluster['common_sectors']}")
    print(f"Stages: {cluster['common_stages']}")
```

**Expected Output:**
```
============================================================
Cluster 0: Enterprise AI Infrastructure
Description: Companies building ML platforms and GPU orchestration tools for enterprise teams.
Companies: 2
Sectors: ["AI Infrastructure", "Developer Tools"]
Stages: ["Series A", "Seed"]

============================================================
Cluster 1: Digital Health & Diagnostics
Description: Healthcare technology companies focused on remote care and clinical workflows.
Companies: 2
Sectors: ["Digital Health", "Healthcare"]
Stages: ["Series A", "Series B"]
```

### Step 6: Start the API

```bash
# Start FastAPI server
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

**Test the API:**
```bash
# Get market map
curl http://localhost:8000/market-map | jq

# Get specific cluster
curl http://localhost:8000/market-map/cluster/{cluster_id} | jq

# Health check
curl http://localhost:8000/health | jq
```

**Expected Response:**
```json
{
  "clusters": [
    {
      "id": "uuid-here",
      "cluster_number": 0,
      "name": "Enterprise AI Infrastructure",
      "description": "Companies building ML platforms...",
      "company_count": 2,
      "common_sectors": ["AI Infrastructure"],
      "common_stages": ["Series A"],
      "companies": [
        {
          "id": "company-1",
          "name": "NeuralEdge",
          "one_liner": "AI-powered GPU orchestration",
          "sector": "AI Infrastructure",
          "stage": "Series A",
          "verdict": "diligence",
          "momentum": "accelerating"
        }
      ]
    }
  ],
  "total_companies": 5
}
```

### Step 7: View in Frontend

1. **Start Frontend**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

2. **Navigate to Market Maps**
   ```
   http://localhost:3000/market-maps
   ```

3. **What You'll See:**
   - Interactive cluster visualization
   - Clusters positioned in circular layout
   - Cluster bubbles sized by company count
   - LLM-generated cluster names
   - Click cluster to see companies
   - Company cards with momentum/verdict badges
   - Real-time data from your databases

## 🔄 Re-running Clustering

To regenerate clusters (e.g., after adding more companies):

```python
# 1. Process new companies
pipeline.process_single_company("newcompany.com")

# 2. Re-run clustering (overwrites previous)
stats = clusterer.compute_clusters()

# 3. Re-generate names (only for new/unnamed clusters)
namer.name_all_clusters()

# 4. Refresh frontend (automatic via API)
```

## 🧪 Testing Different Algorithms

### K-means (Fast, Deterministic)
```python
clusterer = MarketMapClusterer(
    postgres_client=postgres,
    neo4j_client=neo4j,
    algorithm="kmeans",
    n_clusters=5  # Fixed number
)
stats = clusterer.compute_clusters()
```

### HDBSCAN (Density-based, Finds Natural Clusters)
```python
clusterer = MarketMapClusterer(
    postgres_client=postgres,
    neo4j_client=neo4j,
    algorithm="hdbscan",
    n_clusters=None  # Auto-detect
)
stats = clusterer.compute_clusters()
```

## 📊 Monitoring & Debugging

### Check Cluster Quality
```python
# Silhouette score (higher is better, range -1 to 1)
print(f"Silhouette: {stats['silhouette_score']:.3f}")

# Good: > 0.5
# Acceptable: 0.25 - 0.5
# Poor: < 0.25
```

### View Company Assignments
```python
query = """
    SELECT 
        c.name as company_name,
        mc.name as cluster_name,
        cca.distance_to_centroid
    FROM company_cluster_assignments cca
    JOIN market_clusters mc ON mc.id = cca.cluster_id
    JOIN (
        SELECT id, name FROM company_embeddings ce
        JOIN LATERAL (
            SELECT name FROM companies WHERE id = ce.company_id
        ) c ON true
    ) c ON c.id = cca.company_id
    ORDER BY mc.cluster_number, cca.distance_to_centroid
"""
assignments = postgres.execute_query(query, fetch=True)
```

### Check Neo4j Graph
```cypher
// View all clusters
MATCH (cl:Cluster)
RETURN cl.cluster_number, cl.name, cl.description

// View companies in a cluster
MATCH (c:Company)-[:BELONGS_TO_CLUSTER]->(cl:Cluster {name: "Enterprise AI Infrastructure"})
RETURN c.name, c.sector, c.stage

// Count companies per cluster
MATCH (c:Company)-[:BELONGS_TO_CLUSTER]->(cl:Cluster)
RETURN cl.name, count(c) as company_count
ORDER BY company_count DESC
```

## 🐛 Troubleshooting

### Issue: No embeddings found
```
ValueError: Need at least 3 companies to cluster
```
**Solution:** Process more companies first
```python
pipeline.process_all_companies()
```

### Issue: Clustering fails with dimension error
```
ValueError: Embedding dimensions don't match
```
**Solution:** Regenerate all embeddings
```python
# Delete old embeddings
postgres.execute_query("DELETE FROM company_embeddings")

# Regenerate
for company_id in company_ids:
    similarity.generate_company_embedding(company_id, company_data)
```

### Issue: Frontend shows "No clusters yet"
**Solution:** Check API is running and accessible
```bash
# Test API
curl http://localhost:8000/market-map

# Check CORS settings in src/api/main.py
# Ensure frontend URL is allowed
```

### Issue: Cluster names not showing
**Solution:** Run cluster namer
```python
namer.name_all_clusters()
```

## 📈 Performance Tips

1. **Batch Processing**
   ```python
   # Process companies in batches
   for batch in company_batches:
       pipeline.process_company_list(batch)
   ```

2. **Optimal Cluster Count**
   ```python
   # Let algorithm auto-detect
   clusterer = MarketMapClusterer(
       postgres_client=postgres,
       neo4j_client=neo4j,
       n_clusters=None  # Auto-detect using silhouette
   )
   ```

3. **Caching**
   - Embeddings are cached in PostgreSQL
   - Only regenerate when company data changes
   - Clustering can be re-run without regenerating embeddings

## 🎯 Next Steps

1. **Automate Pipeline**
   - Schedule clustering to run nightly
   - Auto-generate names for new clusters
   - Update frontend automatically

2. **Add Filters**
   - Filter by sector, stage, verdict
   - Search companies within clusters
   - Export cluster data

3. **Enhance Visualization**
   - Add cluster evolution over time
   - Show similarity edges between companies
   - Interactive cluster editing

---

**Need Help?** Check the [SYSTEM_INTEGRATION_MAP.md](SYSTEM_INTEGRATION_MAP.md) for detailed architecture.