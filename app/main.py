"""
FastAPI Application Entry Point

This is the main application file that sets up the FastAPI server.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import uvicorn
from typing import Optional

from app.core.config import get_settings
from app.core.vectordb import get_vector_db
from app.core.embeddings import get_embedding_model
from app.core.logging_config import setup_logging, get_logger
from app.core.rate_limit import limiter
from app.core.cache import CacheManager
from app.core import metrics
from app.services.retrieval import HybridRetriever
from app.services.rag_pipeline import RAGPipeline
from app.api.routes import query, health, ingest, documents
from app.middleware.validation import ValidationMiddleware
from app.middleware.request_id import RequestIDMiddleware
from openai import AsyncOpenAI
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator
from app.api.routes.v2 import router as v2_router
from app.middleware.compression import CompressionMiddleware


# Setup logging first
setup_logging()
logger = get_logger(__name__)

settings = get_settings()


# Global instances (initialized at startup)
_rag_pipeline: Optional[RAGPipeline] = None
_initialization_error: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    global _rag_pipeline, _initialization_error

    # Startup
    logger.info("Starting Enterprise RAG System...")

    try:
        # Initialize OpenAI client
        logger.info("Initializing OpenAI async client...")
        openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        app.state.openai_client = openai_client

        # Initialize Redis cache
        cache_enabled = settings.cache_enabled
        logger.info(f"Initializing Redis cache (enabled={cache_enabled})...")
        cache_manager = CacheManager(
            redis_host=settings.redis_host,
            redis_port=settings.redis_port,
            redis_db=settings.redis_db,
            redis_password=settings.redis_password,
            ttl=settings.cache_ttl_seconds,
            enabled=cache_enabled
        )
        app.state.cache_manager = cache_manager

        # Initialize components
        logger.info("Initializing vector database...")
        vector_db = get_vector_db(
            db_type="faiss",
            index_path=settings.faiss_index_path
        )
        vector_db.connect()

        logger.info("Initializing embedding model...")
        embedding_model = get_embedding_model()

        logger.info("Initializing retriever...")
        retriever = HybridRetriever(
            vector_db=vector_db,
            embedding_model=embedding_model,
            alpha=settings.hybrid_search_alpha
        )

        logger.info("Initializing RAG pipeline...")
        _rag_pipeline = RAGPipeline(
            retriever=retriever,
            llm_client=openai_client,
            llm_model=settings.llm_model,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            cache_manager=cache_manager
        )
        app.state.rag_pipeline = _rag_pipeline

        logger.info("Starting background document processor...")
        from app.services.document_processor import start_processor
        await start_processor()

        logger.info("Enterprise RAG System ready!")
        _initialization_error = None

    except Exception as e:
        logger.error(f"Initialization failed: {e}", exc_info=True)
        _initialization_error = f"Initialization failed: {e}"
        _rag_pipeline = None
        # Allow app to start; health/dependencies reflect the error

    yield

    # Shutdown
    logger.info("Shutting down Enterprise RAG System...")
    from app.services.document_processor import stop_processor
    await stop_processor()


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
Enterprise RAG System API / 企業向けRAGシステム API

## Features / 機能

* **Semantic Search**: High-performance vector similarity search / 高性能ベクトル類似度検索
* **Hybrid Search**: Combines semantic and keyword search for optimal results / セマンティック検索とキーワード検索を組み合わせた最適な結果
* **Re-ranking**: Cross-encoder re-ranking for improved accuracy / 改善された精度のためのクロスエンコーダー再ランク付け
* **Multi-collection**: Logical separation and management of document collections / ドキュメントコレクションの論理的分離と管理
* **Response Caching**: Redis-based high-speed response caching / Redisベースの高速応答キャッシュ
* **Rate Limiting**: API protection and fair resource allocation / API保護と公平なリソース配分

## Authentication / 認証

API key authentication is supported (optional) / APIキー認証をサポート（オプション）

```http
X-API-Key: your-api-key-here
```

## Rate Limiting / レート制限

* `/api/v1/query/` endpoint: 60 requests/minute / エンドポイント: 60リクエスト/分
* `/api/v1/query/batch` endpoint: 60 requests/minute / エンドポイント: 60リクエスト/分
* `/api/v1/documents/ingest` endpoint: 20 requests/minute / エンドポイント: 20リクエスト/分
* `/health` endpoints: 120 requests/minute / エンドポイント: 120リクエスト/分

## Documentation / ドキュメント

* **Swagger UI**: Interactive API documentation at `/docs` `/docs`でのインタラクティブなAPIドキュメント
* **ReDoc**: Alternative documentation at `/redoc` `/redoc`での代替ドキュメント
* **OpenAPI JSON**: Schema export at `/openapi.json` `/openapi.json`でのスキーマエクスポート
    """,
    lifespan=lifespan,
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    openapi_tags=[
        {
            "name": "Query",
            "description": "RAG query execution and search functionality / RAGクエリ実行と検索機能"
        },
        {
            "name": "Documents",
            "description": "Document registration and management / ドキュメント登録と管理"
        },
        {
            "name": "Health",
            "description": "Health checks and system information / ヘルスチェックとシステム情報"
        }
    ],
    contact={
        "name": "API Support",
        "email": "support@example.com",
        "url": "https://github.com/jinno-ai/enterprise-rag-system/issues"
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT"
    }
)

# Setup Prometheus instrumentation
instrumentator = Instrumentator(
    should_group_status_codes=False,
    should_ignore_untemplated=True,
    should_group_untemplated=True,
    should_instrument_requests_inprogress=True,
    excluded_handlers=["/metrics"],
    env_var_name="ENABLE_METRICS",
    inprogress_name="http_requests_inprogress",
)
instrumentator.instrument(app).expose(app, endpoint="/metrics")

# Set application info
metrics.app_info.info({
    'version': settings.app_version,
    'name': settings.app_name
})


async def _rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Custom error handler for rate limit exceeded.

    Args:
        request: FastAPI request object
        exc: RateLimitExceeded exception

    Returns:
        JSONResponse with 429 status code
    """
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "message": "Too many requests. Please try again later.",
            "retry_after": str(exc.retry_after) if hasattr(exc, 'retry_after') else None
        },
        headers={"Retry-After": str(exc.retry_after)} if hasattr(exc, 'retry_after') else {}
    )


# Configure rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # Use configured origins
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=settings.ALLOWED_HEADERS_LIST,  # Security: restrict allowed headers
)

# Add request ID middleware for distributed tracing
# This should be added BEFORE validation middleware to ensure all requests are tracked
app.add_middleware(RequestIDMiddleware)

# Add validation middleware for security
# This should be added AFTER CORS middleware but BEFORE request processing
app.add_middleware(
    ValidationMiddleware,
    max_request_size=settings.max_request_size,  # Configurable via MAX_REQUEST_SIZE env
    enable_security_validation=True,
    log_suspicious=True
)

# Add compression middleware
# Compresses responses larger than minimum_size threshold when client supports gzip
app.add_middleware(
    CompressionMiddleware,
    minimum_size=settings.compression_minimum_size,
    compresslevel=settings.compression_level
)


# Include routers
app.include_router(health.router, tags=["Health"])

# v1 API routes (backward compatible)
app.include_router(query.router, prefix="/api/v1", tags=["Query"])
app.include_router(ingest.router, prefix="/api/v1", tags=["Ingest"])
app.include_router(documents.router, prefix="/api/v1", tags=["Documents"])

# v2 API routes (enhanced features)
app.include_router(v2_router)


@app.get("/", tags=["Health"])
@limiter.limit("120/minute")
async def root(request: Request):
    """Root endpoint"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


def get_rag_pipeline() -> RAGPipeline:
    """Get the global RAG pipeline instance"""
    if _rag_pipeline is None:
        raise RuntimeError("RAG pipeline not initialized")
    return _rag_pipeline


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=settings.debug
    )
