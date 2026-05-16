# Market Map Clustering - Implementation Plan

## Executive Summary

This plan details the implementation of **LLM-powered market map clustering** for the VC Intelligence platform. The system will:
1. Cluster companies based on embedding similarity
2. Use LLM to generate meaningful cluster names
3. Provide market map visualization and analysis

## Current State Analysis

### ✅ What We Have
- **Embeddings**: 768-dim vectors stored in PostgreSQL (`company_embeddings` table)
- **Similarity Computation**: Cosine similarity via pgvector
- **LLM Infrastructure**: IBM WatsonX (Llama 3.3 70B, Granite 4.0 H Small)
- **Company Data**: Rich profiles with sector, stage, tags, strengths, concerns

### ❌ What's Missing
- Clustering algorithm implementation
- Cluster storage (database schema)
- LLM-based cluster naming
- Market map API endpoints
- Cluster visualization data structures

---

## Architecture Design

### High-Level Flow

```
Company Embeddings (PostgreSQL)
    ↓
Clustering Algorithm (K-means/HDBSCAN)
    ↓
Cluster Assignments (PostgreSQL + Neo4j)
    ↓
LLM Cluster Naming (Llama 3.3 70B)
    ↓
Market Map API (FastAPI)
    ↓
Frontend Visualization
```

---

## Component 1: Database Schema

### PostgreSQL Tables

```sql
-- Cluster definitions
CREATE TABLE IF NOT EXISTS market_clusters (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cluster_number INT NOT NULL,
    name TEXT,  -- LLM-generated name
    description TEXT,  -- LLM-generated description
    centroid VECTOR(768),  -- Cluster center in embedding space
    company_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(cluster_number)
);

-- Company-to-cluster assignments
CREATE TABLE IF NOT EXISTS company_cluster_assignments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id TEXT NOT NULL REFERENCES company_embeddings(company_id),
    cluster_id UUID NOT NULL REFERENCES market_clusters(id),
    distance_to_centroid FLOAT,  -- How close to cluster center
    assigned_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id)  -- Each company in exactly one cluster
);

-- Cluster metadata (for LLM naming context)
CREATE TABLE IF NOT EXISTS cluster_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cluster_id UUID NOT NULL REFERENCES market_clusters(id),
    common_sectors JSONB,  -- ["AI Infrastructure", "B2B SaaS"]
    common_stages JSONB,   -- ["Seed", "Series A"]
    common_tags JSONB,     -- ["B2B", "Enterprise", "AI"]
    avg_deal_momentum TEXT,  -- "accelerating" | "stable" | etc.
    sample_companies JSONB,  -- [{name, one_liner}] for LLM context
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_cluster_assignments_company ON company_cluster_assignments(company_id);
CREATE INDEX idx_cluster_assignments_cluster ON company_cluster_assignments(cluster_id);
CREATE INDEX idx_cluster_metadata_cluster ON cluster_metadata(cluster_id);
```

### Neo4j Schema

```cypher
// Cluster node
CREATE CONSTRAINT cluster_id IF NOT EXISTS
FOR (cl:Cluster) REQUIRE cl.id IS UNIQUE;

CREATE INDEX cluster_name IF NOT EXISTS
FOR (cl:Cluster) ON (cl.name);

// Relationship: Company belongs to Cluster
// (Company)-[:BELONGS_TO_CLUSTER {distance: float}]->(Cluster)
```

---

## Component 2: Clustering Algorithm

### File: `src/pipeline/clustering.py`

```python
"""Market Map Clustering - Groups companies by embedding similarity"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sklearn.cluster import KMeans, HDBSCAN
from sklearn.metrics import silhouette_score

from src.database.postgres import PostgresClient
from src.database.neo4j_client import Neo4jClient


logger = logging.getLogger(__name__)


class MarketMapClusterer:
    """Clusters companies for market map visualization"""
    
    def __init__(
        self,
        postgres_client: PostgresClient,
        neo4j_client: Neo4jClient,
        algorithm: str = "kmeans",  # "kmeans" or "hdbscan"
        n_clusters: Optional[int] = None,  # Auto-detect if None
    ):
        """Initialize clusterer
        
        Args:
            postgres_client: PostgreSQL client
            neo4j_client: Neo4j client
            algorithm: Clustering algorithm ("kmeans" or "hdbscan")
            n_clusters: Number of clusters (None = auto-detect)
        """
        self.postgres = postgres_client
        self.neo4j = neo4j_client
        self.algorithm = algorithm
        self.n_clusters = n_clusters
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def compute_clusters(self) -> Dict[str, Any]:
        """Compute clusters for all companies with embeddings
        
        Returns:
            Dict with clustering statistics
        """
        self.logger.info("Starting market map clustering...")
        
        # 1. Fetch all embeddings
        embeddings_data = self._fetch_embeddings()
        if len(embeddings_data) < 3:
            raise ValueError("Need at least 3 companies to cluster")
        
        company_ids = [row['company_id'] for row in embeddings_data]
        embeddings = np.array([row['embedding'] for row in embeddings_data])
        
        self.logger.info(f"Clustering {len(company_ids)} companies...")
        
        # 2. Determine optimal number of clusters if not specified
        if self.n_clusters is None:
            self.n_clusters = self._determine_optimal_clusters(embeddings)
        
        # 3. Run clustering algorithm
        if self.algorithm == "kmeans":
            labels, centroids = self._kmeans_clustering(embeddings)
        elif self.algorithm == "hdbscan":
            labels, centroids = self._hdbscan_clustering(embeddings)
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")
        
        # 4. Store cluster definitions
        cluster_ids = self._store_cluster_definitions(centroids)
        
        # 5. Store company assignments
        self._store_company_assignments(company_ids, labels, embeddings, centroids, cluster_ids)
        
        # 6. Compute cluster metadata
        self._compute_cluster_metadata(cluster_ids)
        
        # 7. Create Neo4j relationships
        self._create_neo4j_cluster_relationships(company_ids, labels, cluster_ids)
        
        # 8. Calculate statistics
        stats = self._calculate_clustering_stats(labels, embeddings)
        
        self.logger.info(
            f"Clustering complete: {len(set(labels))} clusters, "
            f"silhouette score: {stats['silhouette_score']:.3f}"
        )
        
        return stats
    
    def _fetch_embeddings(self) -> List[Dict[str, Any]]:
        """Fetch all company embeddings from PostgreSQL"""
        query = """
            SELECT company_id, embedding
            FROM company_embeddings
            WHERE embedding IS NOT NULL
            ORDER BY company_id
        """
        return self.postgres.execute_query(query)
    
    def _determine_optimal_clusters(self, embeddings: np.ndarray) -> int:
        """Use elbow method to find optimal k
        
        Tests k from 3 to sqrt(n), picks best silhouette score
        """
        n = len(embeddings)
        max_k = min(int(np.sqrt(n)), 15)  # Cap at 15 clusters
        min_k = 3
        
        best_k = min_k
        best_score = -1
        
        for k in range(min_k, max_k + 1):
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings)
            score = silhouette_score(embeddings, labels)
            
            self.logger.debug(f"k={k}, silhouette={score:.3f}")
            
            if score > best_score:
                best_score = score
                best_k = k
        
        self.logger.info(f"Optimal clusters: {best_k} (silhouette={best_score:.3f})")
        return best_k
    
    def _kmeans_clustering(
        self,
        embeddings: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Run K-means clustering
        
        Returns:
            (labels, centroids)
        """
        kmeans = KMeans(
            n_clusters=self.n_clusters,
            random_state=42,
            n_init=10,
            max_iter=300
        )
        labels = kmeans.fit_predict(embeddings)
        centroids = kmeans.cluster_centers_
        
        return labels, centroids
    
    def _hdbscan_clustering(
        self,
        embeddings: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Run HDBSCAN clustering (density-based)
        
        Returns:
            (labels, centroids)
        """
        clusterer = HDBSCAN(
            min_cluster_size=3,
            min_samples=2,
            metric='euclidean'
        )
        labels = clusterer.fit_predict(embeddings)
        
        # Compute centroids for each cluster
        unique_labels = set(labels)
        if -1 in unique_labels:
            unique_labels.remove(-1)  # Remove noise cluster
        
        centroids = []
        for label in sorted(unique_labels):
            mask = labels == label
            centroid = embeddings[mask].mean(axis=0)
            centroids.append(centroid)
        
        return labels, np.array(centroids)
    
    def _store_cluster_definitions(self, centroids: np.ndarray) -> List[str]:
        """Store cluster definitions in PostgreSQL
        
        Returns:
            List of cluster UUIDs
        """
        cluster_ids = []
        
        for i, centroid in enumerate(centroids):
            query = """
                INSERT INTO market_clusters (cluster_number, centroid)
                VALUES (%s, %s)
                RETURNING id
            """
            result = self.postgres.execute_query(
                query,
                (i, centroid.tolist()),
                fetch=True
            )
            cluster_ids.append(result[0]['id'])
        
        return cluster_ids
    
    def _store_company_assignments(
        self,
        company_ids: List[str],
        labels: np.ndarray,
        embeddings: np.ndarray,
        centroids: np.ndarray,
        cluster_ids: List[str]
    ):
        """Store company-to-cluster assignments"""
        for company_id, label, embedding in zip(company_ids, labels, embeddings):
            if label == -1:  # Noise in HDBSCAN
                continue
            
            cluster_id = cluster_ids[label]
            centroid = centroids[label]
            distance = np.linalg.norm(embedding - centroid)
            
            query = """
                INSERT INTO company_cluster_assignments
                (company_id, cluster_id, distance_to_centroid)
                VALUES (%s, %s, %s)
                ON CONFLICT (company_id) DO UPDATE
                SET cluster_id = EXCLUDED.cluster_id,
                    distance_to_centroid = EXCLUDED.distance_to_centroid,
                    assigned_at = NOW()
            """
            self.postgres.execute_query(query, (company_id, cluster_id, float(distance)))
    
    def _compute_cluster_metadata(self, cluster_ids: List[str]):
        """Compute metadata for each cluster (for LLM naming)"""
        for cluster_id in cluster_ids:
            # Fetch companies in this cluster
            query = """
                SELECT 
                    c.company_id,
                    c.name,
                    c.one_liner,
                    c.sector,
                    c.stage,
                    c.tags,
                    c.deal_momentum
                FROM company_cluster_assignments cca
                JOIN companies c ON c.id = cca.company_id
                WHERE cca.cluster_id = %s
            """
            companies = self.postgres.execute_query(query, (cluster_id,))
            
            if not companies:
                continue
            
            # Aggregate metadata
            sectors = [c['sector'] for c in companies if c['sector']]
            stages = [c['stage'] for c in companies if c['stage']]
            tags = []
            for c in companies:
                if c['tags']:
                    tags.extend(c['tags'])
            
            # Get top 3 most common
            from collections import Counter
            common_sectors = [s for s, _ in Counter(sectors).most_common(3)]
            common_stages = [s for s, _ in Counter(stages).most_common(3)]
            common_tags = [t for t, _ in Counter(tags).most_common(5)]
            
            # Sample companies for LLM context (top 5 by distance to centroid)
            sample_companies = [
                {"name": c['name'], "one_liner": c['one_liner']}
                for c in companies[:5]
            ]
            
            # Store metadata
            query = """
                INSERT INTO cluster_metadata
                (cluster_id, common_sectors, common_stages, common_tags, sample_companies)
                VALUES (%s, %s, %s, %s, %s)
            """
            self.postgres.execute_query(
                query,
                (
                    cluster_id,
                    json.dumps(common_sectors),
                    json.dumps(common_stages),
                    json.dumps(common_tags),
                    json.dumps(sample_companies)
                )
            )
    
    def _create_neo4j_cluster_relationships(
        self,
        company_ids: List[str],
        labels: np.ndarray,
        cluster_ids: List[str]
    ):
        """Create BELONGS_TO_CLUSTER relationships in Neo4j"""
        # First, create Cluster nodes
        for i, cluster_id in enumerate(cluster_ids):
            query = """
                MERGE (cl:Cluster {id: $cluster_id})
                SET cl.cluster_number = $cluster_number
            """
            self.neo4j.execute_query(query, {
                "cluster_id": cluster_id,
                "cluster_number": i
            })
        
        # Then create relationships
        for company_id, label in zip(company_ids, labels):
            if label == -1:
                continue
            
            cluster_id = cluster_ids[label]
            query = """
                MATCH (c:Company {id: $company_id})
                MATCH (cl:Cluster {id: $cluster_id})
                MERGE (c)-[:BELONGS_TO_CLUSTER]->(cl)
            """
            self.neo4j.execute_query(query, {
                "company_id": company_id,
                "cluster_id": cluster_id
            })
    
    def _calculate_clustering_stats(
        self,
        labels: np.ndarray,
        embeddings: np.ndarray
    ) -> Dict[str, Any]:
        """Calculate clustering quality metrics"""
        unique_labels = set(labels)
        if -1 in unique_labels:
            unique_labels.remove(-1)
        
        n_clusters = len(unique_labels)
        n_noise = np.sum(labels == -1)
        
        # Silhouette score (only if we have 2+ clusters)
        silhouette = 0.0
        if n_clusters >= 2:
            silhouette = silhouette_score(embeddings, labels)
        
        # Cluster sizes
        cluster_sizes = {}
        for label in unique_labels:
            cluster_sizes[int(label)] = int(np.sum(labels == label))
        
        return {
            "n_clusters": n_clusters,
            "n_companies": len(labels),
            "n_noise": n_noise,
            "silhouette_score": float(silhouette),
            "cluster_sizes": cluster_sizes
        }
```

---

## Component 3: LLM Cluster Naming

### File: `src/llm/cluster_namer.py`

```python
"""LLM-based Cluster Naming - Generates meaningful names for market clusters"""

import logging
from typing import Dict, Any, List

from src.llm.watsonx_client import WatsonXClient
from src.database.postgres import PostgresClient


logger = logging.getLogger(__name__)


class ClusterNamer:
    """Generates LLM-powered names and descriptions for clusters"""
    
    def __init__(
        self,
        watsonx_client: WatsonXClient,
        postgres_client: PostgresClient
    ):
        """Initialize cluster namer
        
        Args:
            watsonx_client: WatsonX client (should use "pro" model)
            postgres_client: PostgreSQL client
        """
        self.client = watsonx_client
        self.postgres = postgres_client
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def name_all_clusters(self) -> Dict[str, Any]:
        """Generate names for all clusters
        
        Returns:
            Dict with naming statistics
        """
        self.logger.info("Starting cluster naming...")
        
        # Fetch all clusters
        query = """
            SELECT 
                mc.id,
                mc.cluster_number,
                cm.common_sectors,
                cm.common_stages,
                cm.common_tags,
                cm.sample_companies
            FROM market_clusters mc
            LEFT JOIN cluster_metadata cm ON cm.cluster_id = mc.id
            WHERE mc.name IS NULL
        """
        clusters = self.postgres.execute_query(query)
        
        if not clusters:
            self.logger.info("No unnamed clusters found")
            return {"named": 0}
        
        self.logger.info(f"Naming {len(clusters)} clusters...")
        
        named_count = 0
        for cluster in clusters:
            try:
                name, description = self._generate_cluster_name(cluster)
                self._store_cluster_name(cluster['id'], name, description)
                named_count += 1
                self.logger.info(f"Cluster {cluster['cluster_number']}: {name}")
            except Exception as e:
                self.logger.error(f"Failed to name cluster {cluster['id']}: {e}")
        
        return {"named": named_count, "total": len(clusters)}
    
    def _generate_cluster_name(
        self,
        cluster: Dict[str, Any]
    ) -> tuple[str, str]:
        """Generate name and description for a cluster
        
        Returns:
            (name, description)
        """
        prompt = self._build_naming_prompt(cluster)
        
        response = self.client.generate_json(
            prompt=prompt,
            temperature=0.3,  # Slightly creative
            max_tokens=500
        )
        
        name = response.get('name', f"Cluster {cluster['cluster_number']}")
        description = response.get('description', '')
        
        return name, description
    
    def _build_naming_prompt(self, cluster: Dict[str, Any]) -> str:
        """Build prompt for cluster naming"""
        return f"""You are analyzing a cluster of similar companies in a VC portfolio.

**Cluster Metadata:**
- Common Sectors: {cluster['common_sectors']}
- Common Stages: {cluster['common_stages']}
- Common Tags: {cluster['common_tags']}

**Sample Companies:**
{self._format_sample_companies(cluster['sample_companies'])}

**Task:**
Generate a concise, descriptive name for this cluster that captures the common theme.
Also provide a 1-2 sentence description explaining what unites these companies.

**Guidelines:**
- Name should be 2-5 words, professional, and specific
- Focus on the business model, technology, or market segment
- Examples: "Enterprise AI Infrastructure", "B2B SaaS Platforms", "Climate Tech Hardware"
- Avoid generic terms like "Tech Startups" or "Software Companies"

**Output Format:**
Return ONLY valid JSON:
{{
  "name": "Cluster Name Here",
  "description": "Brief description of what unites these companies."
}}"""
    
    def _format_sample_companies(self, sample_companies: List[Dict]) -> str:
        """Format sample companies for prompt"""
        if not sample_companies:
            return "No sample companies available"
        
        lines = []
        for i, company in enumerate(sample_companies, 1):
            name = company.get('name', 'Unknown')
            one_liner = company.get('one_liner', 'No description')
            lines.append(f"{i}. {name}: {one_liner}")
        
        return "\n".join(lines)
    
    def _store_cluster_name(
        self,
        cluster_id: str,
        name: str,
        description: str
    ):
        """Store cluster name and description"""
        query = """
            UPDATE market_clusters
            SET name = %s,
                description = %s,
                updated_at = NOW()
            WHERE id = %s
        """
        self.postgres.execute_query(query, (name, description, cluster_id))
```

### Prompt Template: `src/llm/prompts/cluster_naming.txt`

```
You are analyzing a cluster of similar companies in a VC portfolio.

**Cluster Metadata:**
- Common Sectors: {{COMMON_SECTORS}}
- Common Stages: {{COMMON_STAGES}}
- Common Tags: {{COMMON_TAGS}}

**Sample Companies:**
{{SAMPLE_COMPANIES}}

**Task:**
Generate a concise, descriptive name for this cluster that captures the common theme.
Also provide a 1-2 sentence description explaining what unites these companies.

**Guidelines:**
- Name should be 2-5 words, professional, and specific
- Focus on the business model, technology, or market segment
- Examples: "Enterprise AI Infrastructure", "B2B SaaS Platforms", "Climate Tech Hardware"
- Avoid generic terms like "Tech Startups" or "Software Companies"

**Output Format:**
Return ONLY valid JSON:
{
  "name": "Cluster Name Here",
  "description": "Brief description of what unites these companies."
}
```

---

## Component 4: API Endpoints

### File: `src/api/main.py` (additions)

```python
# Add to existing FastAPI app

from src.pipeline.clustering import MarketMapClusterer
from src.llm.cluster_namer import ClusterNamer

# ... existing code ...

@app.post("/clustering/compute")
async def compute_clusters(
    algorithm: str = "kmeans",
    n_clusters: Optional[int] = None
):
    """Compute market map clusters
    
    Args:
        algorithm: "kmeans" or "hdbscan"
        n_clusters: Number of clusters (None = auto-detect)
    """
    try:
        clusterer = MarketMapClusterer(
            postgres_client=postgres,
            neo4j_client=neo4j,
            algorithm=algorithm,
            n_clusters=n_clusters
        )
        
        stats = clusterer.compute_clusters()
        
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Clustering failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/clustering/name-clusters")
async def name_clusters():
    """Generate LLM names for all unnamed clusters"""
    try:
        namer = ClusterNamer(
            watsonx_client=pro_client,
            postgres_client=postgres
        )
        
        result = namer.name_all_clusters()
        
        return {
            "success": True,
            "named": result['named'],
            "total": result.get('total', result['named'])
        }
    except Exception as e:
        logger.error(f"Cluster naming failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/market-map")
async def get_market_map():
    """Get complete market map with clusters"""
    try:
        query = """
            SELECT 
                mc.id as cluster_id,
                mc.cluster_number,
                mc.name as cluster_name,
                mc.description as cluster_description,
                mc.company_count,
                json_agg(
                    json_build_object(
                        'id', c.id,
                        'name', c.name,
                        'one_liner', c.one_liner,
                        'sector', c.sector,
                        'stage', c.stage,
                        'verdict', c.verdict,
                        'deal_momentum', c.deal_momentum,
                        'distance_to_centroid', cca.distance_to_centroid
                    )
                ) as companies
            FROM market_clusters mc
            JOIN company_cluster_assignments cca ON cca.cluster_id = mc.id
            JOIN companies c ON c.id = cca.company_id
            GROUP BY mc.id, mc.cluster_number, mc.name, mc.description, mc.company_count
            ORDER BY mc.cluster_number
        """
        
        clusters = postgres.execute_query(query)
        
        return {
            "clusters": clusters,
            "total_clusters": len(clusters),
            "total_companies": sum(c['company_count'] for c in clusters)
        }
    except Exception as e:
        logger.error(f"Failed to fetch market map: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/market-map/cluster/{cluster_id}")
async def get_cluster_details(cluster_id: str):
    """Get detailed information about a specific cluster"""
    try:
        # Cluster info
        cluster_query = """
            SELECT 
                mc.*,
                cm.common_sectors,
                cm.common_stages,
                cm.common_tags
            FROM market_clusters mc
            LEFT JOIN cluster_metadata cm ON cm.cluster_id = mc.id
            WHERE mc.id = %s
        """
        cluster = postgres.execute_query(cluster_query, (cluster_id,))
        
        if not cluster:
            raise HTTPException(status_code=404, detail="Cluster not found")
        
        # Companies in cluster
        companies_query = """
            SELECT 
                c.*,
                cca.distance_to_centroid
            FROM company_cluster_assignments cca
            JOIN companies c ON c.id = cca.company_id
            WHERE cca.cluster_id = %s
            ORDER BY cca.distance_to_centroid ASC
        """
        companies = postgres.execute_query(companies_query, (cluster_id,))
        
        return {
            "cluster": cluster[0],
            "companies": companies
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch cluster details: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

---

## Component 5: Integration with Existing Pipeline

### Update: `src/pipeline/coordinator.py`

```python
# Add to PipelineCoordinator.__init__

from src.pipeline.clustering import MarketMapClusterer
from src.llm.cluster_namer import ClusterNamer

# In __init__ method:
self.clusterer = MarketMapClusterer(
    postgres_client=self.postgres,
    neo4j_client=self.neo4j,
    algorithm="kmeans"
)

self.cluster_namer = ClusterNamer(
    watsonx_client=self.pro_client,
    postgres_client=self.postgres
)

# Add new method:
def compute_market_map(self, name_clusters: bool = True) -> Dict[str, Any]:
    """Compute market map clusters and optionally name them
    
    Args:
        name_clusters: Whether to generate LLM names
        
    Returns:
        Dict with clustering and naming results
    """
    self.logger.info("Computing market map...")
    
    # 1. Compute clusters
    clustering_stats = self.clusterer.compute_clusters()
    
    result = {
        "clustering": clustering_stats,
        "naming": None
    }
    
    # 2. Name clusters if requested
    if name_clusters:
        self.logger.info("Generating cluster names...")
        naming_stats = self.cluster_namer.name_all_clusters()
        result["naming"] = naming_stats
    
    return result
```

---

## Component 6: Dependencies

### Add to `requirements.txt`

```
# Clustering
scikit-learn==1.3.2
hdbscan==0.8.33
```

---

## Implementation Phases

### Phase 1: Core Clustering (Week 1)
- [ ] Create database schema (PostgreSQL + Neo4j)
- [ ] Implement `MarketMapClusterer` class
- [ ] Add clustering API endpoints
- [ ] Test with existing embeddings

### Phase 2: LLM Naming (Week 1-2)
- [ ] Implement `ClusterNamer` class
- [ ] Create cluster naming prompt
- [ ] Add naming API endpoint
- [ ] Test name generation quality

### Phase 3: Integration (Week 2)
- [ ] Integrate with `PipelineCoordinator`
- [ ] Add market map API endpoints
- [ ] Create data structures for frontend
- [ ] Test end-to-end flow

### Phase 4: Optimization (Week 3)
- [ ] Tune clustering parameters
- [ ] Optimize database queries
- [ ] Add caching for market map
- [ ] Performance testing

---

## Testing Strategy

### Unit Tests

```python
# tests/test_clustering.py

def test_clustering_with_mock_embeddings():
    """Test clustering with synthetic embeddings"""
    pass

def test_optimal_cluster_detection():
    """Test elbow method for k selection"""
    pass

def test_cluster_metadata_computation():
    """Test metadata aggregation"""
    pass

# tests/test_cluster_naming.py

def test_cluster_name_generation():
    """Test LLM cluster naming"""
    pass

def test_naming_prompt_building():
    """Test prompt construction"""
    pass
```

### Integration Tests

```python
# tests/test_market_map_integration.py

def test_full_market_map_pipeline():
    """Test complete flow: embeddings → clustering → naming → API"""
    pass

def test_market_map_api_endpoints():
    """Test all market map endpoints"""
    pass
```

---

## API Usage Examples

### 1. Compute Clusters

```bash
POST /clustering/compute
{
  "algorithm": "kmeans",
  "n_clusters": null  # Auto-detect
}

Response:
{
  "success": true,
  "stats": {
    "n_clusters": 5,
    "n_companies": 42,
    "silhouette_score": 0.67,
    "cluster_sizes": {
      "0": 12,
      "1": 8,
      "2": 10,
      "3": 7,
      "4": 5
    }
  }
}
```

### 2. Name Clusters

```bash
POST /clustering/name-clusters

Response:
{
  "success": true,
  "named": 5,
  "total": 5
}
```

### 3. Get Market Map

```bash
GET /market-map

Response:
{
  "clusters": [
    {
      "cluster_id": "uuid",
      "cluster_number": 0,
      "cluster_name": "Enterprise AI Infrastructure",
      "cluster_description": "Companies building foundational AI infrastructure for enterprise deployment",
      "company_count": 12,
      "companies": [
        {
          "id": "uuid",
          "name": "Acme AI",
          "one_liner": "GPU orchestration for ML workloads",
          "sector": "AI Infrastructure",
          "stage": "Series A",
          "verdict": "diligence",
          "distance_to_centroid": 0.23
        }
      ]
    }
  ],
  "total_clusters": 5,
  "total_companies": 42
}
```

---

## Performance Considerations

### Clustering Performance
- **Small portfolios (<100 companies)**: K-means, instant
- **Medium portfolios (100-500)**: K-means, <5 seconds
- **Large portfolios (>500)**: Consider HDBSCAN or batch processing

### LLM Naming Performance
- **Per cluster**: ~2-3 seconds (Llama 3.3 70B)
- **5 clusters**: ~10-15 seconds total
- **Can be run async/background**

### Caching Strategy
- Cache market map response for 1 hour
- Invalidate on new clustering run
- Store in Redis or in-memory

---

## Monitoring & Observability

### Metrics to Track
- Clustering quality (silhouette score)
- Cluster size distribution
- LLM naming success rate
- API response times
- Cache hit rates

### Logging
- Log clustering parameters and results
- Log LLM prompts and responses
- Log API access patterns

---

## Future Enhancements

### Phase 2 Features
- [ ] Dynamic re-clustering (weekly/monthly)
- [ ] Cluster evolution tracking over time
- [ ] Sub-cluster detection (hierarchical)
- [ ] Cluster comparison and diff
- [ ] Export market map as PDF/PNG

### Advanced Features
- [ ] Multi-dimensional clustering (sector + stage + momentum)
- [ ] Anomaly detection (companies that don't fit any cluster)
- [ ] Cluster-based recommendations
- [ ] Competitive landscape analysis per cluster

---

## Success Criteria

### Functional Requirements
- ✅ Clusters companies based on embedding similarity
- ✅ Generates meaningful, LLM-powered cluster names
- ✅ Provides market map API for visualization
- ✅ Integrates with existing pipeline

### Quality Requirements
- Silhouette score > 0.5 (good clustering)
- Cluster names are descriptive and specific
- API response time < 500ms (with caching)
- 95%+ uptime for clustering service

---

## Conclusion

This implementation plan provides a complete, production-ready market map clustering system that:

1. **Leverages existing infrastructure** (embeddings, LLM, databases)
2. **Uses proven algorithms** (K-means, HDBSCAN)
3. **Adds LLM intelligence** (cluster naming)
4. **Provides clean APIs** (FastAPI endpoints)
5. **Scales efficiently** (optimized queries, caching)

The system can be implemented in 2-3 weeks and will provide valuable market insights for VC deal flow analysis.