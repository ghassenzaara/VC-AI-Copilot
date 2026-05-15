"""Geocoding Service - Enriches company locations with coordinates

Uses a simple geocoding approach to convert location strings to coordinates.
Can be extended to use external APIs like Google Maps, OpenCage, etc.
"""

import logging
import time
from typing import Optional, Tuple, Dict

import requests


logger = logging.getLogger(__name__)


# Simple city coordinates database (can be extended or replaced with API)
CITY_COORDINATES = {
    # Major tech hubs
    'san francisco': (37.7749, -122.4194),
    'new york': (40.7128, -74.0060),
    'london': (51.5074, -0.1278),
    'berlin': (52.5200, 13.4050),
    'paris': (48.8566, 2.3522),
    'amsterdam': (52.3676, 4.9041),
    'stockholm': (59.3293, 18.0686),
    'tel aviv': (32.0853, 34.7818),
    'singapore': (1.3521, 103.8198),
    'bangalore': (12.9716, 77.5946),
    'tokyo': (35.6762, 139.6503),
    'seoul': (37.5665, 126.9780),
    'sydney': (-33.8688, 151.2093),
    'toronto': (43.6532, -79.3832),
    'austin': (30.2672, -97.7431),
    'seattle': (47.6062, -122.3321),
    'boston': (42.3601, -71.0589),
    'los angeles': (34.0522, -118.2437),
    'chicago': (41.8781, -87.6298),
    'munich': (48.1351, 11.5820),
    'zurich': (47.3769, 8.5417),
    'dublin': (53.3498, -6.2603),
    'copenhagen': (55.6761, 12.5683),
    'helsinki': (60.1699, 24.9384),
    'oslo': (59.9139, 10.7522),
    'barcelona': (41.3851, 2.1734),
    'madrid': (40.4168, -3.7038),
    'milan': (45.4642, 9.1900),
    'rome': (41.9028, 12.4964),
    'vienna': (48.2082, 16.3738),
    'prague': (50.0755, 14.4378),
    'warsaw': (52.2297, 21.0122),
    'lisbon': (38.7223, -9.1393),
    'brussels': (50.8503, 4.3517),
    'hong kong': (22.3193, 114.1694),
    'shanghai': (31.2304, 121.4737),
    'beijing': (39.9042, 116.4074),
    'shenzhen': (22.5431, 114.0579),
    'mumbai': (19.0760, 72.8777),
    'delhi': (28.7041, 77.1025),
    'dubai': (25.2048, 55.2708),
    'sao paulo': (-23.5505, -46.6333),
    'mexico city': (19.4326, -99.1332),
    'buenos aires': (-34.6037, -58.3816),
}


class GeocodingService:
    """Service for geocoding company locations.

    Primary backend: Nominatim (OpenStreetMap). Hardcoded CITY_COORDINATES
    is used as a fallback for offline / rate-limited cases.
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    def __init__(self, user_agent: str = "vc-intelligence/0.1", use_nominatim: bool = True):
        """Initialize geocoding service"""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache: Dict[str, Optional[Tuple[float, float]]] = {}
        # Per-instance copy of the city dict so add_custom_location doesn't
        # leak into module-level state (BUG-066).
        self.coords = dict(CITY_COORDINATES)
        self.user_agent = user_agent
        self.use_nominatim = use_nominatim
        self._last_nominatim_call = 0.0

    def geocode(self, location: Optional[str]) -> Optional[Tuple[float, float]]:
        """Geocode a location string to coordinates."""
        if not location:
            return None

        location_lower = location.lower().strip()
        if location_lower in self.cache:
            return self.cache[location_lower]

        coords: Optional[Tuple[float, float]] = None

        # Primary: Nominatim
        if self.use_nominatim:
            coords = self._geocode_nominatim(location)

        # Fallback: hardcoded dict (direct match only — no substring matching)
        if not coords:
            coords = self._lookup_coordinates(location_lower)

        self.cache[location_lower] = coords
        if coords:
            self.logger.debug(f"Geocoded '{location}' to {coords}")
        else:
            self.logger.warning(f"Could not geocode location: {location}")

        return coords

    def _geocode_nominatim(self, location: str) -> Optional[Tuple[float, float]]:
        """Geocode via Nominatim. Respects 1 req/sec rate limit."""
        elapsed = time.time() - self._last_nominatim_call
        if elapsed < 1.1:
            time.sleep(1.1 - elapsed)
        try:
            response = requests.get(
                self.NOMINATIM_URL,
                params={"q": location, "format": "json", "limit": 1},
                headers={"User-Agent": self.user_agent},
                timeout=10,
            )
            self._last_nominatim_call = time.time()
            response.raise_for_status()
            hits = response.json()
            if hits:
                return (float(hits[0]["lat"]), float(hits[0]["lon"]))
        except Exception as e:
            self.logger.warning(f"Nominatim failed for '{location}': {e}")
        return None

    def _lookup_coordinates(self, location: str) -> Optional[Tuple[float, float]]:
        """Direct-match fallback (no substring matching — too dangerous, see BUG-059)."""
        if location in self.coords:
            return self.coords[location]

        # Try "City, Country" format — match on city only
        parts = [p.strip() for p in location.split(',')]
        if parts and parts[0] in self.coords:
            return self.coords[parts[0]]

        return None
    
    def geocode_batch(
        self,
        locations: list[str]
    ) -> Dict[str, Optional[Tuple[float, float]]]:
        """Geocode multiple locations
        
        Args:
            locations: List of location strings
            
        Returns:
            Dict mapping location -> coordinates
        """
        results = {}
        for location in locations:
            results[location] = self.geocode(location)
        return results
    
    def add_custom_location(
        self,
        location: str,
        latitude: float,
        longitude: float
    ) -> None:
        """Add a custom location to the database
        
        Args:
            location: Location name
            latitude: Latitude
            longitude: Longitude
        """
        location_lower = location.lower().strip()
        # Per-instance, not module-level (BUG-066)
        self.coords[location_lower] = (latitude, longitude)
        self.cache[location_lower] = (latitude, longitude)
        self.logger.info(f"Added custom location: {location} -> ({latitude}, {longitude})")


# Global instance
_geocoding_service: Optional[GeocodingService] = None


def get_geocoding_service() -> GeocodingService:
    """Get or create geocoding service instance"""
    global _geocoding_service
    
    if _geocoding_service is None:
        _geocoding_service = GeocodingService()
    
    return _geocoding_service


# Made with Bob