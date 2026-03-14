import pytest
import os

@pytest.fixture(autouse=True)
def setup_env():
    os.environ["OPENAI_API_KEY"] = "dummy"
