"""Storage Orchestrator - Coordinates PostgreSQL and Neo4j writers

Handles the complete storage workflow:
1. Write to Neo4j (knowledge graph)
2. Write to PostgreSQL (data warehouse)
3. Handle errors and rollback if needed
"""

import logging
from typing import Dict, Any

from src.database.postgres import PostgresClient
from src.database.neo4j_client import Neo4jClient
from src.llm.schemas import ExtractionOutput
from .postgres_writer import PostgresWriter
from .neo4j_writer import Neo4jWriter


logger = logging.getLogger(__name__)


class StorageOrchestrator:
    """Orchestrates storage of extraction output to both databases"""
    
    def __init__(
        self,
        postgres_client: PostgresClient,
        neo4j_client: Neo4jClient
    ):
        """Initialize storage orchestrator
        
        Args:
            postgres_client: Configured PostgresClient
            neo4j_client: Configured Neo4jClient
        """
        self.postgres_writer = PostgresWriter(postgres_client)
        self.neo4j_writer = Neo4jWriter(neo4j_client)
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def store_extraction(
        self,
        extraction: ExtractionOutput
    ) -> Dict[str, Any]:
        """Store extraction output to both databases
        
        Workflow:
        1. Write to Neo4j first (creates company_id)
        2. Write to PostgreSQL using company_id
        3. Return combined results
        
        Args:
            extraction: ExtractionOutput from LLM
            
        Returns:
            Dict with storage results from both databases
        """
        company_name = extraction.company.name
        self.logger.info(f"Storing extraction for {company_name}")
        
        result = {
            'company_name': company_name,
            'neo4j': None,
            'postgres': None,
            'success': False
        }
        
        # Step 1: Write to Neo4j (creates nodes and relationships)
        self.logger.info(f"Writing {company_name} to Neo4j...")
        neo4j_result = self.neo4j_writer.write_extraction(extraction)
        result['neo4j'] = neo4j_result
        company_id = neo4j_result['company_id']
        self.logger.info(f"Neo4j write complete: company_id={company_id}")

        # Step 2: Write to PostgreSQL — rollback Neo4j on failure (BUG-044)
        try:
            self.logger.info(f"Writing {company_name} to PostgreSQL...")
            postgres_result = self.postgres_writer.write_extraction(
                extraction=extraction,
                company_id=company_id,
            )
            result['postgres'] = postgres_result
            result['success'] = True
            self.logger.info(f"Successfully stored {company_name} in both databases")
            return result
        except Exception as pg_err:
            self.logger.error(
                f"Postgres write failed for {company_name}: {pg_err}. "
                f"Rolling back Neo4j (company_id={company_id})."
            )
            try:
                self.neo4j_writer.delete_company(company_id)
                self.logger.info(f"Rolled back Neo4j subgraph for {company_id}")
            except Exception as rb_err:
                self.logger.error(
                    f"Neo4j rollback also failed (manual cleanup needed): {rb_err}"
                )
                result['rollback_failed'] = True
                result['orphan_company_id'] = company_id
            raise
    
    def store_batch(
        self,
        extractions: list[ExtractionOutput]
    ) -> list[Dict[str, Any]]:
        """Store multiple extractions
        
        Args:
            extractions: List of ExtractionOutput objects
            
        Returns:
            List of storage results
        """
        results = []
        
        for i, extraction in enumerate(extractions, 1):
            company_name = extraction.company.name
            
            try:
                result = self.store_extraction(extraction)
                results.append(result)
                
                self.logger.info(
                    f"Progress: {i}/{len(extractions)} companies stored"
                )
                
            except Exception as e:
                self.logger.error(
                    f"Failed to store {company_name}: {e}. Continuing with next."
                )
                results.append({
                    'company_name': company_name,
                    'success': False,
                    'error': str(e)
                })
                continue
        
        successful = sum(1 for r in results if r.get('success'))
        self.logger.info(
            f"Batch storage complete: {successful}/{len(extractions)} successful"
        )
        
        return results


# Made with Bob