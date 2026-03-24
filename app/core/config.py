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
    openai_api_key: Optional[str] = Field(None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(None, validation_alias="ANTHROPIC_API_KEY")
    cohere_api_key: Optional[str] = Field(None, validation_alias="COHERE_API_KEY")
    
    # Vector Database
    vector_db_type: str = Field("faiss", validation_alias="VECTOR_DB_TYPE")
    faiss_index_path: str = Field("./data/faiss_index.bin", validation_alias="FAISS_INDEX_PATH")
    pinecone_api_key: Optional[str] = Field(None, validation_alias="PINECONE_API_KEY")
    pinecone_environment: str = Field("us-west1-gcp", validation_alias="PINECONE_ENVIRONMENT")
    pinecone_index_name: str = Field("enterprise-rag", validation_alias="PINECONE_INDEX_NAME")
    
    # Embedding Configuration
    embedding_model: str = Field("text-embedding-ada-002", validation_alias="EMBEDDING_MODEL")
    embedding_dimension: int = Field(1536, validation_alias="EMBEDDING_DIMENSION")
    
    # Search Configuration
    hybrid_search_alpha: float = Field(0.5, validation_alias="HYBRID_SEARCH_ALPHA")
    top_k_results: int = Field(5, validation_alias="TOP_K_RESULTS")
    reranker_model: str = Field(
        "cross-encoder/ms-marco-MiniLM-L-12-v2",
        validation_alias="RERANKER_MODEL"
    )
    
    # LLM Configuration
    llm_model: str = Field("gpt-4-turbo-preview", validation_alias="LLM_MODEL")
    llm_temperature: float = Field(0.7, validation_alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(2048, validation_alias="LLM_MAX_TOKENS")
    
    # Performance
    enable_caching: bool = Field(True, validation_alias="ENABLE_CACHING")
    cache_ttl_seconds: int = Field(3600, validation_alias="CACHE_TTL_SECONDS")
    max_workers: int = Field(4, validation_alias="MAX_WORKERS")
    
    # Monitoring
    langsmith_api_key: Optional[str] = Field(None, validation_alias="LANGSMITH_API_KEY")
    langsmith_project: str = Field("enterprise-rag", validation_alias="LANGSMITH_PROJECT")
    arize_api_key: Optional[str] = Field(None, validation_alias="ARIZE_API_KEY")
    
    # Application
    app_name: str = "Enterprise RAG System"
    app_version: str = "0.1.0"
    debug: bool = Field(False, validation_alias="DEBUG")
    
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
