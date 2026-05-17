"""Storage Orchestrator - Coordinates per-user PostgreSQL and Neo4j writers."""

import logging
from typing import Dict, Any

from src.database.postgres import PostgresClient
from src.database.neo4j_client import Neo4jClient
from src.llm.schemas import ExtractionOutput
from .postgres_writer import PostgresWriter
from .neo4j_writer import Neo4jWriter


logger = logging.getLogger(__name__)


class StorageOrchestrator:
    """Orchestrates storage of an extraction to both databases, scoped to one user."""

    def __init__(self, postgres_client: PostgresClient, neo4j_client: Neo4jClient):
        self.postgres_writer = PostgresWriter(postgres_client)
        self.neo4j_writer = Neo4jWriter(neo4j_client)
        self.logger = logging.getLogger(self.__class__.__name__)

    def store_extraction(
        self,
        clerk_id: str,
        extraction: ExtractionOutput,
    ) -> Dict[str, Any]:
        """Write extraction to Neo4j then PostgreSQL, rolling Neo4j back on PG failure."""
        company_name = extraction.company.name
        self.logger.info("Storing extraction for %s (user=%s)", company_name, clerk_id)

        result = {
            'company_name': company_name,
            'neo4j': None,
            'postgres': None,
            'success': False,
        }

        self.logger.info("Writing %s to Neo4j...", company_name)
        neo4j_result = self.neo4j_writer.write_extraction(clerk_id, extraction)
        result['neo4j'] = neo4j_result
        company_id = neo4j_result['company_id']
        self.logger.info("Neo4j write complete: company_id=%s", company_id)

        try:
            self.logger.info("Writing %s to PostgreSQL...", company_name)
            postgres_result = self.postgres_writer.write_extraction(
                clerk_id=clerk_id,
                extraction=extraction,
                company_id=company_id,
            )
            result['postgres'] = postgres_result
            result['success'] = True
            self.logger.info("Successfully stored %s in both databases", company_name)
            return result
        except Exception as pg_err:
            self.logger.error(
                "Postgres write failed for %s: %s. Rolling back Neo4j (company_id=%s).",
                company_name, pg_err, company_id,
            )
            try:
                self.neo4j_writer.delete_company(clerk_id, company_id)
                self.logger.info("Rolled back Neo4j subgraph for %s", company_id)
            except Exception as rb_err:
                self.logger.error(
                    "Neo4j rollback also failed (manual cleanup needed): %s", rb_err
                )
                result['rollback_failed'] = True
                result['orphan_company_id'] = company_id
            raise

    def store_batch(
        self,
        clerk_id: str,
        extractions: list[ExtractionOutput],
    ) -> list[Dict[str, Any]]:
        results = []
        for i, extraction in enumerate(extractions, 1):
            company_name = extraction.company.name
            try:
                result = self.store_extraction(clerk_id, extraction)
                results.append(result)
                self.logger.info("Progress: %d/%d companies stored", i, len(extractions))
            except Exception as e:
                self.logger.error("Failed to store %s: %s. Continuing with next.", company_name, e)
                results.append({
                    'company_name': company_name,
                    'success': False,
                    'error': str(e),
                })
                continue

        successful = sum(1 for r in results if r.get('success'))
        self.logger.info("Batch storage complete: %d/%d successful", successful, len(extractions))
        return results
