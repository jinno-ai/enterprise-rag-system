import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI chat completions and embeddings globally for tests"""
    with patch("openai.chat.completions.create") as mock_chat,          patch("app.core.embeddings.OpenAIEmbeddings.embed_query") as mock_embed_query,          patch("app.core.embeddings.OpenAIEmbeddings.embed_texts") as mock_embed_texts:

        # Mock Chat Completion
        mock_chat_response = Mock()
        mock_chat_response.choices = [
            Mock(message=Mock(content="Mocked answer from LLM"), finish_reason="stop")
        ]
        mock_chat_response.usage.total_tokens = 50
        mock_chat.return_value = mock_chat_response

        # Mock Embeddings
        mock_embed_query.return_value = [0.1] * 1536
        mock_embed_texts.return_value = [[0.1] * 1536] * 3

        yield mock_chat, mock_embed_query, mock_embed_texts
