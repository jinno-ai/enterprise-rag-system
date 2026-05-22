import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    with patch("openai.resources.embeddings.Embeddings.create") as mock_create:
        mock_response = Mock()
        # Mocking 1536 dimension embedding (standard for ada-002)
        mock_response.data = [Mock(embedding=[0.1] * 1536)]
        mock_create.return_value = mock_response
        yield mock_create

@pytest.fixture(autouse=True)
def mock_openai_chat():
    with patch("openai.resources.chat.completions.Completions.create") as mock_create:
        mock_response = Mock()
        mock_response.choices = [Mock(message=Mock(content="Mocked answer"), finish_reason="stop")]
        mock_response.usage = Mock(total_tokens=100)
        mock_create.return_value = mock_response
        yield mock_create
