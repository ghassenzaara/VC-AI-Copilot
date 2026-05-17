"""Market Map Clustering - per-user company clustering for the market map.

All reads, writes, and Cypher merges are scoped to the calling user's `clerk_id`.
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
    """Clusters one user's companies for market map visualization."""

    def __init__(
        self,
        postgres_client: PostgresClient,
        neo4j_client: Neo4jClient,
        algorithm: str = "kmeans",
        n_clusters: Optional[int] = None,
    ):
        self.postgres = postgres_client
        self.neo4j = neo4j_client
        self.algorithm = algorithm
        self.n_clusters = n_clusters
        self.logger = logging.getLogger(self.__class__.__name__)

    def compute_clusters(self, clerk_id: str) -> Dict[str, Any]:
        self.logger.info("Starting market map clustering for user=%s", clerk_id)

        embeddings_data = self._fetch_embeddings(clerk_id)
        if len(embeddings_data) < 3:
            raise ValueError("Need at least 3 companies to cluster")

        company_ids = [row['company_id'] for row in embeddings_data]
        embeddings = np.array([row['embedding'] for row in embeddings_data])

        self.logger.info("Clustering %d companies...", len(company_ids))

        if self.n_clusters is None:
            self.n_clusters = self._determine_optimal_clusters(embeddings)

        if self.algorithm == "kmeans":
            labels, centroids = self._kmeans_clustering(embeddings)
        elif self.algorithm == "hdbscan":
            labels, centroids = self._hdbscan_clustering(embeddings)
        else:
            raise ValueError(f"Unknown algorithm: {self.algorithm}")

        cluster_ids = self._store_cluster_definitions(clerk_id, centroids)
        self._store_company_assignments(
            clerk_id, company_ids, labels, embeddings, centroids, cluster_ids
        )
        # Create Neo4j :Cluster nodes + BELONGS_TO_CLUSTER edges BEFORE
        # metadata so metadata can reflect the actual cluster membership.
        self._create_neo4j_cluster_relationships(clerk_id, company_ids, labels, cluster_ids)
        self._compute_cluster_metadata(clerk_id, cluster_ids)

        stats = self._calculate_clustering_stats(labels, embeddings)
        self.logger.info(
            "Clustering complete: %d clusters, silhouette score: %.3f",
            len(set(labels)), stats['silhouette_score'],
        )
        return stats

    def _fetch_embeddings(self, clerk_id: str) -> List[Dict[str, Any]]:
        query = """
            SELECT company_id, embedding
            FROM company_embeddings
            WHERE owner_clerk_id = %s AND embedding IS NOT NULL
            ORDER BY company_id
        """
        return self.postgres.execute_query(query, (clerk_id,), fetch=True)

    def _determine_optimal_clusters(self, embeddings: np.ndarray) -> int:
        n = len(embeddings)
        max_k = min(int(np.sqrt(n)), 15)
        min_k = 3

        best_k = min_k
        best_score = -1

        for k in range(min_k, max_k + 1):
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = kmeans.fit_predict(embeddings)
            score = silhouette_score(embeddings, labels)
            self.logger.debug("k=%d, silhouette=%.3f", k, score)
            if score > best_score:
                best_score = score
                best_k = k

        self.logger.info("Optimal clusters: %d (silhouette=%.3f)", best_k, best_score)
        return best_k

    def _kmeans_clustering(
        self, embeddings: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        kmeans = KMeans(
            n_clusters=self.n_clusters,
            random_state=42,
            n_init=10,
            max_iter=300,
        )
        labels = kmeans.fit_predict(embeddings)
        return labels, kmeans.cluster_centers_

    def _hdbscan_clustering(
        self, embeddings: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        clusterer = HDBSCAN(
            min_cluster_size=3,
            min_samples=2,
            metric='euclidean',
        )
        labels = clusterer.fit_predict(embeddings)

        unique_labels = set(labels)
        if -1 in unique_labels:
            unique_labels.remove(-1)

        centroids = []
        for label in sorted(unique_labels):
            mask = labels == label
            centroid = embeddings[mask].mean(axis=0)
            centroids.append(centroid)

        return labels, np.array(centroids)

    def _store_cluster_definitions(
        self, clerk_id: str, centroids: np.ndarray
    ) -> List[str]:
        cluster_ids: List[str] = []
        for i, centroid in enumerate(centroids):
            query = """
                INSERT INTO market_clusters (owner_clerk_id, cluster_number, centroid)
                VALUES (%s, %s, %s)
                ON CONFLICT (owner_clerk_id, cluster_number) DO UPDATE
                    SET centroid   = EXCLUDED.centroid,
                        updated_at = NOW()
                RETURNING id
            """
            result = self.postgres.execute_query(
                query, (clerk_id, i, centroid.tolist()), fetch=True
            )
            # Force str — psycopg2 returns UUID objects but Neo4j stores the
            # property as a string; passing the UUID native type produces a
            # silent mismatch when we later MATCH on `id`.
            cluster_ids.append(str(result[0]['id']))
        return cluster_ids

    def _store_company_assignments(
        self,
        clerk_id: str,
        company_ids: List[str],
        labels: np.ndarray,
        embeddings: np.ndarray,
        centroids: np.ndarray,
        cluster_ids: List[str],
    ):
        for company_id, label, embedding in zip(company_ids, labels, embeddings):
            if label == -1:
                continue
            cluster_id = cluster_ids[label]
            centroid = centroids[label]
            distance = np.linalg.norm(embedding - centroid)
            query = """
                INSERT INTO company_cluster_assignments
                    (owner_clerk_id, company_id, cluster_id, distance_to_centroid)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (owner_clerk_id, company_id) DO UPDATE
                SET cluster_id           = EXCLUDED.cluster_id,
                    distance_to_centroid = EXCLUDED.distance_to_centroid,
                    assigned_at          = NOW()
            """
            # cluster_id is already a str (forced in _store_cluster_definitions);
            # PG accepts both UUID and string for uuid columns.
            self.postgres.execute_query(
                query,
                (clerk_id, company_id, cluster_id, float(distance)),
                fetch=False,
            )

    def _compute_cluster_metadata(self, clerk_id: str, cluster_ids: List[str]):
        """Read cluster members via BELONGS_TO_CLUSTER and write aggregated
        metadata. Runs AFTER Neo4j relationships exist so we read the truth,
        not a stale PG sample."""
        for cluster_id in cluster_ids:
            query = """
                MATCH (cl:Cluster {clerk_id: $clerk_id, id: $cluster_id})
                      <-[:BELONGS_TO_CLUSTER]-(c:Company {clerk_id: $clerk_id})
                RETURN c.id as company_id, c.name as name, c.one_liner as one_liner,
                       c.sector as sector, c.stage as stage, c.tags as tags,
                       c.deal_momentum as deal_momentum
                ORDER BY c.name
            """
            companies = self.neo4j.execute_query(
                query, {"clerk_id": clerk_id, "cluster_id": cluster_id}
            )
            if not companies:
                self.logger.warning(
                    "Cluster %s has no Neo4j members — skipping metadata write",
                    cluster_id,
                )
                continue

            sectors = [c['sector'] for c in companies if c.get('sector')]
            stages = [c['stage'] for c in companies if c.get('stage')]
            tags: List[str] = []
            for c in companies:
                if c.get('tags') and isinstance(c['tags'], list):
                    tags.extend(c['tags'])

            from collections import Counter
            common_sectors = [s for s, _ in Counter(sectors).most_common(3)]
            common_stages = [s for s, _ in Counter(stages).most_common(3)]
            common_tags = [t for t, _ in Counter(tags).most_common(5)]
            # Keep ALL companies (not just 5) so naming can use full context.
            sample_companies = [
                {"name": c['name'], "one_liner": c.get('one_liner', '') or ''}
                for c in companies
            ]

            # Refresh metadata: delete + insert so re-runs don't accumulate rows.
            self.postgres.execute_query(
                """
                DELETE FROM cluster_metadata
                WHERE owner_clerk_id = %s AND cluster_id = %s
                """,
                (clerk_id, cluster_id),
                fetch=False,
            )
            self.postgres.execute_query(
                """
                INSERT INTO cluster_metadata
                (owner_clerk_id, cluster_id, common_sectors, common_stages, common_tags, sample_companies)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    clerk_id,
                    cluster_id,
                    json.dumps(common_sectors),
                    json.dumps(common_stages),
                    json.dumps(common_tags),
                    json.dumps(sample_companies),
                ),
                fetch=False,
            )
            # Also keep market_clusters.company_count fresh.
            self.postgres.execute_query(
                """
                UPDATE market_clusters
                SET company_count = %s, updated_at = NOW()
                WHERE id = %s AND owner_clerk_id = %s
                """,
                (len(companies), cluster_id, clerk_id),
                fetch=False,
            )

    def _create_neo4j_cluster_relationships(
        self,
        clerk_id: str,
        company_ids: List[str],
        labels: np.ndarray,
        cluster_ids: List[str],
    ):
        # Create Cluster nodes per user
        for i, cluster_id in enumerate(cluster_ids):
            query = """
                MERGE (u:User {clerk_id: $clerk_id})
                MERGE (cl:Cluster {clerk_id: $clerk_id, id: $cluster_id})
                SET cl.cluster_number = $cluster_number
                MERGE (u)-[:OWNS]->(cl)
            """
            self.neo4j.execute_write(
                query,
                {
                    "clerk_id": clerk_id,
                    "cluster_id": cluster_id,
                    "cluster_number": i,
                },
            )

        for company_id, label in zip(company_ids, labels):
            if label == -1:
                continue
            cluster_id = cluster_ids[label]
            query = """
                MATCH (c:Company {clerk_id: $clerk_id, id: $company_id})
                MATCH (cl:Cluster {clerk_id: $clerk_id, id: $cluster_id})
                MERGE (c)-[:BELONGS_TO_CLUSTER]->(cl)
            """
            self.neo4j.execute_write(
                query,
                {
                    "clerk_id": clerk_id,
                    "company_id": company_id,
                    "cluster_id": cluster_id,
                },
            )

    def _calculate_clustering_stats(
        self, labels: np.ndarray, embeddings: np.ndarray
    ) -> Dict[str, Any]:
        unique_labels = set(labels)
        if -1 in unique_labels:
            unique_labels.remove(-1)

        n_clusters = len(unique_labels)
        n_noise = int(np.sum(labels == -1))

        silhouette = 0.0
        if n_clusters >= 2:
            silhouette = silhouette_score(embeddings, labels)

        # Cast everything to native Python types so FastAPI's JSON encoder
        # can serialize the response (numpy scalars are not JSON-serializable).
        cluster_sizes = {
            str(int(label)): int(np.sum(labels == label)) for label in unique_labels
        }
        return {
            "n_clusters": int(n_clusters),
            "n_companies": int(len(labels)),
            "n_noise": n_noise,
            "silhouette_score": float(silhouette),
            "cluster_sizes": cluster_sizes,
        }
