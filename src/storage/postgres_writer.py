"""PostgreSQL Writer - Persists extraction output to PostgreSQL (per-user)."""

import logging

from src.database.postgres import PostgresClient
from src.llm.schemas import ExtractionOutput


logger = logging.getLogger(__name__)


class PostgresWriter:
    """Writes extraction output to PostgreSQL data warehouse, scoped to one user."""

    def __init__(self, postgres_client: PostgresClient):
        self.client = postgres_client
        self.logger = logging.getLogger(self.__class__.__name__)

    def write_extraction(
        self,
        clerk_id: str,
        extraction: ExtractionOutput,
        company_id: str,
    ) -> dict:
        self.logger.info("Writing extraction to PostgreSQL for company %s (user=%s)", company_id, clerk_id)

        result = {
            'company_id': company_id,
            'interaction_ids': [],
            'metadata_id': None,
            'debate_id': None,
            'decision_id': None,
        }

        try:
            for interaction in extraction.interactions:
                interaction_id = self._write_interaction_content(
                    clerk_id=clerk_id,
                    interaction_id=interaction.id,
                    what_happened=interaction.what_happened,
                )
                result['interaction_ids'].append(interaction_id)

            result['metadata_id'] = self._write_extraction_metadata(
                clerk_id=clerk_id,
                company_id=company_id,
                meta=extraction.extraction_meta,
            )

            result['debate_id'] = self._write_team_debate(
                clerk_id=clerk_id,
                company_id=company_id,
                debate=extraction.team_debate,
            )

            result['decision_id'] = self._write_decision_record(
                clerk_id=clerk_id,
                company_id=company_id,
                decision=extraction.decision_record,
            )

            if extraction.company_now.fetched_at:
                result['snapshot_id'] = self._write_company_snapshot(
                    clerk_id=clerk_id,
                    company_id=company_id,
                    company_now=extraction.company_now,
                )

            self.logger.info(
                "Successfully wrote extraction for %s: %d interactions",
                company_id, len(result['interaction_ids']),
            )
            return result
        except Exception as e:
            self.logger.error("Failed to write extraction for %s: %s", company_id, e)
            raise

    def _write_interaction_content(self, clerk_id: str, interaction_id: str, what_happened) -> str:
        metrics = [m.model_dump() for m in what_happened.metrics_mentioned]
        quotes = [q.model_dump() for q in what_happened.quotes]

        return self.client.insert_interaction_content(
            owner_clerk_id=clerk_id,
            neo4j_interaction_id=interaction_id,
            full_transcript=None,
            summary=what_happened.summary,
            takeaways=what_happened.takeaways or None,
            topics=what_happened.topics or None,
            quotes=quotes or None,
            metrics_mentioned=metrics or None,
        )

    def _write_extraction_metadata(self, clerk_id: str, company_id: str, meta) -> str:
        return self.client.insert_extraction_metadata(
            owner_clerk_id=clerk_id,
            company_id=company_id,
            model_used=meta.model,
            confidence=meta.confidence,
            warnings=meta.warnings or None,
        )

    def _write_team_debate(self, clerk_id: str, company_id: str, debate) -> str:
        for_args = [arg.model_dump() for arg in debate.for_arguments]
        against_args = [arg.model_dump() for arg in debate.against_arguments]

        return self.client.insert_team_debate(
            owner_clerk_id=clerk_id,
            company_id=company_id,
            detected=debate.detected,
            for_arguments=for_args or None,
            against_arguments=against_args or None,
            open_questions=debate.open_questions or None,
        )

    def _write_decision_record(self, clerk_id: str, company_id: str, decision) -> str:
        return self.client.insert_decision_record(
            owner_clerk_id=clerk_id,
            company_id=company_id,
            verdict=decision.verdict,
            rationale=decision.rationale,
            conditions=decision.conditions or None,
            check_size=decision.check_size,
            valuation=decision.valuation,
            decided_at=decision.decided_at,
        )

    def _write_company_snapshot(self, clerk_id: str, company_id: str, company_now) -> str:
        snapshot_id = self.client.insert_company_snapshot(
            owner_clerk_id=clerk_id,
            company_id=company_id,
            domain=company_now.domain,
            headcount=company_now.headcount,
            open_roles=company_now.open_roles,
            funding=company_now.funding.model_dump() if company_now.funding else None,
            fetched_at=company_now.fetched_at,
        )

        for news in company_now.latest_news:
            self.client.insert_company_news(
                owner_clerk_id=clerk_id,
                company_id=company_id,
                headline=news.headline,
                url=news.url,
                published_at=news.published_at,
                source=news.source,
            )

        for signal in company_now.signals:
            self.client.insert_company_signal(
                owner_clerk_id=clerk_id,
                company_id=company_id,
                label=signal.label,
                detected_at=signal.detected_at,
            )

        return snapshot_id
