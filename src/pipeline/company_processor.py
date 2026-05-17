"""Single Company Processor - End-to-end processing for one company (per user)."""

import logging
from typing import Dict, Any, Optional

from src.ingestion.aggregator import DataAggregator
from src.llm.relevance_filter import RelevanceFilter
from src.llm.extraction_engine import ExtractionEngine
from src.storage.orchestrator import StorageOrchestrator
from src.pipeline.geocoding import GeocodingService
from src.pipeline.similarity import SimilarityComputer


logger = logging.getLogger(__name__)


class CompanyProcessor:
    """Processes a single company through the complete pipeline for one user."""

    def __init__(
        self,
        aggregator: DataAggregator,
        relevance_filter: RelevanceFilter,
        extraction_engine: ExtractionEngine,
        storage_orchestrator: StorageOrchestrator,
        similarity: Optional[SimilarityComputer] = None,
        geocoding: Optional[GeocodingService] = None,
    ):
        self.aggregator = aggregator
        self.relevance_filter = relevance_filter
        self.extraction_engine = extraction_engine
        self.storage_orchestrator = storage_orchestrator
        self.similarity = similarity
        self.geocoding = geocoding
        self.logger = logging.getLogger(self.__class__.__name__)

    def process_company(
        self,
        clerk_id: str,
        company_domain: str,
        limit_per_source: int = 100,
    ) -> Dict[str, Any]:
        self.logger.info("Processing company %s (user=%s)", company_domain, clerk_id)

        company_data = self.aggregator.aggregate_single_company(
            company_domain=company_domain,
            limit_per_source=limit_per_source,
        )

        if not company_data:
            self.logger.warning("No data found for %s", company_domain)
            return {
                'company_domain': company_domain,
                'success': False,
                'steps': {'aggregation': 'no_data'},
                'stats': {},
            }

        return self.process_company_from_data(
            clerk_id=clerk_id,
            company_data=company_data,
            source_label=company_domain,
        )

    def process_company_from_data(
        self,
        clerk_id: str,
        company_data,
        source_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        company_domain = source_label or company_data.company_name

        result = {
            'company_domain': company_domain,
            'success': False,
            'steps': {
                'aggregation': 'success',
                'filtering': None,
                'extraction': None,
                'storage': None,
            },
            'stats': {},
        }

        try:
            result['stats']['total_interactions'] = len(company_data.interactions)
            self.logger.info(
                "Processing %d interactions for %s",
                len(company_data.interactions), company_domain,
            )

            self.logger.info("Step 2/4: Filtering interactions for %s", company_domain)
            filtered_data = self.relevance_filter.filter_company_data(
                company_data.model_dump()
            )
            result['steps']['filtering'] = 'success'
            result['stats']['relevant_interactions'] = len(filtered_data['interactions'])
            result['stats']['filtered_out'] = (
                result['stats']['total_interactions'] - result['stats']['relevant_interactions']
            )
            self.logger.info(
                "Filtered to %d relevant interactions",
                result['stats']['relevant_interactions'],
            )

            if result['stats']['relevant_interactions'] == 0:
                self.logger.warning("No relevant interactions for %s", company_domain)
                result['steps']['filtering'] = 'no_relevant_data'
                return result

            self.logger.info("Step 3/4: Extracting intelligence for %s", company_domain)
            extraction = self.extraction_engine.extract(filtered_data)
            result['steps']['extraction'] = 'success'
            result['stats']['confidence'] = extraction.extraction_meta.confidence
            result['stats']['warnings'] = len(extraction.extraction_meta.warnings)
            result['stats']['contacts'] = len(extraction.contacts)
            result['stats']['interactions_extracted'] = len(extraction.interactions)
            self.logger.info(
                "Extracted intelligence (confidence: %.2f)",
                extraction.extraction_meta.confidence,
            )

            self.logger.info("Step 4/4: Storing to databases for %s", company_domain)
            storage_result = self.storage_orchestrator.store_extraction(
                clerk_id=clerk_id, extraction=extraction,
            )
            result['steps']['storage'] = 'success'
            result['stats']['company_id'] = storage_result['neo4j']['company_id']
            result['stats']['neo4j_nodes'] = (
                storage_result['neo4j']['person_count']
                + storage_result['neo4j']['interaction_count']
                + 1
            )
            result['stats']['postgres_records'] = len(
                storage_result['postgres']['interaction_ids']
            )
            self.logger.info(
                "Stored to databases (company_id: %s)", result['stats']['company_id']
            )

            company_id = result['stats']['company_id']

            if self.similarity:
                try:
                    self.similarity.generate_company_embedding(
                        clerk_id=clerk_id,
                        company_id=company_id,
                        company_data=extraction.company.model_dump(),
                    )
                    result['steps']['embedding'] = 'success'
                except Exception as e:
                    self.logger.warning(
                        "Embedding generation failed for %s: %s", company_domain, e
                    )
                    result['steps']['embedding'] = f'failed: {e}'

            if self.geocoding and extraction.company.location:
                try:
                    coords = self.geocoding.geocode(extraction.company.location)
                    if coords:
                        self.storage_orchestrator.neo4j_writer.client.execute_write(
                            "MATCH (c:Company {clerk_id: $clerk_id, id: $id}) "
                            "SET c.lat = $lat, c.lng = $lng",
                            {
                                "clerk_id": clerk_id,
                                "id": company_id,
                                "lat": coords[0],
                                "lng": coords[1],
                            },
                        )
                        result['stats']['coords'] = coords
                        result['steps']['geocoding'] = 'success'
                    else:
                        result['steps']['geocoding'] = 'not_found'
                except Exception as e:
                    self.logger.warning("Geocoding failed for %s: %s", company_domain, e)
                    result['steps']['geocoding'] = f'failed: {e}'

            result['success'] = True
            result['extraction'] = extraction.model_dump()
            self.logger.info("✅ Successfully processed %s", company_domain)
            return result
        except Exception as e:
            self.logger.error("Failed to process %s: %s", company_domain, e)
            result['error'] = str(e)
            return result

    def process_company_batch(
        self,
        clerk_id: str,
        company_domains: list[str],
        limit_per_source: int = 100,
    ) -> list[Dict[str, Any]]:
        results = []
        for i, domain in enumerate(company_domains, 1):
            self.logger.info("Processing %d/%d: %s", i, len(company_domains), domain)
            result = self.process_company(
                clerk_id=clerk_id,
                company_domain=domain,
                limit_per_source=limit_per_source,
            )
            results.append(result)

        successful = sum(1 for r in results if r.get('success'))
        self.logger.info(
            "Batch processing complete: %d/%d successful", successful, len(company_domains)
        )
        return results
