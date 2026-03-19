"""
Configuration management for Enterprise RAG System

This module handles all configuration settings using Pydantic for validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices
from typing import Optional


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # API Keys
    openai_api_key: str = Field(..., validation_alias=AliasChoices("OPENAI_API_KEY", "openai_api_key"))
    anthropic_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("ANTHROPIC_API_KEY", "anthropic_api_key"))
    cohere_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("COHERE_API_KEY", "cohere_api_key"))
    
    # Vector Database
    pinecone_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("PINECONE_API_KEY", "pinecone_api_key"))
    pinecone_environment: str = Field("us-west1-gcp", validation_alias=AliasChoices("PINECONE_ENVIRONMENT", "pinecone_environment"))
    pinecone_index_name: str = Field("enterprise-rag", validation_alias=AliasChoices("PINECONE_INDEX_NAME", "pinecone_index_name"))
    
    # Embedding Configuration
    embedding_model: str = Field("text-embedding-ada-002", validation_alias=AliasChoices("EMBEDDING_MODEL", "embedding_model"))
    embedding_dimension: int = Field(1536, validation_alias=AliasChoices("EMBEDDING_DIMENSION", "embedding_dimension"))
    
    # Search Configuration
    hybrid_search_alpha: float = Field(0.5, validation_alias=AliasChoices("HYBRID_SEARCH_ALPHA", "hybrid_search_alpha"))
    top_k_results: int = Field(5, validation_alias=AliasChoices("TOP_K_RESULTS", "top_k_results"))
    reranker_model: str = Field(
        "cross-encoder/ms-marco-MiniLM-L-12-v2",
        validation_alias=AliasChoices("RERANKER_MODEL", "reranker_model")
    )
    
    # LLM Configuration
    llm_model: str = Field("gpt-4-turbo-preview", validation_alias=AliasChoices("LLM_MODEL", "llm_model"))
    llm_temperature: float = Field(0.7, validation_alias=AliasChoices("LLM_TEMPERATURE", "llm_temperature"))
    llm_max_tokens: int = Field(2048, validation_alias=AliasChoices("LLM_MAX_TOKENS", "llm_max_tokens"))
    
    # Performance
    enable_caching: bool = Field(True, validation_alias=AliasChoices("ENABLE_CACHING", "enable_caching"))
    cache_ttl_seconds: int = Field(3600, validation_alias=AliasChoices("CACHE_TTL_SECONDS", "cache_ttl_seconds"))
    max_workers: int = Field(4, validation_alias=AliasChoices("MAX_WORKERS", "max_workers"))
    
    # Monitoring
    langsmith_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("LANGSMITH_API_KEY", "langsmith_api_key"))
    langsmith_project: str = Field("enterprise-rag", validation_alias=AliasChoices("LANGSMITH_PROJECT", "langsmith_project"))
    arize_api_key: Optional[str] = Field(None, validation_alias=AliasChoices("ARIZE_API_KEY", "arize_api_key"))
    
    # Application
    app_name: str = "Enterprise RAG System"
    app_version: str = "0.1.0"
    debug: bool = Field(False, validation_alias=AliasChoices("DEBUG", "debug"))


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings
