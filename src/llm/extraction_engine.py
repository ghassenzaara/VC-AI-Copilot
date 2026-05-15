"""Extraction Engine - Extracts structured intelligence from company data

Uses Gemini 2.5 Pro to extract comprehensive deal intelligence from aggregated
company interactions, producing a structured output matching extraction_output_format.json
"""

import json
import logging
from typing import Dict, Any, List, NamedTuple, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone

from pydantic import ValidationError

from .gemini_client import GeminiClient, GeminiError
from .schemas import ExtractionOutput


logger = logging.getLogger(__name__)


class BatchExtractionResult(NamedTuple):
    """Result of `extract_batch` — surfaces which companies succeeded vs. failed (BUG-028)."""
    successes: List[ExtractionOutput]
    failures: List[Tuple[str, str]]  # (company_name, error_message)


class ExtractionEngine:
    """Extracts structured intelligence from company data using Gemini 2.5
    
    The extraction engine:
    1. Takes filtered CompanyData with relevant interactions
    2. Builds a comprehensive prompt with all interaction data
    3. Calls Gemini 2.5 Pro for deep extraction
    4. Validates output against ExtractionOutput schema
    5. Returns structured intelligence ready for storage
    """
    
    def __init__(
        self,
        gemini_client: GeminiClient,
        prompt_path: Optional[str] = None
    ):
        """Initialize extraction engine
        
        Args:
            gemini_client: Configured GeminiClient instance (should use Pro model)
            prompt_path: Path to prompt template (defaults to bundled template)
        """
        self.client = gemini_client
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Load prompt template
        if prompt_path is None:
            default_path = Path(__file__).parent / "prompts" / "extraction_engine.txt"
            prompt_path = str(default_path)
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.prompt_template = f.read()

        required = ['{{COMPANY_DATA}}', '{{CURRENT_DATETIME}}', '{{MODEL_NAME}}']
        missing = [p for p in required if p not in self.prompt_template]
        if missing:
            raise ValueError(
                f"Prompt template at {prompt_path} is missing required placeholders: {missing}"
            )

        self.logger.info("Initialized extraction engine")
    
    def extract(
        self,
        company_data: Dict[str, Any]
    ) -> ExtractionOutput:
        """Extract structured intelligence from company data
        
        Args:
            company_data: CompanyData dict (typically after relevance filtering)
            
        Returns:
            ExtractionOutput with complete structured intelligence
            
        Raises:
            GeminiError: If extraction fails
            ValidationError: If output doesn't match schema
        """
        company_name = company_data.get('company_name', 'Unknown')
        interaction_count = len(company_data.get('interactions', []))
        
        self.logger.info(
            f"Extracting intelligence for {company_name} "
            f"({interaction_count} interactions)"
        )
        
        try:
            # Build prompt
            prompt = self._build_prompt(company_data)
            
            # Call Gemini (use Pro model for complex extraction)
            self.logger.debug(f"Calling Gemini for extraction (model: {self.client.model_name})")
            response = self.client.generate_json(
                prompt=prompt,
                temperature=0.2,  # Slightly creative for synthesis
                max_tokens=16384,  # Full ExtractionOutput needs headroom (BUG-025)
                retry_on_parse_error=True
            )
            
            # Surface schema drift (BUG-032): log keys the LLM emitted that
            # are not part of ExtractionOutput.
            expected_top_level = set(ExtractionOutput.model_fields.keys())
            extras = set(response.keys()) - expected_top_level
            if extras:
                self.logger.warning(
                    f"Extraction returned unknown top-level keys (silently dropped): {sorted(extras)}"
                )

            # Validate against schema
            extraction = ExtractionOutput(**response)
            
            self.logger.info(
                f"Extraction complete for {company_name} "
                f"(confidence: {extraction.extraction_meta.confidence:.2f})"
            )
            
            # Log warnings if any
            if extraction.extraction_meta.warnings:
                for warning in extraction.extraction_meta.warnings:
                    self.logger.warning(f"{company_name}: {warning}")
            
            return extraction
            
        except GeminiError as e:
            self.logger.error(f"Gemini error during extraction: {e}")
            raise
        except ValidationError as e:
            self.logger.error(f"Extraction output validation failed: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during extraction: {e}")
            raise
    
    def extract_batch(
        self,
        companies: List[Dict[str, Any]],
    ) -> BatchExtractionResult:
        """Extract intelligence for multiple companies.

        Returns a `BatchExtractionResult` with both successes and failures so
        callers can retry or alert on the failed companies (BUG-028).
        """
        successes: List[ExtractionOutput] = []
        failures: List[Tuple[str, str]] = []

        for i, company_data in enumerate(companies, 1):
            company_name = company_data.get('company_name') or f'Company {i}'
            try:
                successes.append(self.extract(company_data))
                self.logger.info(f"Progress: {i}/{len(companies)} companies extracted")
            except Exception as e:
                self.logger.error(f"Failed to extract {company_name}: {e}")
                failures.append((company_name, str(e)))

        self.logger.info(
            f"Batch extraction complete: {len(successes)}/{len(companies)} successful, "
            f"{len(failures)} failed"
        )
        return BatchExtractionResult(successes=successes, failures=failures)
    
    def _build_prompt(self, company_data: Dict[str, Any]) -> str:
        """Build extraction prompt from company data
        
        Args:
            company_data: CompanyData dict
            
        Returns:
            Complete prompt with template variables replaced
        """
        # Serialize company data to JSON (default=str guards against datetime / Pydantic objects)
        company_json = json.dumps(company_data, indent=2, default=str)
        
        # Get current datetime
        current_datetime = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # Get model name
        model_name = self.client.model_name
        
        # Replace template variables
        prompt = self.prompt_template
        prompt = prompt.replace('{{COMPANY_DATA}}', company_json)
        prompt = prompt.replace('{{CURRENT_DATETIME}}', current_datetime)
        prompt = prompt.replace('{{MODEL_NAME}}', model_name)
        
        return prompt
    
    def to_dict(self, extraction: 'ExtractionOutput') -> Dict[str, Any]:
        """Convert an existing ExtractionOutput to a dict (no extra API call)."""
        return extraction.model_dump()

    def to_json(self, extraction: 'ExtractionOutput', output_path: str) -> None:
        """Save an existing ExtractionOutput to a JSON file (no extra API call)."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(extraction.model_dump(), f, indent=2)
        self.logger.info(f"Saved extraction to {output_path}")


# Made with Bob