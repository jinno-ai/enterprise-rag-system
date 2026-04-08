import pytest
from unittest.mock import MagicMock
import openai

def test_mock_openai(mocker):
    mock_create = mocker.patch("openai.resources.embeddings.Embeddings.create")
    mock_create.return_value = MagicMock(data=[MagicMock(embedding=[0.1]*1536)])

    # This should use the mock
    response = openai.embeddings.create(model="text-embedding-ada-002", input="test")
    print(f"\nResponse: {response}")
    assert mock_create.called

if __name__ == "__main__":
    pytest.main([__file__, "-s"])
