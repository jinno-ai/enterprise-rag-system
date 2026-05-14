import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Global mock for OpenAI services to prevent real API calls in tests."""
    with patch("openai.embeddings.create") as mock_embeddings,          patch("openai.chat.completions.create") as mock_completions:

        # Mock embeddings response
        mock_embeddings.return_value = Mock(
            data=[Mock(embedding=[0.1] * 1536)]
        )

        # Mock chat completions response
        mock_completions.return_value = Mock(
            choices=[Mock(message=Mock(content="Mocked answer"), finish_reason="stop")],
            usage=Mock(total_tokens=100)
        )

        yield mock_embeddings, mock_completions

@pytest.fixture(autouse=True)
def mock_settings_env_vars(monkeypatch):
    """Ensure environment variables don't affect tests."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
