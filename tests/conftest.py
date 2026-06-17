import pytest
from unittest.mock import MagicMock
import openai

@pytest.fixture(autouse=True)
def mock_openai_embeddings(monkeypatch):
    """Globally mock OpenAI embeddings for all tests"""
    mock_create = MagicMock()
    mock_create.return_value.data = [
        MagicMock(embedding=[0.1] * 1536) for _ in range(10) # Mock vector dimension 1536
    ]
    monkeypatch.setattr("openai.embeddings.create", mock_create)
    return mock_create

@pytest.fixture(autouse=True)
def mock_openai_chat(monkeypatch):
    """Globally mock OpenAI chat completions for all tests"""
    mock_create = MagicMock()
    mock_create.return_value.choices = [
        MagicMock(message=MagicMock(content="Mocked LLM response content."), finish_reason="stop")
    ]
    mock_create.return_value.usage.total_tokens = 100
    monkeypatch.setattr("openai.chat.completions.create", mock_create)
    return mock_create
