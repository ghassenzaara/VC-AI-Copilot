"""Slack API connector

Fetches messages from Slack channels and transforms them into standardized format.
Uses Bot Token for authentication.
API Documentation: https://api.slack.com/methods
"""

import requests
from typing import List, Dict, Any, Optional
from pydantic import ValidationError

from .base import BaseConnector
from .models import SlackMessage, SlackChannel, SlackUser, SlackData, UnifiedInteraction
from .utils import normalize_to_utc_iso
from src.config import get_settings

settings = get_settings()


class SlackConnector(BaseConnector):
    """Connector for Slack API"""
    
    BASE_URL = "https://slack.com/api"
    
    def __init__(self, bot_token: Optional[str] = None):
        """
        Initialize Slack connector
        
        Args:
            bot_token: Slack Bot Token (defaults to settings)
        """
        super().__init__()
        self.bot_token = bot_token or settings.slack_bot_token
        self.headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }
        self.user_cache: Dict[str, SlackUser] = {}
    
    def authenticate(self) -> bool:
        """
        Verify bot token is valid
        
        Returns:
            bool: True if authentication successful
        """
        try:
            response = requests.post(
                f"{self.BASE_URL}/auth.test",
                headers=self.headers,
                timeout=10
            )
            data = response.json()
            return data.get('ok', False)
        except Exception as e:
            self.logger.error(f"Authentication failed: {e}")
            return False
    
    def fetch_data(
        self,
        channel_id: Optional[str] = None,
        channel_name: Optional[str] = None,
        limit: int = 100,
        oldest: Optional[str] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Fetch messages from Slack channels
        
        Args:
            channel_id: Specific channel ID to fetch from
            channel_name: Channel name (will be resolved to ID)
            limit: Maximum number of messages to fetch
            oldest: Fetch messages after this timestamp
            **kwargs: Additional parameters
            
        Returns:
            List of SlackData objects (message + channel + users) as dicts
        """
        # Resolve channel name to ID if needed
        if channel_name and not channel_id:
            channel_id = self._get_channel_id_by_name(channel_name)
            if not channel_id:
                self.logger.error(f"Channel '{channel_name}' not found")
                return []
        
        # If no channel specified, fetch from all channels
        if not channel_id:
            channels = self._get_all_channels()
            all_data = []
            for channel in channels[:5]:  # Limit to first 5 channels
                channel_data = self._fetch_channel_messages(
                    channel['id'],
                    limit=limit // 5,
                    oldest=oldest
                )
                all_data.extend(channel_data)
            return all_data
        
        return self._fetch_channel_messages(channel_id, limit, oldest)
    
    def _get_all_channels(self) -> List[Dict[str, Any]]:
        """Get list of all channels the bot has access to"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/conversations.list",
                headers=self.headers,
                params={"types": "public_channel,private_channel"},
                timeout=10
            )
            data = response.json()
            if data.get('ok'):
                return data.get('channels', [])
        except Exception as e:
            self.logger.error(f"Failed to fetch channels: {e}")
        return []
    
    def _get_channel_id_by_name(self, channel_name: str) -> Optional[str]:
        """Resolve channel name to ID"""
        channels = self._get_all_channels()
        for channel in channels:
            if channel.get('name') == channel_name.lstrip('#'):
                return channel['id']
        return None
    
    def _fetch_channel_messages(
        self,
        channel_id: str,
        limit: int = 100,
        oldest: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch messages from a specific channel"""
        slack_data_list = []
        
        try:
            # Get channel info
            channel_info = self._get_channel_info(channel_id)
            if not channel_info:
                return []
            
            # Fetch messages
            params = {"channel": channel_id, "limit": min(limit, 100)}
            if oldest:
                params["oldest"] = oldest
            
            response = requests.get(
                f"{self.BASE_URL}/conversations.history",
                headers=self.headers,
                params=params,
                timeout=30
            )
            data = response.json()
            
            if not data.get('ok'):
                self.logger.error(f"Failed to fetch messages: {data.get('error')}")
                return []
            
            messages = data.get('messages', [])
            
            # Fetch user info for all unique users (including bot messages)
            user_ids = set()
            for msg in messages:
                if msg.get('user'):
                    user_ids.add(msg.get('user'))
                elif msg.get('bot_id'):
                    # Handle bot messages - use bot_id as placeholder
                    user_ids.add(f"bot:{msg.get('bot_id')}")
            
            users = self._fetch_users(list(user_ids))
            
            # Build SlackData objects
            for message in messages:
                # Keep original user ID for matching, resolve name separately
                user_id = message.get('user')
                if not user_id and message.get('bot_id'):
                    # Bot message - use bot_id as user
                    user_id = f"bot:{message.get('bot_id')}"
                
                # Store original user_id for later matching
                message['user_id'] = user_id
                
                # Resolve to name for display
                user_name = self._get_user_name(user_id) if user_id else None
                if user_name:
                    message['user'] = user_name  # Display name
                elif user_id:
                    message['user'] = user_id  # Fallback to ID
                
                slack_data = {
                    'message': message,
                    'channel': channel_info,
                    'users': users
                }
                slack_data_list.append(slack_data)
        
        except Exception as e:
            self.logger.error(f"Failed to fetch channel messages: {e}")
        
        return slack_data_list
    
    def _get_channel_info(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """Get channel information"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/conversations.info",
                headers=self.headers,
                params={"channel": channel_id},
                timeout=10
            )
            data = response.json()
            if data.get('ok'):
                channel = data.get('channel', {})
                return {
                    'id': channel.get('id'),
                    'name': channel.get('name'),
                    'is_private': channel.get('is_private', False)
                }
        except Exception as e:
            self.logger.error(f"Failed to fetch channel info: {e}")
        return None
    
    def _fetch_users(self, user_ids: List[str]) -> List[Dict[str, Any]]:
        """Fetch user information for multiple users"""
        users = []
        for user_id in user_ids:
            if user_id in self.user_cache:
                users.append(self.user_cache[user_id].model_dump())
                continue
            
            try:
                response = requests.get(
                    f"{self.BASE_URL}/users.info",
                    headers=self.headers,
                    params={"user": user_id},
                    timeout=10
                )
                data = response.json()
                if data.get('ok'):
                    user_data = data.get('user', {})
                    user = {
                        'id': user_data.get('id'),
                        'real_name': user_data.get('real_name', ''),
                        'profile': {
                            'email': user_data.get('profile', {}).get('email', ''),
                            'title': user_data.get('profile', {}).get('title')
                        }
                    }
                    users.append(user)
                    self.user_cache[user_id] = SlackUser(**user)
            except Exception as e:
                self.logger.warning(f"Failed to fetch user {user_id}: {e}")
        
        return users
    
    def _get_user_name(self, user_id: str) -> Optional[str]:
        """Get user's real name from cache or API"""
        if user_id in self.user_cache:
            return self.user_cache[user_id].real_name
        
        users = self._fetch_users([user_id])
        if users:
            return users[0].get('real_name')
        return None
    
    def transform_to_standard_format(
        self,
        raw_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Transform Slack data to standardized interaction format
        
        Args:
            raw_data: List of SlackData objects as dicts
            
        Returns:
            List of UnifiedInteraction objects as dicts
        """
        standardized = []
        
        for slack_data_dict in raw_data:
            try:
                # Validate with Pydantic model
                slack_data = SlackData(**slack_data_dict)
                
                message = slack_data.message
                channel = slack_data.channel
                
                # Extract participants (message author + thread participants)
                participants = []
                
                # Add message author using stored user_id
                user_id = message.user_id if hasattr(message, 'user_id') else message.get('user_id')
                if user_id:
                    author_user = next(
                        (u for u in slack_data.users if u.id == user_id or u.id == user_id.replace('bot:', '')),
                        None
                    )
                    if author_user and author_user.profile.email:
                        participants.append(author_user.profile.email)
                
                # Build content
                content = message.text
                if message.reactions:
                    reactions_str = ", ".join([
                        f"{r.name} ({r.count})" for r in message.reactions
                    ])
                    content += f"\n\nReactions: {reactions_str}"
                
                # Create unified interaction
                interaction = UnifiedInteraction(
                    id=f"slack_{channel.id}_{message.ts}",
                    source="slack",
                    type="message",
                    title=f"Message in #{channel.name}",
                    content=content,
                    occurred_at=normalize_to_utc_iso(message.ts),
                    participants=participants,
                    metadata={
                        "channel_id": channel.id,
                        "channel_name": channel.name,
                        "is_private": channel.is_private,
                        "thread_ts": message.thread_ts,
                        "reply_count": message.reply_count,
                        "user": message.user
                    },
                    raw_data=slack_data_dict
                )
                
                standardized.append(interaction.model_dump())
                
            except ValidationError as e:
                self.logger.warning(f"Validation failed: {e}")
                continue
            except Exception as e:
                self.logger.error(f"Transform failed: {e}")
                continue
        
        return standardized
    
    def search_messages(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search messages across all channels
        
        Args:
            query: Search query
            limit: Maximum number of results
            
        Returns:
            List of standardized interactions
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/search.messages",
                headers=self.headers,
                params={"query": query, "count": limit},
                timeout=30
            )
            data = response.json()
            
            if not data.get('ok'):
                self.logger.error(f"Search failed: {data.get('error')}")
                return []
            
            messages = data.get('messages', {}).get('matches', [])
            
            # Fetch user info for search results
            user_ids = set()
            for msg in messages:
                if msg.get('user'):
                    user_ids.add(msg.get('user'))
                elif msg.get('bot_id'):
                    user_ids.add(f"bot:{msg.get('bot_id')}")
            
            users = self._fetch_users(list(user_ids)) if user_ids else []
            
            # Transform to SlackData format
            slack_data_list = []
            for msg in messages:
                channel_info = {
                    'id': msg.get('channel', {}).get('id'),
                    'name': msg.get('channel', {}).get('name'),
                    'is_private': msg.get('channel', {}).get('is_private', False)
                }
                
                slack_data_list.append({
                    'message': msg,
                    'channel': channel_info,
                    'users': users  # Include resolved users
                })
            
            return self.transform_to_standard_format(slack_data_list)
            
        except Exception as e:
            self.logger.error(f"Search failed: {e}")
            return []

# Made with Bob
