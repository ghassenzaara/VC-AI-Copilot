"""Base connector interface for data ingestion"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Set
import logging

logger = logging.getLogger(__name__)


class IngestionError(Exception):
    """Custom exception for ingestion failures"""
    pass


class AuthenticationError(IngestionError):
    """Raised when authentication fails"""
    pass


class BaseConnector(ABC):
    """Abstract base class for all data source connectors
    
    Note: Subclasses should define their own authentication parameters
    (api_key, credentials_path, token, etc.) as needed. The base class
    doesn't enforce a specific authentication mechanism.
    """
    
    def __init__(self):
        """Initialize connector with logging and auth state"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self._authenticated = False  # Cache authentication state
    
    @abstractmethod
    def authenticate(self) -> bool:
        """
        Authenticate with the data source
        
        Returns:
            bool: True if authentication successful
        """
        pass
    
    @abstractmethod
    def fetch_data(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Fetch data from the source
        
        Args:
            **kwargs: Source-specific parameters
            
        Returns:
            List of raw data objects
        """
        pass
    
    @abstractmethod
    def transform_to_standard_format(
        self,
        raw_data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Transform raw data to standardized format
        
        Args:
            raw_data: Raw data from source
            
        Returns:
            List of standardized data objects
        """
        pass
    
    def validate_data(self, data: Dict[str, Any]) -> bool:
        """
        Validate data structure using Pydantic UnifiedInteraction schema
        
        Args:
            data: Data object to validate
            
        Returns:
            bool: True if valid UnifiedInteraction
            
        Note:
            Validates that the data conforms to UnifiedInteraction schema.
            This catches any drift if connectors hand-build dicts incorrectly.
        """
        try:
            from .models import UnifiedInteraction
            from pydantic import ValidationError
            UnifiedInteraction(**data)
            return True
        except ValidationError as e:
            self.logger.warning(f"Invalid UnifiedInteraction: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            return False
    
    def ingest(
        self,
        existing_ids: Optional[Set[str]] = None,
        **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Complete ingestion pipeline: authenticate, fetch, transform, validate, deduplicate
        
        Args:
            existing_ids: Set of IDs already in storage (for deduplication)
            **kwargs: Source-specific parameters
            
        Returns:
            List of standardized, validated data objects
            
        Raises:
            AuthenticationError: If authentication fails
            IngestionError: If ingestion fails for other reasons
        """
        try:
            # Authenticate (cached - only runs once unless overridden)
            if not self._authenticated:
                self.logger.info("Authenticating...")
                if not self.authenticate():
                    raise AuthenticationError(f"Authentication failed for {self.get_source_name()}")
                self._authenticated = True
            else:
                self.logger.debug("Using cached authentication")
            
            # Fetch raw data
            self.logger.info("Fetching data...")
            raw_data = self.fetch_data(**kwargs)
            
            if not raw_data:
                self.logger.info("No data fetched (empty result)")
                return []
            
            self.logger.info(f"Fetched {len(raw_data)} records")
            
            # Transform to standard format
            self.logger.info("Transforming data...")
            standardized_data = self.transform_to_standard_format(raw_data)
            
            # Deduplicate if existing_ids provided
            if existing_ids:
                before_dedup = len(standardized_data)
                standardized_data = [
                    item for item in standardized_data
                    if item.get('id') not in existing_ids
                ]
                deduped = before_dedup - len(standardized_data)
                if deduped > 0:
                    self.logger.info(f"Deduplicated {deduped} existing records")
            
            # Validate
            self.logger.info("Validating data...")
            valid_data = [
                item for item in standardized_data
                if self.validate_data(item)
            ]
            
            invalid_count = len(standardized_data) - len(valid_data)
            if invalid_count > 0:
                self.logger.warning(f"Filtered out {invalid_count} invalid records")
            
            self.logger.info(
                f"Ingestion complete: {len(valid_data)} valid records"
            )
            
            return valid_data
            
        except AuthenticationError:
            raise  # Re-raise authentication errors
        except Exception as e:
            self.logger.error(f"Ingestion failed: {e}", exc_info=True)
            raise IngestionError(f"Ingestion failed for {self.get_source_name()}: {e}") from e
    
    def get_source_name(self) -> str:
        """Get the name of the data source"""
        return self.__class__.__name__.replace("Connector", "").lower()

# Made with Bob
