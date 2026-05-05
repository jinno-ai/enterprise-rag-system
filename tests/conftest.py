import pytest
from unittest.mock import Mock

@pytest.fixture(autouse=True)
def mock_openai_services(monkeypatch):
    """Global mock for OpenAI services"""
    mock_embeddings = Mock()
    mock_embeddings.create.return_value.data = [
        Mock(embedding=[0.1] * 1536)
    ]

    mock_chat = Mock()
    mock_chat.completions.create.return_value.choices = [
        Mock(message=Mock(content="Mocked answer"))
    ]
    mock_chat.completions.create.return_value.usage.total_tokens = 50

    # Mocking both the class and the instance methods if needed
    import openai
    monkeypatch.setattr("openai.embeddings", mock_embeddings)
    monkeypatch.setattr("openai.chat", mock_chat)

@pytest.fixture(autouse=True)
def mock_settings_env_vars(monkeypatch):
    """Mock environment variables for settings"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy")
