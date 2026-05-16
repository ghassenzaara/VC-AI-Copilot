"""Relevance Filter - Filters out non-deal-related interactions

Uses IBM WatsonX (Granite 4.0 H Small) to determine if an interaction
contains meaningful deal signal before expensive extraction processing.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

from pydantic import BaseModel, Field

from .watsonx_client import WatsonXClient, WatsonXError


logger = logging.getLogger(__name__)


# Sentinel reason strings used to distinguish filter errors from genuine
# relevance decisions in batch stats (BUG-021).
_ERROR_REASON_PREFIX = "Error during filtering"
_UNEXPECTED_REASON_PREFIX = "Unexpected error"


class RelevanceDecision(BaseModel):
    """Relevance filter decision"""
    relevant: bool
    reason: str
    errored: bool = False


class RelevanceFilter:
    """Filters interactions for deal relevance using IBM WatsonX

    The filter uses a carefully crafted prompt to identify interactions that:
    - Mention specific startups or founders
    - Contain deal decisions or investment discussions
    - Include due diligence or validation conversations

    And filters out:
    - Generic internal meetings
    - Marketing emails
    - Social/personal conversations
    """

    def __init__(
        self,
        watsonx_client: WatsonXClient,
        prompt_path: Optional[str] = None
    ):
        """Initialize relevance filter

        Args:
            watsonx_client: Configured WatsonXClient instance (should use the "flash" model)
            prompt_path: Path to prompt template (defaults to bundled template)
        """
        self.client = watsonx_client
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Load prompt template
        if prompt_path is None:
            # Default to bundled template
            default_path = Path(__file__).parent / "prompts" / "relevance_filter.txt"
            prompt_path = str(default_path)
        
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.prompt_template = f.read()

        if '{{INTERACTION}}' not in self.prompt_template:
            raise ValueError(
                f"Prompt template at {prompt_path} is missing required placeholder '{{INTERACTION}}'"
            )

        self.logger.info("Initialized relevance filter")
    
    def filter_interaction(
        self,
        interaction: Dict[str, Any]
    ) -> RelevanceDecision:
        """Filter a single interaction for relevance
        
        Args:
            interaction: UnifiedInteraction dict
            
        Returns:
            RelevanceDecision with relevant flag and reason
        """
        try:
            # Build prompt
            interaction_json = json.dumps(interaction, indent=2)
            prompt = self.prompt_template.replace('{{INTERACTION}}', interaction_json)
            
            # Call WatsonX
            self.logger.debug(f"Filtering interaction {interaction.get('id')}")
            response = self.client.generate_json(
                prompt=prompt,
                temperature=0.1,  # Deterministic
                max_tokens=200    # Short response; headroom prevents truncation parse-fail (BUG-022)
            )
            
            # Parse decision
            decision = RelevanceDecision(**response)
            
            self.logger.info(
                f"Interaction {interaction.get('id')}: "
                f"{'RELEVANT' if decision.relevant else 'IRRELEVANT'} - {decision.reason}"
            )
            
            return decision
            
        except WatsonXError as e:
            self.logger.error(f"WatsonX error filtering interaction: {e}")
            # BUG-021: errored=True so batch stats can distinguish from real decisions
            return RelevanceDecision(
                relevant=True,
                reason=f"{_ERROR_REASON_PREFIX}: {e}",
                errored=True,
            )
        except Exception as e:
            self.logger.error(f"Unexpected error filtering interaction: {e}")
            return RelevanceDecision(
                relevant=True,
                reason=f"{_UNEXPECTED_REASON_PREFIX}: {e}",
                errored=True,
            )
    
    def filter_interactions(
        self,
        interactions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter a list of interactions, returning only relevant ones
        
        Args:
            interactions: List of UnifiedInteraction dicts
            
        Returns:
            List of relevant interactions (subset of input)
        """
        relevant_interactions = []
        error_count = 0

        for interaction in interactions:
            decision = self.filter_interaction(interaction)
            if decision.errored:
                error_count += 1

            if decision.relevant:
                # Stash filter result inside `metadata` so it survives Pydantic
                # re-validation. Shallow copy avoids mutating caller's dict.
                tagged = dict(interaction)
                meta = dict(tagged.get('metadata') or {})
                meta['filter'] = {
                    'relevant': True,
                    'reason': decision.reason,
                    'errored': decision.errored,
                }
                tagged['metadata'] = meta
                relevant_interactions.append(tagged)
            else:
                self.logger.debug(
                    f"Filtered out {interaction.get('id')}: {decision.reason}"
                )

        # Expose the error count on the instance so callers can read it after
        # a filter run (BUG-021).
        self.last_error_count = error_count

        if interactions:
            rate = len(relevant_interactions) / len(interactions) * 100
            err_note = f" ({error_count} errored)" if error_count else ""
            self.logger.info(
                f"Filtered {len(interactions)} interactions -> "
                f"{len(relevant_interactions)} relevant ({rate:.1f}%){err_note}"
            )
        else:
            self.logger.info("Filtered 0 interactions (empty input)")

        return relevant_interactions
    
    def filter_company_data(
        self,
        company_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Filter interactions in a CompanyData object
        
        Args:
            company_data: CompanyData dict with 'interactions' list
            
        Returns:
            CompanyData dict with only relevant interactions
        """
        interactions = company_data.get('interactions', [])
        
        if not interactions:
            self.logger.warning("No interactions to filter")
            return company_data
        
        # Filter interactions
        relevant_interactions = self.filter_interactions(interactions)
        
        # Update company data
        filtered_company_data = company_data.copy()
        filtered_company_data['interactions'] = relevant_interactions
        
        # Update metadata
        if 'metadata' not in filtered_company_data:
            filtered_company_data['metadata'] = {}
        
        filtered_company_data['metadata']['filter_stats'] = {
            'total_interactions': len(interactions),
            'relevant_interactions': len(relevant_interactions),
            'filtered_out': len(interactions) - len(relevant_interactions),
            'errored': getattr(self, 'last_error_count', 0),
            'relevance_rate': len(relevant_interactions) / len(interactions) if interactions else 0,
        }
        
        return filtered_company_data


# Made with Bob