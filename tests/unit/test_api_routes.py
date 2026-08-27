"""
Unit tests for API routes
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.api.routes import query, health, ingest
from fastapi import FastAPI


@pytest.fixture
def client():
    """Create test client without lifespan"""
    # Create a test app without lifespan
    test_app = FastAPI()
    test_app.include_router(health.router)
    test_app.include_router(query.router, prefix="/api/v1")
    test_app.include_router(ingest.router, prefix="/api/v1")

    # Initialize app.state to simulate healthy state
    from unittest.mock import MagicMock
    test_app.state.rag_pipeline = MagicMock()
    test_app.state.initialization_error = None

    return TestClient(test_app)


class TestHealthRoutes:
    """Test health check routes"""

    def test_health_endpoint(self, client):
        """Test basic health check"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_detailed_health_check(self, client):
        """Test detailed health check endpoint"""
        response = client.get("/health/detailed")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "services" in data
        assert data["services"]["api"] == "healthy"
        assert data["services"]["vector_db"] == "healthy"
        assert data["services"]["llm"] == "healthy"


class TestQueryRoutes:
    """Test query routes"""

    def test_query_health_check(self, client):
        """Test query route health check"""
        response = client.get("/api/v1/query/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "RAG Query API"

    def test_query_endpoint_invalid_min_length(self, client):
        """Test query validation - empty query"""
        response = client.post(
            "/api/v1/query/",
            json={
                "query": "",
                "top_k": 5
            }
        )
        assert response.status_code == 422  # Validation error

    def test_query_endpoint_invalid_top_k_below_minimum(self, client):
        """Test query validation - top_k too small"""
        response = client.post(
            "/api/v1/query/",
            json={
                "query": "Test",
                "top_k": 0
            }
        )
        assert response.status_code == 422

    def test_query_endpoint_invalid_top_k_above_maximum(self, client):
        """Test query validation - top_k too large"""
        response = client.post(
            "/api/v1/query/",
            json={
                "query": "Test",
                "top_k": 25
            }
        )
        assert response.status_code == 422


class TestIngestRoutes:
    """Test document ingest routes"""

    def test_ingest_documents(self, client):
        """Test document ingest endpoint"""
        response = client.post(
            "/api/v1/ingest",
            params={"source_path": "/test/path", "collection": "test"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "documents_processed" in data

    def test_get_ingestion_status(self, client):
        """Test get ingestion status endpoint"""
        response = client.get("/api/v1/ingest/status/test-task-123")
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-123"
        assert data["status"] == "completed"


class TestAPIModels:
    """Test API data models"""

    def test_query_request_model(self):
        """Test QueryRequest model validation"""
        from app.api.routes.query import QueryRequest

        # Valid request
        req = QueryRequest(
            query="Test question",
            top_k=5,
            use_hybrid=True
        )
        assert req.query == "Test question"
        assert req.top_k == 5
        assert req.use_hybrid is True

    def test_query_request_with_optional_fields(self):
        """Test QueryRequest with optional fields"""
        from app.api.routes.query import QueryRequest

        req = QueryRequest(
            query="Test",
            collection="test-collection",
            filters={"key": "value"}
        )
        assert req.collection == "test-collection"
        assert req.filters == {"key": "value"}

    def test_batch_query_request_model(self):
        """Test BatchQueryRequest model"""
        from app.api.routes.query import BatchQueryRequest

        req = BatchQueryRequest(
            queries=["Q1", "Q2"],
            top_k=10
        )
        assert len(req.queries) == 2
        assert req.top_k == 10


def _make_retrieval_result(document: str, score: float, metadata=None):
    """Build a retrieval-result-like object matching RAGResponse structure"""
    from types import SimpleNamespace

    return SimpleNamespace(
        document=document, score=score, metadata=metadata or {}
    )


def _make_rag_response(sources, retrieval_results):
    """Build a RAGResponse-like object as returned by pipeline.query"""
    from types import SimpleNamespace

    return SimpleNamespace(
        answer="test answer",
        sources=sources,
        confidence=0.9,
        latency_ms=10,
        tokens_used=100,
        retrieval_results=retrieval_results,
    )


class TestQueryRankingIntegration:
    """Regression tests for the ranking integration in POST /query"""

    def _post_query(self, client, pipeline_result):
        from unittest.mock import MagicMock

        pipeline = MagicMock()
        pipeline.query.return_value = pipeline_result

        suggestion = MagicMock()

        with patch("app.main.get_rag_pipeline", return_value=pipeline), \
             patch("app.services.suggestion.get_suggestion_service", return_value=suggestion):
            response = client.post(
                "/api/v1/query/",
                json={"query": "company policy", "top_k": 10}
            )
        return response

    def test_query_ranking_length_mismatch_keeps_all_sources(self, client):
        """Sources longer than retrieval_results must not be silently dropped

        The old zip()-based pairing truncated to the shorter list, so
        sources without a paired retrieval result vanished from the response.
        Documents are deliberately dissimilar so promote_diversity keeps them.
        """
        sources = [
            {"document": "vacation policy", "relevance_score": 0.9},
            {"document": "security guidelines", "relevance_score": 0.8},
            {"document": "payroll calendar", "relevance_score": 0.7},
            {"document": "office floor plan", "relevance_score": 0.6},
        ]
        retrieval_results = [
            _make_retrieval_result("vacation policy content", 0.9),
            _make_retrieval_result("security guidelines content", 0.8),
        ]

        response = self._post_query(client, _make_rag_response(sources, retrieval_results))

        assert response.status_code == 200
        returned_docs = [s["document"] for s in response.json()["sources"]]
        assert len(returned_docs) == 4
        assert set(returned_docs) == {
            "vacation policy", "security guidelines",
            "payroll calendar", "office floor plan",
        }

    def test_query_ranking_aligned_lists_rank_all_sources(self, client):
        """1:1 sources/retrieval_results still returns every source, ranked"""
        sources = [
            {"document": "low result", "relevance_score": 0.2},
            {"document": "high result", "relevance_score": 0.95},
            {"document": "middle result", "relevance_score": 0.6},
        ]
        retrieval_results = [
            _make_retrieval_result("low content", 0.2),
            _make_retrieval_result("high content", 0.95),
            _make_retrieval_result("middle content", 0.6),
        ]

        response = self._post_query(client, _make_rag_response(sources, retrieval_results))

        assert response.status_code == 200
        returned_docs = [s["document"] for s in response.json()["sources"]]
        assert len(returned_docs) == 3
        assert set(returned_docs) == {"low result", "high result", "middle result"}
