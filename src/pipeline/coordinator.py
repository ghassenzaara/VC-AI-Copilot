"""Pipeline Coordinator - Main orchestrator for the complete system

Initializes all components and provides high-level pipeline operations:
- Process all companies
- Process specific companies
- Incremental updates
"""

import logging
import os
from typing import Optional, List, Dict, Any

from src.config import get_settings
from src.ingestion.aggregator import DataAggregator
from src.ingestion.granola import GranolaConnector
from src.ingestion.affinity import AffinityConnector
from src.ingestion.gmail import GmailConnector
from src.ingestion.slack import SlackConnector
from src.llm.watsonx_client import WatsonXClient
from src.llm.relevance_filter import RelevanceFilter
from src.llm.extraction_engine import ExtractionEngine
from src.storage.orchestrator import StorageOrchestrator
from src.database.postgres import get_postgres_connection
from src.database.neo4j_client import get_neo4j_driver
from .company_processor import CompanyProcessor
from .geocoding import get_geocoding_service
from .similarity import SimilarityComputer


logger = logging.getLogger(__name__)


class PipelineCoordinator:
    """Main coordinator for the VC Intelligence pipeline
    
    Initializes all components and provides high-level operations.
    """
    
    def __init__(
        self,
        granola_api_key: Optional[str] = None,
        affinity_api_key: Optional[str] = None,
        gmail_credentials_path: Optional[str] = None,
        slack_bot_token: Optional[str] = None,
        ibm_api_key: Optional[str] = None,
        ibm_project_id: Optional[str] = None,
        ibm_url: Optional[str] = None,
    ):
        """Initialize pipeline coordinator

        Args:
            granola_api_key: Granola API key (defaults to env var)
            affinity_api_key: Affinity API key (defaults to env var)
            gmail_credentials_path: Gmail OAuth credentials path
            slack_bot_token: Slack bot token (defaults to env var)
            ibm_api_key: IBM Cloud API key (defaults to env var)
            ibm_project_id: WatsonX project ID (defaults to env var)
            ibm_url: WatsonX endpoint URL (defaults to env var)
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.info("Initializing Pipeline Coordinator...")

        settings = get_settings()

        # Resolve credentials from constructor args > settings (BUG-061, BUG-069)
        granola_key = granola_api_key or settings.granola_api_key
        affinity_key = affinity_api_key or settings.affinity_api_key
        gmail_creds = gmail_credentials_path or settings.gmail_credentials
        slack_token = slack_bot_token or settings.slack_bot_token

        # Initialize data source connectors
        self.logger.info("Initializing data source connectors...")
        self.granola = GranolaConnector(api_key=granola_key) if granola_key else None
        self.affinity = AffinityConnector(api_key=affinity_key) if affinity_key else None
        # Gmail: only instantiate if the credentials file actually exists.
        self.gmail = (
            GmailConnector(credentials_path=gmail_creds)
            if gmail_creds and os.path.exists(gmail_creds)
            else None
        )
        self.slack = SlackConnector(bot_token=slack_token) if slack_token else None
        
        # Initialize aggregator
        self.aggregator = DataAggregator(
            granola=self.granola,
            affinity=self.affinity,
            gmail=self.gmail,
            slack=self.slack
        )
        
        # Initialize LLM components
        self.logger.info("Initializing LLM components...")
        self.flash_client = WatsonXClient(
            api_key=ibm_api_key,
            project_id=ibm_project_id,
            url=ibm_url,
            model="flash",
        )
        self.pro_client = WatsonXClient(
            api_key=ibm_api_key,
            project_id=ibm_project_id,
            url=ibm_url,
            model="pro",
        )

        self.relevance_filter = RelevanceFilter(
            watsonx_client=self.flash_client
        )

        self.extraction_engine = ExtractionEngine(
            watsonx_client=self.pro_client
        )
        
        # Initialize database clients
        self.logger.info("Initializing database connections...")
        self.postgres = get_postgres_connection()
        self.neo4j = get_neo4j_driver()
        
        # Initialize storage orchestrator
        self.storage_orchestrator = StorageOrchestrator(
            postgres_client=self.postgres,
            neo4j_client=self.neo4j
        )

        # Initialize geocoding and similarity (BUG-054)
        self.logger.info("Initializing geocoding and similarity services...")
        self.geocoding = get_geocoding_service()
        self.similarity = SimilarityComputer(
            postgres_client=self.postgres,
            neo4j_client=self.neo4j,
            watsonx_client=self.flash_client,
        )

        # Initialize company processor
        self.company_processor = CompanyProcessor(
            aggregator=self.aggregator,
            relevance_filter=self.relevance_filter,
            extraction_engine=self.extraction_engine,
            storage_orchestrator=self.storage_orchestrator,
            similarity=self.similarity,
            geocoding=self.geocoding,
        )
        
        self.logger.info("✅ Pipeline Coordinator initialized successfully")
    
    def process_all_companies(
        self,
        limit_per_source: int = 100,
        company_domains: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Process all companies (or filtered list)
        
        Args:
            limit_per_source: Max interactions per source
            company_domains: Optional list of domains to filter by
            
        Returns:
            List of processing results
        """
        self.logger.info("Starting full pipeline processing...")
        
        # Step 1: Aggregate all companies
        self.logger.info("Aggregating companies from all sources...")
        companies = self.aggregator.aggregate_by_company(
            company_domains=company_domains,
            limit_per_source=limit_per_source
        )
        
        if not companies:
            self.logger.warning("No companies found")
            return []
        
        self.logger.info(f"Found {len(companies)} companies to process")
        
        # Step 2: Process each company (delegate to CompanyProcessor — BUG-057)
        results = []
        for i, company_data in enumerate(companies, 1):
            company_name = company_data.company_name
            self.logger.info(f"Processing {i}/{len(companies)}: {company_name}")
            # Use the already-aggregated company_data to avoid re-fetching
            result = self.company_processor.process_company_from_data(company_data)
            results.append(result)

        # Step 3: Compute similarity relationships across all companies (BUG-054 — plan §6.1)
        try:
            self.logger.info("Computing cross-company similarities...")
            self.similarity.compute_all_similarities(threshold=0.75, limit=10)
        except Exception as e:
            self.logger.error(f"Similarity computation failed: {e}")

        # Summary
        successful = sum(1 for r in results if r.get('success'))
        self.logger.info(
            f"Pipeline complete: {successful}/{len(results)} companies processed successfully"
        )

        return results
    
    def process_single_company(
        self,
        company_domain: str,
        limit_per_source: int = 100
    ) -> Dict[str, Any]:
        """Process a single company
        
        Args:
            company_domain: Company domain
            limit_per_source: Max interactions per source
            
        Returns:
            Processing result
        """
        return self.company_processor.process_company(
            company_domain=company_domain,
            limit_per_source=limit_per_source
        )
    
    def process_company_list(
        self,
        company_domains: List[str],
        limit_per_source: int = 100
    ) -> List[Dict[str, Any]]:
        """Process a list of specific companies
        
        Args:
            company_domains: List of company domains
            limit_per_source: Max interactions per source
            
        Returns:
            List of processing results
        """
        return self.company_processor.process_company_batch(
            company_domains=company_domains,
            limit_per_source=limit_per_source
        )
    
    def _postgres_alive(self) -> bool:
        try:
            self.postgres.execute_query("SELECT 1", fetch=True)
            return True
        except Exception:
            return False

    def _neo4j_alive(self) -> bool:
        try:
            self.neo4j.execute_query("RETURN 1")
            return True
        except Exception:
            return False

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get status of all pipeline components (pings databases — BUG-068)"""
        return {
            'connectors': {
                'granola': self.granola is not None,
                'affinity': self.affinity is not None,
                'gmail': self.gmail is not None,
                'slack': self.slack is not None
            },
            'llm': {
                'flash_model': self.flash_client.model_name,
                'pro_model': self.pro_client.model_name
            },
            'databases': {
                'postgres': self._postgres_alive(),
                'neo4j': self._neo4j_alive()
            }
        }
    
    def close(self):
        """Close all connections"""
        self.logger.info("Closing pipeline connections...")
        
        if self.postgres:
            self.postgres.close()
        
        if self.neo4j:
            self.neo4j.close()
        
        self.logger.info("Pipeline connections closed")


# Made with Bob