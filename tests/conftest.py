import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_openai_embeddings():
    with Mock() as mock:
        yield mock

@pytest.fixture(autouse=True)
def mock_openai(monkeypatch):
    mock_client = Mock()
    # Mock for embeddings
    mock_client.embeddings.create.return_value = Mock(data=[Mock(embedding=[0.1] * 1536)])
    # Mock for chat completions
    mock_client.chat.completions.create.return_value = Mock(
        choices=[Mock(message=Mock(content="Mocked answer"), finish_reason="stop")],
        usage=Mock(total_tokens=10)
    )
    monkeypatch.setattr("openai.embeddings.create", mock_client.embeddings.create)
    monkeypatch.setattr("openai.chat.completions.create", mock_client.chat.completions.create)
    return mock_client
