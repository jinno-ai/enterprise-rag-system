import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_openai_embeddings():
    with patch("openai.embeddings.create") as mock_create:
        mock_response = MagicMock()
        # Mock for 3 texts as used in some tests
        mock_response.data = [
            MagicMock(embedding=[0.1] * 1536),
            MagicMock(embedding=[0.2] * 1536),
            MagicMock(embedding=[0.3] * 1536),
            MagicMock(embedding=[0.4] * 1536),
            MagicMock(embedding=[0.5] * 1536),
        ]
        mock_create.return_value = mock_response
        yield mock_create

@pytest.fixture(autouse=True)
def mock_openai_chat():
    with patch("openai.chat.completions.create") as mock_create:
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="Mocked LLM response"))
        ]
        mock_response.usage = MagicMock(total_tokens=100)
        mock_create.return_value = mock_response
        yield mock_create
