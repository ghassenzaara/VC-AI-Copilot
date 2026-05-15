"""Utility functions for data ingestion connectors

Provides common utilities for timestamp normalization, email extraction, etc.
"""

from datetime import datetime, timezone
from typing import List, Optional, Any, Tuple
import re
import logging
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)


def normalize_to_utc_iso(timestamp: Any) -> str:
    """
    Normalize any timestamp format to UTC ISO 8601
    
    Handles:
    - ISO 8601 strings (with or without timezone)
    - RFC 2822 email dates
    - Unix timestamps (seconds or milliseconds)
    - Slack timestamps (float strings)
    
    Args:
        timestamp: Timestamp in any supported format
        
    Returns:
        UTC ISO 8601 string (e.g., "2026-04-28T14:00:00Z")
    """
    if not timestamp:
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    try:
        # Already ISO 8601 with Z
        if isinstance(timestamp, str) and timestamp.endswith('Z'):
            # Validate it's parseable
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # ISO 8601 with timezone
        if isinstance(timestamp, str) and ('+' in timestamp or timestamp.endswith('+00:00')):
            dt = datetime.fromisoformat(timestamp)
            return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        
        # RFC 2822 (email Date header) - try parsing first
        if isinstance(timestamp, str):
            try:
                dt = parsedate_to_datetime(timestamp)
                return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
            except (TypeError, ValueError):
                pass  # Not RFC 2822, try other formats
        
        # Unix timestamp in milliseconds (Gmail internalDate)
        if isinstance(timestamp, str) and timestamp.isdigit() and len(timestamp) == 13:
            dt = datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc)
            return dt.isoformat().replace('+00:00', 'Z')
        
        # Unix timestamp in seconds (10-digit string)
        if isinstance(timestamp, str) and timestamp.isdigit() and len(timestamp) == 10:
            dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
            return dt.isoformat().replace('+00:00', 'Z')
        
        # Unix timestamp in seconds or Slack timestamp (float string)
        if isinstance(timestamp, (int, float)) or (isinstance(timestamp, str) and '.' in timestamp):
            dt = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
            return dt.isoformat().replace('+00:00', 'Z')
        
        # ISO 8601 without timezone (assume UTC - see docstring note)
        if isinstance(timestamp, str):
            dt = datetime.fromisoformat(timestamp)
            if dt.tzinfo is None:
                # NOTE: Assuming UTC for timezone-naive timestamps
                # This is the contract for all data sources
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        
    except Exception as e:
        # Fallback to current time if parsing fails - LOG LOUDLY
        logger.warning(
            f"Failed to parse timestamp '{timestamp}' (type: {type(timestamp).__name__}): {e}. "
            f"Falling back to current time - THIS MAY CAUSE DATA ORDERING ISSUES!"
        )
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    # Ultimate fallback
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def extract_emails_from_string(text: str) -> List[str]:
    """
    Extract email addresses from a string
    
    Args:
        text: String potentially containing emails
        
    Returns:
        List of extracted email addresses
    """
    if not text:
        return []
    
    # Email regex pattern (fixed: [A-Za-z] not [A-Z|a-z])
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    return list(set(emails))  # Remove duplicates


def extract_name_and_email(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract name and email from formats like "John Doe <john@example.com>"
    
    Args:
        text: String in format "Name <email>" or just "email"
        
    Returns:
        Tuple of (name, email)
    """
    if not text:
        return None, None
    
    # Pattern: "Name <email@domain.com>"
    match = re.match(r'^(.+?)\s*<([^>]+)>$', text.strip())
    if match:
        name = match.group(1).strip().strip('"')
        email = match.group(2).strip()
        return name, email
    
    # Just an email
    emails = extract_emails_from_string(text)
    if emails:
        return None, emails[0]
    
    return None, None


def safe_get_last_event_date(interaction_dates: Optional[dict]) -> str:
    """
    Safely get last_event_date from Affinity interaction_dates
    
    Args:
        interaction_dates: Affinity interaction_dates dict
        
    Returns:
        UTC ISO 8601 timestamp or current time if not available
    """
    if not interaction_dates:
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    last_event = interaction_dates.get('last_event_date')
    if last_event:
        return normalize_to_utc_iso(last_event)
    
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

# Made with Bob
