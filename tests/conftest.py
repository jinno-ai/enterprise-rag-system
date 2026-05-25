import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    """Globally mock OpenAI embeddings for all tests"""
    with patch('app.core.embeddings.openai.embeddings.create') as mock_create:
        mock_response = Mock()
        # Mocking 1536 dimensional vector (default for text-embedding-ada-002)
        mock_response.data = [
            Mock(embedding=[0.1] * 1536)
        ]
        mock_create.return_value = mock_response
        yield mock_create

@pytest.fixture(autouse=True)
def mock_openai_chat():
    """Globally mock OpenAI chat completions for all tests"""
    with patch('app.services.rag_pipeline.openai.chat.completions.create') as mock_create:
        mock_response = Mock()
        mock_response.choices = [
            Mock(message=Mock(content="This is a mocked LLM response for testing."))
        ]
        mock_response.usage = Mock(total_tokens=100)
        mock_create.return_value = mock_response
        yield mock_create
