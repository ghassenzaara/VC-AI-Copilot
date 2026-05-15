"""Data Aggregator - Combines all data sources into unified company objects

Orchestrates the four connectors (Granola, Affinity, Gmail, Slack) and aggregates
their data into `CompanyData` objects ready for LLM processing.

Company-key strategy (per PLAN-001):
1. Prefer Affinity-emitted `metadata.organization_domain` when present.
2. Fall back to a domain extracted from interaction participant emails,
   excluding generic email providers and the firm's own `self_domains`.
"""

import logging
from typing import Any, Dict, List, Optional, Set
from datetime import datetime, timezone

from .models import CompanyData, UnifiedInteraction
from .granola import GranolaConnector
from .affinity import AffinityConnector
from .gmail import GmailConnector
from .slack import SlackConnector
from src.config import get_settings


logger = logging.getLogger(__name__)


# Generic email providers — never used as company identifiers.
GENERIC_EMAIL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com",
    "yahoo.com", "ymail.com", "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "pm.me",
    "fastmail.com", "fastmail.fm",
    "gmx.com", "gmx.de", "gmx.net",
    "mail.com", "aol.com", "yandex.com", "zoho.com",
})


class DataAggregator:
    """Aggregates data from all sources into company-centric objects."""

    def __init__(
        self,
        granola: Optional[GranolaConnector] = None,
        affinity: Optional[AffinityConnector] = None,
        gmail: Optional[GmailConnector] = None,
        slack: Optional[SlackConnector] = None,
        self_domains: Optional[Set[str]] = None,
    ):
        """Initialize aggregator with connectors.

        Args:
            granola/affinity/gmail/slack: Connector instances (optional).
            self_domains: Set of domains belonging to the VC firm itself
                (e.g. {"yellowvc.com"}). Excluded from company-key candidates.
                Defaults to `Settings.self_domains`.
        """
        self.granola = granola
        self.affinity = affinity
        self.gmail = gmail
        self.slack = slack

        settings = get_settings()
        if self_domains is None:
            raw = settings.self_domains or ""
            self_domains = {
                d.strip().lower() for d in raw.split(",") if d.strip()
            }
        self.self_domains: Set[str] = self_domains
        self.logger = logging.getLogger(self.__class__.__name__)

    def aggregate_by_company(
        self,
        company_domains: Optional[List[str]] = None,
        limit_per_source: int = 100,
    ) -> List[CompanyData]:
        """Aggregate data from all sources, grouped by company."""
        self.logger.info(f"Starting aggregation (limit={limit_per_source})")

        all_interactions = self._fetch_all_interactions(limit_per_source)
        self.logger.info(f"Fetched {len(all_interactions)} total interactions")

        company_groups = self._group_by_company(all_interactions, company_domains)
        self.logger.info(f"Grouped into {len(company_groups)} companies")

        company_data_list: List[CompanyData] = []
        for company_key, interactions in company_groups.items():
            company_data_list.append(self._build_company_data(company_key, interactions))

        # Most active companies first.
        company_data_list.sort(key=lambda c: len(c.interactions), reverse=True)

        self.logger.info(f"Built {len(company_data_list)} CompanyData objects")
        return company_data_list

    def aggregate_single_company(
        self,
        company_domain: str,
        limit_per_source: int = 100,
    ) -> Optional[CompanyData]:
        """Aggregate data for a single company by domain."""
        companies = self.aggregate_by_company(
            company_domains=[company_domain],
            limit_per_source=limit_per_source,
        )
        if not companies:
            self.logger.warning(f"No data found for {company_domain}")
            return None
        return companies[0]

    # ------------------------------------------------------------------ #
    # Fetch                                                              #
    # ------------------------------------------------------------------ #

    def _fetch_all_interactions(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch interactions from every enabled connector."""
        all_interactions: List[Dict[str, Any]] = []
        for name, connector in (
            ("Granola", self.granola),
            ("Affinity", self.affinity),
            ("Gmail", self.gmail),
            ("Slack", self.slack),
        ):
            if not connector:
                continue
            try:
                interactions = connector.ingest(limit=limit)
                all_interactions.extend(interactions)
                self.logger.info(f"Fetched {len(interactions)} from {name}")
            except Exception as e:
                self.logger.error(f"{name} fetch failed: {e}")
        return all_interactions

    # ------------------------------------------------------------------ #
    # Group                                                              #
    # ------------------------------------------------------------------ #

    def _group_by_company(
        self,
        interactions: List[Dict[str, Any]],
        filter_domains: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group interactions by company. Surfaces drop counts (BUG-008)."""
        company_groups: Dict[str, List[Dict[str, Any]]] = {}
        dropped_no_key = 0
        dropped_filtered = 0

        for interaction in interactions:
            company_key = self._extract_company_key(interaction)
            if not company_key:
                dropped_no_key += 1
                continue
            if filter_domains and company_key not in filter_domains:
                dropped_filtered += 1
                continue
            company_groups.setdefault(company_key, []).append(interaction)

        if dropped_no_key:
            self.logger.warning(
                f"Dropped {dropped_no_key} interactions with no resolvable company key"
            )
        if dropped_filtered:
            self.logger.info(
                f"Dropped {dropped_filtered} interactions outside domain filter"
            )
        return company_groups

    def _extract_company_key(self, interaction: Dict[str, Any]) -> Optional[str]:
        """Extract canonical company key (domain) for an interaction."""
        source = interaction.get("source")

        # Affinity carries the organization domain directly.
        if source == "affinity":
            org_domain = interaction.get("metadata", {}).get("organization_domain")
            if org_domain:
                return org_domain.lower()

        # Otherwise, extract from participant email domains.
        candidates: Set[str] = set()
        for participant in interaction.get("participants", []) or []:
            if "@" not in participant:
                continue
            domain = participant.split("@", 1)[1].lower().strip()
            if not domain:
                continue
            if domain in GENERIC_EMAIL_DOMAINS:
                continue
            if domain in self.self_domains:  # BUG-002: never group under our own domain
                continue
            candidates.add(domain)

        if not candidates:
            return None
        # Deterministic pick (alphabetical) when multiple non-self domains remain.
        return sorted(candidates)[0]

    # ------------------------------------------------------------------ #
    # Build                                                              #
    # ------------------------------------------------------------------ #

    def _build_company_data(
        self,
        company_key: str,
        interactions: List[Dict[str, Any]],
    ) -> CompanyData:
        """Build a CompanyData object from grouped interactions."""
        # Dedup by id within group.
        seen_ids: Set[str] = set()
        unique_interactions: List[Dict[str, Any]] = []
        for interaction in interactions:
            interaction_id = interaction.get("id")
            if interaction_id and interaction_id not in seen_ids:
                seen_ids.add(interaction_id)
                unique_interactions.append(interaction)

        # BUG-007: trust connector-side Pydantic validation; let any drift surface
        # in tests rather than re-validating defensively.
        unified_interactions: List[UnifiedInteraction] = []
        for interaction in unique_interactions:
            try:
                unified_interactions.append(UnifiedInteraction(**interaction))
            except Exception as e:
                self.logger.warning(
                    f"Invalid interaction {interaction.get('id')}: {e}"
                )

        unified_interactions.sort(key=lambda i: i.occurred_at, reverse=True)

        # BUG-006: the per-source typed fields on CompanyData (granola_notes,
        # affinity_data, gmail_messages, slack_messages) require validated Pydantic
        # models that don't 1:1 match the raw_data dicts we carry. We deliberately
        # leave them empty — the LLM accesses raw source content via
        # UnifiedInteraction.raw_data, which is preserved per-interaction.

        contacts = self._extract_contacts(unified_interactions)

        metadata: Dict[str, Any] = {
            "company_domain": company_key,
            "total_interactions": len(unified_interactions),
            "sources": list(set(i.source for i in unified_interactions)),
            "date_range": {
                "earliest": min((i.occurred_at for i in unified_interactions), default=None),
                "latest": max((i.occurred_at for i in unified_interactions), default=None),
            },
            "aggregated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }

        # BUG-005: company_name is empty (placeholder), company_id carries the
        # domain. The LLM fills company_name during extraction.
        return CompanyData(
            company_name="",
            company_id=company_key,
            interactions=unified_interactions,
            contacts=contacts,
            metadata=metadata,
        )

    def _extract_contacts(
        self,
        interactions: List[UnifiedInteraction],
    ) -> List[Dict[str, Optional[str]]]:
        """Extract unique contacts from participants."""
        contacts_map: Dict[str, Dict[str, Optional[str]]] = {}

        for interaction in interactions:
            for participant in interaction.participants:
                if "@" in participant:
                    email = participant.lower()
                    if email not in contacts_map:
                        contacts_map[email] = {
                            "email": email,
                            "name": email.split("@")[0],
                        }
                else:
                    name = participant
                    if name not in contacts_map:
                        contacts_map[name] = {"name": name, "email": None}

        return list(contacts_map.values())
