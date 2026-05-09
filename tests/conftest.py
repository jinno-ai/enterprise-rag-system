import pytest
import numpy as np
from unittest.mock import Mock

@pytest.fixture(autouse=True)
def mock_openai_api(monkeypatch):
    """Mock OpenAI API calls globally for tests"""

    # Mock for openai.chat.completions.create
    mock_chat = Mock()
    mock_chat.choices = [
        Mock(
            message=Mock(content="This is a mocked response from OpenAI."),
            finish_reason="stop"
        )
    ]
    mock_chat.usage = Mock(total_tokens=150)

    monkeypatch.setattr("openai.chat.completions.create", Mock(return_value=mock_chat))

    # Mock for openai.embeddings.create
    def mock_embeddings_create(model, input, **kwargs):
        mock_resp = Mock()
        if isinstance(input, str):
            mock_resp.data = [Mock(embedding=list(np.random.rand(1536).astype(np.float32)))]
        else:
            mock_resp.data = [Mock(embedding=list(np.random.rand(1536).astype(np.float32))) for _ in input]
        return mock_resp

    monkeypatch.setattr("openai.embeddings.create", mock_embeddings_create)
