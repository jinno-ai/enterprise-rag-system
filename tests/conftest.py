import pytest
from unittest.mock import MagicMock

@pytest.fixture(autouse=True)
def mock_openai(monkeypatch):
    """Mock OpenAI globally to prevent real API calls during tests"""
    mock_client = MagicMock()

    # Mock embeddings
    mock_embeddings = MagicMock()
    mock_embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1] * 1536) for _ in range(10)]
    )
    mock_client.embeddings = mock_embeddings

    # Mock chat completions
    mock_chat = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices = [
        MagicMock(
            message=MagicMock(content="This is a mocked response."),
            finish_reason="stop"
        )
    ]
    mock_completion.usage = MagicMock(total_tokens=100)
    mock_chat.completions.create.return_value = mock_completion
    mock_client.chat = mock_chat

    monkeypatch.setattr("openai.embeddings", mock_embeddings)
    monkeypatch.setattr("openai.chat.completions", mock_chat.completions)

    return mock_client
