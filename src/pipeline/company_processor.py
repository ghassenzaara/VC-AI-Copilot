"""Single Company Processor - End-to-end processing for one company

Orchestrates the complete workflow:
1. Aggregate data from all sources
2. Filter for relevance
3. Extract intelligence
4. Store to databases
"""

import logging
from typing import Dict, Any, Optional

from src.ingestion.aggregator import DataAggregator
from src.llm.relevance_filter import RelevanceFilter
from src.llm.extraction_engine import ExtractionEngine
from src.llm.schemas import ExtractionOutput
from src.storage.orchestrator import StorageOrchestrator
from src.pipeline.geocoding import GeocodingService
from src.pipeline.similarity import SimilarityComputer


logger = logging.getLogger(__name__)


class CompanyProcessor:
    """Processes a single company through the complete pipeline"""
    
    def __init__(
        self,
        aggregator: DataAggregator,
        relevance_filter: RelevanceFilter,
        extraction_engine: ExtractionEngine,
        storage_orchestrator: StorageOrchestrator,
        similarity: Optional[SimilarityComputer] = None,
        geocoding: Optional[GeocodingService] = None,
    ):
        """Initialize company processor

        Args:
            aggregator: Data aggregator instance
            relevance_filter: Relevance filter instance
            extraction_engine: Extraction engine instance
            storage_orchestrator: Storage orchestrator instance
            similarity: Optional similarity computer (for embedding generation).
                If None, embedding step is skipped.
            geocoding: Optional geocoding service. If None, geocoding step is skipped.
        """
        self.aggregator = aggregator
        self.relevance_filter = relevance_filter
        self.extraction_engine = extraction_engine
        self.storage_orchestrator = storage_orchestrator
        self.similarity = similarity
        self.geocoding = geocoding
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def process_company(
        self,
        company_domain: str,
        limit_per_source: int = 100
    ) -> Dict[str, Any]:
        """Process a single company end-to-end (aggregates then processes).

        Args:
            company_domain: Company domain to process
            limit_per_source: Max interactions per source

        Returns:
            Dict with processing results and statistics
        """
        self.logger.info(f"Processing company: {company_domain}")

        # Step 1: Aggregate data
        self.logger.info(f"Aggregating data for {company_domain}")
        company_data = self.aggregator.aggregate_single_company(
            company_domain=company_domain,
            limit_per_source=limit_per_source,
        )

        if not company_data:
            self.logger.warning(f"No data found for {company_domain}")
            return {
                'company_domain': company_domain,
                'success': False,
                'steps': {'aggregation': 'no_data'},
                'stats': {},
            }

        return self.process_company_from_data(company_data, source_label=company_domain)

    def process_company_from_data(
        self,
        company_data,
        source_label: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process a single company starting from already-aggregated CompanyData.

        Args:
            company_data: CompanyData object (typically from DataAggregator)
            source_label: Optional label for logs (defaults to company_data.company_name)

        Returns:
            Dict with processing results and statistics
        """
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
            self.logger.info(f"Processing {len(company_data.interactions)} interactions for {company_domain}")
            
            # Step 2: Filter for relevance
            self.logger.info(f"Step 2/4: Filtering interactions for {company_domain}")
            filtered_data = self.relevance_filter.filter_company_data(
                company_data.model_dump()
            )
            
            result['steps']['filtering'] = 'success'
            result['stats']['relevant_interactions'] = len(filtered_data['interactions'])
            result['stats']['filtered_out'] = (
                result['stats']['total_interactions'] - 
                result['stats']['relevant_interactions']
            )
            self.logger.info(
                f"Filtered to {result['stats']['relevant_interactions']} relevant interactions"
            )
            
            if result['stats']['relevant_interactions'] == 0:
                self.logger.warning(f"No relevant interactions for {company_domain}")
                result['steps']['filtering'] = 'no_relevant_data'
                return result
            
            # Step 3: Extract intelligence
            self.logger.info(f"Step 3/4: Extracting intelligence for {company_domain}")
            extraction = self.extraction_engine.extract(filtered_data)
            
            result['steps']['extraction'] = 'success'
            result['stats']['confidence'] = extraction.extraction_meta.confidence
            result['stats']['warnings'] = len(extraction.extraction_meta.warnings)
            result['stats']['contacts'] = len(extraction.contacts)
            result['stats']['interactions_extracted'] = len(extraction.interactions)
            self.logger.info(
                f"Extracted intelligence (confidence: {extraction.extraction_meta.confidence:.2f})"
            )
            
            # Step 4: Store to databases
            self.logger.info(f"Step 4/4: Storing to databases for {company_domain}")
            storage_result = self.storage_orchestrator.store_extraction(extraction)
            
            result['steps']['storage'] = 'success'
            result['stats']['company_id'] = storage_result['neo4j']['company_id']
            result['stats']['neo4j_nodes'] = (
                storage_result['neo4j']['person_count'] +
                storage_result['neo4j']['interaction_count'] + 1  # +1 for company
            )
            result['stats']['postgres_records'] = len(
                storage_result['postgres']['interaction_ids']
            )
            self.logger.info(f"Stored to databases (company_id: {result['stats']['company_id']})")

            company_id = result['stats']['company_id']

            # Step 5: Generate embedding (BUG-054)
            if self.similarity:
                try:
                    self.similarity.generate_company_embedding(
                        company_id=company_id,
                        company_data=extraction.company.model_dump(),
                    )
                    result['steps']['embedding'] = 'success'
                except Exception as e:
                    self.logger.warning(f"Embedding generation failed for {company_domain}: {e}")
                    result['steps']['embedding'] = f'failed: {e}'

            # Step 6: Geocode location (BUG-054)
            if self.geocoding and extraction.company.location:
                try:
                    coords = self.geocoding.geocode(extraction.company.location)
                    if coords:
                        self.storage_orchestrator.neo4j_writer.client.execute_write(
                            "MATCH (c:Company {id: $id}) SET c.lat = $lat, c.lng = $lng",
                            {"id": company_id, "lat": coords[0], "lng": coords[1]},
                        )
                        result['stats']['coords'] = coords
                        result['steps']['geocoding'] = 'success'
                    else:
                        result['steps']['geocoding'] = 'not_found'
                except Exception as e:
                    self.logger.warning(f"Geocoding failed for {company_domain}: {e}")
                    result['steps']['geocoding'] = f'failed: {e}'

            result['success'] = True
            result['extraction'] = extraction.model_dump()
            
            self.logger.info(f"✅ Successfully processed {company_domain}")
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to process {company_domain}: {e}")
            result['error'] = str(e)
            return result
    
    def process_company_batch(
        self,
        company_domains: list[str],
        limit_per_source: int = 100
    ) -> list[Dict[str, Any]]:
        """Process multiple companies
        
        Args:
            company_domains: List of company domains
            limit_per_source: Max interactions per source
            
        Returns:
            List of processing results
        """
        results = []
        
        for i, domain in enumerate(company_domains, 1):
            self.logger.info(f"Processing {i}/{len(company_domains)}: {domain}")
            # process_company catches its own exceptions and returns a result dict
            result = self.process_company(
                company_domain=domain,
                limit_per_source=limit_per_source,
            )
            results.append(result)
        
        # Summary statistics
        successful = sum(1 for r in results if r.get('success'))
        self.logger.info(
            f"Batch processing complete: {successful}/{len(company_domains)} successful"
        )
        
        return results


# Made with Bob