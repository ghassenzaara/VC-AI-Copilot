"""Extraction Engine - Extracts structured intelligence from company data

Uses IBM WatsonX (Llama 3.3 70B Instruct) to extract comprehensive deal
intelligence from aggregated company interactions, producing a structured
output matching extraction_output_format.json
"""

import json
import logging
from typing import Dict, Any, List, NamedTuple, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone

from pydantic import ValidationError

from .watsonx_client import WatsonXClient, WatsonXError
from .schemas import ExtractionOutput


logger = logging.getLogger(__name__)


class BatchExtractionResult(NamedTuple):
    """Result of `extract_batch` — surfaces which companies succeeded vs. failed (BUG-028)."""
    successes: List[ExtractionOutput]
    failures: List[Tuple[str, str]]  # (company_name, error_message)


class ExtractionEngine:
    """Extracts structured intelligence from company data using IBM WatsonX

    The extraction engine:
    1. Takes filtered CompanyData with relevant interactions
    2. Builds a comprehensive prompt with all interaction data
    3. Calls WatsonX (Llama 3.3 70B Instruct) for deep extraction
    4. Validates output against ExtractionOutput schema
    5. Returns structured intelligence ready for storage
    """

    def __init__(
        self,
        watsonx_client: WatsonXClient,
        prompt_path: Optional[str] = None
    ):
        """Initialize extraction engine

        Args:
            watsonx_client: Configured WatsonXClient instance (should use the "pro" model)
            prompt_path: Path to prompt template (defaults to bundled template)
        """
        self.client = watsonx_client
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
            WatsonXError: If extraction fails
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

            # Call WatsonX (Llama 3.3 70B Instruct for complex extraction)
            self.logger.debug(f"Calling WatsonX for extraction (model: {self.client.model_name})")
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

            # Audit enum coercions on interactions BEFORE Pydantic mutates them,
            # so we can record warnings the LLM omitted.
            coercion_warnings = self._audit_enum_drift(response)

            # Validate against schema
            extraction = ExtractionOutput(**response)

            # Attach coercion warnings discovered during the audit pass.
            for w in coercion_warnings:
                if w not in extraction.extraction_meta.warnings:
                    extraction.extraction_meta.warnings.append(w)

            self.logger.info(
                f"Extraction complete for {company_name} "
                f"(confidence: {extraction.extraction_meta.confidence:.2f})"
            )

            # Log warnings if any
            if extraction.extraction_meta.warnings:
                for warning in extraction.extraction_meta.warnings:
                    self.logger.warning(f"{company_name}: {warning}")
            
            return extraction
            
        except WatsonXError as e:
            self.logger.error(f"WatsonX error during extraction: {e}")
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
    
    def _audit_enum_drift(self, response: Dict[str, Any]) -> List[str]:
        """Compare raw LLM output against canonical+synonym universes.

        The schema's `mode='before'` validators try a synonym match first
        ("zoom" -> "video", "amazing" -> "positive"). When even synonym
        matching fails, the value is coerced to the field's default and the
        LLM's intent is lost. We log only those *real* misses so the
        warnings list stays useful (synonym-resolved values are silent).
        """
        from src.llm.schemas import (
            _resolve_enum,
            STAGE_SYNONYMS,
            MOMENTUM_SYNONYMS,
            PIPELINE_STAGE_SYNONYMS,
            VERDICT_SYNONYMS,
            ROLE_SYNONYMS,
            SENTIMENT_SYNONYMS,
            CHANNEL_SYNONYMS,
            INTERACTION_TYPE_SYNONYMS,
            METRIC_LABEL_SYNONYMS,
            SOURCE_TYPE_SYNONYMS,
        )

        warnings: List[str] = []
        _SENTINEL = object()

        def _check(raw: Any, synonyms: dict, label: str, context: str = "") -> None:
            """Record a warning iff the raw value can't be mapped to any canonical."""
            if not isinstance(raw, str) or not raw.strip():
                return
            resolved = _resolve_enum(raw, synonyms, _SENTINEL)
            if resolved is _SENTINEL:
                # `_SENTINEL` came back, meaning no canonical OR synonym matched.
                where = f" ({context})" if context else ""
                warnings.append(
                    f"LLM emitted {label}='{raw}'{where} — no synonym matched; coerced to default"
                )

        # Company-level enums
        company = response.get("company") or {}
        if isinstance(company, dict):
            _check(company.get("stage"), STAGE_SYNONYMS, "company.stage")
            _check(company.get("deal_momentum"), MOMENTUM_SYNONYMS, "company.deal_momentum")
            src = company.get("source")
            if isinstance(src, dict):
                for t in src.get("types") or []:
                    _check(t, SOURCE_TYPE_SYNONYMS, "company.source.types[]")

        # Deal status
        ds = response.get("deal_status") or {}
        if isinstance(ds, dict):
            _check(ds.get("pipeline_stage"), PIPELINE_STAGE_SYNONYMS, "deal_status.pipeline_stage")

        # Contacts
        for c in response.get("contacts") or []:
            if isinstance(c, dict):
                _check(c.get("role"), ROLE_SYNONYMS, "contacts[].role",
                       context=c.get("name") or "?")

        # Interactions + nested metrics
        for interaction in response.get("interactions") or []:
            if not isinstance(interaction, dict):
                continue
            iid = interaction.get("id", "<no id>")
            _check(interaction.get("type"), INTERACTION_TYPE_SYNONYMS, "interaction.type", context=iid)
            _check(interaction.get("channel"), CHANNEL_SYNONYMS, "interaction.channel", context=iid)
            _check(interaction.get("sentiment"), SENTIMENT_SYNONYMS, "interaction.sentiment", context=iid)
            src = interaction.get("source")
            if isinstance(src, dict):
                _check(src.get("type"), SOURCE_TYPE_SYNONYMS, "interaction.source.type", context=iid)
            for m in (interaction.get("what_happened") or {}).get("metrics_mentioned", []) or []:
                if isinstance(m, dict):
                    _check(m.get("label"), METRIC_LABEL_SYNONYMS, "metric.label", context=iid)

        # Decision record
        dr = response.get("decision_record") or {}
        if isinstance(dr, dict):
            _check(dr.get("verdict"), VERDICT_SYNONYMS, "decision_record.verdict")

        return warnings

    def to_dict(self, extraction: 'ExtractionOutput') -> Dict[str, Any]:
        """Convert an existing ExtractionOutput to a dict (no extra API call)."""
        return extraction.model_dump()

    def to_json(self, extraction: 'ExtractionOutput', output_path: str) -> None:
        """Save an existing ExtractionOutput to a JSON file (no extra API call)."""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(extraction.model_dump(), f, indent=2)
        self.logger.info(f"Saved extraction to {output_path}")


# Made with Bob