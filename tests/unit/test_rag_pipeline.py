import pytest
from unittest.mock import Mock, patch
from app.services.rag_pipeline import RAGPipeline, RAGResponse
from app.services.retrieval import RetrievalResult


@pytest.fixture
def mock_retriever():
    return Mock()


@pytest.fixture
def sample_retrieval_results():
    return [
        RetrievalResult(
            document="Sample document text 1",
            score=0.85,
            metadata={"filename": "test1.pdf", "page": 1}
        ),
        RetrievalResult(
            document="Sample document text 2",
            score=0.75,
            metadata={"filename": "test2.pdf", "page": 2}
        )
    ]


@pytest.fixture
def mock_llm_response():
    return {
        "answer": "This is a test answer based on the context.",
        "tokens_used": 100,
        "finish_reason": "stop"
    }


def test_rag_pipeline_init(mock_retriever):
    """Test RAG pipeline initialization"""
    pipeline = RAGPipeline(
        retriever=mock_retriever,
        llm_model="gpt-3.5-turbo",
        temperature=0.5
    )
    assert pipeline.retriever == mock_retriever
    assert pipeline.llm_model == "gpt-3.5-turbo"
    assert pipeline.temperature == 0.5


def test_calculate_confidence(mock_retriever, sample_retrieval_results):
    """Test confidence score calculation"""
    pipeline = RAGPipeline(retriever=mock_retriever)

    # Test with high quality results
    confidence = pipeline._calculate_confidence(sample_retrieval_results, "A relatively long answer that should satisfy the length factor.")
    assert 0.5 < confidence <= 1.0

    # Test with no results
    assert pipeline._calculate_confidence([], "Answer") == 0.0


@patch('app.services.rag_pipeline.openai')
@patch('time.time', side_effect=[1000.0, 1000.1, 1000.2, 1000.3])
def test_rag_pipeline_query(mock_time, mock_openai, mock_retriever, sample_retrieval_results, mock_llm_response):
    """Test RAG pipeline query"""
    # Setup mocks
    mock_retriever.retrieve.return_value = sample_retrieval_results
    mock_openai.chat.completions.create.return_value.choices = [
        Mock(message=Mock(content=mock_llm_response['answer']))
    ]
    mock_openai.chat.completions.create.return_value.usage.total_tokens = mock_llm_response['tokens_used']

    # Create pipeline
    pipeline = RAGPipeline(
        retriever=mock_retriever,
        llm_model='gpt-4'
    )

    # Run query
    response = pipeline.query("What is the test question?")

    # Assertions
    assert isinstance(response, RAGResponse)
    assert response.answer == mock_llm_response['answer']
    assert response.confidence > 0
    assert len(response.sources) == 2
    assert response.latency_ms > 0


@patch('app.services.rag_pipeline.openai')
def test_rag_pipeline_batch_query(mock_openai, mock_retriever, sample_retrieval_results, mock_llm_response):
    """Test batch query processing"""
    # Setup mocks
    mock_retriever.retrieve.return_value = sample_retrieval_results
    mock_openai.chat.completions.create.return_value.choices = [
        Mock(message=Mock(content=mock_llm_response['answer']))
    ]
    mock_openai.chat.completions.create.return_value.usage.total_tokens = mock_llm_response['tokens_used']

    # Create pipeline
    pipeline = RAGPipeline(retriever=mock_retriever)

    # Run batch query
    questions = ["Question 1?", "Question 2?"]
    responses = pipeline.batch_query(questions)

    # Assertions
    assert len(responses) == 2
    assert all(isinstance(r, RAGResponse) for r in responses)
    assert responses[0].answer == mock_llm_response['answer']
