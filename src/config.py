"""Configuration management for VC Intelligence platform"""

from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # LLM Configuration (IBM WatsonX)
    ibm_api_key: str
    ibm_project_id: str
    ibm_url: str = "https://us-south.ml.cloud.ibm.com"
    # "pro" tier — complex reasoning (extraction)
    watsonx_pro_model: str = "meta-llama/llama-3-3-70b-instruct"
    # "flash" tier — lightweight filtering
    watsonx_flash_model: str = "ibm/granite-4-0-h-small"
    # Embedding model. Slate v2 is 768-dim; WatsonXClient zero-pads to the
    # caller's requested dimensionality (e.g. 1536 for the pgvector column).
    watsonx_embedding_model: str = "ibm/slate-125m-english-rtrvr-v2"
    watsonx_temperature: float = 0.1
    watsonx_max_tokens: int = 4096

    # Data Source API Keys
    granola_api_key: Optional[str] = None
    affinity_api_key: Optional[str] = None
    gmail_credentials: Optional[str] = None
    slack_bot_token: Optional[str] = None

    # VC firm identity (used by aggregator to exclude internal email domains
    # when picking a company key from participants). Comma-separated env value.
    self_domains: str = "yellowvc.com,projecta.com"

    # VC partners alias map. Each entry is "Canonical Name|alias1|alias2".
    # Used by the Neo4j writer to canonicalize `deal_status.owner` strings.
    # Pipe-separated within entries, comma-separated between entries.
    vc_partners: str = "Ahmed Zaara|Ahmed|AZ,Project A Partner|PA"
    
    # Database Configuration
    postgres_url: str
    neo4j_uri: str
    neo4j_user: str = "neo4j"
    neo4j_password: str
    
    # Application Configuration
    log_level: str = "INFO"
    environment: str = "development"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # Processing Configuration
    relevance_filter_temperature: float = 0.1
    extraction_temperature: float = 0.2
    similarity_threshold: float = 0.75
    batch_size: int = 10
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings

# Made with Bob
