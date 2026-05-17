"""Similarity Computation - per-user company embeddings and SIMILAR_TO edges."""

import logging
from typing import List, Dict, Any, Optional

from src.database.postgres import PostgresClient
from src.database.neo4j_client import Neo4jClient
from src.llm.watsonx_client import WatsonXClient


logger = logging.getLogger(__name__)


class SimilarityComputer:
    """Computes company similarity using embeddings, scoped to one user."""

    def __init__(
        self,
        postgres_client: PostgresClient,
        neo4j_client: Neo4jClient,
        watsonx_client: Optional[WatsonXClient] = None
    ):
        self.postgres = postgres_client
        self.neo4j = neo4j_client
        self.watsonx = watsonx_client
        self.logger = logging.getLogger(self.__class__.__name__)

    def generate_company_embedding(
        self,
        clerk_id: str,
        company_id: str,
        company_data: Dict[str, Any]
    ) -> str:
        embedding_text = self._build_embedding_text(company_data)

        if not self.watsonx:
            raise RuntimeError(
                "SimilarityComputer requires a watsonx_client to generate embeddings. "
                "Pass one to the constructor."
            )
        embedding = self.watsonx.embed_content(
            text=embedding_text,
            output_dimensionality=768,
            task_type="SEMANTIC_SIMILARITY",
        )

        embedding_id = self.postgres.insert_company_embedding(
            owner_clerk_id=clerk_id,
            company_id=company_id,
            embedding=embedding,
            embedding_text=embedding_text,
        )

        self.logger.info("Generated embedding for company %s (user=%s)", company_id, clerk_id)
        return embedding_id

    def compute_similarities(
        self,
        clerk_id: str,
        company_id: str,
        threshold: float = 0.75,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        self.logger.info("Computing similarities for %s (user=%s)", company_id, clerk_id)

        query = """
            SELECT embedding FROM company_embeddings
            WHERE owner_clerk_id = %s AND company_id = %s
            ORDER BY generated_at DESC
            LIMIT 1
        """
        result = self.postgres.execute_query(query, (clerk_id, company_id))

        if not result:
            self.logger.warning("No embedding found for %s (user=%s)", company_id, clerk_id)
            return []

        embedding = result[0]['embedding']

        similar = self.postgres.search_similar_companies(
            owner_clerk_id=clerk_id,
            embedding=embedding,
            limit=limit,
            threshold=threshold,
        )

        for similar_company in similar:
            similar_id = similar_company['company_id']
            score = similar_company['similarity']

            if similar_id != company_id:
                self.neo4j.create_similar_to_relationship(
                    clerk_id=clerk_id,
                    company_id_1=company_id,
                    company_id_2=similar_id,
                    score=score,
                )

        self.logger.info(
            "Found %d similar companies for %s (user=%s)", len(similar), company_id, clerk_id
        )
        return similar

    def compute_all_similarities(
        self,
        clerk_id: str,
        threshold: float = 0.75,
        limit: int = 10
    ) -> Dict[str, int]:
        self.logger.info("Computing similarities for all companies (user=%s)", clerk_id)

        query = """
            SELECT DISTINCT company_id FROM company_embeddings
            WHERE owner_clerk_id = %s
        """
        result = self.postgres.execute_query(query, (clerk_id,))

        if not result:
            self.logger.warning("No companies with embeddings found for user=%s", clerk_id)
            return {'total': 0, 'processed': 0}

        company_ids = [r['company_id'] for r in result]

        total_relationships = 0
        for i, company_id in enumerate(company_ids, 1):
            try:
                similar = self.compute_similarities(
                    clerk_id=clerk_id,
                    company_id=company_id,
                    threshold=threshold,
                    limit=limit,
                )
                total_relationships += len(similar)
                if i % 10 == 0:
                    self.logger.info("Progress: %d/%d companies", i, len(company_ids))
            except Exception as e:
                self.logger.error("Failed to compute similarities for %s: %s", company_id, e)

        self.logger.info(
            "Computed %d similarity relationships for %d companies (user=%s)",
            total_relationships, len(company_ids), clerk_id,
        )

        return {
            'total': len(company_ids),
            'processed': len(company_ids),
            'relationships': total_relationships,
        }

    def _build_embedding_text(self, company_data: Dict[str, Any]) -> str:
        parts = []
        if 'name' in company_data:
            parts.append(f"Company: {company_data['name']}")
        if 'one_liner' in company_data:
            parts.append(f"Description: {company_data['one_liner']}")
        if 'sector' in company_data:
            parts.append(f"Sector: {company_data['sector']}")
        if 'stage' in company_data:
            parts.append(f"Stage: {company_data['stage']}")
        if 'tags' in company_data:
            parts.append(f"Tags: {', '.join(company_data['tags'])}")
        if 'key_strengths' in company_data:
            parts.append(f"Strengths: {', '.join(company_data['key_strengths'])}")
        return ' | '.join(parts)
