"""
Configuration management for Enterprise RAG System

This module handles all configuration settings using Pydantic for validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional, List
import os


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # API Keys
    openai_api_key: str = Field(..., validation_alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(None, validation_alias="ANTHROPIC_API_KEY")
    cohere_api_key: Optional[str] = Field(None, validation_alias="COHERE_API_KEY")

    # Vector Database
    pinecone_api_key: Optional[str] = Field(None, validation_alias="PINECONE_API_KEY")
    pinecone_environment: str = Field("us-west1-gcp", validation_alias="PINECONE_ENVIRONMENT")
    pinecone_index_name: str = Field("enterprise-rag", validation_alias="PINECONE_INDEX_NAME")

    # File Paths (Security: no hardcoded paths)
    faiss_index_path: str = Field("./data/faiss_index.bin", validation_alias="FAISS_INDEX_PATH")
    chroma_persist_dir: str = Field("./data/chroma", validation_alias="CHROMA_PERSIST_DIR")

    # CORS (Security: controlled origins)
    allowed_origins: str = Field(
        "http://localhost:8000,http://localhost:3000",
        validation_alias="ALLOWED_ORIGINS"
    )

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
    enable_metrics: bool = Field(True, validation_alias="ENABLE_METRICS")

    # Application
    app_name: str = "Enterprise RAG System"
    app_version: str = "0.2.0"
    debug: bool = Field(False, validation_alias="DEBUG")

    # Server
    server_host: str = Field("0.0.0.0", validation_alias="SERVER_HOST")
    server_port: int = Field(8000, validation_alias="SERVER_PORT")

    # CORS Headers (security: restrict allowed headers)
    allowed_headers: str = Field(
        "Content-Type,Authorization,X-API-Key,X-Request-ID",
        validation_alias="ALLOWED_HEADERS",
    )

    # Request size limit (bytes)
    max_request_size: int = Field(10 * 1024 * 1024, validation_alias="MAX_REQUEST_SIZE")

    # Rate Limiting
    rate_limit_enabled: bool = Field(True, validation_alias="RATE_LIMIT_ENABLED")
    rate_limit_per_minute: int = Field(60, validation_alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_per_hour: int = Field(1000, validation_alias="RATE_LIMIT_PER_HOUR")
    rate_limit_burst: int = Field(10, validation_alias="RATE_LIMIT_BURST")

    # Redis Cache Configuration
    redis_host: str = Field("localhost", validation_alias="REDIS_HOST")
    redis_port: int = Field(6379, validation_alias="REDIS_PORT")
    redis_db: int = Field(0, validation_alias="REDIS_DB")
    redis_password: Optional[str] = Field(None, validation_alias="REDIS_PASSWORD")
    cache_enabled: bool = Field(True, validation_alias="CACHE_ENABLED")
    cache_ttl_seconds_redis: int = Field(3600, validation_alias="CACHE_TTL_SECONDS") # Renamed to avoid collision

    # Celery Configuration
    celery_broker_url: str = Field("redis://localhost:6379/1", validation_alias="CELERY_BROKER_URL")
    celery_result_backend: str = Field("redis://localhost:6379/2", validation_alias="CELERY_RESULT_BACKEND")

    # PostgreSQL Database Configuration
    postgres_host: str = Field("localhost", validation_alias="POSTGRES_HOST")
    postgres_port: int = Field(5432, validation_alias="POSTGRES_PORT")
    postgres_database: str = Field("enterprise_rag", validation_alias="POSTGRES_DATABASE")
    postgres_user: str = Field("postgres", validation_alias="POSTGRES_USER")
    postgres_password: str = Field("", validation_alias="POSTGRES_PASSWORD")
    postgres_pool_min_size: int = Field(10, validation_alias="POSTGRES_POOL_MIN_SIZE")
    postgres_pool_max_size: int = Field(50, validation_alias="POSTGRES_POOL_MAX_SIZE")
    postgres_command_timeout: int = Field(60, validation_alias="POSTGRES_COMMAND_TIMEOUT")

    @property
    def ALLOWED_ORIGINS(self) -> List[str]:
        """Parse comma-separated origins into a list"""
        return [origin.strip() for origin in self.allowed_origins.split(",")]

    @property
    def ALLOWED_HEADERS_LIST(self) -> List[str]:
        """Parse comma-separated headers into a list"""
        return [h.strip() for h in self.allowed_headers.split(",")]


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings"""
    return settings
