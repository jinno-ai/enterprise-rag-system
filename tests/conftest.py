import pytest
from unittest.mock import Mock

@pytest.fixture(autouse=True)
def mock_openai_embeddings(monkeypatch):
    """Mock OpenAI embeddings for all tests"""
    mock_response = Mock()
    mock_response.data = [Mock(embedding=[0.1] * 1536)]
    monkeypatch.setattr("openai.resources.embeddings.Embeddings.create", Mock(return_value=mock_response))

@pytest.fixture(autouse=True)
def mock_openai_chat(monkeypatch):
    """Mock OpenAI chat completions for all tests"""
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Mocked answer"), finish_reason="stop")]
    mock_response.usage = Mock(total_tokens=100)
    monkeypatch.setattr("openai.resources.chat.completions.Completions.create", Mock(return_value=mock_response))
