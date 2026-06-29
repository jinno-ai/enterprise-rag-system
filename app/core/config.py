"""
Configuration management for Enterprise RAG System

This module handles all configuration settings using Pydantic for validation.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices
from typing import Optional, List


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

    # File Paths (Security: no hardcoded paths)
    faiss_index_path: str = Field("./data/faiss_index.bin", validation_alias=AliasChoices("FAISS_INDEX_PATH", "faiss_index_path"))
    chroma_persist_dir: str = Field("./data/chroma", validation_alias=AliasChoices("CHROMA_PERSIST_DIR", "chroma_persist_dir"))

    # CORS (Security: controlled origins)
    allowed_origins: str = Field(
        "http://localhost:8000,http://localhost:3000",
        validation_alias=AliasChoices("ALLOWED_ORIGINS", "allowed_origins")
    )

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
    enable_metrics: bool = Field(True, validation_alias=AliasChoices("ENABLE_METRICS", "enable_metrics"))

    # Application
    app_name: str = "Enterprise RAG System"
    app_version: str = "0.2.0"
    debug: bool = Field(False, validation_alias=AliasChoices("DEBUG", "debug"))

    # Server
    server_host: str = Field("0.0.0.0", validation_alias=AliasChoices("SERVER_HOST", "server_host"))
    server_port: int = Field(8000, validation_alias=AliasChoices("SERVER_PORT", "server_port"))

    # CORS Headers (security: restrict allowed headers)
    allowed_headers: str = Field(
        "Content-Type,Authorization,X-API-Key,X-Request-ID",
        validation_alias=AliasChoices("ALLOWED_HEADERS", "allowed_headers"),
    )

    # Request size limit (bytes)
    max_request_size: int = Field(10 * 1024 * 1024, validation_alias=AliasChoices("MAX_REQUEST_SIZE", "max_request_size"))

    # Rate Limiting
    rate_limit_enabled: bool = Field(True, validation_alias=AliasChoices("RATE_LIMIT_ENABLED", "rate_limit_enabled"))
    rate_limit_per_minute: int = Field(60, validation_alias=AliasChoices("RATE_LIMIT_PER_MINUTE", "rate_limit_per_minute"))
    rate_limit_per_hour: int = Field(1000, validation_alias=AliasChoices("RATE_LIMIT_PER_HOUR", "rate_limit_per_hour"))
    rate_limit_burst: int = Field(10, validation_alias=AliasChoices("RATE_LIMIT_BURST", "rate_limit_burst"))

    # Redis Cache Configuration
    redis_host: str = Field("localhost", validation_alias=AliasChoices("REDIS_HOST", "redis_host"))
    redis_port: int = Field(6379, validation_alias=AliasChoices("REDIS_PORT", "redis_port"))
    redis_db: int = Field(0, validation_alias=AliasChoices("REDIS_DB", "redis_db"))
    redis_password: Optional[str] = Field(None, validation_alias=AliasChoices("REDIS_PASSWORD", "redis_password"))
    cache_enabled: bool = Field(True, validation_alias=AliasChoices("CACHE_ENABLED", "cache_enabled"))

    # Celery Configuration
    celery_broker_url: str = Field("redis://localhost:6379/1", validation_alias=AliasChoices("CELERY_BROKER_URL", "celery_broker_url"))
    celery_result_backend: str = Field("redis://localhost:6379/2", validation_alias=AliasChoices("CELERY_RESULT_BACKEND", "celery_result_backend"))

    # PostgreSQL Database Configuration
    postgres_host: str = Field("localhost", validation_alias=AliasChoices("POSTGRES_HOST", "postgres_host"))
    postgres_port: int = Field(5432, validation_alias=AliasChoices("POSTGRES_PORT", "postgres_port"))
    postgres_database: str = Field("enterprise_rag", validation_alias=AliasChoices("POSTGRES_DATABASE", "postgres_database"))
    postgres_user: str = Field("postgres", validation_alias=AliasChoices("POSTGRES_USER", "postgres_user"))
    postgres_password: str = Field("", validation_alias=AliasChoices("POSTGRES_PASSWORD", "postgres_password"))
    postgres_pool_min_size: int = Field(10, validation_alias=AliasChoices("POSTGRES_POOL_MIN_SIZE", "postgres_pool_min_size"))
    postgres_pool_max_size: int = Field(50, validation_alias=AliasChoices("POSTGRES_POOL_MAX_SIZE", "postgres_pool_max_size"))
    postgres_command_timeout: int = Field(60, validation_alias=AliasChoices("POSTGRES_COMMAND_TIMEOUT", "postgres_command_timeout"))

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
