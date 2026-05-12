import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    with patch("openai.resources.embeddings.Embeddings.create") as mock_embed_create, \
         patch("openai.resources.chat.completions.Completions.create") as mock_chat_create:

        # Mock Embeddings
        mock_embed_response = MagicMock()
        mock_embed_response.data = [
            MagicMock(embedding=[0.1] * 1536) for _ in range(10)
        ]
        mock_embed_create.return_value = mock_embed_response

        # Mock Chat
        mock_chat_response = MagicMock()
        mock_chat_response.choices = [
            MagicMock(message=MagicMock(content="Mocked LLM response"), finish_reason="stop")
        ]
        mock_chat_response.usage = MagicMock(total_tokens=100)
        mock_chat_create.return_value = mock_chat_response

        yield mock_embed_create, mock_chat_create

@pytest.fixture(autouse=True)
def mock_settings_env_vars(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-dummy")
    monkeypatch.setenv("COHERE_API_KEY", "sk-dummy")
