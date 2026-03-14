"""
Performance Monitoring Middleware for FastAPI

This middleware provides automatic performance tracking for all HTTP requests,
with special handling for query endpoints to track RAG-specific metrics.
"""

import time
import uuid
import logging
from typing import Callable, Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.core.performance import get_performance_monitor

logger = logging.getLogger(__name__)


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware to track performance metrics for all HTTP requests.

    Features:
    - Automatic request timing
    - Query-specific metrics tracking
    - Response status tracking
    - Error tracking
    - Thread-safe metric collection

    Special handling for query endpoints:
    - Extracts query-specific metrics (tokens, sources, confidence)
    - Tracks query execution time separately from total request time
    - Stores query text for analysis (truncated for privacy)
    """

    def __init__(
        self,
        app: ASGIApp,
        enable_query_tracking: bool = True,
        track_all_requests: bool = True,
        query_path_prefix: str = "/api/v1/query",
    ) -> None:
        """
        Initialize the performance monitoring middleware

        Args:
            app: The ASGI application to wrap
            enable_query_tracking: Enable special tracking for query endpoints
            track_all_requests: Track all requests or only queries
            query_path_prefix: Path prefix to identify query endpoints
        """
        super().__init__(app)
        self.enable_query_tracking = enable_query_tracking
        self.track_all_requests = track_all_requests
        self.query_path_prefix = query_path_prefix

        logger.info(
            f"Performance monitoring middleware initialized: "
            f"query_tracking={enable_query_tracking}, "
            f"track_all={track_all_requests}"
        )

    def is_query_endpoint(self, path: str) -> bool:
        """
        Check if the request path is a query endpoint

        Args:
            path: Request path

        Returns:
            True if this is a query endpoint
        """
        return path.startswith(self.query_path_prefix)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and track performance metrics

        Args:
            request: Incoming request
            call_next: Next middleware/route handler

        Returns:
            Response from the next handler
        """
        # Generate unique request ID
        request_id = str(uuid.uuid4())

        # Skip tracking if tracking is disabled
        if not self.track_all_requests and not self.is_query_endpoint(request.url.path):
            return await call_next(request)

        # Get performance monitor
        monitor = get_performance_monitor()

        # Start timing
        start_time = time.time()

        # Cache request body for query endpoint tracking
        # This prevents consuming the stream before the route handler can read it
        query_metrics = None
        query_text = None
        if self.enable_query_tracking and self.is_query_endpoint(request.url.path):
            try:
                # Read and cache the body
                body = await request.body()

                # Store in request state for potential later use
                if not hasattr(request.state, "_cached_body"):
                    request.state._cached_body = body

                # Extract query text from cached body
                query_text = self._extract_query_from_bytes(body)

                # Start tracking
                query_metrics = monitor.start_query(
                    query_id=request_id,
                    query=query_text or f"{request.method} {request.url.path}",
                    metadata={
                        "method": request.method,
                        "path": request.url.path,
                        "client_host": request.client.host if request.client else None,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to start query tracking: {e}", exc_info=True)

        # Process request
        try:
            response = await call_next(request)

            # Calculate total request time
            request_time_ms = (time.time() - start_time) * 1000

            # End query tracking for query endpoints
            if query_metrics:
                try:
                    # Extract query-specific metrics from response headers
                    tokens_used = self._extract_header(response, "X-Tokens-Used", default=0, type=int)
                    sources_count = self._extract_header(response, "X-Sources-Count", default=0, type=int)
                    confidence = self._extract_header(response, "X-Confidence", default=0.0, type=float)

                    monitor.end_query(
                        query_id=request_id,
                        latency_ms=request_time_ms,
                        tokens_used=tokens_used,
                        sources_count=sources_count,
                        confidence=confidence,
                        status="success" if response.status_code < 400 else "error",
                    )
                except Exception as e:
                    logger.warning(f"Failed to end query tracking: {e}")

            # Add request ID and timing to response headers for all tracked requests
            # Use dict.update() for safer header mutation
            response.headers.update({
                "X-Request-ID": request_id,
                "X-Request-Time-Ms": f"{request_time_ms:.2f}"
            })

            # Log request completion
            logger.debug(
                f"{request.method} {request.url.path} "
                f"completed in {request_time_ms:.2f}ms "
                f"with status {response.status_code}"
            )

            return response

        except Exception as e:
            # Calculate request time even for errors
            request_time_ms = (time.time() - start_time) * 1000

            # End query tracking with error status
            if query_metrics:
                try:
                    monitor.end_query(
                        query_id=request_id,
                        latency_ms=request_time_ms,
                        status="error",
                        error_message=str(e),
                    )
                except Exception as tracking_error:
                    logger.warning(f"Failed to record query error: {tracking_error}")

            # Log error
            logger.error(
                f"{request.method} {request.url.path} "
                f"failed after {request_time_ms:.2f}ms: {e}"
            )

            # Re-raise the exception
            raise

    def _extract_query_from_bytes(self, body: bytes) -> Optional[str]:
        """
        Extract query text from cached request body bytes

        Args:
            body: Request body as bytes

        Returns:
            Query text if found, None otherwise
        """
        try:
            import json
            data = json.loads(body.decode("utf-8"))

            # Try common field names
            for field in ["query", "question", "text", "prompt"]:
                if field in data and isinstance(data[field], str):
                    return data[field]

            return None
        except Exception:
            return None

        except Exception as e:
            logger.debug(f"Failed to extract query text: {e}")
            return None

    def _extract_header(
        self,
        response: Response,
        header_name: str,
        default: Any = None,
        type: Callable = str
    ) -> Any:
        """
        Extract and convert header value

        Args:
            response: Response object
            header_name: Name of the header
            default: Default value if header not found
            type: Type converter function

        Returns:
            Header value converted to specified type
        """
        try:
            value = response.headers.get(header_name)
            if value is None:
                return default
            return type(value)
        except (ValueError, TypeError):
            return default


class QueryPerformanceTracker:
    """
    Context manager for tracking query performance in route handlers.

    This provides a manual way to track query performance when automatic
    middleware tracking is not sufficient.

    Example:
        ```python
        async def query_endpoint(request: QueryRequest):
            tracker = QueryPerformanceTracker(
                query=request.query,
                metadata={"user_id": request.user_id}
            )

            with tracker:
                # Execute query
                result = pipeline.query(...)
                tracker.set_metrics(
                    tokens_used=result.tokens_used,
                    sources_count=len(result.sources),
                    confidence=result.confidence
                )

            return result
        ```
    """

    def __init__(self, query: str, query_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """
        Initialize query performance tracker

        Args:
            query: Query text
            query_id: Optional unique identifier (auto-generated if not provided)
            metadata: Optional metadata to attach to the query
        """
        self.query = query
        self.query_id = query_id or str(uuid.uuid4())
        self.metadata = metadata or {}
        self.monitor = get_performance_monitor()
        self.start_time: Optional[float] = None
        self._tokens_used: int = 0
        self._sources_count: int = 0
        self._confidence: float = 0.0

    def set_metrics(self, tokens_used: int = 0, sources_count: int = 0, confidence: float = 0.0):
        """
        Set query-specific metrics

        Args:
            tokens_used: Number of tokens used
            sources_count: Number of sources retrieved
            confidence: Confidence score
        """
        self._tokens_used = tokens_used
        self._sources_count = sources_count
        self._confidence = confidence

    def __enter__(self):
        """Start tracking query"""
        self.start_time = time.time()
        self.monitor.start_query(
            query_id=self.query_id,
            query=self.query,
            metadata=self.metadata
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """End tracking query"""
        if self.start_time is None:
            return

        latency_ms = (time.time() - self.start_time) * 1000

        if exc_type is not None:
            # Query failed
            self.monitor.end_query(
                query_id=self.query_id,
                latency_ms=latency_ms,
                status="error",
                error_message=str(exc_val)
            )
        else:
            # Query succeeded
            self.monitor.end_query(
                query_id=self.query_id,
                latency_ms=latency_ms,
                tokens_used=self._tokens_used,
                sources_count=self._sources_count,
                confidence=self._confidence,
                status="success"
            )

        return False  # Don't suppress exceptions
