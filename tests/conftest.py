import pytest
from unittest.mock import MagicMock

@pytest.fixture(autouse=True)
def mock_openai(monkeypatch):
    mock_client = MagicMock()

    # Mock Chat Completions
    mock_chat = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "This is a mocked response."
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    mock_response.usage.total_tokens = 100
    mock_chat.completions.create.return_value = mock_response

    # Mock Embeddings
    mock_embeddings = MagicMock()
    mock_emb_response = MagicMock()
    mock_data = MagicMock()
    mock_data.embedding = [0.1] * 1536
    mock_emb_response.data = [mock_data]
    mock_embeddings.create.return_value = mock_emb_response

    monkeypatch.setattr("openai.chat.completions", mock_chat)
    monkeypatch.setattr("openai.embeddings", mock_embeddings)
    return mock_client
