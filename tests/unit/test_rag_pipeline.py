import pytest
import time
from unittest.mock import Mock, MagicMock
from app.services.rag_pipeline import RAGPipeline, RAGResponse
from app.services.retrieval import RetrievalResult

@pytest.fixture
def mock_retriever():
    return Mock()

@pytest.fixture
def mock_llm_response():
    return {
        'answer': 'This is a test answer based on the context.',
        'tokens_used': 100,
        'finish_reason': 'stop'
    }

@pytest.fixture
def sample_retrieval_results():
    return [
        RetrievalResult(
            document='Sample document text 1',
            score=0.85,
            metadata={'filename': 'test1.pdf', 'page': 1},
            source='test1.pdf'
        ),
        RetrievalResult(
            document='Sample document text 2',
            score=0.75,
            metadata={'filename': 'test2.pdf', 'page': 2},
            source='test2.pdf'
        )
    ]

def test_rag_pipeline_initialization(mock_retriever):
    pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')
    assert pipeline.retriever == mock_retriever
    assert pipeline.llm_model == 'gpt-4'

def test_rag_pipeline_query(mocker, mock_retriever, sample_retrieval_results, mock_llm_response):
    # Setup mocks
    mock_time = mocker.patch('app.services.rag_pipeline.time.time')
    mock_time.side_effect = [1000.0, 1000.5]

    mock_openai = mocker.patch('app.services.rag_pipeline.openai.chat.completions.create')

    mock_retriever.retrieve.return_value = sample_retrieval_results

    mock_res = MagicMock()
    mock_res.choices = [MagicMock()]
    mock_res.choices[0].message.content = mock_llm_response['answer']
    mock_res.choices[0].finish_reason = 'stop'
    mock_res.usage.total_tokens = mock_llm_response['tokens_used']
    mock_openai.return_value = mock_res

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
    assert response.latency_ms == 500

def test_rag_pipeline_no_results(mocker, mock_retriever):
    mock_retriever.retrieve.return_value = []

    pipeline = RAGPipeline(
        retriever=mock_retriever,
        llm_model='gpt-4'
    )

    response = pipeline.query("What is the test question?")

    assert isinstance(response, RAGResponse)
    assert "couldn't find any relevant information" in response.answer.lower()
    assert response.confidence == 0.0
    assert len(response.sources) == 0

def test_rag_pipeline_batch_query(mocker, mock_retriever, sample_retrieval_results):
    mock_retriever.retrieve.return_value = sample_retrieval_results
    pipeline = RAGPipeline(retriever=mock_retriever, llm_model='gpt-4')

    # Mocking query to avoid internal logic and OpenAI calls
    mocker.patch.object(RAGPipeline, 'query', return_value=RAGResponse(answer="Mocked Answer", sources=[], confidence=1.0, latency_ms=10, tokens_used=10, retrieval_results=[]))

    questions = ["Question 1?", "Question 2?"]
    responses = pipeline.batch_query(questions)

    assert len(responses) == 2
    assert responses[0].answer == "Mocked Answer"

def test_confidence_calculation(mock_retriever, sample_retrieval_results):
    pipeline = RAGPipeline(
        retriever=mock_retriever,
        llm_model='gpt-4'
    )

    confidence = pipeline._calculate_confidence(
        sample_retrieval_results,
        "This is a reasonable test answer with enough length to be valid."
    )

    assert 0 <= confidence <= 1.0

def test_prompt_building():
    pipeline = RAGPipeline(
        retriever=Mock(),
        llm_model='gpt-4'
    )

    prompt = pipeline._build_prompt(
        "What is AI?",
        "AI stands for Artificial Intelligence."
    )

    assert "What is AI?" in prompt
    assert "AI stands for Artificial Intelligence." in prompt
