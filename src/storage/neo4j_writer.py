"""Neo4j Writer - Persists extraction output to Neo4j knowledge graph

Handles creating:
- Company nodes with properties
- Person nodes (contacts)
- VCPartner nodes (deal owners)
- Interaction nodes
- Sector and Tag nodes
- All relationships between nodes
"""

import logging
import re
from typing import List, Dict, Any, Optional
import hashlib

from src.config import get_settings
from src.database.neo4j_client import Neo4jClient
from src.llm.schemas import ExtractionOutput


def _build_partner_alias_map() -> Dict[str, str]:
    """Parse Settings.vc_partners into {alias_lower: canonical_name}."""
    settings = get_settings()
    raw = settings.vc_partners or ""
    mapping: Dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = [p.strip() for p in entry.split("|") if p.strip()]
        if not parts:
            continue
        canonical = parts[0]
        # Canonical name maps to itself; all listed aliases map to canonical.
        for alias in parts:
            mapping[alias.lower()] = canonical
    return mapping


logger = logging.getLogger(__name__)


class Neo4jWriter:
    """Writes extraction output to Neo4j knowledge graph"""
    
    def __init__(self, neo4j_client: Neo4jClient):
        """Initialize Neo4j writer

        Args:
            neo4j_client: Configured Neo4jClient instance
        """
        self.client = neo4j_client
        self.logger = logging.getLogger(self.__class__.__name__)
        self._partner_aliases = _build_partner_alias_map()
    
    def write_extraction(
        self,
        extraction: ExtractionOutput
    ) -> Dict[str, Any]:
        """Write complete extraction output to Neo4j
        
        Args:
            extraction: ExtractionOutput from LLM
            
        Returns:
            Dict with company_id and counts of created nodes/relationships
        """
        company_name = extraction.company.name
        self.logger.info(f"Writing extraction to Neo4j for {company_name}")
        
        result = {
            'company_id': None,
            'person_count': 0,
            'interaction_count': 0,
            'relationship_count': 0
        }
        
        try:
            # 1. Create company node
            company_id = self._create_company_node(extraction)
            result['company_id'] = company_id
            
            # 2. Create sector and tag nodes + relationships
            self._create_sector_and_tags(company_id, extraction.company)
            
            # 3. Create person nodes (contacts) + relationships
            person_ids = self._create_person_nodes(company_id, extraction.contacts)
            result['person_count'] = len(person_ids)
            
            # 4. Create VC partner node + relationship
            if extraction.deal_status.owner:
                self._create_vc_partner_node(company_id, extraction.deal_status.owner)
            
            # 5. Create interaction nodes + relationships
            interaction_ids = self._create_interaction_nodes(company_id, extraction.interactions)
            result['interaction_count'] = len(interaction_ids)
            
            # 6. Link interactions to participants
            self._link_interactions_to_participants(extraction.interactions, person_ids)
            
            self.logger.info(
                f"Successfully wrote {company_name} to Neo4j: "
                f"{result['person_count']} contacts, {result['interaction_count']} interactions"
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"Failed to write extraction to Neo4j: {e}")
            raise
    
    def _create_company_node(self, extraction: ExtractionOutput) -> str:
        """Create Company node with all properties
        
        Args:
            extraction: ExtractionOutput
            
        Returns:
            Company ID
        """
        company = extraction.company
        deal_status = extraction.deal_status
        decision = extraction.decision_record
        
        # Prefer Affinity external_id; fall back to normalized-name hash (BUG-046)
        company_id = self._company_id_for(company)
        
        # Build properties dict
        properties = {
            'name': company.name,
            'one_liner': company.one_liner,
            'sector': company.sector,
            'stage': company.stage,
            'location': company.location,
            'website': company.website,
            'first_met_at': company.first_met_at,
            'deal_momentum': company.deal_momentum,
            'pipeline_stage': deal_status.pipeline_stage,
            'last_touch_at': deal_status.last_touch_at,
            'next_step': deal_status.next_step,
            'verdict': decision.verdict,
            'check_size': decision.check_size,
            'valuation': decision.valuation,
            'decided_at': decision.decided_at,
            'key_strengths': company.key_strengths,
            'key_concerns': company.key_concerns,
            'external_id': company.source.external_id
        }
        
        # Remove None values
        properties = {k: v for k, v in properties.items() if v is not None}
        
        self.client.create_company(
            company_id=company_id,
            name=company.name,
            properties=properties
        )
        
        return company_id
    
    def _create_sector_and_tags(self, company_id: str, company) -> None:
        """Create Sector and Tag nodes and link to company

        Sector and Tag nodes are identified by `name` (per schema constraints),
        not `id`, so we use the dedicated link helpers instead of the generic
        id-based create_relationship.

        Args:
            company_id: Company ID
            company: Company object
        """
        # Create sector node and relationship
        if company.sector:
            self.client.create_sector(company.sector)
            self.client.link_company_to_sector(company_id, company.sector)

        # Create tag nodes and relationships
        for tag in company.tags:
            self.client.create_tag(tag)
            self.client.link_company_to_tag(company_id, tag)
    
    def _create_person_nodes(
        self,
        company_id: str,
        contacts: List
    ) -> Dict[str, str]:
        """Create Person nodes for all contacts
        
        Args:
            company_id: Company ID
            contacts: List of Contact objects
            
        Returns:
            Dict mapping contact name -> person_id
        """
        person_ids = {}
        
        for contact in contacts:
            # Prefer email over name for stable identity (BUG-046)
            person_id = self._person_id_for(contact)
            if not person_id:
                self.logger.warning(
                    f"Skipping contact with no usable email/name: {contact}"
                )
                continue
            
            # Build properties
            properties = {
                'name': contact.name,
                'role': contact.role,
                'is_primary': contact.is_primary,
                'email': contact.email,
                'phone': contact.phone,
                'linkedin': contact.linkedin,
                'twitter': contact.twitter,
                'notes': contact.notes
            }
            
            # Remove None values
            properties = {k: v for k, v in properties.items() if v is not None}
            
            # Create person node
            self.client.create_person(
                person_id=person_id,
                name=contact.name,
                properties=properties
            )
            
            # Create relationship to company
            rel_type = 'FOUNDER_OF' if contact.is_primary else 'WORKS_AT'
            self.client.create_relationship(
                from_id=person_id,
                from_label='Person',
                to_id=company_id,
                to_label='Company',
                rel_type=rel_type
            )
            
            # Also create HAS_CONTACT relationship from company
            self.client.create_relationship(
                from_id=company_id,
                from_label='Company',
                to_id=person_id,
                to_label='Person',
                rel_type='HAS_CONTACT'
            )
            
            # Index by both email (lowercased) AND name so participant lookup
            # works regardless of whether interactions store emails or names.
            if contact.email:
                person_ids[contact.email.lower()] = person_id
            person_ids[contact.name] = person_id

        return person_ids
    
    def _create_vc_partner_node(self, company_id: str, owner_name: str) -> Optional[str]:
        """Create VCPartner node and link to company.

        BUG-050: canonicalize owner name via the partners alias map before
        computing the partner_id, so "Ahmed" and "Ahmed Zaara" resolve to the
        same node. Returns None when the owner is unrecognized (and skips the
        write entirely, rather than creating noise nodes).
        """
        canonical = self._partner_aliases.get((owner_name or "").lower())
        if not canonical:
            self.logger.info(
                f"Skipping VCPartner write — unrecognized owner '{owner_name}'. "
                f"Add to Settings.vc_partners to track."
            )
            return None

        partner_id = self._generate_id(canonical)
        self.client.create_vc_partner(
            partner_id=partner_id,
            name=canonical,
            properties={},
        )
        self.client.create_relationship(
            from_id=partner_id,
            from_label='VCPartner',
            to_id=company_id,
            to_label='Company',
            rel_type='OWNS',
        )
        return partner_id
    
    def _create_interaction_nodes(
        self,
        company_id: str,
        interactions: List
    ) -> List[str]:
        """Create Interaction nodes
        
        Args:
            company_id: Company ID
            interactions: List of Interaction objects
            
        Returns:
            List of interaction IDs
        """
        interaction_ids = []
        
        for interaction in interactions:
            # Build properties
            properties = {
                'type': interaction.type,
                'title': interaction.title,
                'subtitle': interaction.subtitle,
                'occurred_at': interaction.occurred_at,
                'duration_minutes': interaction.duration_minutes,
                'channel': interaction.channel,
                'sentiment': interaction.sentiment,
                'participants': interaction.participants,
                'source_type': interaction.source.type,
                'source_url': interaction.source.url,
                'source_external_id': interaction.source.external_id
            }
            
            # Remove None values
            properties = {k: v for k, v in properties.items() if v is not None}
            
            # Create interaction node
            self.client.create_interaction(
                interaction_id=interaction.id,
                properties=properties
            )
            
            # Create ABOUT relationship to company
            self.client.create_relationship(
                from_id=interaction.id,
                from_label='Interaction',
                to_id=company_id,
                to_label='Company',
                rel_type='ABOUT'
            )
            
            interaction_ids.append(interaction.id)
        
        return interaction_ids
    
    def _link_interactions_to_participants(
        self,
        interactions: List,
        person_ids: Dict[str, str]
    ) -> None:
        """Link interactions to participant Person nodes
        
        Args:
            interactions: List of Interaction objects
            person_ids: Dict mapping name -> person_id
        """
        for interaction in interactions:
            for participant in interaction.participants:
                # interaction.participants contains emails (from connectors).
                # person_ids is keyed by both email (lowercased) AND name.
                key = participant.lower() if '@' in participant else participant
                person_id = person_ids.get(key)

                if person_id:
                    # Create PARTICIPATED_IN relationship
                    self.client.create_relationship(
                        from_id=person_id,
                        from_label='Person',
                        to_id=interaction.id,
                        to_label='Interaction',
                        rel_type='PARTICIPATED_IN'
                    )
    
    def delete_company(self, company_id: str) -> None:
        """Detach-delete a Company and its Interaction subgraph (compensation for BUG-044).

        Persons are NOT deleted — they may be linked to other companies.
        """
        self.client.execute_write(
            """
            MATCH (c:Company {id: $id})
            OPTIONAL MATCH (c)<-[:ABOUT]-(i:Interaction)
            DETACH DELETE c, i
            """,
            {"id": company_id},
        )

    @staticmethod
    def _normalize(text: str) -> str:
        """Aggressive normalization for ID hashing: lowercase, strip non-alnum."""
        return re.sub(r"[^\w]+", "", (text or "").lower())

    def _generate_id(self, text: str) -> str:
        """Deterministic ID from normalized text (SHA256, first 16 hex chars)."""
        return hashlib.sha256(self._normalize(text).encode()).hexdigest()[:16]

    def _company_id_for(self, company) -> str:
        """Prefer the Affinity external_id when present; else hash the normalized name.

        Closes BUG-046 for Company nodes.
        """
        ext = getattr(company.source, "external_id", None) if getattr(company, "source", None) else None
        if ext:
            return f"affinity_{ext}"
        return self._generate_id(company.name)

    def _person_id_for(self, contact) -> Optional[str]:
        """Prefer email (already normalized) over name. Return None if neither usable.

        Closes BUG-046 for Person nodes.
        """
        if contact.email and "@" in contact.email:
            return self._generate_id(contact.email)
        if contact.name and contact.name.strip():
            return self._generate_id(contact.name)
        return None


# Made with Bob