"""Affinity CRM connector

Fetches company data from Affinity CRM including organizations, persons, opportunities,
field values, notes, and interactions. Combines all 6 objects into unified format.
API Documentation: https://api-docs.affinity.co
"""

import requests
import base64
from typing import List, Dict, Any, Optional
from pydantic import ValidationError

from .base import BaseConnector
from .models import (
    AffinityOrganization, AffinityPerson, AffinityOpportunity,
    AffinityFieldValue, AffinityNote, AffinityData, UnifiedInteraction
)
from .utils import normalize_to_utc_iso, safe_get_last_event_date
from src.config import get_settings

settings = get_settings()


class AffinityConnector(BaseConnector):
    """Connector for Affinity CRM API"""
    
    BASE_URL = "https://api.affinity.co"
    
    # Field ID mappings (these would be configured per Affinity instance)
    FIELD_MAPPINGS = {
        "sector": 61223,
        "stage": 61224,
        "mrr": 61225,
        "location": 61226,
        "verdict": 61227,
        "owner": 61228,
        "next_followup": 61229
    }
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Affinity connector
        
        Args:
            api_key: Affinity API key (defaults to settings)
        """
        super().__init__()
        self.api_key = api_key or settings.affinity_api_key
        # Affinity uses HTTP Basic Auth with empty username and API key as password
        # Alternative: use Affinity-API-Key header
        auth_string = base64.b64encode(f":{self.api_key}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {auth_string}",
            "Content-Type": "application/json"
        }
    
    def authenticate(self) -> bool:
        """
        Verify API key is valid
        
        Returns:
            bool: True if authentication successful
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/organizations",
                headers=self.headers,
                params={"limit": 1},
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False
    
    def fetch_data(
        self,
        limit: int = 100,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch flattened Affinity data (one item per interaction)
        
        Args:
            limit: Maximum number of organizations to fetch
            **kwargs: Additional parameters
            
        Returns:
            List of flat interaction items (one per note, or one CRM record if no notes)
            Each item carries organization, persons, field_values, interactions context
        """
        flat_items = []
        
        # Fetch organizations
        organizations = self._fetch_organizations(limit)
        
        for org in organizations:
            try:
                # Fetch complete company data bundle
                affinity_data = self._fetch_complete_company_data(org)
                
                # Flatten: one item per note
                if affinity_data.notes:
                    for note in affinity_data.notes:
                        flat_items.append({
                            'type': 'note',
                            'note': note.model_dump(),
                            'organization': affinity_data.organization.model_dump(),
                            'persons': [p.model_dump() for p in affinity_data.persons],
                            'opportunities': [o.model_dump() for o in affinity_data.opportunities],
                            'field_values': [fv.model_dump() for fv in affinity_data.field_values],
                            'interactions': affinity_data.interactions.model_dump() if affinity_data.interactions else None
                        })
                else:
                    # Fallback: one CRM record if no notes
                    flat_items.append({
                        'type': 'crm_record',
                        'note': None,
                        'organization': affinity_data.organization.model_dump(),
                        'persons': [p.model_dump() for p in affinity_data.persons],
                        'opportunities': [o.model_dump() for o in affinity_data.opportunities],
                        'field_values': [fv.model_dump() for fv in affinity_data.field_values],
                        'interactions': affinity_data.interactions.model_dump() if affinity_data.interactions else None
                    })
                    
            except Exception as e:
                self.logger.error(f"Failed to fetch data for org {org.get('id')}: {e}")
                continue
        
        return flat_items
    
    def _fetch_organizations(self, limit: int) -> List[Dict[str, Any]]:
        """Fetch organizations from Affinity"""
        organizations = []
        page_size = min(limit, 100)
        page_token = None
        
        while len(organizations) < limit:
            params = {"limit": page_size}
            if page_token:
                params["page_token"] = page_token
            
            try:
                response = requests.get(
                    f"{self.BASE_URL}/organizations",
                    headers=self.headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                
                data = response.json()
                batch = data.get("organizations", [])
                
                if not batch:
                    break
                
                organizations.extend(batch)
                page_token = data.get("next_page_token")
                
                if not page_token:
                    break
                    
            except requests.exceptions.RequestException as e:
                self.logger.error(f"Failed to fetch organizations: {e}")
                break
        
        return organizations[:limit]
    
    def _fetch_complete_company_data(self, org: Dict[str, Any]) -> AffinityData:
        """
        Fetch all 6 Affinity objects for a company
        
        Args:
            org: Organization object
            
        Returns:
            Complete AffinityData Pydantic model
        """
        org_id = org["id"]
        
        # Fetch persons
        persons = self._fetch_persons_for_org(org.get("person_ids", []))
        
        # Fetch opportunities
        opportunities = self._fetch_opportunities_for_org(org.get("opportunity_ids", []))
        
        # Fetch field values
        field_values = self._fetch_field_values(org_id)
        
        # Fetch notes
        notes = self._fetch_notes_for_org(org_id)
        
        # Interaction dates are in the org object
        interaction_dates = org.get("interaction_dates")
        
        # Build complete data object
        affinity_data = AffinityData(
            organization=AffinityOrganization(**org),
            persons=[AffinityPerson(**p) for p in persons],
            opportunities=[AffinityOpportunity(**o) for o in opportunities],
            field_values=[AffinityFieldValue(**fv) for fv in field_values],
            notes=[AffinityNote(**n) for n in notes],
            interactions=interaction_dates
        )
        
        return affinity_data
    
    def _fetch_persons_for_org(self, person_ids: List[int]) -> List[Dict[str, Any]]:
        """Fetch person objects by IDs"""
        persons = []
        for person_id in person_ids:
            try:
                response = requests.get(
                    f"{self.BASE_URL}/persons/{person_id}",
                    headers=self.headers,
                    timeout=10
                )
                response.raise_for_status()
                persons.append(response.json())
            except Exception as e:
                self.logger.warning(f"Failed to fetch person {person_id}: {e}")
        return persons
    
    def _fetch_opportunities_for_org(self, opp_ids: List[int]) -> List[Dict[str, Any]]:
        """Fetch opportunity objects by IDs"""
        opportunities = []
        for opp_id in opp_ids:
            try:
                response = requests.get(
                    f"{self.BASE_URL}/opportunities/{opp_id}",
                    headers=self.headers,
                    timeout=10
                )
                response.raise_for_status()
                opportunities.append(response.json())
            except Exception as e:
                self.logger.warning(f"Failed to fetch opportunity {opp_id}: {e}")
        return opportunities
    
    def _fetch_field_values(self, entity_id: int) -> List[Dict[str, Any]]:
        """Fetch field values for an entity"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/field-values",
                headers=self.headers,
                params={"entity_id": entity_id},
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("field_values", [])
        except Exception as e:
            self.logger.warning(f"Failed to fetch field values for {entity_id}: {e}")
            return []
    
    def _fetch_notes_for_org(self, org_id: int) -> List[Dict[str, Any]]:
        """Fetch notes for an organization"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/notes",
                headers=self.headers,
                params={"organization_id": org_id},
                timeout=10
            )
            response.raise_for_status()
            return response.json().get("notes", [])
        except Exception as e:
            self.logger.warning(f"Failed to fetch notes for org {org_id}: {e}")
            return []
    
    def transform_to_standard_format(
        self,
        raw_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Transform flattened Affinity items to standardized interaction format
        
        Args:
            raw_data: List of flat Affinity items (one per note or CRM record)
            
        Returns:
            List of UnifiedInteraction objects as dicts
        """
        standardized = []
        
        for item in raw_data:
            try:
                item_type = item['type']
                org = AffinityOrganization(**item['organization'])
                persons = [AffinityPerson(**p) for p in item['persons']]
                field_values = [AffinityFieldValue(**fv) for fv in item['field_values']]
                
                if item_type == 'note':
                    # Transform note into interaction
                    note = AffinityNote(**item['note'])
                    
                    # Get person names for participants
                    participants = []
                    for person_id in note.person_ids:
                        person = next((p for p in persons if p.id == person_id), None)
                        if person and person.primary_email:
                            participants.append(person.primary_email)
                    
                    interaction = UnifiedInteraction(
                        id=f"affinity_note_{note.id}",
                        source="affinity",
                        type="note",
                        title=f"Note about {org.name}",
                        content=note.content,
                        occurred_at=normalize_to_utc_iso(note.created_at),
                        participants=participants,
                        metadata={
                            "organization_id": org.id,
                            "organization_name": org.name,
                            "organization_domain": org.domain,
                            "note_id": note.id
                        },
                        raw_data=item
                    )
                    
                    standardized.append(interaction.model_dump())
                
                elif item_type == 'crm_record':
                    # Create CRM record interaction
                    field_content = self._build_field_content(field_values)
                    
                    opportunities = [AffinityOpportunity(**o) for o in item['opportunities']]
                    
                    interaction = UnifiedInteraction(
                        id=f"affinity_org_{org.id}",
                        source="affinity",
                        type="note",
                        title=f"CRM Record: {org.name}",
                        content=f"Organization: {org.name}\nDomain: {org.domain}\n\n{field_content}",
                        occurred_at=safe_get_last_event_date(item['interactions']),
                        participants=[p.primary_email for p in persons if p.primary_email],
                        metadata={
                            "organization_id": org.id,
                            "organization_name": org.name,
                            "organization_domain": org.domain,
                            "person_count": len(persons),
                            "opportunity_count": len(opportunities)
                        },
                        raw_data=item
                    )
                    
                    standardized.append(interaction.model_dump())
                
            except ValidationError as e:
                self.logger.warning(f"Validation failed: {e}")
                continue
            except Exception as e:
                self.logger.error(f"Transform failed: {e}")
                continue
        
        return standardized
    
    def _build_field_content(self, field_values: List[AffinityFieldValue]) -> str:
        """Build readable content from field values"""
        content_parts = []
        
        # Reverse mapping for field names
        field_names = {v: k for k, v in self.FIELD_MAPPINGS.items()}
        
        for fv in field_values:
            field_name = field_names.get(fv.field_id, f"field_{fv.field_id}")
            content_parts.append(f"{field_name}: {fv.value}")
        
        return "\n".join(content_parts)
    
    def get_company_by_name(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Fetch complete data for a specific company by name
        
        Args:
            company_name: Company name to search for
            
        Returns:
            Complete AffinityData or None
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/organizations",
                headers=self.headers,
                params={"term": company_name, "limit": 1},
                timeout=10
            )
            response.raise_for_status()
            
            orgs = response.json().get("organizations", [])
            if not orgs:
                return None
            
            return self._fetch_complete_company_data(orgs[0])
            
        except Exception as e:
            self.logger.error(f"Failed to fetch company {company_name}: {e}")
            return None

# Made with Bob
