"""
Unit tests for Analytics Dashboard (Feature 45)

Tests the search analytics dashboard functionality, including:
- Analytics API endpoints
- Dashboard UI components
- Data aggregation and visualization
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import json

from fastapi.testclient import TestClient

from app.main import app
from app.api.analytics import router
from app.core.performance import PerformanceMonitor, QueryMetrics


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def performance_monitor():
    """Create performance monitor with sample data"""
    monitor = PerformanceMonitor(max_history=100)

    # Add sample queries
    base_time = datetime.now(timezone.utc) - timedelta(hours=2)

    # Successful queries
    for i in range(20):
        query_time = base_time + timedelta(minutes=i * 5)
        metrics = QueryMetrics(
            query_id=f"query-{i}",
            query=f"Test query {i}",
            start_time=query_time,
        )
        metrics.end_time = query_time + timedelta(milliseconds=1000 + i * 50)
        metrics.latency_ms = 1000 + i * 50
        metrics.tokens_used = 500 + i * 10
        metrics.sources_count = 5
        metrics.confidence = 0.8 + (i % 20) * 0.01
        metrics.status = "success"

        monitor._query_history.append(metrics)

    # Failed queries
    for i in range(3):
        query_time = base_time + timedelta(minutes=i * 30)
        metrics = QueryMetrics(
            query_id=f"query-fail-{i}",
            query=f"Failed query {i}",
            start_time=query_time,
        )
        metrics.end_time = query_time + timedelta(milliseconds=500)
        metrics.latency_ms = 500
        metrics.status = "error"
        metrics.error_message = "Test error"

        monitor._query_history.append(metrics)

    return monitor


class TestAnalyticsStatistics:
    """Test analytics statistics endpoint"""

    def test_get_analytics_statistics_success(self, client, performance_monitor):
        """Test successful retrieval of analytics statistics"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/statistics")

            assert response.status_code == 200
            data = response.json()

            # Verify all required fields
            assert "total_queries" in data
            assert "avg_latency_ms" in data
            assert "p50_latency_ms" in data
            assert "p95_latency_ms" in data
            assert "p99_latency_ms" in data
            assert "success_rate" in data
            assert "avg_tokens_used" in data
            assert "avg_sources_count" in data
            assert "avg_confidence" in data

            # Verify data correctness
            assert data["total_queries"] == 23  # 20 success + 3 failed
            assert data["success_rate"] == pytest.approx(20/23, rel=0.01)
            assert data["avg_latency_ms"] > 0

    def test_get_analytics_statistics_with_limit(self, client, performance_monitor):
        """Test analytics statistics with limit parameter"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/statistics?limit=10")

            assert response.status_code == 200
            data = response.json()
            assert data["total_queries"] <= 10

    def test_get_analytics_statistics_invalid_limit(self, client, performance_monitor):
        """Test analytics statistics with invalid limit"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            # Limit too high
            response = client.get("/api/v1/analytics/statistics?limit=100000")
            assert response.status_code == 422  # Validation error

            # Limit too low
            response = client.get("/api/v1/analytics/statistics?limit=0")
            assert response.status_code == 422


class TestRecentQueries:
    """Test recent queries endpoint"""

    def test_get_recent_queries_default(self, client, performance_monitor):
        """Test getting recent queries with default limit"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/recent")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) <= 10  # Default limit

    def test_get_recent_queries_with_limit(self, client, performance_monitor):
        """Test getting recent queries with custom limit"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/recent?limit=5")

            assert response.status_code == 200
            data = response.json()
            assert len(data) <= 5

    def test_get_recent_queries_response_structure(self, client, performance_monitor):
        """Test that recent queries have correct structure"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/recent?limit=1")

            assert response.status_code == 200
            data = response.json()

            if len(data) > 0:
                query = data[0]
                assert "query_id" in query
                assert "query" in query
                assert "start_time" in query
                assert "latency_ms" in query
                assert "tokens_used" in query
                assert "sources_count" in query
                assert "confidence" in query
                assert "status" in query


class TestActiveQueries:
    """Test active queries endpoint"""

    def test_get_active_queries_empty(self, client):
        """Test getting active queries when none are active"""
        monitor = PerformanceMonitor()
        with patch('app.api.analytics.get_performance_monitor', return_value=monitor):
            response = client.get("/api/v1/analytics/queries/active")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 0

    def test_get_active_queries_with_active(self, client, performance_monitor):
        """Test getting active queries when some are active"""
        # Start a query without ending it
        performance_monitor.start_query("active-query-1", "Active test query")

        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/active")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) == 1


class TestTimeSeriesData:
    """Test time series endpoint"""

    def test_get_time_series_default(self, client, performance_monitor):
        """Test getting time series with default parameters"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/time-series")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_get_time_series_custom_params(self, client, performance_monitor):
        """Test getting time series with custom parameters"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get(
                "/api/v1/analytics/queries/time-series?hours=12&interval_minutes=30"
            )

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_get_time_series_response_structure(self, client, performance_monitor):
        """Test that time series data has correct structure"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/time-series")

            assert response.status_code == 200
            data = response.json()

            if len(data) > 0:
                point = data[0]
                assert "timestamp" in point
                assert "count" in point
                assert "avg_latency_ms" in point
                assert isinstance(point["count"], int)
                assert isinstance(point["avg_latency_ms"], (int, float))

    def test_get_time_series_invalid_params(self, client):
        """Test time series with invalid parameters"""
        # Hours too high
        response = client.get("/api/v1/analytics/queries/time-series?hours=200")
        assert response.status_code == 422

        # Interval too low
        response = client.get("/api/v1/analytics/queries/time-series?interval_minutes=1")
        assert response.status_code == 422


class TestTopQueries:
    """Test top queries endpoint"""

    def test_get_top_queries_default(self, client, performance_monitor):
        """Test getting top queries with default limit"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/top")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)

    def test_get_top_queries_with_limit(self, client, performance_monitor):
        """Test getting top queries with custom limit"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/top?limit=5")

            assert response.status_code == 200
            data = response.json()
            assert len(data) <= 5

    def test_get_top_queries_sorted(self, client, performance_monitor):
        """Test that top queries are sorted by frequency"""
        # Create monitor with duplicate queries
        monitor = PerformanceMonitor(max_history=100)

        # Add duplicate query
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            metrics = QueryMetrics(
                query_id=f"dup-query-{i}",
                query="duplicate test query",
                start_time=base_time,
            )
            metrics.end_time = base_time + timedelta(milliseconds=1000)
            metrics.latency_ms = 1000
            metrics.status = "success"
            monitor._query_history.append(metrics)

        # Add single query
        metrics = QueryMetrics(
            query_id="single-query",
            query="single test query",
            start_time=base_time,
        )
        metrics.end_time = base_time + timedelta(milliseconds=1000)
        metrics.latency_ms = 1000
        metrics.status = "success"
        monitor._query_history.append(metrics)

        with patch('app.api.analytics.get_performance_monitor', return_value=monitor):
            response = client.get("/api/v1/analytics/queries/top")

            assert response.status_code == 200
            data = response.json()

            if len(data) >= 2:
                # First item should have higher or equal count
                assert data[0]["count"] >= data[1]["count"]

    def test_get_top_queries_response_structure(self, client, performance_monitor):
        """Test that top queries have correct structure"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/queries/top?limit=1")

            assert response.status_code == 200
            data = response.json()

            if len(data) > 0:
                query = data[0]
                assert "query" in query
                assert "count" in query
                assert "avg_latency_ms" in query
                assert "avg_confidence" in query


class TestClearHistory:
    """Test clear history endpoint"""

    def test_clear_history_success(self, client, performance_monitor):
        """Test successful history clearing"""
        initial_size = performance_monitor.get_history_size()

        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.post("/api/v1/analytics/queries/clear")

            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["cleared_count"] == initial_size

    def test_clear_history_empty(self, client):
        """Test clearing empty history"""
        monitor = PerformanceMonitor()

        with patch('app.api.analytics.get_performance_monitor', return_value=monitor):
            response = client.post("/api/v1/analytics/queries/clear")

            assert response.status_code == 200
            data = response.json()
            assert data["cleared_count"] == 0


class TestHealthCheck:
    """Test health check endpoint"""

    def test_analytics_health_check(self, client, performance_monitor):
        """Test analytics health check"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/health")

            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "history_size" in data
            assert "max_history" in data

    def test_analytics_health_check_status(self, client, performance_monitor):
        """Test that health check returns correct status"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            response = client.get("/api/v1/analytics/health")

            assert response.status_code == 200
            data = response.json()
            assert data["status"] in ["healthy", "unhealthy"]


class TestErrorHandling:
    """Test error handling"""

    def test_statistics_with_monitor_error(self, client):
        """Test statistics endpoint when monitor raises error"""
        def mock_error():
            raise Exception("Monitor error")

        with patch('app.api.analytics.get_performance_monitor', side_effect=mock_error):
            response = client.get("/api/v1/analytics/statistics")

            assert response.status_code == 500
            assert "Failed to retrieve statistics" in response.json()["detail"]

    def test_recent_queries_with_monitor_error(self, client):
        """Test recent queries endpoint when monitor raises error"""
        def mock_error():
            raise Exception("Monitor error")

        with patch('app.api.analytics.get_performance_monitor', side_effect=mock_error):
            response = client.get("/api/v1/analytics/queries/recent")

            assert response.status_code == 500
            assert "Failed to retrieve recent queries" in response.json()["detail"]


class TestDataModels:
    """Test data model validation"""

    def test_analytics_statistics_model(self):
        """Test AnalyticsStatistics model validation"""
        from app.api.analytics import AnalyticsStatistics

        stats = AnalyticsStatistics(
            total_queries=100,
            avg_latency_ms=1500.5,
            p50_latency_ms=1200.0,
            p95_latency_ms=2500.0,
            p99_latency_ms=3500.0,
            success_rate=0.95,
            avg_tokens_used=800.0,
            avg_sources_count=5.5,
            avg_confidence=0.85
        )

        assert stats.total_queries == 100
        assert stats.avg_latency_ms == 1500.5

    def test_query_metrics_model(self):
        """Test QueryMetrics model validation"""
        from app.api.analytics import QueryMetrics

        metrics = QueryMetrics(
            query_id="test-123",
            query="Test query",
            start_time="2024-01-01T00:00:00Z",
            end_time="2024-01-01T00:00:01Z",
            latency_ms=1000.0,
            tokens_used=500,
            sources_count=5,
            confidence=0.9,
            status="success",
            error_message=None
        )

        assert metrics.query_id == "test-123"
        assert metrics.status == "success"


class TestIntegration:
    """Integration tests for analytics dashboard"""

    def test_full_analytics_workflow(self, client, performance_monitor):
        """Test complete analytics workflow"""
        with patch('app.api.analytics.get_performance_monitor', return_value=performance_monitor):
            # Get statistics
            stats_response = client.get("/api/v1/analytics/statistics")
            assert stats_response.status_code == 200
            stats = stats_response.json()

            # Get recent queries
            queries_response = client.get("/api/v1/analytics/queries/recent?limit=5")
            assert queries_response.status_code == 200
            queries = queries_response.json()

            # Get time series
            series_response = client.get("/api/v1/analytics/queries/time-series")
            assert series_response.status_code == 200
            series = series_response.json()

            # Get top queries
            top_response = client.get("/api/v1/analytics/queries/top")
            assert top_response.status_code == 200
            top = top_response.json()

            # Verify data consistency
            assert stats["total_queries"] > 0
            assert len(queries) > 0
            assert isinstance(series, list)
            assert isinstance(top, list)

    def test_analytics_with_no_data(self, client):
        """Test analytics endpoints with empty monitor"""
        empty_monitor = PerformanceMonitor()

        with patch('app.api.analytics.get_performance_monitor', return_value=empty_monitor):
            # Statistics should return zeros
            response = client.get("/api/v1/analytics/statistics")
            assert response.status_code == 200
            data = response.json()
            assert data["total_queries"] == 0
            assert data["avg_latency_ms"] == 0.0

            # Recent queries should be empty
            response = client.get("/api/v1/analytics/queries/recent")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 0
