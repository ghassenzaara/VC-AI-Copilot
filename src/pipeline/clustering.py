"""Market Map Clustering - Groups companies by embedding similarity

This module implements clustering algorithms to group similar companies
for market map visualization. It supports both K-means (fast, deterministic)
and HDBSCAN (density-based, finds natural clusters).
"""

import json
import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from sklearn.cluster import KMeans
from hdbscan import HDBSCAN
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
        return self.postgres.execute_query(query, fetch=True)
    
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
            # Fetch companies in this cluster from Neo4j
            query = """
                MATCH (c:Company)
                WHERE c.id IN (
                    SELECT company_id 
                    FROM company_cluster_assignments 
                    WHERE cluster_id = $cluster_id
                )
                RETURN c.id as company_id, c.name as name, c.one_liner as one_liner,
                       c.sector as sector, c.stage as stage, c.tags as tags,
                       c.deal_momentum as deal_momentum
                ORDER BY c.name
            """
            companies = self.neo4j.execute_query(query, {"cluster_id": cluster_id})
            
            if not companies:
                continue
            
            # Aggregate metadata
            sectors = [c['sector'] for c in companies if c.get('sector')]
            stages = [c['stage'] for c in companies if c.get('stage')]
            tags = []
            for c in companies:
                if c.get('tags'):
                    if isinstance(c['tags'], list):
                        tags.extend(c['tags'])
            
            # Get top 3 most common
            from collections import Counter
            common_sectors = [s for s, _ in Counter(sectors).most_common(3)]
            common_stages = [s for s, _ in Counter(stages).most_common(3)]
            common_tags = [t for t, _ in Counter(tags).most_common(5)]
            
            # Sample companies for LLM context (top 5)
            sample_companies = [
                {"name": c['name'], "one_liner": c.get('one_liner', '')}
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
            self.neo4j.execute_write(query, {
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
            self.neo4j.execute_write(query, {
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


# Made with Bob