"""
Configuration management for Enterprise RAG System

This module handles all configuration settings using Pydantic for validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # API Keys
    openai_api_key: str = Field(..., description="OpenAI API Key")
    anthropic_api_key: Optional[str] = None
    cohere_api_key: Optional[str] = None
    
    # Vector Database
    pinecone_api_key: Optional[str] = None
    pinecone_environment: str = "us-west1-gcp"
    pinecone_index_name: str = "enterprise-rag"
    
    # Embedding Configuration
    embedding_model: str = "text-embedding-ada-002"
    embedding_dimension: int = 1536
    
    # Search Configuration
    hybrid_search_alpha: float = 0.5
    top_k_results: int = 5
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-12-v2"
    
    # LLM Configuration
    llm_model: str = "gpt-4-turbo-preview"
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2048
    
    # Performance
    enable_caching: bool = True
    cache_ttl_seconds: int = 3600
    max_workers: int = 4
    
    # Monitoring
    langsmith_api_key: Optional[str] = None
    langsmith_project: str = "enterprise-rag"
    arize_api_key: Optional[str] = None
    
    # Application
    app_name: str = "Enterprise RAG System"
    app_version: str = "0.1.0"
    debug: bool = False
    
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
