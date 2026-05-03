import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Global mock for OpenAI services to prevent real API calls in tests"""
    with patch("openai.embeddings.create") as mock_embed, \
         patch("openai.chat.completions.create") as mock_chat:

        # Mock embedding response
        mock_embed.return_value = Mock(data=[Mock(embedding=[0.1] * 1536)])

        # Mock chat completion response
        mock_chat.return_value = Mock(
            choices=[Mock(message=Mock(content="Mocked LLM response"), finish_reason="stop")],
            usage=Mock(total_tokens=100)
        )

        yield mock_embed, mock_chat

@pytest.fixture(autouse=True)
def mock_settings_env_vars(monkeypatch):
    """Ensure dummy API keys are used for tests"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-dummy")
    monkeypatch.setenv("COHERE_API_KEY", "sk-dummy")
