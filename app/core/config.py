"""
Configuration management for Enterprise RAG System

This module handles all configuration settings using Pydantic for validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # API Keys
    openai_api_key: str = Field(...)
    anthropic_api_key: Optional[str] = Field(None)
    cohere_api_key: Optional[str] = Field(None)
    
    # Vector Database
    pinecone_api_key: Optional[str] = Field(None)
    pinecone_environment: str = Field("us-west1-gcp")
    pinecone_index_name: str = Field("enterprise-rag")
    
    # Embedding Configuration
    embedding_model: str = Field("text-embedding-ada-002")
    embedding_dimension: int = Field(1536)
    
    # Search Configuration
    hybrid_search_alpha: float = Field(0.5)
    top_k_results: int = Field(5)
    reranker_model: str = Field("cross-encoder/ms-marco-MiniLM-L-12-v2")
    
    # LLM Configuration
    llm_model: str = Field("gpt-4-turbo-preview")
    llm_temperature: float = Field(0.7)
    llm_max_tokens: int = Field(2048)
    
    # Performance
    enable_caching: bool = Field(True)
    cache_ttl_seconds: int = Field(3600)
    max_workers: int = Field(4)
    
    # Monitoring
    langsmith_api_key: Optional[str] = Field(None)
    langsmith_project: str = Field("enterprise-rag")
    arize_api_key: Optional[str] = Field(None)
    
    # Application
    app_name: str = "Enterprise RAG System"
    app_version: str = "0.1.0"
    debug: bool = Field(False)
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings
