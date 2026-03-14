"""
Unit tests for Response Streaming (Feature 16)

Tests Server-Sent Events (SSE) streaming functionality for RAG query responses.
Ensures streaming works correctly with proper chunk formatting, error handling,
and backward compatibility.
"""

import pytest
import json
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from app.services.streaming import (
    StreamChunk,
    StreamingResponseGenerator,
    create_streaming_response
)
from app.services.rag_pipeline import RAGPipeline, RAGResponse
from app.services.retrieval import RetrievalResult
from app.api.routes.query import router as query_router


# ==================== Fixtures ====================

@pytest.fixture
def mock_retriever():
    """Mock retriever for testing"""
    retriever = Mock()
    return retriever


@pytest.fixture
def sample_retrieval_results():
    """Sample retrieval results for testing"""
    return [
        RetrievalResult(
            document='Sample document text about company policies. This document contains remote work guidelines.',
            score=0.85,
            metadata={'filename': 'hr_policy.pdf', 'page': 1}
        ),
        RetrievalResult(
            document='Another document with additional information about benefits and compensation.',
            score=0.75,
            metadata={'filename': 'benefits.pdf', 'page': 2}
        ),
        RetrievalResult(
            document='Third document containing technical specifications and system requirements.',
            score=0.65,
            metadata={'filename': 'tech_spec.pdf', 'page': 3}
        )
    ]


@pytest.fixture
def mock_pipeline(sample_retrieval_results):
    """Mock RAG pipeline for testing"""
    from app.services.retrieval import HybridRetriever, ContextCompressor

    # Create a real RAGPipeline but mock its dependencies
    retriever = Mock(spec=HybridRetriever)
    retriever.retrieve = Mock(return_value=sample_retrieval_results)

    compressor = Mock(spec=ContextCompressor)
    compressor.compress = Mock(return_value="Compressed context text")

    # Create pipeline with mocked dependencies
    pipeline = RAGPipeline(
        retriever=retriever,
        llm_model="gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=2048
    )

    # Mock compressor
    pipeline.compressor.compress = Mock(return_value="Compressed context text")

    # Mock _build_prompt
    pipeline._build_prompt = Mock(return_value="Test prompt")

    # Mock _call_llm
    pipeline._call_llm = Mock(return_value={
        'answer': 'This is a comprehensive test answer about the query that demonstrates streaming capability.',
        'tokens_used': 150,
        'finish_reason': 'stop'
    })

    # Mock _calculate_confidence
    pipeline._calculate_confidence = Mock(return_value=0.85)

    return pipeline


@pytest.fixture
def client(mock_pipeline):
    """Create test client for API testing"""
    test_app = FastAPI()
    test_app.include_router(query_router, prefix="/api/v1")

    def mock_get_rag_pipeline():
        return mock_pipeline

    with patch('app.main.get_rag_pipeline', mock_get_rag_pipeline):
        yield TestClient(test_app)


# ==================== StreamChunk Tests ====================

class TestStreamChunk:
    """Test suite for StreamChunk data model"""

    def test_stream_chunk_creation(self):
        """Test creating a basic stream chunk"""
        chunk = StreamChunk(type="generation", content="Hello world")

        assert chunk.type == "generation"
        assert chunk.content == "Hello world"
        assert chunk.data is None

    def test_stream_chunk_with_data(self):
        """Test stream chunk with data field"""
        chunk = StreamChunk(
            type="metadata",
            data={"confidence": 0.85, "tokens": 150}
        )

        assert chunk.type == "metadata"
        assert chunk.content is None
        assert chunk.data == {"confidence": 0.85, "tokens": 150}

    def test_stream_chunk_to_sse_generation(self):
        """Test SSE conversion for generation chunk"""
        chunk = StreamChunk(type="generation", content="Hello")

        sse = chunk.to_sse()

        assert sse.startswith("data: ")
        assert "\n\n" in sse

        # Parse and verify JSON
        data_start = sse.index("data: ") + 6
        data_end = sse.index("\n\n")
        json_data = json.loads(sse[data_start:data_end])

        assert json_data["type"] == "generation"
        assert json_data["content"] == "Hello"
        assert "data" not in json_data  # None values removed

    def test_stream_chunk_to_sse_retrieval(self):
        """Test SSE conversion for retrieval chunk"""
        chunk = StreamChunk(
            type="retrieval",
            data={"count": 3, "sources": []}
        )

        sse = chunk.to_sse()

        data_start = sse.index("data: ") + 6
        data_end = sse.index("\n\n")
        json_data = json.loads(sse[data_start:data_end])

        assert json_data["type"] == "retrieval"
        assert json_data["data"]["count"] == 3
        assert "content" not in json_data  # None values removed

    def test_stream_chunk_to_sse_done(self):
        """Test SSE conversion for done signal"""
        chunk = StreamChunk(type="done")

        sse = chunk.to_sse()

        data_start = sse.index("data: ") + 6
        data_end = sse.index("\n\n")
        json_data = json.loads(sse[data_start:data_end])

        assert json_data["type"] == "done"
        assert "content" not in json_data
        assert "data" not in json_data


# ==================== StreamingResponseGenerator Tests ====================

class TestStreamingResponseGenerator:
    """Test suite for StreamingResponseGenerator"""

    @pytest.mark.asyncio
    async def test_stream_response_retrieval_stage(self, mock_pipeline, sample_retrieval_results):
        """Test retrieval stage of streaming response"""
        generator = StreamingResponseGenerator(
            pipeline=mock_pipeline,
            query="Test query",
            top_k=3,
            use_hybrid=True
        )

        chunks = []
        async for chunk in generator.stream_response():
            chunks.append(chunk)
            # Break after retrieval to test first stage
            if '"type": "retrieval"' in chunk:
                break

        # Should have status and retrieval chunks
        assert len(chunks) >= 2
        assert any('"type": "status"' in c for c in chunks)
        assert any('"type": "retrieval"' in c for c in chunks)

        # Verify retrieval data
        retrieval_chunk = next(c for c in chunks if '"type": "retrieval"' in c)
        data_start = retrieval_chunk.index("data: ") + 6
        data_end = retrieval_chunk.index("\n\n")
        retrieval_data = json.loads(retrieval_chunk[data_start:data_end])

        assert retrieval_data["data"]["count"] == 3
        assert len(retrieval_data["data"]["sources"]) == 3

    @pytest.mark.asyncio
    async def test_stream_response_complete_flow(self, mock_pipeline):
        """Test complete streaming flow"""
        generator = StreamingResponseGenerator(
            pipeline=mock_pipeline,
            query="Test query",
            top_k=3,
            enable_token_streaming=False  # Disable token streaming for faster test
        )

        chunks = []
        async for chunk in generator.stream_response():
            chunks.append(chunk)

        # Should have: status, retrieval, status, generation, metadata, done
        assert len(chunks) >= 5

        chunk_types = []
        for chunk in chunks:
            if '"type":' in chunk:
                try:
                    data_start = chunk.index("data: ") + 6
                    data_end = chunk.index("\n\n")
                    chunk_data = json.loads(chunk[data_start:data_end])
                    chunk_types.append(chunk_data["type"])
                except:
                    pass

        assert "status" in chunk_types
        assert "retrieval" in chunk_types
        assert "generation" in chunk_types
        assert "metadata" in chunk_types
        assert "done" in chunk_types

    @pytest.mark.asyncio
    async def test_stream_response_with_token_streaming(self, mock_pipeline):
        """Test streaming with token-level streaming enabled"""
        # Mock the _call_llm_streaming method to simulate OpenAI streaming
        mock_stream_result = []

        def mock_streaming_call(prompt):
            """Create a mock OpenAI streaming response"""
            class MockChunk:
                def __init__(self, content):
                    self.choices = [MockDelta(content)]

            class MockDelta:
                def __init__(self, content):
                    self.content = content
                    self.delta = self

            class MockStream:
                def __init__(self):
                    self.chunks = [
                        MockChunk("This "),
                        MockChunk("is "),
                        MockChunk("a "),
                        MockChunk("test "),
                        MockChunk("answer.")
                    ]
                    self.usage = Mock()
                    self.usage.total_tokens = 100

                def __iter__(self):
                    return iter(self.chunks)

            return MockStream()

        mock_pipeline._call_llm_streaming = mock_streaming_call

        generator = StreamingResponseGenerator(
            pipeline=mock_pipeline,
            query="Test query",
            top_k=3,
            enable_token_streaming=True
        )

        chunks = []
        async for chunk in generator.stream_response():
            chunks.append(chunk)

        # With token streaming, should have multiple generation chunks
        generation_chunks = [c for c in chunks if '"type": "generation"' in c]

        # Should have multiple generation chunks due to token streaming
        assert len(generation_chunks) >= 5  # "This ", "is ", "a ", "test ", "answer."

    @pytest.mark.asyncio
    async def test_stream_response_error_handling(self, mock_pipeline):
        """Test error handling in streaming response"""
        # Make retriever raise an error
        mock_pipeline.retriever.retrieve = Mock(side_effect=Exception("Retrieval failed"))

        generator = StreamingResponseGenerator(
            pipeline=mock_pipeline,
            query="Test query",
            top_k=3
        )

        chunks = []
        async for chunk in generator.stream_response():
            chunks.append(chunk)

        # Should have an error chunk
        error_chunks = [c for c in chunks if '"type": "error"' in c]
        assert len(error_chunks) > 0

        error_chunk = error_chunks[0]
        data_start = error_chunk.index("data: ") + 6
        data_end = error_chunk.index("\n\n")
        error_data = json.loads(error_chunk[data_start:data_end])

        assert "Retrieval failed" in error_data["content"]

    @pytest.mark.asyncio
    async def test_stream_response_with_filters(self, mock_pipeline):
        """Test streaming with metadata filters"""
        generator = StreamingResponseGenerator(
            pipeline=mock_pipeline,
            query="Test query",
            top_k=5,
            filter_dict={"category": "hr", "year": 2024}
        )

        chunks = []
        async for chunk in generator.stream_response():
            chunks.append(chunk)
            if '"type": "retrieval"' in chunk:
                break

        # Verify retriever was called with filters
        mock_pipeline.retriever.retrieve.assert_called_once()
        call_args = mock_pipeline.retriever.retrieve.call_args

        assert call_args.kwargs['filter_dict'] == {"category": "hr", "year": 2024}


# ==================== Factory Function Tests ====================

class TestCreateStreamingResponse:
    """Test suite for create_streaming_response factory function"""

    @pytest.mark.asyncio
    async def test_factory_function(self, mock_pipeline):
        """Test factory function creates correct generator"""
        stream = create_streaming_response(
            pipeline=mock_pipeline,
            query="Test query",
            top_k=3,
            use_hybrid=True
        )

        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
            if len(chunks) >= 3:  # Collect a few chunks
                break

        assert len(chunks) >= 3
        assert all("data: " in c for c in chunks)
        assert all("\n\n" in c for c in chunks)

    @pytest.mark.asyncio
    async def test_factory_function_default_parameters(self, mock_pipeline):
        """Test factory function with default parameters"""
        stream = create_streaming_response(
            pipeline=mock_pipeline,
            query="Test query"
        )

        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
            if len(chunks) >= 2:
                break

        assert len(chunks) >= 2


# ==================== API Endpoint Tests ====================

class TestStreamingAPIEndpoint:
    """Test suite for streaming API endpoint"""

    def test_stream_query_endpoint_exists(self, client):
        """Test that streaming endpoint is registered"""
        # This test verifies the endpoint exists
        response = client.post(
            "/api/v1/query/stream",
            json={"query": "test"}
        )

        # Should either work (200) or be a valid FastAPI response (not 404)
        assert response.status_code != 404

    def test_stream_query_validation_valid_request(self, client):
        """Test streaming endpoint with valid request"""
        response = client.post(
            "/api/v1/query/stream",
            json={
                "query": "What is the company policy?",
                "top_k": 5,
                "use_hybrid": True
            }
        )

        # Streaming responses should return 200
        assert response.status_code == 200

        # Verify content-type is SSE
        assert "text/event-stream" in response.headers.get("content-type", "")

        # Verify streaming headers
        assert response.headers.get("Cache-Control") == "no-cache"
        assert response.headers.get("Connection") == "keep-alive"

    def test_stream_query_validation_empty_query(self, client):
        """Test streaming endpoint validation - empty query"""
        response = client.post(
            "/api/v1/query/stream",
            json={"query": "", "top_k": 5}
        )

        # Should return validation error
        assert response.status_code == 422

    def test_stream_query_validation_invalid_top_k(self, client):
        """Test streaming endpoint validation - top_k out of range"""
        response = client.post(
            "/api/v1/query/stream",
            json={"query": "Test", "top_k": 25}
        )

        # Should return validation error
        assert response.status_code == 422

    def test_stream_query_with_filters(self, client):
        """Test streaming endpoint with metadata filters"""
        response = client.post(
            "/api/v1/query/stream",
            json={
                "query": "Test query",
                "filters": {"category": "hr", "year": 2024}
            }
        )

        assert response.status_code == 200

    def test_stream_query_consumes_stream(self, client):
        """Test that streaming response can be consumed"""
        response = client.post(
            "/api/v1/query/stream",
            json={"query": "Test query", "top_k": 3},
            headers={"Accept": "text/event-stream"}
        )

        assert response.status_code == 200

        # Try to consume some of the stream
        content = response.content.decode('utf-8')

        # Should contain SSE markers
        assert "data: " in content
        assert "\n\n" in content

        # Should contain chunk types
        assert '"type"' in content


# ==================== Backward Compatibility Tests ====================

class TestBackwardCompatibility:
    """Test suite for ensuring backward compatibility"""

    def test_non_streaming_endpoint_still_works(self, client):
        """Test that non-streaming endpoint still functions"""
        # Mock the query method
        def mock_query_impl(question, **kwargs):
            return RAGResponse(
                answer="Test answer",
                sources=[],
                confidence=0.8,
                latency_ms=100,
                tokens_used=50,
                retrieval_results=[]
            )

        from app.main import get_rag_pipeline
        pipeline = get_rag_pipeline()
        pipeline.query = mock_query_impl

        response = client.post(
            "/api/v1/query/",
            json={"query": "Test query"}
        )

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "confidence" in data

    def test_batch_query_still_works(self, client):
        """Test that batch query endpoint still functions"""
        def mock_batch_query(questions, **kwargs):
            return [
                RAGResponse(
                    answer=f"Answer to {q}",
                    sources=[],
                    confidence=0.8,
                    latency_ms=100,
                    tokens_used=50,
                    retrieval_results=[]
                )
                for q in questions
            ]

        from app.main import get_rag_pipeline
        pipeline = get_rag_pipeline()
        pipeline.batch_query = mock_batch_query

        response = client.post(
            "/api/v1/query/batch",
            json={"queries": ["Q1", "Q2"]}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


# ==================== Edge Cases Tests ====================

class TestEdgeCases:
    """Test suite for edge cases and error scenarios"""

    @pytest.mark.asyncio
    async def test_empty_retrieval_results(self, mock_pipeline):
        """Test streaming when no documents are retrieved"""
        mock_pipeline.retriever.retrieve = Mock(return_value=[])

        generator = StreamingResponseGenerator(
            pipeline=mock_pipeline,
            query="Test query",
            top_k=3
        )

        chunks = []
        async for chunk in generator.stream_response():
            chunks.append(chunk)

        # Should still complete successfully
        assert any('"type": "done"' in c for c in chunks)

    @pytest.mark.asyncio
    async def test_very_long_answer(self, mock_pipeline):
        """Test streaming with a very long generated answer"""
        long_answer = "This is a test answer. " * 50  # Create a long answer

        mock_pipeline._call_llm = Mock(return_value={
            'answer': long_answer,
            'tokens_used': 500,
            'finish_reason': 'stop'
        })

        generator = StreamingResponseGenerator(
            pipeline=mock_pipeline,
            query="Test query",
            top_k=3,
            enable_token_streaming=True
        )

        chunks = []
        async for chunk in generator.stream_response():
            chunks.append(chunk)

        # Should complete without errors
        assert any('"type": "done"' in c for c in chunks)

    @pytest.mark.asyncio
    async def test_concurrent_streams(self, mock_pipeline):
        """Test multiple concurrent streaming requests"""
        async def run_stream(query_id):
            generator = StreamingResponseGenerator(
                pipeline=mock_pipeline,
                query=f"Query {query_id}",
                top_k=3,
                enable_token_streaming=False
            )

            chunks = []
            async for chunk in generator.stream_response():
                chunks.append(chunk)
            return len(chunks)

        # Run 3 concurrent streams
        results = await asyncio.gather(
            run_stream(1),
            run_stream(2),
            run_stream(3)
        )

        # All should complete
        assert all(r > 0 for r in results)


# ==================== Integration Tests ====================

class TestStreamingIntegration:
    """Integration tests for streaming functionality"""

    def test_end_to_end_streaming_flow(self, client):
        """Test complete end-to-end streaming flow"""
        response = client.post(
            "/api/v1/query/stream",
            json={
                "query": "What are the company remote work policies?",
                "top_k": 5,
                "use_hybrid": True
            }
        )

        assert response.status_code == 200

        # Parse SSE stream
        content = response.content.decode('utf-8')
        events = content.split('\n\n')

        # Filter empty events
        events = [e for e in events if e.strip()]

        # Should have multiple events
        assert len(events) >= 4

        # Verify event structure
        for event in events[:3]:  # Check first 3 events
            assert "data: " in event
            try:
                data_start = event.index("data: ") + 6
                json_data = json.loads(event[data_start:])
                assert "type" in json_data
            except (ValueError, json.JSONDecodeError):
                # Some events might be partial
                pass

    def test_stream_parsing_in_client_like_scenario(self, client):
        """Test parsing stream as a client would"""
        response = client.post(
            "/api/v1/query/stream",
            json={"query": "Test query", "top_k": 3}
        )

        assert response.status_code == 200

        # Simulate client-side parsing
        events_received = []
        content = response.content.decode('utf-8')

        for line in content.split('\n'):
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])  # Remove 'data: ' prefix
                    events_received.append(data)
                except json.JSONDecodeError:
                    pass

        # Should have received multiple events
        assert len(events_received) >= 3

        # Verify event types
        event_types = [e.get("type") for e in events_received]
        assert "status" in event_types
        assert "retrieval" in event_types or "generation" in event_types
