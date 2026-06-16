import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Globally mock OpenAI services for all tests"""
    with patch("openai.embeddings.create") as mock_embeddings, \
         patch("openai.chat.completions.create") as mock_chat:

        # Mock embeddings response
        mock_embeddings.return_value = Mock(
            data=[Mock(embedding=[0.1] * 1536) for _ in range(10)]
        )

        # Mock chat completions response
        mock_chat.return_value = Mock(
            choices=[Mock(message=Mock(content="Mocked RAG answer"), finish_reason="stop")],
            usage=Mock(total_tokens=100)
        )

        yield mock_embeddings, mock_chat
