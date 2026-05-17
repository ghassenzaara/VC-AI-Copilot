"""Neo4j Writer - Persists extraction output to per-user Neo4j subgraph.

Every node and relationship is scoped to the calling user's `clerk_id`.
"""

import logging
import re
from typing import List, Dict, Any, Optional
import hashlib

from src.config import get_settings
from src.database.neo4j_client import Neo4jClient
from src.llm.schemas import ExtractionOutput


def _build_partner_alias_map() -> Dict[str, str]:
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
        for alias in parts:
            mapping[alias.lower()] = canonical
    return mapping


logger = logging.getLogger(__name__)


class Neo4jWriter:
    """Writes extraction output to a user-scoped slice of the Neo4j graph."""

    def __init__(self, neo4j_client: Neo4jClient):
        self.client = neo4j_client
        self.logger = logging.getLogger(self.__class__.__name__)
        self._partner_aliases = _build_partner_alias_map()

    def write_extraction(
        self,
        clerk_id: str,
        extraction: ExtractionOutput,
    ) -> Dict[str, Any]:
        company_name = extraction.company.name
        self.logger.info("Writing extraction to Neo4j for %s (user=%s)", company_name, clerk_id)

        result = {
            'company_id': None,
            'person_count': 0,
            'interaction_count': 0,
            'relationship_count': 0,
        }

        try:
            # 1. Create company node
            company_id = self._create_company_node(clerk_id, extraction)
            result['company_id'] = company_id

            # 2. Create sector and tag nodes + relationships
            self._create_sector_and_tags(clerk_id, company_id, extraction.company)

            # 3. Create person nodes (contacts) + relationships
            person_ids = self._create_person_nodes(clerk_id, company_id, extraction.contacts)
            result['person_count'] = len(person_ids)

            # 4. Create VC partner node + relationship
            if extraction.deal_status.owner:
                self._create_vc_partner_node(clerk_id, company_id, extraction.deal_status.owner)

            # 5. Create interaction nodes + relationships
            interaction_ids = self._create_interaction_nodes(
                clerk_id, company_id, extraction.interactions
            )
            result['interaction_count'] = len(interaction_ids)

            # 6. Link interactions to participants
            self._link_interactions_to_participants(clerk_id, extraction.interactions, person_ids)

            self.logger.info(
                "Successfully wrote %s to Neo4j: %d contacts, %d interactions",
                company_name, result['person_count'], result['interaction_count'],
            )
            return result
        except Exception as e:
            self.logger.error("Failed to write extraction to Neo4j: %s", e)
            raise

    def _create_company_node(self, clerk_id: str, extraction: ExtractionOutput) -> str:
        company = extraction.company
        deal_status = extraction.deal_status
        decision = extraction.decision_record

        company_id = self._company_id_for(company)

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
            'external_id': company.source.external_id,
        }
        properties = {k: v for k, v in properties.items() if v is not None}

        self.client.create_company(
            clerk_id=clerk_id,
            company_id=company_id,
            name=company.name,
            properties=properties,
        )
        return company_id

    def _create_sector_and_tags(self, clerk_id: str, company_id: str, company) -> None:
        if company.sector:
            self.client.create_sector(clerk_id, company.sector)
            self.client.link_company_to_sector(clerk_id, company_id, company.sector)

        for tag in company.tags:
            self.client.create_tag(clerk_id, tag)
            self.client.link_company_to_tag(clerk_id, company_id, tag)

    def _create_person_nodes(
        self,
        clerk_id: str,
        company_id: str,
        contacts: List,
    ) -> Dict[str, str]:
        person_ids: Dict[str, str] = {}

        for contact in contacts:
            person_id = self._person_id_for(contact)
            if not person_id:
                self.logger.warning("Skipping contact with no usable email/name: %s", contact)
                continue

            properties = {
                'name': contact.name,
                'role': contact.role,
                'is_primary': contact.is_primary,
                'email': contact.email,
                'phone': contact.phone,
                'linkedin': contact.linkedin,
                'twitter': contact.twitter,
                'notes': contact.notes,
            }
            properties = {k: v for k, v in properties.items() if v is not None}

            self.client.create_person(
                clerk_id=clerk_id,
                person_id=person_id,
                name=contact.name,
                properties=properties,
            )

            rel_type = 'FOUNDER_OF' if contact.is_primary else 'WORKS_AT'
            self.client.create_relationship(
                clerk_id=clerk_id,
                from_id=person_id,
                from_label='Person',
                to_id=company_id,
                to_label='Company',
                rel_type=rel_type,
            )
            self.client.create_relationship(
                clerk_id=clerk_id,
                from_id=company_id,
                from_label='Company',
                to_id=person_id,
                to_label='Person',
                rel_type='HAS_CONTACT',
            )

            if contact.email:
                person_ids[contact.email.lower()] = person_id
            person_ids[contact.name] = person_id

        return person_ids

    def _create_vc_partner_node(
        self,
        clerk_id: str,
        company_id: str,
        owner_name: str,
    ) -> Optional[str]:
        canonical = self._partner_aliases.get((owner_name or "").lower())
        if not canonical:
            self.logger.info(
                "Skipping VCPartner write — unrecognized owner '%s'. "
                "Add to Settings.vc_partners to track.",
                owner_name,
            )
            return None

        partner_id = self._generate_id(canonical)
        self.client.create_vc_partner(
            clerk_id=clerk_id,
            partner_id=partner_id,
            name=canonical,
            properties={},
        )
        self.client.create_relationship(
            clerk_id=clerk_id,
            from_id=partner_id,
            from_label='VCPartner',
            to_id=company_id,
            to_label='Company',
            rel_type='OWNS',
        )
        return partner_id

    def _create_interaction_nodes(
        self,
        clerk_id: str,
        company_id: str,
        interactions: List,
    ) -> List[str]:
        interaction_ids: List[str] = []

        for interaction in interactions:
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
                'source_external_id': interaction.source.external_id,
            }
            properties = {k: v for k, v in properties.items() if v is not None}

            self.client.create_interaction(
                clerk_id=clerk_id,
                interaction_id=interaction.id,
                properties=properties,
            )
            self.client.create_relationship(
                clerk_id=clerk_id,
                from_id=interaction.id,
                from_label='Interaction',
                to_id=company_id,
                to_label='Company',
                rel_type='ABOUT',
            )
            interaction_ids.append(interaction.id)

        return interaction_ids

    def _link_interactions_to_participants(
        self,
        clerk_id: str,
        interactions: List,
        person_ids: Dict[str, str],
    ) -> None:
        for interaction in interactions:
            for participant in interaction.participants:
                key = participant.lower() if '@' in participant else participant
                person_id = person_ids.get(key)
                if person_id:
                    self.client.create_relationship(
                        clerk_id=clerk_id,
                        from_id=person_id,
                        from_label='Person',
                        to_id=interaction.id,
                        to_label='Interaction',
                        rel_type='PARTICIPATED_IN',
                    )

    def delete_company(self, clerk_id: str, company_id: str) -> None:
        """Detach-delete a Company and its Interaction subgraph for one user."""
        self.client.execute_write(
            """
            MATCH (c:Company {clerk_id: $clerk_id, id: $id})
            OPTIONAL MATCH (c)<-[:ABOUT]-(i:Interaction {clerk_id: $clerk_id})
            DETACH DELETE c, i
            """,
            {"clerk_id": clerk_id, "id": company_id},
        )

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^\w]+", "", (text or "").lower())

    def _generate_id(self, text: str) -> str:
        return hashlib.sha256(self._normalize(text).encode()).hexdigest()[:16]

    def _company_id_for(self, company) -> str:
        ext = getattr(company.source, "external_id", None) if getattr(company, "source", None) else None
        if ext:
            return f"affinity_{ext}"
        return self._generate_id(company.name)

    def _person_id_for(self, contact) -> Optional[str]:
        if contact.email and "@" in contact.email:
            return self._generate_id(contact.email)
        if contact.name and contact.name.strip():
            return self._generate_id(contact.name)
        return None
