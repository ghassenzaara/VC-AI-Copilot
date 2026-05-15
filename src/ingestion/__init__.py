"""Data ingestion layer for VC Intelligence platform"""

from .base import BaseConnector
from .granola import GranolaConnector
from .affinity import AffinityConnector
from .gmail import GmailConnector
from .slack import SlackConnector

__all__ = [
    "BaseConnector",
    "GranolaConnector",
    "AffinityConnector",
    "GmailConnector",
    "SlackConnector",
]

# Made with Bob
