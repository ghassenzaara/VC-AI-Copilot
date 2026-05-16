"""Similarity Computation - Finds similar companies using embeddings

Uses company embeddings from PostgreSQL to compute similarity scores
and create SIMILAR_TO relationships in Neo4j.
"""

import logging
from typing import List, Dict, Any, Optional

from src.database.postgres import PostgresClient
from src.database.neo4j_client import Neo4jClient
from src.llm.watsonx_client import WatsonXClient, WatsonXError


logger = logging.getLogger(__name__)


class SimilarityComputer:
    """Computes company similarity using embeddings"""
    
    def __init__(
        self,
        postgres_client: PostgresClient,
        neo4j_client: Neo4jClient,
        watsonx_client: Optional[WatsonXClient] = None
    ):
        """Initialize similarity computer

        Args:
            postgres_client: PostgreSQL client for embeddings
            neo4j_client: Neo4j client for relationships
            watsonx_client: Optional WatsonX client for generating embeddings
        """
        self.postgres = postgres_client
        self.neo4j = neo4j_client
        self.watsonx = watsonx_client
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def generate_company_embedding(
        self,
        company_id: str,
        company_data: Dict[str, Any]
    ) -> str:
        """Generate and store embedding for a company
        
        Args:
            company_id: Company ID
            company_data: Company data dict (from extraction)
            
        Returns:
            Embedding ID
        """
        # Build embedding text from company data
        embedding_text = self._build_embedding_text(company_data)

        # Generate real embedding via WatsonX's embedding model
        if not self.watsonx:
            raise RuntimeError(
                "SimilarityComputer requires a watsonx_client to generate embeddings. "
                "Pass one to the constructor."
            )
        embedding = self.watsonx.embed_content(
            text=embedding_text,
            output_dimensionality=1536,
            task_type="SEMANTIC_SIMILARITY",
        )
        
        # Store in PostgreSQL
        embedding_id = self.postgres.insert_company_embedding(
            company_id=company_id,
            embedding=embedding,
            embedding_text=embedding_text
        )
        
        self.logger.info(f"Generated embedding for company {company_id}")
        return embedding_id
    
    def compute_similarities(
        self,
        company_id: str,
        threshold: float = 0.75,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Compute and store similarities for a company
        
        Args:
            company_id: Company ID to find similarities for
            threshold: Minimum similarity score (0-1)
            limit: Max number of similar companies
            
        Returns:
            List of similar companies with scores
        """
        self.logger.info(f"Computing similarities for {company_id}")
        
        # Get company embedding
        query = """
            SELECT embedding FROM company_embeddings
            WHERE company_id = %s
            ORDER BY generated_at DESC
            LIMIT 1
        """
        result = self.postgres.execute_query(query, (company_id,))
        
        if not result:
            self.logger.warning(f"No embedding found for {company_id}")
            return []
        
        embedding = result[0]['embedding']
        
        # Find similar companies
        similar = self.postgres.search_similar_companies(
            embedding=embedding,
            limit=limit,
            threshold=threshold
        )
        
        # Create SIMILAR_TO relationships in Neo4j
        for similar_company in similar:
            similar_id = similar_company['company_id']
            score = similar_company['similarity']
            
            if similar_id != company_id:  # Don't link to self
                self.neo4j.create_similar_to_relationship(
                    company_id_1=company_id,
                    company_id_2=similar_id,
                    score=score
                )
        
        self.logger.info(
            f"Found {len(similar)} similar companies for {company_id}"
        )
        
        return similar
    
    def compute_all_similarities(
        self,
        threshold: float = 0.75,
        limit: int = 10
    ) -> Dict[str, int]:
        """Compute similarities for all companies
        
        Args:
            threshold: Minimum similarity score
            limit: Max similar companies per company
            
        Returns:
            Dict with statistics
        """
        self.logger.info("Computing similarities for all companies")
        
        # Get all company IDs with embeddings
        query = """
            SELECT DISTINCT company_id FROM company_embeddings
        """
        result = self.postgres.execute_query(query)
        
        if not result:
            self.logger.warning("No companies with embeddings found")
            return {'total': 0, 'processed': 0}
        
        company_ids = [r['company_id'] for r in result]
        
        # Compute similarities for each
        total_relationships = 0
        for i, company_id in enumerate(company_ids, 1):
            try:
                similar = self.compute_similarities(
                    company_id=company_id,
                    threshold=threshold,
                    limit=limit
                )
                total_relationships += len(similar)
                
                if i % 10 == 0:
                    self.logger.info(f"Progress: {i}/{len(company_ids)} companies")
                    
            except Exception as e:
                self.logger.error(f"Failed to compute similarities for {company_id}: {e}")
        
        self.logger.info(
            f"Computed {total_relationships} similarity relationships "
            f"for {len(company_ids)} companies"
        )
        
        return {
            'total': len(company_ids),
            'processed': len(company_ids),
            'relationships': total_relationships
        }
    
    def _build_embedding_text(self, company_data: Dict[str, Any]) -> str:
        """Build text representation for embedding
        
        Args:
            company_data: Company data from extraction
            
        Returns:
            Text string for embedding
        """
        parts = []
        
        # Company info
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
    


# Made with Bob