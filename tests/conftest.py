import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI services globally for tests"""
    with patch("openai.embeddings.create") as mock_embeddings, \
         patch("openai.chat.completions.create") as mock_chat:

        # Mock embeddings response
        mock_embedding_val = [0.1] * 1536  # Default dimension
        mock_embeddings.return_value.data = [
            MagicMock(embedding=mock_embedding_val)
        ]

        # Mock chat response
        mock_chat.return_value.choices = [
            MagicMock(message=MagicMock(content="Mocked LLM answer"))
        ]
        mock_chat.return_value.usage.total_tokens = 100

        yield {
            "embeddings": mock_embeddings,
            "chat": mock_chat
        }

@pytest.fixture(autouse=True)
def mock_settings_env_vars(monkeypatch):
    """Ensure dummy API key is set for all tests"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
