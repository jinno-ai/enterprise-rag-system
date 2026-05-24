import pytest
from unittest.mock import Mock, patch

@pytest.fixture(autouse=True)
def mock_openai_services():
    """Mock OpenAI chat completions and embeddings globally for all tests"""
    with patch('openai.chat.completions.create') as mock_chat, \
         patch('openai.embeddings.create') as mock_embeddings:

        # Mock Chat Completion
        mock_chat.return_value.choices = [
            Mock(message=Mock(content="Mocked LLM answer"), finish_reason="stop")
        ]
        mock_chat.return_value.usage.total_tokens = 150

        # Mock Embeddings
        # Return a list of lists of floats for texts, or a list of floats for a query
        # Let's make it flexible
        def mock_embed_side_effect(*args, **kwargs):
            input_data = kwargs.get('input')
            if isinstance(input_data, str):
                # Single query
                mock_item = Mock()
                mock_item.embedding = [0.1] * 1536
                mock_resp = Mock()
                mock_resp.data = [mock_item]
                return mock_resp
            else:
                # List of texts
                mock_data = []
                for _ in input_data:
                    mock_item = Mock()
                    mock_item.embedding = [0.1] * 1536
                    mock_data.append(mock_item)
                mock_resp = Mock()
                mock_resp.data = mock_data
                return mock_resp

        mock_embeddings.side_effect = mock_embed_side_effect

        yield mock_chat, mock_embeddings
