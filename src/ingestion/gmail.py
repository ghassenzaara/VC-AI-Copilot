"""Gmail API connector

Fetches email messages from Gmail API and transforms them into standardized format.
Uses OAuth 2.0 for authentication with token persistence.
API Documentation: https://developers.google.com/gmail/api
"""

import base64
import os
from pathlib import Path
from typing import List, Dict, Any, Optional
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from pydantic import ValidationError

from .base import BaseConnector
from .models import GmailMessage, UnifiedInteraction
from .utils import normalize_to_utc_iso, extract_name_and_email
from src.config import get_settings

settings = get_settings()


class GmailConnector(BaseConnector):
    """Connector for Gmail API"""
    
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    
    def __init__(self, credentials_path: Optional[str] = None, token_path: Optional[str] = None):
        """
        Initialize Gmail connector
        
        Args:
            credentials_path: Path to OAuth credentials JSON (defaults to settings)
            token_path: Path to store/load token.json (defaults to ./token.json)
        """
        super().__init__()
        self.credentials_path = credentials_path or settings.gmail_credentials
        self.token_path = token_path or "token.json"
        self.service = None
        self.creds = None
    
    def authenticate(self) -> bool:
        """
        Authenticate with Gmail using OAuth 2.0 with token persistence
        
        Returns:
            bool: True if authentication successful
        """
        try:
            # Check for existing token
            if os.path.exists(self.token_path):
                self.creds = Credentials.from_authorized_user_file(self.token_path, self.SCOPES)
            
            # If no valid credentials, get new ones
            if not self.creds or not self.creds.valid:
                if self.creds and self.creds.expired and self.creds.refresh_token:
                    # Refresh expired token
                    self.logger.info("Refreshing expired OAuth token")
                    self.creds.refresh(Request())
                else:
                    # Run OAuth flow
                    self.logger.info("Running OAuth flow (browser will open)")
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.credentials_path,
                        self.SCOPES
                    )
                    self.creds = flow.run_local_server(port=0)
                
                # Save token for future use
                with open(self.token_path, 'w') as token_file:
                    token_file.write(self.creds.to_json())
                self.logger.info(f"Token saved to {self.token_path}")
            
            # Build service
            self.service = build('gmail', 'v1', credentials=self.creds)
            
            # Test connection
            self.service.users().getProfile(userId='me').execute()
            return True
            
        except Exception as e:
            self.logger.error(f"Gmail authentication failed: {e}")
            return False
    
    def fetch_data(
        self,
        limit: int = 100,
        query: Optional[str] = None,
        after_date: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch email messages from Gmail
        
        Args:
            limit: Maximum number of messages to fetch
            query: Gmail search query (e.g., "from:sara@acme.ai")
            after_date: Fetch messages after this date (YYYY/MM/DD)
            **kwargs: Additional parameters
            
        Returns:
            List of raw Gmail message objects
        """
        if not self.service:
            self.logger.error("Not authenticated. Call authenticate() first.")
            return []
        
        messages = []
        
        try:
            # Build query
            search_query = query or ""
            if after_date:
                search_query += f" after:{after_date}"
            
            # Get message IDs
            results = self.service.users().messages().list(
                userId='me',
                q=search_query,
                maxResults=limit
            ).execute()
            
            message_ids = results.get('messages', [])
            
            # Fetch full message details
            for msg_id in message_ids[:limit]:
                try:
                    message = self.service.users().messages().get(
                        userId='me',
                        id=msg_id['id'],
                        format='full'
                    ).execute()
                    messages.append(message)
                except HttpError as e:
                    self.logger.warning(f"Failed to fetch message {msg_id['id']}: {e}")
                    continue
            
        except HttpError as e:
            self.logger.error(f"Gmail API error: {e}")
        
        return messages
    
    def fetch_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all messages in a thread
        
        Args:
            thread_id: Gmail thread ID
            
        Returns:
            List of messages in the thread
        """
        if not self.service:
            return []
        
        try:
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full'
            ).execute()
            
            return thread.get('messages', [])
            
        except HttpError as e:
            self.logger.error(f"Failed to fetch thread {thread_id}: {e}")
            return []
    
    def transform_to_standard_format(
        self,
        raw_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Transform Gmail messages to standardized interaction format
        
        Args:
            raw_data: List of raw Gmail message objects
            
        Returns:
            List of UnifiedInteraction objects as dicts
        """
        standardized = []
        
        for raw_message in raw_data:
            try:
                # Transform Gmail API format to our model format
                transformed = self._transform_gmail_format(raw_message)
                
                # Validate with Pydantic model
                message = GmailMessage(**transformed)
                
                # Extract key information
                from_email = message.get_header("From") or ""
                to_email = message.get_header("To") or ""
                subject = message.get_header("Subject") or "(No Subject)"
                date = message.get_header("Date") or message.internalDate
                body = message.get_body_text()
                
                # Extract contacts with names preserved
                contacts = self._extract_emails_with_names([from_email, to_email])
                participants = [c['email'] for c in contacts if c['email']]
                
                # Create unified interaction
                interaction = UnifiedInteraction(
                    id=message.id,
                    source="gmail",
                    type="email",
                    title=subject,
                    content=f"From: {from_email}\nTo: {to_email}\n\n{body}",
                    occurred_at=normalize_to_utc_iso(date),
                    participants=participants,
                    metadata={
                        "thread_id": message.threadId,
                        "snippet": message.snippet,
                        "from": from_email,
                        "to": to_email,
                        "contacts": contacts  # Preserve name/email pairs
                    },
                    raw_data=raw_message
                )
                
                standardized.append(interaction.model_dump())
                
            except ValidationError as e:
                self.logger.warning(f"Validation failed for message {raw_message.get('id')}: {e}")
                continue
            except Exception as e:
                self.logger.error(f"Transform failed for message {raw_message.get('id')}: {e}")
                continue
        
        return standardized
    
    def _transform_gmail_format(self, raw_message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform Gmail API format to our GmailMessage model format
        
        Args:
            raw_message: Raw Gmail API message
            
        Returns:
            Transformed message matching GmailMessage model
        """
        payload = raw_message.get('payload', {})
        headers = payload.get('headers', [])
        
        # Extract body parts
        parts = []
        if 'parts' in payload:
            for part in payload['parts']:
                if part.get('mimeType') == 'text/plain':
                    body_data = part.get('body', {}).get('data', '')
                    # Decode base64
                    try:
                        decoded = base64.urlsafe_b64decode(body_data).decode('utf-8')
                    except Exception:
                        decoded = body_data
                    
                    parts.append({
                        'mimeType': 'text/plain',
                        'body': {'data': decoded}
                    })
        elif 'body' in payload:
            # Single part message
            body_data = payload['body'].get('data', '')
            try:
                decoded = base64.urlsafe_b64decode(body_data).decode('utf-8')
            except Exception:
                decoded = body_data
            
            parts.append({
                'mimeType': 'text/plain',
                'body': {'data': decoded}
            })
        
        return {
            'id': raw_message['id'],
            'threadId': raw_message['threadId'],
            'internalDate': raw_message.get('internalDate', ''),
            'payload': {
                'headers': headers,
                'parts': parts
            },
            'snippet': raw_message.get('snippet', '')
        }
    
    def _extract_emails_with_names(self, email_strings: List[str]) -> List[Dict[str, Optional[str]]]:
        """
        Extract email addresses and names from email strings
        
        Args:
            email_strings: List of strings containing emails (e.g., "John Doe <john@example.com>")
            
        Returns:
            List of dicts with 'name' and 'email' keys
        """
        contacts = []
        seen_emails = set()
        
        for email_str in email_strings:
            if email_str:
                name, email = extract_name_and_email(email_str)
                if email and email not in seen_emails:
                    contacts.append({'name': name, 'email': email})
                    seen_emails.add(email)
        
        return contacts
    
    def search_by_company(self, company_name: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search emails mentioning a specific company
        
        Args:
            company_name: Company name to search for
            limit: Maximum number of results
            
        Returns:
            List of standardized interactions
        """
        query = f'"{company_name}"'
        raw_messages = self.fetch_data(limit=limit, query=query)
        return self.transform_to_standard_format(raw_messages)
    
    def get_emails_from_domain(self, domain: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get emails from a specific domain
        
        Args:
            domain: Email domain (e.g., "acme.ai")
            limit: Maximum number of results
            
        Returns:
            List of standardized interactions
        """
        query = f'from:@{domain} OR to:@{domain}'
        raw_messages = self.fetch_data(limit=limit, query=query)
        return self.transform_to_standard_format(raw_messages)

# Made with Bob
