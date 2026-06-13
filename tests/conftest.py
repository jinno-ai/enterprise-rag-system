import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    with patch("openai.resources.embeddings.Embeddings.create") as mock_create:
        mock_create.return_value = Mock(data=[Mock(embedding=[0.1] * 1536)])
        yield mock_create

@pytest.fixture(autouse=True)
def mock_openai_chat():
    with patch("openai.resources.chat.completions.Completions.create") as mock_create:
        mock_create.return_value = Mock(
            choices=[Mock(message=Mock(content="Mocked answer"), finish_reason="stop")],
            usage=Mock(total_tokens=100)
        )
        yield mock_create
