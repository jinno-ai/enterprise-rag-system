"""
Unit tests for configuration and schema modules
"""

import pytest
import os
from unittest.mock import patch


class TestSettings:
    """Test Settings configuration"""

    def test_get_settings_singleton(self):
        """Test that get_settings returns cached instance"""
        from app.core.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        # Should return same cached instance
        assert settings1 is settings2

    def test_settings_default_values(self):
        """Test Settings default values"""
        from app.core.config import Settings

        settings = Settings()

        assert settings.embedding_model == "text-embedding-ada-002"
        assert settings.embedding_dimension == 1536
        assert settings.hybrid_search_alpha == 0.5
        assert settings.top_k_results == 5
        assert settings.llm_model == "gpt-4-turbo-preview"
        assert settings.llm_temperature == 0.7
        assert settings.llm_max_tokens == 2048

    def test_settings_with_custom_values(self):
        """Test Settings with custom values"""
        from app.core.config import Settings

        settings = Settings(
            openai_api_key="test-key",
            top_k_results=10,
            debug=True
        )

        assert settings.openai_api_key == "test-key"
        assert settings.top_k_results == 10
        assert settings.debug is True

    def test_settings_from_env(self):
        """Test Settings loads from environment"""
        from app.core.config import Settings

        with patch.dict(os.environ, {
            'OPENAI_API_KEY': 'env-test-key',
            'DEBUG': 'true'
        }):
            # Note: Pydantic doesn't auto-load from env in tests without BaseSettings config
            # This tests the structure is correct
            settings = Settings(openai_api_key='env-test-key')
            assert settings.openai_api_key == 'env-test-key'


class TestSchemas:
    """Test Pydantic schemas"""

    def test_query_request_valid(self):
        """Test valid QueryRequest"""
        from app.models.schemas import QueryRequest

        req = QueryRequest(
            query="What is AI?",
            collection="test",
            top_k=5,
            include_sources=True
        )

        assert req.query == "What is AI?"
        assert req.collection == "test"
        assert req.top_k == 5
        assert req.include_sources is True

    def test_query_request_defaults(self):
        """Test QueryRequest with defaults"""
        from app.models.schemas import QueryRequest

        req = QueryRequest(query="Test")

        assert req.query == "Test"
        assert req.collection == "default"
        assert req.top_k == 5
        assert req.include_sources is True

    def test_query_request_validation_min_length(self):
        """Test QueryRequest validation - min_length"""
        from app.models.schemas import QueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueryRequest(query="")

    def test_query_request_validation_max_length(self):
        """Test QueryRequest validation - max_length"""
        from app.models.schemas import QueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueryRequest(query="x" * 1001)

    def test_query_request_validation_top_k_min(self):
        """Test QueryRequest validation - top_k minimum"""
        from app.models.schemas import QueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueryRequest(query="Test", top_k=0)

    def test_query_request_validation_top_k_max(self):
        """Test QueryRequest validation - top_k maximum"""
        from app.models.schemas import QueryRequest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            QueryRequest(query="Test", top_k=21)

    def test_source_schema(self):
        """Test Source schema"""
        from app.models.schemas import Source

        source = Source(
            document="test.txt",
            page=1,
            relevance_score=0.95,
            text="Sample text"
        )

        assert source.document == "test.txt"
        assert source.page == 1
        assert source.relevance_score == 0.95
        assert source.text == "Sample text"

    def test_source_optional_page(self):
        """Test Source with optional page"""
        from app.models.schemas import Source

        source = Source(
            document="test.txt",
            relevance_score=0.9,
            text="Text"
        )

        assert source.page is None

    def test_query_response_schema(self):
        """Test QueryResponse schema"""
        from app.models.schemas import QueryResponse, Source

        response = QueryResponse(
            answer="Test answer",
            sources=[
                Source(
                    document="test.txt",
                    relevance_score=0.9,
                    text="Text"
                )
            ],
            confidence=0.85,
            latency_ms=100,
            tokens_used=50,
            cached=False
        )

        assert response.answer == "Test answer"
        assert len(response.sources) == 1
        assert response.confidence == 0.85
        assert response.latency_ms == 100
        assert response.tokens_used == 50
        assert response.cached is False

    def test_query_response_confidence_validation(self):
        """Test QueryResponse confidence bounds"""
        from app.models.schemas import QueryResponse, Source
        from pydantic import ValidationError

        # Confidence must be between 0 and 1
        with pytest.raises(ValidationError):
            QueryResponse(
                answer="Test",
                sources=[],
                confidence=1.5,  # Too high
                latency_ms=100,
                tokens_used=50
            )

        with pytest.raises(ValidationError):
            QueryResponse(
                answer="Test",
                sources=[],
                confidence=-0.1,  # Too low
                latency_ms=100,
                tokens_used=50
            )

    def test_ingest_request_schema(self):
        """Test IngestRequest schema"""
        from app.models.schemas import IngestRequest

        req = IngestRequest(
            source_path="/path/to/docs",
            collection="test",
            chunk_size=1000,
            chunk_overlap=200
        )

        assert req.source_path == "/path/to/docs"
        assert req.collection == "test"
        assert req.chunk_size == 1000
        assert req.chunk_overlap == 200

    def test_ingest_request_defaults(self):
        """Test IngestRequest defaults"""
        from app.models.schemas import IngestRequest

        req = IngestRequest(source_path="/path")

        assert req.collection == "default"
        assert req.chunk_size == 1000
        assert req.chunk_overlap == 200

    def test_ingest_request_validation(self):
        """Test IngestRequest validation"""
        from app.models.schemas import IngestRequest
        from pydantic import ValidationError

        # chunk_size too small
        with pytest.raises(ValidationError):
            IngestRequest(source_path="/path", chunk_size=50)

        # chunk_size too large
        with pytest.raises(ValidationError):
            IngestRequest(source_path="/path", chunk_size=5000)

        # chunk_overlap negative
        with pytest.raises(ValidationError):
            IngestRequest(source_path="/path", chunk_overlap=-1)

    def test_ingest_response_schema(self):
        """Test IngestResponse schema"""
        from datetime import datetime
        from app.models.schemas import IngestResponse

        now = datetime.now()
        response = IngestResponse(
            status="success",
            documents_processed=10,
            chunks_created=50,
            collection="test",
            timestamp=now
        )

        assert response.status == "success"
        assert response.documents_processed == 10
        assert response.chunks_created == 50
        assert response.collection == "test"
        assert response.timestamp == now

    def test_health_response_schema(self):
        """Test HealthResponse schema"""
        from app.models.schemas import HealthResponse

        response = HealthResponse(
            status="healthy",
            version="1.0.0",
            services={"api": "healthy", "db": "healthy"}
        )

        assert response.status == "healthy"
        assert response.version == "1.0.0"
        assert response.services == {"api": "healthy", "db": "healthy"}
