"""PostgreSQL Writer - Persists extraction output to PostgreSQL

Handles writing:
- Interaction content (transcripts, summaries, takeaways)
- Team debates
- Decision records
- Company snapshots
- Extraction metadata
"""

import logging
from typing import Optional
import psycopg2.extras

from src.database.postgres import PostgresClient
from src.llm.schemas import ExtractionOutput


logger = logging.getLogger(__name__)


class PostgresWriter:
    """Writes extraction output to PostgreSQL data warehouse"""
    
    def __init__(self, postgres_client: PostgresClient):
        """Initialize PostgreSQL writer
        
        Args:
            postgres_client: Configured PostgresClient instance
        """
        self.client = postgres_client
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def write_extraction(
        self,
        extraction: ExtractionOutput,
        company_id: str
    ) -> dict:
        """Write complete extraction output to PostgreSQL
        
        Args:
            extraction: ExtractionOutput from LLM
            company_id: Company ID (from Neo4j)
            
        Returns:
            Dict with IDs of created records
        """
        self.logger.info(f"Writing extraction to PostgreSQL for company {company_id}")
        
        result = {
            'company_id': company_id,
            'interaction_ids': [],
            'metadata_id': None,
            'debate_id': None,
            'decision_id': None
        }
        
        try:
            # 1. Write interaction content
            for interaction in extraction.interactions:
                interaction_id = self._write_interaction_content(
                    interaction_id=interaction.id,
                    what_happened=interaction.what_happened
                )
                result['interaction_ids'].append(interaction_id)
            
            # 2. Write extraction metadata
            result['metadata_id'] = self._write_extraction_metadata(
                company_id=company_id,
                meta=extraction.extraction_meta
            )
            
            # 3. Write team debate (always, so we have a "checked, found nothing" record)
            result['debate_id'] = self._write_team_debate(
                company_id=company_id,
                debate=extraction.team_debate
            )
            
            # 4. Write decision record
            result['decision_id'] = self._write_decision_record(
                company_id=company_id,
                decision=extraction.decision_record
            )
            
            # 5. Write company snapshot (if company_now is populated)
            if extraction.company_now.fetched_at:
                result['snapshot_id'] = self._write_company_snapshot(
                    company_id=company_id,
                    company_now=extraction.company_now
                )
            
            self.logger.info(
                f"Successfully wrote extraction for {company_id}: "
                f"{len(result['interaction_ids'])} interactions"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to write extraction for {company_id}: {e}")
            raise
    
    def _write_interaction_content(
        self,
        interaction_id: str,
        what_happened
    ) -> str:
        """Write interaction content to PostgreSQL
        
        Args:
            interaction_id: Interaction ID (from Neo4j)
            what_happened: WhatHappened object from extraction
            
        Returns:
            PostgreSQL record ID
        """
        # Convert metrics and quotes to JSON-serializable format
        metrics = [m.model_dump() for m in what_happened.metrics_mentioned]
        quotes = [q.model_dump() for q in what_happened.quotes]
        
        # BUG-048: store raw JSONB arrays, not {'items': [...]} envelopes.
        return self.client.insert_interaction_content(
            neo4j_interaction_id=interaction_id,
            full_transcript=None,  # Not available in extraction
            summary=what_happened.summary,
            takeaways=what_happened.takeaways or None,
            topics=what_happened.topics or None,
            quotes=quotes or None,
            metrics_mentioned=metrics or None,
        )
    
    def _write_extraction_metadata(
        self,
        company_id: str,
        meta
    ) -> str:
        """Write extraction metadata
        
        Args:
            company_id: Company ID
            meta: ExtractionMeta object
            
        Returns:
            PostgreSQL record ID
        """
        return self.client.insert_extraction_metadata(
            company_id=company_id,
            model_used=meta.model,
            confidence=meta.confidence,
            warnings=meta.warnings or None,  # BUG-048: raw JSONB array
        )
    
    def _write_team_debate(
        self,
        company_id: str,
        debate
    ) -> str:
        """Write team debate record
        
        Args:
            company_id: Company ID
            debate: TeamDebate object
            
        Returns:
            PostgreSQL record ID
        """
        # Convert arguments to JSON-serializable format
        for_args = [arg.model_dump() for arg in debate.for_arguments]
        against_args = [arg.model_dump() for arg in debate.against_arguments]
        
        return self.client.insert_team_debate(
            company_id=company_id,
            detected=debate.detected,
            for_arguments=for_args or None,  # BUG-048
            against_arguments=against_args or None,
            open_questions=debate.open_questions or None,
        )
    
    def _write_decision_record(
        self,
        company_id: str,
        decision
    ) -> str:
        """Write decision record
        
        Args:
            company_id: Company ID
            decision: DecisionRecord object
            
        Returns:
            PostgreSQL record ID
        """
        return self.client.insert_decision_record(
            company_id=company_id,
            verdict=decision.verdict,
            rationale=decision.rationale,
            conditions=decision.conditions or None,  # BUG-048
            check_size=decision.check_size,
            valuation=decision.valuation,
            decided_at=decision.decided_at,
        )
    
    def _write_company_snapshot(
        self,
        company_id: str,
        company_now
    ) -> str:
        """Write company snapshot
        
        Args:
            company_id: Company ID
            company_now: CompanyNow object
            
        Returns:
            PostgreSQL record ID
        """
        snapshot_id = self.client.insert_company_snapshot(
            company_id=company_id,
            domain=company_now.domain,
            headcount=company_now.headcount,
            open_roles=company_now.open_roles,
            funding=company_now.funding.model_dump() if company_now.funding else None,
            fetched_at=company_now.fetched_at
        )
        
        # Write news articles
        for news in company_now.latest_news:
            self.client.insert_company_news(
                company_id=company_id,
                headline=news.headline,
                url=news.url,
                published_at=news.published_at,
                source=news.source
            )
        
        # Write signals
        for signal in company_now.signals:
            self.client.insert_company_signal(
                company_id=company_id,
                label=signal.label,
                detected_at=signal.detected_at
            )
        
        return snapshot_id


# Made with Bob