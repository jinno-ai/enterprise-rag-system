import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI services globally for tests"""
    with patch("openai.embeddings.create") as mock_embeddings, \
         patch("openai.chat.completions.create") as mock_chat:

        # Mock embeddings response
        mock_embeddings.return_value.data = [
            MagicMock(embedding=[0.1] * 1536)
        ]

        # Mock chat completion response
        mock_chat.return_value.choices = [
            MagicMock(message=MagicMock(content="Mocked answer"))
        ]
        mock_chat.return_value.usage.total_tokens = 50

        yield

@pytest.fixture(autouse=True)
def mock_settings_env_vars(monkeypatch):
    """Ensure dummy API keys are used in all tests"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
