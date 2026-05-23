import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI services to avoid API calls during tests."""
    with patch("openai.resources.chat.completions.Completions.create") as mock_chat,          patch("openai.resources.embeddings.Embeddings.create") as mock_embeddings:

        # Mock Chat Completion
        mock_chat_response = MagicMock()
        mock_chat_response.choices = [
            MagicMock(message=MagicMock(content="Mocked LLM answer"), finish_reason="stop")
        ]
        mock_chat_response.usage = MagicMock(total_tokens=100)
        mock_chat.return_value = mock_chat_response

        # Mock Embeddings
        mock_embedding_response = MagicMock()
        # Assume 1536 is the dimension
        mock_embedding_response.data = [
            MagicMock(embedding=[0.1] * 1536)
        ]
        # For multiple inputs, adjust if needed
        def side_effect(input, *args, **kwargs):
            res = MagicMock()
            if isinstance(input, list):
                res.data = [MagicMock(embedding=[0.1] * 1536) for _ in input]
            else:
                res.data = [MagicMock(embedding=[0.1] * 1536)]
            return res

        mock_embeddings.side_effect = side_effect

        yield mock_chat, mock_embeddings
