"""Granola API connector for meeting notes

Fetches meeting notes from Granola API and transforms them into standardized format.
API Documentation: https://granola.so/api/docs
"""

import requests
from typing import List, Dict, Any, Optional
from pydantic import ValidationError

from .base import BaseConnector
from .models import GranolaNote, UnifiedInteraction
from .utils import normalize_to_utc_iso
from src.config import get_settings

settings = get_settings()


class GranolaConnector(BaseConnector):
    """Connector for Granola meeting notes API"""
    
    BASE_URL = "https://api.granola.so/v1"
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Granola connector
        
        Args:
            api_key: Granola API key (defaults to settings)
        """
        super().__init__()
        self.api_key = api_key or settings.granola_api_key
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
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
                f"{self.BASE_URL}/notes",
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
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch meeting notes from Granola API
        
        Args:
            limit: Maximum number of notes to fetch
            start_date: Filter notes after this date (ISO 8601)
            end_date: Filter notes before this date (ISO 8601)
            **kwargs: Additional API parameters
            
        Returns:
            List of raw note objects
        """
        notes = []
        offset = 0
        page_size = min(limit, 50)  # API max per page
        
        while len(notes) < limit:
            params = {
                "limit": page_size,
                "offset": offset
            }
            
            if start_date:
                params["start_date"] = start_date
            if end_date:
                params["end_date"] = end_date
            
            try:
                response = requests.get(
                    f"{self.BASE_URL}/notes",
                    headers=self.headers,
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                
                data = response.json()
                batch = data.get("notes", [])
                
                if not batch:
                    break
                
                notes.extend(batch)
                offset += len(batch)
                
                # Check if we've reached the end
                if len(batch) < page_size:
                    break
                    
            except requests.exceptions.RequestException as e:
                self.logger.error(f"API request failed: {e}")
                break
        
        return notes[:limit]
    
    def fetch_note_by_id(self, note_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single note by ID
        
        Args:
            note_id: Granola note ID
            
        Returns:
            Note object or None if not found
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/notes/{note_id}",
                headers=self.headers,
                timeout=10
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Failed to fetch note {note_id}: {e}")
            return None
    
    def transform_to_standard_format(
        self,
        raw_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Transform Granola notes to standardized interaction format
        
        Args:
            raw_data: List of raw Granola note objects
            
        Returns:
            List of UnifiedInteraction objects as dicts
        """
        standardized = []
        
        for raw_note in raw_data:
            try:
                # Validate with Pydantic model
                note = GranolaNote(**raw_note)
                
                # Extract participants
                participants = [
                    attendee.email for attendee in note.attendees
                    if attendee.email
                ]
                
                # Build full transcript text with improved speaker resolution
                transcript_text = "\n\n".join([
                    f"[{segment.start_time}] {self._resolve_speaker(segment.speaker.source, note)}: {segment.text}"
                    for segment in note.transcript
                ])
                
                # Create unified interaction
                interaction = UnifiedInteraction(
                    id=note.id,
                    source="granola",
                    type="meeting",
                    title=note.title,
                    content=f"{note.summary_text}\n\n--- TRANSCRIPT ---\n{transcript_text}",
                    occurred_at=normalize_to_utc_iso(note.calendar_event.scheduled_start_time),
                    participants=participants,
                    metadata={
                        "owner": note.owner.model_dump(),
                        "duration_minutes": self._calculate_duration(
                            note.calendar_event.scheduled_start_time,
                            note.calendar_event.scheduled_end_time
                        ),
                        "organizer": note.calendar_event.organiser,
                        "attendee_count": len(note.attendees)
                    },
                    raw_data=raw_note
                )
                
                standardized.append(interaction.model_dump())
                
            except ValidationError as e:
                self.logger.warning(f"Validation failed for note {raw_note.get('id')}: {e}")
                continue
            except Exception as e:
                self.logger.error(f"Transform failed for note {raw_note.get('id')}: {e}")
                continue
        
        return standardized
    
    def _calculate_duration(self, start: str, end: str) -> int:
        """
        Calculate meeting duration in minutes
        
        Args:
            start: ISO 8601 start time
            end: ISO 8601 end time
            
        Returns:
            Duration in minutes
        """
        try:
            from datetime import datetime
            start_dt = datetime.fromisoformat(start.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end.replace('Z', '+00:00'))
            duration = (end_dt - start_dt).total_seconds() / 60
            return int(duration)
        except Exception as e:
            self.logger.warning(f"Failed to calculate duration for {start} to {end}: {e}")
            return 0
    
    def _resolve_speaker(self, source: str, note: 'GranolaNote') -> str:
        """
        Resolve speaker source to actual name
        
        Args:
            source: "microphone" or "speaker"
            note: GranolaNote object
            
        Returns:
            Speaker name or email
        """
        if source == "microphone":
            # Microphone is typically the meeting owner
            return note.owner.email
        elif source == "speaker":
            # Speaker is typically other attendees
            # Return first non-owner attendee or "Other Participant"
            for attendee in note.attendees:
                if attendee.email != note.owner.email:
                    return attendee.email
            return "Other Participant"
        else:
            return source
    
    def get_notes_by_company(self, company_name: str) -> List[Dict[str, Any]]:
        """
        Fetch notes mentioning a specific company
        
        Args:
            company_name: Company name to search for
            
        Returns:
            List of standardized interactions
        """
        # Fetch all recent notes
        raw_notes = self.fetch_data(limit=100)
        
        # Filter by company name in title or summary
        filtered = [
            note for note in raw_notes
            if company_name.lower() in note.get('title', '').lower()
            or company_name.lower() in note.get('summary_text', '').lower()
        ]
        
        return self.transform_to_standard_format(filtered)

# Made with Bob
