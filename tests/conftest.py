import pytest
from unittest.mock import MagicMock

@pytest.fixture
def mock_openai_embeddings(mocker):
    """Mock OpenAI embeddings for tests"""
    mock_create = mocker.patch("openai.resources.embeddings.Embeddings.create")
    mock_response = MagicMock()
    mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
    mock_create.return_value = mock_response
    return mock_create

@pytest.fixture
def mock_openai_chat(mocker):
    """Mock OpenAI chat completions for tests"""
    mock_create = mocker.patch("openai.resources.chat.completions.Completions.create")
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Mocked response"))]
    mock_response.usage.total_tokens = 100
    mock_create.return_value = mock_response
    return mock_create
