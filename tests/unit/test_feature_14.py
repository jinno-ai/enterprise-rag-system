"""
Unit tests for Batch Query Support (Feature 14)

Tests batch query endpoint and pipeline functionality.
Ensures multiple queries can be processed efficiently with proper error handling.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from typing import List, Dict, Any

from app.services.rag_pipeline import RAGPipeline, RAGResponse
from app.services.retrieval import RetrievalResult
from app.api.routes.query import router as query_router


@pytest.fixture
def mock_retriever():
    """Mock retriever for testing"""
    retriever = Mock()
    return retriever


@pytest.fixture
def mock_llm_response():
    """Mock LLM response"""
    return {
        'answer': 'This is a test answer based on the context.',
        'tokens_used': 100,
        'finish_reason': 'stop'
    }


@pytest.fixture
def sample_retrieval_results():
    """Sample retrieval results for testing"""
    return [
        RetrievalResult(
            document='Sample document text 1',
            score=0.85,
            metadata={'filename': 'test1.pdf', 'page': 1}
        ),
        RetrievalResult(
            document='Sample document text 2',
            score=0.75,
            metadata={'filename': 'test2.pdf', 'page': 2}
        ),
        RetrievalResult(
            document='Sample document text 3',
            score=0.65,
            metadata={'filename': 'test3.pdf', 'page': 3}
        )
    ]


@pytest.fixture
def client():
    """Create test client for API testing"""
    test_app = FastAPI()
    test_app.include_router(query_router, prefix="/api/v1")

    pipeline = Mock()

    async def mock_batch_query(questions, **kwargs):
        # Return the same number of responses as questions
        return [
            RAGResponse(
                answer=f"Answer for question {i+1}",
                sources=[],
                confidence=0.8,
                latency_ms=100,
                tokens_used=50,
                retrieval_results=[]
            )
            for i in range(len(questions))
        ]

    async def mock_query(question, **kwargs):
        return RAGResponse(
            answer="Test answer",
            sources=[],
            confidence=0.8,
            latency_ms=100,
            tokens_used=50,
            retrieval_results=[]
        )

    pipeline.query = mock_query
    pipeline.batch_query = mock_batch_query
    # Routes resolve the pipeline via request.app.state.rag_pipeline
    test_app.state.rag_pipeline = pipeline

    def mock_get_rag_pipeline():
        return pipeline

    with patch('app.main.get_rag_pipeline', mock_get_rag_pipeline):
        yield TestClient(test_app)


def configure_llm_mock(mock_openai, llm_response):
    """Point the pipeline's AsyncOpenAI client at a fake completion response"""
    response = Mock(
        choices=[Mock(message=Mock(content=llm_response['answer']))],
        usage=Mock(
            total_tokens=llm_response['tokens_used'],
            prompt_tokens=10,
            completion_tokens=10
        )
    )
    mock_openai.AsyncOpenAI.return_value.chat.completions.create = AsyncMock(
        return_value=response
    )


class TestBatchQueryPipeline:
    """Test suite for batch query pipeline functionality"""

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_basic(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results,
        mock_llm_response
    ):
        """Test basic batch query processing with multiple questions"""
        # Setup mocks
        mock_retriever.retrieve.return_value = sample_retrieval_results
        configure_llm_mock(mock_openai, mock_llm_response)

        # Create pipeline
        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        # Execute batch query
        questions = ["What is AI?", "Explain machine learning", "What is deep learning?"]
        responses = await pipeline.batch_query(questions)

        # Assertions
        assert len(responses) == 3
        assert all(isinstance(r, RAGResponse) for r in responses)
        assert all(r.answer == mock_llm_response['answer'] for r in responses)
        assert mock_retriever.retrieve.call_count == 3

    async def test_batch_query_empty_list(self, mock_retriever):
        """Test batch query with empty question list"""
        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        responses = await pipeline.batch_query([])

        assert responses == []
        mock_retriever.retrieve.assert_not_called()

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_single_question(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results,
        mock_llm_response
    ):
        """Test batch query with single question (edge case)"""
        mock_retriever.retrieve.return_value = sample_retrieval_results
        configure_llm_mock(mock_openai, mock_llm_response)

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        responses = await pipeline.batch_query(["Single question?"])

        assert len(responses) == 1
        assert isinstance(responses[0], RAGResponse)

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_with_no_results(
        self,
        mock_openai,
        mock_retriever
    ):
        """Test batch query when some questions return no results"""
        mock_retriever.retrieve.return_value = []

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        questions = ["Question 1?", "Question 2?", "Question 3?"]
        responses = await pipeline.batch_query(questions)

        assert len(responses) == 3
        assert all("couldn't find any relevant information" in r.answer.lower() for r in responses)
        assert all(r.confidence == 0.0 for r in responses)

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_with_error_handling(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results
    ):
        """Test batch query handles individual query errors gracefully"""
        # First query succeeds, second fails, third succeeds
        call_count = [0]

        async def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise Exception("Simulated LLM error")
            return Mock(
                choices=[Mock(message=Mock(content="Success answer"))],
                usage=Mock(total_tokens=100, prompt_tokens=10, completion_tokens=10)
            )

        mock_openai.AsyncOpenAI.return_value.chat.completions.create = AsyncMock(side_effect=side_effect)
        mock_retriever.retrieve.return_value = sample_retrieval_results

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        questions = ["Question 1?", "Question 2?", "Question 3?"]
        responses = await pipeline.batch_query(questions)

        assert len(responses) == 3
        assert responses[0].answer == "Success answer"
        assert "Error" in responses[1].answer
        assert responses[2].answer == "Success answer"

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_with_different_top_k(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results,
        mock_llm_response
    ):
        """Test batch query with different top_k values"""
        mock_retriever.retrieve.return_value = sample_retrieval_results
        configure_llm_mock(mock_openai, mock_llm_response)

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        questions = ["Q1?", "Q2?", "Q3?"]
        responses = await pipeline.batch_query(questions, top_k=10)

        assert len(responses) == 3
        # Verify retriever was called with correct top_k
        for call in mock_retriever.retrieve.call_args_list:
            assert call.kwargs.get('top_k') == 10

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_with_hybrid_search(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results,
        mock_llm_response
    ):
        """Test batch query with hybrid search enabled/disabled"""
        mock_retriever.retrieve.return_value = sample_retrieval_results
        configure_llm_mock(mock_openai, mock_llm_response)

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        questions = ["Q1?", "Q2?"]
        responses = await pipeline.batch_query(questions, use_hybrid=False)

        assert len(responses) == 2
        # Verify retriever was called with use_hybrid=False
        for call in mock_retriever.retrieve.call_args_list:
            assert call.kwargs.get('use_hybrid') is False

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_response_metadata(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results,
        mock_llm_response
    ):
        """Test batch query responses include correct metadata"""
        mock_retriever.retrieve.return_value = sample_retrieval_results
        configure_llm_mock(mock_openai, mock_llm_response)

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        questions = ["Question 1?", "Question 2?"]
        responses = await pipeline.batch_query(questions)

        assert len(responses) == 2
        for response in responses:
            assert response.tokens_used > 0
            assert response.latency_ms >= 0
            assert 0 <= response.confidence <= 1
            assert len(response.sources) == len(sample_retrieval_results)

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_large_batch(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results,
        mock_llm_response
    ):
        """Test batch query with a large number of questions (performance test)"""
        mock_retriever.retrieve.return_value = sample_retrieval_results
        configure_llm_mock(mock_openai, mock_llm_response)

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        # Test with 20 questions
        questions = [f"Question {i}?" for i in range(20)]
        responses = await pipeline.batch_query(questions)

        assert len(responses) == 20
        assert all(isinstance(r, RAGResponse) for r in responses)


class TestBatchQueryAPI:
    """Test suite for batch query API endpoint"""

    def test_batch_query_endpoint_success(self, client):
        """Test batch query API endpoint with valid request"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": ["What is AI?", "Explain ML"],
                "top_k": 5
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2

    def test_batch_query_endpoint_empty_queries(self, client):
        """Test batch query API with empty query list"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": [],
                "top_k": 5
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

    def test_batch_query_endpoint_validation_invalid_top_k(self, client):
        """Test batch query API validation - invalid top_k"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": ["Question 1?"],
                "top_k": 0  # Invalid: must be >= 1
            }
        )

        assert response.status_code == 422  # Validation error

    def test_batch_query_endpoint_validation_top_k_too_large(self, client):
        """Test batch query API validation - top_k exceeds maximum"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": ["Question 1?"],
                "top_k": 25  # Invalid: must be <= 20
            }
        )

        assert response.status_code == 422  # Validation error

    def test_batch_query_endpoint_with_collection(self, client):
        """Test batch query API with collection parameter"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": ["Question 1?", "Question 2?"],
                "collection": "hr-policies",
                "top_k": 5
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_batch_query_endpoint_single_query(self, client):
        """Test batch query API with single query (edge case)"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": ["Single question?"],
                "top_k": 10
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_batch_query_request_model_validation(self):
        """Test BatchQueryRequest model validation"""
        from app.api.routes.query import BatchQueryRequest

        # Valid request
        req = BatchQueryRequest(
            queries=["Q1", "Q2", "Q3"],
            collection="test-collection",
            top_k=10
        )
        assert len(req.queries) == 3
        assert req.collection == "test-collection"
        assert req.top_k == 10

    def test_batch_query_request_defaults(self):
        """Test BatchQueryRequest default values"""
        from app.api.routes.query import BatchQueryRequest

        req = BatchQueryRequest(queries=["Q1"])
        assert req.queries == ["Q1"]
        assert req.collection is None
        assert req.top_k == 5  # Default value


class TestBatchQueryResponseFormat:
    """Test suite for batch query response formatting"""

    def test_batch_query_response_structure(self, client):
        """Test batch query response has correct structure"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": ["Test question?"],
                "top_k": 5
            }
        )

        assert response.status_code == 200
        data = response.json()

        # Should return a list
        assert isinstance(data, list)
        assert len(data) > 0

        # Each response should have required fields
        response_item = data[0]
        assert 'answer' in response_item
        assert 'sources' in response_item
        assert 'confidence' in response_item
        assert 'latency_ms' in response_item
        assert 'tokens_used' in response_item

    def test_batch_query_response_types(self, client):
        """Test batch query response field types"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": ["Test question?"],
                "top_k": 5
            }
        )

        assert response.status_code == 200
        data = response.json()
        response_item = data[0]

        assert isinstance(response_item['answer'], str)
        assert isinstance(response_item['sources'], list)
        assert isinstance(response_item['confidence'], (int, float))
        assert isinstance(response_item['latency_ms'], int)
        assert isinstance(response_item['tokens_used'], int)

    def test_batch_query_confidence_range(self, client):
        """Test confidence scores are in valid range"""
        response = client.post(
            "/api/v1/query/batch",
            json={
                "queries": ["Test question?"],
                "top_k": 5
            }
        )

        assert response.status_code == 200
        data = response.json()
        response_item = data[0]

        confidence = response_item['confidence']
        assert 0 <= confidence <= 1


class TestBatchQueryPerformance:
    """Test suite for batch query performance characteristics"""

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_vs_individual_queries(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results,
        mock_llm_response
    ):
        """Compare batch query efficiency vs individual queries"""
        mock_retriever.retrieve.return_value = sample_retrieval_results
        configure_llm_mock(mock_openai, mock_llm_response)

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        questions = ["Q1?", "Q2?", "Q3?"]

        # Batch query
        batch_responses = await pipeline.batch_query(questions)

        # Individual query
        individual_responses = [await pipeline.query(q) for q in questions]

        # Both should complete successfully with same results
        assert len(batch_responses) == len(individual_responses)
        assert len(batch_responses) == 3
        assert all(isinstance(r, RAGResponse) for r in batch_responses)
        assert all(isinstance(r, RAGResponse) for r in individual_responses)

    @patch('app.services.rag_pipeline.openai')
    async def test_batch_query_memory_efficiency(
        self,
        mock_openai,
        mock_retriever,
        sample_retrieval_results,
        mock_llm_response
    ):
        """Test batch query doesn't leak memory or accumulate state"""
        mock_retriever.retrieve.return_value = sample_retrieval_results
        configure_llm_mock(mock_openai, mock_llm_response)

        pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

        # Run multiple batches
        for _ in range(5):
            questions = [f"Question {i}?" for i in range(10)]
            responses = await pipeline.batch_query(questions)
            assert len(responses) == 10

        # Verify retriever call count matches expected
        assert mock_retriever.retrieve.call_count == 50  # 5 batches * 10 questions
