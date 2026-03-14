"""
Unit tests for Query Performance Monitoring Feature (Feature 32)

Tests performance tracking for query execution including:
- Metrics collection and storage
- Statistics calculation
- Thread safety
- Middleware integration
"""

import pytest
import time
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.core.performance import (
    PerformanceMonitor,
    QueryMetrics,
    get_performance_monitor,
    reset_performance_monitor,
)
from app.middleware.monitoring import (
    PerformanceMonitoringMiddleware,
    QueryPerformanceTracker,
)


@pytest.fixture
def monitor():
    """Create a fresh performance monitor for each test"""
    reset_performance_monitor()
    monitor = PerformanceMonitor(max_history=100)
    return monitor


@pytest.fixture
def app_with_monitoring():
    """Create a test app with performance monitoring middleware"""
    app = FastAPI()

    # Add performance monitoring middleware
    app.add_middleware(
        PerformanceMonitoringMiddleware,
        enable_query_tracking=True,
        track_all_requests=True,
        query_path_prefix="/api/v1/query",
    )

    @app.get("/test")
    async def test_endpoint():
        return {"status": "ok", "message": "test"}

    @app.post("/api/v1/query")
    async def query_endpoint(request: dict):
        # Simulate query processing
        time.sleep(0.01)
        response = JSONResponse(
            {
                "answer": "test answer",
                "sources": [],
                "confidence": 0.95,
            }
        )
        response.headers["X-Tokens-Used"] = "100"
        response.headers["X-Sources-Count"] = "5"
        response.headers["X-Confidence"] = "0.95"
        return response

    @app.post("/api/v1/query/error")
    async def query_error_endpoint():
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Test error")

    return app


@pytest.fixture
def client(app_with_monitoring):
    """Create test client"""
    return TestClient(app_with_monitoring)


class TestQueryMetrics:
    """Test QueryMetrics dataclass"""

    def test_query_metrics_creation(self):
        """Test creating a QueryMetrics object"""
        metrics = QueryMetrics(
            query_id="test-123",
            query="What is the meaning of life?",
            start_time=datetime.utcnow(),
        )

        assert metrics.query_id == "test-123"
        assert metrics.query == "What is the meaning of life?"
        assert metrics.status == "in_progress"
        assert metrics.latency_ms == 0.0

    def test_query_metrics_to_dict(self):
        """Test converting QueryMetrics to dictionary"""
        metrics = QueryMetrics(
            query_id="test-123",
            query="x" * 200,  # Long query
            start_time=datetime.utcnow(),
            latency_ms=123.45,
            tokens_used=500,
            sources_count=5,
            confidence=0.95,
            status="success",
        )

        data = metrics.to_dict()

        assert data["query_id"] == "test-123"
        assert len(data["query"]) <= 100  # Should be truncated
        assert data["latency_ms"] == 123.45
        assert data["tokens_used"] == 500
        assert data["sources_count"] == 5
        assert data["confidence"] == 0.95
        assert data["status"] == "success"


class TestPerformanceMonitor:
    """Test PerformanceMonitor core functionality"""

    def test_start_query(self, monitor):
        """Test starting query tracking"""
        metrics = monitor.start_query(
            query_id="test-1",
            query="test query",
            metadata={"user_id": "user123"},
        )

        assert metrics.query_id == "test-1"
        assert metrics.query == "test query"
        assert metrics.status == "in_progress"
        assert metrics.metadata == {"user_id": "user123"}

    def test_end_query_success(self, monitor):
        """Test ending query tracking with success"""
        monitor.start_query(query_id="test-2", query="test query")

        metrics = monitor.end_query(
            query_id="test-2",
            latency_ms=100.0,
            tokens_used=50,
            sources_count=3,
            confidence=0.85,
            status="success",
        )

        assert metrics is not None
        assert metrics.status == "success"
        assert metrics.latency_ms == 100.0
        assert metrics.tokens_used == 50
        assert metrics.sources_count == 3
        assert metrics.confidence == 0.85
        assert metrics.end_time is not None

    def test_end_query_error(self, monitor):
        """Test ending query tracking with error"""
        monitor.start_query(query_id="test-3", query="test query")

        metrics = monitor.end_query(
            query_id="test-3",
            latency_ms=50.0,
            status="error",
            error_message="Connection timeout",
        )

        assert metrics is not None
        assert metrics.status == "error"
        assert metrics.error_message == "Connection timeout"

    def test_end_nonexistent_query(self, monitor):
        """Test ending a query that doesn't exist"""
        metrics = monitor.end_query(query_id="nonexistent", latency_ms=100.0)

        assert metrics is None

    def test_get_query_metrics_active(self, monitor):
        """Test getting metrics for an active query"""
        monitor.start_query(query_id="test-4", query="active query")

        metrics = monitor.get_query_metrics("test-4")

        assert metrics is not None
        assert metrics.query_id == "test-4"
        assert metrics.status == "in_progress"

    def test_get_query_metrics_history(self, monitor):
        """Test getting metrics from history"""
        monitor.start_query(query_id="test-5", query="history query")
        monitor.end_query(query_id="test-5", latency_ms=100.0, status="success")

        metrics = monitor.get_query_metrics("test-5")

        assert metrics is not None
        assert metrics.query_id == "test-5"
        assert metrics.status == "success"

    def test_get_query_metrics_not_found(self, monitor):
        """Test getting metrics for non-existent query"""
        metrics = monitor.get_query_metrics("nonexistent")

        assert metrics is None

    def test_get_statistics_empty(self, monitor):
        """Test statistics with no queries"""
        stats = monitor.get_statistics()

        assert stats["total_queries"] == 0
        assert stats["avg_latency_ms"] == 0.0
        assert stats["success_rate"] == 0.0

    def test_get_statistics_with_queries(self, monitor):
        """Test statistics with multiple queries"""
        # Add some successful queries
        for i in range(10):
            monitor.start_query(query_id=f"test-{i}", query=f"query {i}")
            monitor.end_query(
                query_id=f"test-{i}",
                latency_ms=100.0 + i * 10,
                tokens_used=50 + i * 5,
                sources_count=3,
                confidence=0.8 + i * 0.01,
                status="success",
            )

        # Add one failed query
        monitor.start_query(query_id="test-failed", query="failed query")
        monitor.end_query(query_id="test-failed", latency_ms=50.0, status="error")

        stats = monitor.get_statistics()

        assert stats["total_queries"] == 11
        assert stats["success_rate"] == 10 / 11
        assert stats["avg_latency_ms"] > 0
        assert stats["p50_latency_ms"] > 0
        assert stats["p95_latency_ms"] > 0
        assert stats["avg_tokens_used"] > 0
        # Average includes failed query with 0 sources: (10*3 + 0) / 11 = 30/11
        assert stats["avg_sources_count"] == 30 / 11

    def test_get_recent_queries(self, monitor):
        """Test getting recent queries"""
        # Add 5 queries
        for i in range(5):
            monitor.start_query(query_id=f"test-{i}", query=f"query {i}")
            monitor.end_query(
                query_id=f"test-{i}",
                latency_ms=100.0,
                tokens_used=50,
                status="success",
            )

        recent = monitor.get_recent_queries(limit=3)

        assert len(recent) == 3
        # Should be in reverse chronological order
        assert recent[0]["query_id"] == "test-4"
        assert recent[1]["query_id"] == "test-3"
        assert recent[2]["query_id"] == "test-2"

    def test_get_active_queries(self, monitor):
        """Test getting active queries"""
        # Start some queries
        monitor.start_query(query_id="active-1", query="query 1")
        monitor.start_query(query_id="active-2", query="query 2")

        # End one
        monitor.end_query(query_id="active-1", latency_ms=100.0, status="success")

        active = monitor.get_active_queries()

        assert len(active) == 1
        assert active[0]["query_id"] == "active-2"

    def test_clear_history(self, monitor):
        """Test clearing query history"""
        # Add some queries
        for i in range(5):
            monitor.start_query(query_id=f"test-{i}", query=f"query {i}")
            monitor.end_query(query_id=f"test-{i}", latency_ms=100.0, status="success")

        count = monitor.clear_history()

        assert count == 5
        assert monitor.get_history_size() == 0

    def test_max_history_limit(self):
        """Test that history is limited to max_history"""
        monitor = PerformanceMonitor(max_history=5)

        # Add 10 queries
        for i in range(10):
            monitor.start_query(query_id=f"test-{i}", query=f"query {i}")
            monitor.end_query(query_id=f"test-{i}", latency_ms=100.0, status="success")

        # Should only keep last 5
        assert monitor.get_history_size() == 5


class TestPerformanceMonitoringMiddleware:
    """Test performance monitoring middleware"""

    def test_middleware_adds_request_id(self, client):
        """Test that middleware adds request ID to response"""
        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

    def test_middleware_tracks_request_time(self, client):
        """Test that middleware tracks request time"""
        response = client.get("/test")

        assert response.status_code == 200
        assert "X-Request-Time-Ms" in response.headers

        request_time = float(response.headers["X-Request-Time-Ms"])
        assert request_time >= 0

    def test_middleware_tracks_query_endpoint(self, client):
        """Test that middleware tracks query endpoints"""
        response = client.post(
            "/api/v1/query",
            json={"query": "test query"},
        )

        assert response.status_code == 200
        assert "X-Request-ID" in response.headers

        # Check that query was tracked
        monitor = get_performance_monitor()
        stats = monitor.get_statistics()
        assert stats["total_queries"] > 0

    def test_middleware_extracts_query_metrics_from_headers(self, client):
        """Test that middleware extracts metrics from response headers"""
        response = client.post(
            "/api/v1/query",
            json={"query": "test query"},
        )

        assert response.status_code == 200

        # Get the tracked query
        request_id = response.headers["X-Request-ID"]
        monitor = get_performance_monitor()
        metrics = monitor.get_query_metrics(request_id)

        assert metrics is not None
        assert metrics.tokens_used == 100
        assert metrics.sources_count == 5
        assert metrics.confidence == 0.95

    def test_middleware_handles_errors(self, client):
        """Test that middleware handles errors gracefully"""
        response = client.post("/api/v1/query/error")

        assert response.status_code == 500

        # Query should still be tracked with error status
        monitor = get_performance_monitor()
        stats = monitor.get_statistics()

        # Should have tracked the error
        assert stats["total_queries"] > 0
        assert stats["success_rate"] < 1.0


class TestQueryPerformanceTracker:
    """Test QueryPerformanceTracker context manager"""

    def test_tracker_context_manager_success(self):
        """Test tracker context manager for successful query"""
        reset_performance_monitor()

        with QueryPerformanceTracker(query="test query") as tracker:
            # Simulate query execution
            time.sleep(0.01)
            tracker.set_metrics(
                tokens_used=100,
                sources_count=5,
                confidence=0.95,
            )

        # Verify query was tracked
        monitor = get_performance_monitor()
        metrics = monitor.get_query_metrics(tracker.query_id)

        assert metrics is not None
        assert metrics.status == "success"
        assert metrics.latency_ms >= 10  # At least 10ms
        assert metrics.tokens_used == 100
        assert metrics.sources_count == 5
        assert metrics.confidence == 0.95

    def test_tracker_context_manager_error(self):
        """Test tracker context manager for failed query"""
        reset_performance_monitor()

        try:
            with QueryPerformanceTracker(query="test query") as tracker:
                time.sleep(0.01)
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected

        # Verify query was tracked with error
        monitor = get_performance_monitor()
        metrics = monitor.get_query_metrics(tracker.query_id)

        assert metrics is not None
        assert metrics.status == "error"
        assert metrics.error_message == "Test error"

    def test_tracker_with_metadata(self):
        """Test tracker with custom metadata"""
        reset_performance_monitor()

        metadata = {"user_id": "user123", "collection": "test"}

        tracker = QueryPerformanceTracker(query="test query", metadata=metadata)
        with tracker:
            pass

        # Verify metadata was stored
        monitor = get_performance_monitor()
        metrics = monitor.get_query_metrics(tracker.query_id)

        assert metrics is not None
        assert metrics.metadata == metadata

    def test_tracker_custom_query_id(self):
        """Test tracker with custom query ID"""
        reset_performance_monitor()

        custom_id = "custom-query-id"

        with QueryPerformanceTracker(query="test query", query_id=custom_id):
            pass

        # Verify custom ID was used
        monitor = get_performance_monitor()
        metrics = monitor.get_query_metrics(custom_id)

        assert metrics is not None
        assert metrics.query_id == custom_id


class TestThreadSafety:
    """Test thread safety of performance monitor"""

    def test_concurrent_query_tracking(self, monitor):
        """Test that multiple threads can track queries concurrently"""
        import threading

        results = []
        errors = []

        def track_query(query_id):
            try:
                monitor.start_query(query_id=query_id, query=f"query {query_id}")
                time.sleep(0.01)  # Simulate work
                monitor.end_query(
                    query_id=query_id,
                    latency_ms=10.0,
                    status="success",
                )
                results.append(query_id)
            except Exception as e:
                errors.append(e)

        # Start 10 threads
        threads = []
        for i in range(10):
            t = threading.Thread(target=track_query, args=(f"thread-{i}",))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # Verify all queries were tracked
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 10
        assert monitor.get_history_size() == 10


class TestPercentileCalculation:
    """Test percentile calculation in statistics"""

    def test_percentiles_with_varied_latencies(self, monitor):
        """Test percentile calculation with varied latencies"""
        latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]

        for i, latency in enumerate(latencies):
            monitor.start_query(query_id=f"test-{i}", query=f"query {i}")
            monitor.end_query(
                query_id=f"test-{i}",
                latency_ms=float(latency),
                status="success",
            )

        stats = monitor.get_statistics()

        # Percentile calculation: index = int(len(data) * p / 100)
        # For 10 items: p50 = int(10 * 50/100) = int(5.0) = 5 -> latencies[5] = 60
        # p95 = int(10 * 95/100) = int(9.5) = 9 -> latencies[9] = 100
        # p99 = int(10 * 99/100) = int(9.9) = 9 -> latencies[9] = 100
        assert stats["p50_latency_ms"] == 60.0  # 50th percentile
        assert stats["p95_latency_ms"] == 100.0  # 95th percentile
        assert stats["p99_latency_ms"] == 100.0  # 99th percentile

    def test_percentiles_with_single_query(self, monitor):
        """Test percentiles with only one query"""
        monitor.start_query(query_id="test-1", query="query")
        monitor.end_query(query_id="test-1", latency_ms=100.0, status="success")

        stats = monitor.get_statistics()

        assert stats["p50_latency_ms"] == 100.0
        assert stats["p95_latency_ms"] == 100.0
        assert stats["p99_latency_ms"] == 100.0


class TestGlobalPerformanceMonitor:
    """Test global performance monitor instance"""

    def test_get_performance_monitor_singleton(self):
        """Test that get_performance_monitor returns singleton"""
        reset_performance_monitor()

        monitor1 = get_performance_monitor()
        monitor2 = get_performance_monitor()

        assert monitor1 is monitor2

    def test_reset_performance_monitor(self):
        """Test resetting the global monitor"""
        monitor1 = get_performance_monitor()

        reset_performance_monitor()

        monitor2 = get_performance_monitor()

        assert monitor1 is not monitor2


class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_duplicate_query_id(self, monitor):
        """Test handling of duplicate query IDs"""
        monitor.start_query(query_id="duplicate", query="first")

        # Should log warning but allow overwrite
        monitor.start_query(query_id="duplicate", query="second")

        active = monitor.get_active_queries()
        assert len(active) == 1
        assert active[0]["query"] == "second"

    def test_very_long_query(self, monitor):
        """Test handling of very long queries"""
        long_query = "x" * 10000

        monitor.start_query(query_id="test", query=long_query)
        monitor.end_query(query_id="test", latency_ms=100.0, status="success")

        metrics = monitor.get_query_metrics("test")
        assert metrics is not None

        # Query should be truncated in to_dict
        data = metrics.to_dict()
        assert len(data["query"]) <= 100

    def test_zero_latency(self, monitor):
        """Test handling of zero latency"""
        monitor.start_query(query_id="test", query="test")
        monitor.end_query(query_id="test", latency_ms=0.0, status="success")

        metrics = monitor.get_query_metrics("test")
        assert metrics.latency_ms == 0.0

    def test_negative_tokens(self, monitor):
        """Test handling of negative token count"""
        monitor.start_query(query_id="test", query="test")
        monitor.end_query(
            query_id="test",
            latency_ms=100.0,
            tokens_used=-10,  # Invalid but should be stored
            status="success",
        )

        metrics = monitor.get_query_metrics("test")
        assert metrics.tokens_used == -10
